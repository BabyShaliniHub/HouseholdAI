"""LEGACY v1 pipeline, kept only so ml/diagnose.py can reproduce and dissect the original
(406 anomalies / 35% in installation_3) results. Not used by the application."""
from __future__ import annotations

import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = Path(os.getenv("HOUSEHOLDAI_DATA", ROOT / "data/processed/household_final_10000.csv"))
RESULTS_DIR = Path(os.getenv("HOUSEHOLDAI_RESULTS", ROOT / "data/results"))

REQUIRED = ["installation", "ts_dt", "powerW", "volumeFlow", "hour", "day_of_week", "month", "is_weekend"]
Z_CAP = 10.0          # robust z-scores are capped so one extreme value cannot dominate
ROLL = 6              # rolling window, in observations (sampling is not necessarily regular)
PERSIST_WINDOW = 4    # preceding observations inspected for persistence
EVIDENCE_MIN = 2.0    # |robust z| from which a resource counts as visibly deviating
SEED = 42
FENCE_K = 1.5        # Tukey fence multiplier for the anomaly-score boundary

# Risk index: anomalous rows live in 40..100, normal rows in 0..39.
LOW_MAX, MEDIUM_MAX = 55, 70


# --------------------------------------------------------------------------- preprocessing
def load(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    df = pd.read_csv(path, parse_dates=["ts_dt"])
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing columns: {missing}")
    if df[["powerW", "volumeFlow"]].isna().any().any():
        raise ValueError("powerW / volumeFlow contain missing values")
    df = df.sort_values(["installation", "ts_dt"]).reset_index(drop=True)
    df["is_weekend"] = df["is_weekend"].astype(int)
    return df


# --------------------------------------------------------------------------- feature engineering
def _robust_spread(x: pd.Series) -> float:
    """Spread of a household's signal. Water flow is zero-inflated, so the MAD is often 0;
    in that case fall back to the standard deviation."""
    mad = 1.4826 * float(np.median(np.abs(x - np.median(x))))
    std = float(x.std(ddof=0))
    spread = mad if mad >= 0.1 * std else std
    return max(spread, 1e-6)


def engineer(df: pd.DataFrame) -> pd.DataFrame:
    """Every statistic is computed per household, so a household that simply uses more
    electricity than another is not treated as anomalous."""
    parts = []
    for _, g in df.groupby("installation", sort=False):
        g = g.copy()
        for raw, name, scale in (("powerW", "power", 1.0), ("volumeFlow", "flow", 100.0)):
            x = np.log1p(g[raw].clip(lower=0) * scale)          # tame heavy right tails
            centre, spread = float(x.median()), _robust_spread(x)
            g[f"{name}_z"] = ((x - centre) / spread).clip(-Z_CAP, Z_CAP)      # vs this household
            hour_med = x.groupby(g["hour"]).transform("median")                # typical for this hour
            g[f"{name}_hour_dev"] = ((x - hour_med) / spread).clip(-Z_CAP, Z_CAP)
            g[f"{raw}_hour_baseline"] = np.expm1(hour_med) / scale
            g[f"{name}_delta"] = ((x - x.shift(1)) / spread).fillna(0).clip(-Z_CAP, Z_CAP)
            g[f"{name}_roll_mean"] = g[f"{name}_z"].rolling(ROLL, min_periods=1).mean()
            g[f"{name}_roll_std"] = g[f"{name}_z"].rolling(ROLL, min_periods=2).std().fillna(0)
        gap_h = g["ts_dt"].diff().dt.total_seconds().div(3600).fillna(0).clip(lower=0)
        g["gap_log"] = np.log1p(gap_h)
        parts.append(g)
    df = pd.concat(parts).sort_values(["installation", "ts_dt"]).reset_index(drop=True)

    for col, key, period in (("hour", "hour", 24), ("day_of_week", "day", 7), ("month", "month", 12)):
        angle = 2 * np.pi * df[col] / period
        df[f"{key}_sin"], df[f"{key}_cos"] = np.sin(angle), np.cos(angle)
    return df


FEATURES = [
    "power_z", "flow_z", "power_hour_dev", "flow_hour_dev",
    "power_delta", "flow_delta", "power_roll_mean", "flow_roll_mean",
    "power_roll_std", "flow_roll_std", "gap_log",
    "hour_sin", "hour_cos", "day_sin", "day_cos", "month_sin", "month_cos", "is_weekend",
]


# --------------------------------------------------------------------------- model + calibration
def score_and_calibrate(df: pd.DataFrame, features: list[str]):
    """Fit Isolation Forest and decide where 'unusual' starts.

    The forest's `contamination` argument is NOT used to decide labels: a fixed value just
    forces that percentage of anomalies ("auto" gave 28% in an earlier experiment, 0.05 gave
    exactly 5% by construction). Instead we take the anomaly score s = -score_samples
    (higher = more easily isolated) and flag observations beyond Tukey's upper fence of
    the score distribution:

        threshold = Q3(s) + FENCE_K * IQR(s)        (FENCE_K = 1.5)

    The fence adapts to the data: calm data yields few anomalies, noisy data more. The
    share of anomalies is therefore a result of the data, not an input.
    """
    model = IsolationForest(n_estimators=400, max_samples="auto", contamination="auto",
                            random_state=SEED, n_jobs=-1)
    model.fit(df[features])
    s = pd.Series(-model.score_samples(df[features]), index=df.index, name="anomaly_score")
    q1, q3 = s.quantile([0.25, 0.75])
    return model, s, float(q3 + FENCE_K * (q3 - q1))


# --------------------------------------------------------------------------- risk engine
def _prior_count(flag: pd.Series, installation: pd.Series) -> pd.Series:
    """How many of the previous PERSIST_WINDOW observations of the same household had `flag`."""
    return (flag.astype(float).groupby(installation)
            .transform(lambda x: x.shift(1).rolling(PERSIST_WINDOW, min_periods=1).sum())
            .fillna(0))


def risk_engine(df: pd.DataFrame, score: pd.Series, thr: float) -> pd.DataFrame:
    """Risk is built from several signals, not from the raw anomaly score alone:
    score margin (40%), magnitude of deviation (30%), recent change (15%), persistence (15%)."""
    df = df.copy()
    df["anomaly_score"] = score
    df["is_anomaly"] = score > thr

    p = df[["power_z", "power_hour_dev"]].abs().max(axis=1)
    f = df[["flow_z", "flow_hour_dev"]].abs().max(axis=1)
    df["problem_type"] = np.select(
        [~df["is_anomaly"], (p >= EVIDENCE_MIN) & (f >= EVIDENCE_MIN),
         (p < EVIDENCE_MIN) & (f < EVIDENCE_MIN), p >= f],
        ["none", "combined", "contextual", "electricity"], default="water")

    inst = df["installation"]
    cnt_p = _prior_count(p >= EVIDENCE_MIN, inst)
    cnt_f = _prior_count(f >= EVIDENCE_MIN, inst)
    cnt_a = _prior_count(df["is_anomaly"], inst)
    df["persist_count"] = np.select(
        [df["problem_type"] == "electricity", df["problem_type"] == "water"],
        [cnt_p, cnt_f], default=np.maximum(cnt_a, np.maximum(cnt_p, cnt_f))).clip(0, PERSIST_WINDOW).astype(int)

    s_part = ((score - thr) / max(score.max() - thr, 1e-9)).clip(0, 1)
    m_part = (np.maximum(p, f) / 8).clip(0, 1)
    c_part = (df[["power_delta", "flow_delta"]].abs().max(axis=1) / 6).clip(0, 1)
    raw = 0.40 * s_part + 0.30 * m_part + 0.15 * c_part + 0.15 * (df["persist_count"] / PERSIST_WINDOW)
    df["risk_index"] = np.where(df["is_anomaly"], 40 + 60 * raw, 39 * (score / thr).clip(0, 1) ** 2).round(1)
    df["risk_level"] = np.select(
        [~df["is_anomaly"], df["risk_index"] < LOW_MAX, df["risk_index"] < MEDIUM_MAX],
        ["NORMAL", "LOW", "MEDIUM"], default="HIGH")
    return df


# --------------------------------------------------------------------------- explanation engine
HEADLINE = {
    "electricity": "Possible abnormal electricity usage",
    "water": "Possible abnormal water flow",
    "combined": "Unusual electricity and water behaviour",
    "contextual": "Unusual combination of activity and timing",
    "none": "Within this household's learned normal behaviour",
}

RECOMMENDATION = {
    "electricity": "Check whether a high-power appliance is operating and monitor whether the unusual consumption continues.",
    "water": "Check taps, toilets and visible water connections for unexpected continuous flow.",
    "combined": "Review recent electricity and water use together; check running appliances, taps and visible connections.",
    "contextual": "No single resource stands out. Keep monitoring and see whether the pattern repeats.",
    "none": "No action needed.",
}

LEVEL_PREFIX = {"LOW": "Minor deviation. ", "MEDIUM": "Monitoring recommended. ", "HIGH": "Inspection recommended soon. "}


def _bullets(r: pd.Series) -> list[str]:
    items: list[str] = []
    kinds = ["power"] if r["problem_type"] == "electricity" else ["flow"] if r["problem_type"] == "water" else ["power", "flow"]
    for k in kinds:
        raw = "powerW" if k == "power" else "volumeFlow"
        label = "Electricity usage" if k == "power" else "Water flow"
        fmt = (lambda v: f"{v:.0f} W") if k == "power" else (lambda v: f"{v:.3f}")
        if r[f"{k}_z"] >= EVIDENCE_MIN:
            items.append(f"{label} ({fmt(r[raw])}) is well above this household's learned pattern.")
        elif r[f"{k}_z"] <= -EVIDENCE_MIN:
            items.append(f"{label} ({fmt(r[raw])}) is well below this household's learned pattern.")
        if abs(r[f"{k}_hour_dev"]) >= EVIDENCE_MIN:
            items.append(f"{label} is unusual for this time of day; this household typically shows about "
                         f"{fmt(r[raw + '_hour_baseline'])} around {int(r['hour']):02d}:00.")
        if abs(r[f"{k}_delta"]) >= EVIDENCE_MIN:
            items.append(f"{label} changed sharply compared with the previous observation.")
    if r["persist_count"] >= 1 and r["problem_type"] != "contextual":
        items.append(f"A similar deviation was already present in {int(r['persist_count'])} of the previous {PERSIST_WINDOW} observations.")
    return items or ["The combination of usage and timing is statistically rare for this household."]


def explain(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["headline"] = df["problem_type"].map(HEADLINE)
    df["recommendation"] = [
        (LEVEL_PREFIX[lvl] + RECOMMENDATION[t]) if lvl != "NORMAL" else RECOMMENDATION["none"]
        for lvl, t in zip(df["risk_level"], df["problem_type"])]
    normal = ["Electricity and water behaviour are within this household's learned normal range."]
    df["explanation"] = [json.dumps(_bullets(r) if r["is_anomaly"] else normal) for _, r in df.iterrows()]
    return df


# --------------------------------------------------------------------------- orchestration
def run(data_path: Path = DATA_PATH, results_dir: Path = RESULTS_DIR) -> dict:
    results_dir.mkdir(parents=True, exist_ok=True)
    df = engineer(load(data_path))
    has_temp = "temperature" in df.columns and df["temperature"].notna().all()
    features = FEATURES + (["temperature"] if has_temp else [])
    model, score, thr = score_and_calibrate(df, features)
    df = explain(risk_engine(df, score, thr))

    df["anomaly_id"] = (df["installation"].str.replace("installation_", "H", regex=False) + "-"
                        + df.groupby("installation").cumcount().astype(str).str.zfill(4))
    if not has_temp:
        df["temperature"] = np.nan
    cols = ["anomaly_id", "installation", "ts_dt", "powerW", "volumeFlow", "temperature", "hour",
            "powerW_hour_baseline", "volumeFlow_hour_baseline", "anomaly_score", "is_anomaly",
            "problem_type", "risk_index", "risk_level", "persist_count", "headline",
            "explanation", "recommendation"]
    df[cols].to_csv(results_dir / "predictions.csv", index=False)
    joblib.dump({"model": model, "features": features, "threshold": thr}, results_dir / "isolation_forest.joblib")

    report = {
        "rows": int(len(df)), "households": int(df["installation"].nunique()),
        "signals": {"electricity": "powerW", "water": "volumeFlow"},
        "features": features,
        "model": {"type": "IsolationForest", "n_estimators": 400, "random_state": SEED},
        "calibration": {"method": f"Tukey upper fence on anomaly score: Q3 + {FENCE_K}*IQR", "threshold": round(thr, 5)},
        "anomalies": int(df["is_anomaly"].sum()),
        "anomaly_rate_pct": round(100 * float(df["is_anomaly"].mean()), 2),
        "by_risk_level": df["risk_level"].value_counts().to_dict(),
        "by_problem_type": df.loc[df["is_anomaly"], "problem_type"].value_counts().to_dict(),
        "anomaly_rate_by_household_pct": (100 * df.groupby("installation")["is_anomaly"].mean()).round(2).to_dict(),
        "temperature_available": has_temp,
    }
    (results_dir / "model_report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
