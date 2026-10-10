"""HouseholdAI ML pipeline (v2).

household_final_10000.csv -> preprocessing -> zero-aware, household-normalised features
-> one Isolation Forest PER HOUSEHOLD -> per-household score fence (statistical anomaly)
-> evidence layer (is it excess consumption?) -> risk engine -> explanations -> predictions.csv

Two separate concepts:
  statistical anomaly  the observation is unusual for this household      (column is_anomaly)
  actionable warning   unusual AND there is evidence of excess usage      (column is_warning)
Only warnings receive LOW / MEDIUM / HIGH. Unusual-but-not-actionable rows (for example no activity
at all) stay NORMAL and are explained as informational.

Run from the project root:  python -m ml.pipeline
Env:  HOUSEHOLDAI_DATA (input CSV), HOUSEHOLDAI_RESULTS (output dir)
"""
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
Z_CAP = 10.0
SPREAD_FLOOR = 0.15     # minimum spread in log units, so near-constant signals cannot blow z-scores up
MIN_POSITIVE = 20       # positive readings needed to learn a household's "when active" level
MIN_HOUR_POS = 5        # positive readings needed to learn a level for one specific hour
ROLL = 6
PERSIST_WINDOW = 4
RARE_HOUR_RATE = 0.05   # activity at an hour where the household is on <5% of the time counts as unusual timing
TIMING_BONUS = 1.5
RUN_CONTINUOUS = 3      # consecutive meaningful-flow samples before "possible continuous water usage" is mentioned
# Warning interpretation only: the raw volumeFlow values are never modified, and the model features are unchanged.
# Readings below this (e.g. 0.001, 0.005) are treated as sensor residue and cannot create or sustain a water warning.
MIN_MEANINGFUL_FLOW = 0.05
RUN_GAP_FACTOR = 3.0    # a flow run breaks when the time gap exceeds 3x the household's median sampling gap
SEED = 42
FENCE_K = 1.5           # Tukey fence on each household's own score distribution
FAR_K = 3.0             # "far-out" fence, used to measure how far beyond the fence a score is

# Evidence of excess, in robust sigmas above this household's typical level for the hour.
EV_LOW, EV_MED, EV_HIGH = 1.5, 3.0, 4.5
LOW_MAX, MEDIUM_MAX = 50, 65     # risk index cut-offs for warnings (index range 40..100)

# Water is judged more conservatively than electricity, because flow is zero-inflated and a long run of
# ordinary flow is not a problem by itself. Water counts toward a warning only if, with meaningful flow:
#   (a) its excess evidence is strong (EV_WATER_MIN), OR
#   (b) it is substantially above this household's baseline for the hour AND has been sustained, AND it already
#       carries the minimum evidence (flow_ev >= EV_LOW), so this rule can only narrow, never widen, water warnings.
# Persistence alone is never enough, and neither is the rare-hour timing bonus alone (it is worth 1.5 < 2.0).
EV_WATER_MIN = 2.0
WATER_BASELINE_RATIO = 1.5


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


# --------------------------------------------------------------------------- features
def _spread(x: pd.Series) -> float:
    mad = 1.4826 * float(np.median(np.abs(x - np.median(x))))
    std = float(x.std(ddof=0)) if len(x) > 1 else 0.0
    return max(mad if mad >= 0.1 * std else std, SPREAD_FLOOR)


def _resource(g: pd.DataFrame, raw: str, name: str, scale: float) -> None:
    """Zero-aware features for one signal of one household (modifies g in place).

    Both signals are zero-inflated. Centring on all readings would make every zero (or every
    flow event) look extreme, so the level is learned from the *active* readings only and the
    on/off state is a separate feature."""
    value = g[raw].clip(lower=0)
    on = value > 0
    x = np.log1p(value * scale)
    pos = x[on]
    centre, spread = (float(pos.median()), _spread(pos)) if len(pos) >= MIN_POSITIVE else (float(x.median()), _spread(x))

    stats = pos.groupby(g.loc[on, "hour"]).agg(["median", "count"])
    hour_level = {h: (r["median"] if r["count"] >= MIN_HOUR_POS else centre) for h, r in stats.iterrows()}
    hour_med = g["hour"].map(hour_level).fillna(centre)

    z = ((x - centre) / spread).where(on, 0.0).clip(-Z_CAP, Z_CAP)
    g[f"{name}_on"] = on.astype(int)
    g[f"{name}_z"] = z
    g[f"{name}_hour_dev"] = ((x - hour_med) / spread).where(on, 0.0).clip(-Z_CAP, Z_CAP)
    g[f"{name}_hour_on_rate"] = on.astype(float).groupby(g["hour"]).transform("mean")
    run = on.astype(int).groupby((~on).cumsum()).cumsum()           # consecutive active observations
    g[f"{name}_run"] = run
    g[f"{name}_run_log"] = np.log1p(run)
    g[f"{name}_delta"] = z.diff().fillna(0.0).clip(-Z_CAP, Z_CAP)
    g[f"{name}_roll_mean"] = z.rolling(ROLL, min_periods=1).mean()
    g[f"{name}_roll_on"] = on.astype(float).rolling(ROLL, min_periods=1).mean()
    g[f"{raw}_hour_baseline"] = np.expm1(hour_med) / scale          # typical level WHEN ACTIVE at this hour


def _flow_persistence(g: pd.DataFrame) -> None:
    """Elapsed-time persistence of meaningful water flow, from real timestamps (modifies g in place).

    A run is consecutive observations whose volumeFlow >= MIN_MEANINGFUL_FLOW. It breaks when flow becomes
    non-meaningful OR when the gap to the previous observation exceeds RUN_GAP_FACTOR x this household's
    median sampling gap (derived from its own data, so hourly sampling is not assumed).
    flow_persistence_hours = time from the first observation of the run to the current one.
    flow_meaningful_samples counts observations in the run; it is a sample count, not a duration.
    (flow_run, used as a model feature, is a plain observation count of any positive flow and is not a duration either.)"""
    meaningful = g["volumeFlow"] >= MIN_MEANINGFUL_FLOW
    gap_h = g["ts_dt"].diff().dt.total_seconds().div(3600)
    max_gap = RUN_GAP_FACTOR * float(gap_h.median()) if gap_h.notna().any() else np.inf
    start = meaningful & (~meaningful.shift(1, fill_value=False) | (gap_h > max_gap))
    run_id = start.cumsum().where(meaningful)
    first_ts = g["ts_dt"].groupby(run_id).transform("min")
    g["flow_meaningful"] = meaningful
    g["flow_meaningful_samples"] = meaningful.astype(int).groupby(run_id).cumsum().where(meaningful, 0).astype(int)
    g["flow_persistence_hours"] = ((g["ts_dt"] - first_ts).dt.total_seconds() / 3600).where(meaningful, 0.0).fillna(0.0).round(2)


def engineer(df: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, g in df.groupby("installation", sort=False):
        g = g.copy()
        _resource(g, "powerW", "power", 1.0)
        _resource(g, "volumeFlow", "flow", 100.0)
        _flow_persistence(g)
        parts.append(g)
    df = pd.concat(parts).sort_values(["installation", "ts_dt"]).reset_index(drop=True)
    for col, key, period in (("hour", "hour", 24), ("day_of_week", "day", 7)):
        angle = 2 * np.pi * df[col] / period
        df[f"{key}_sin"], df[f"{key}_cos"] = np.sin(angle), np.cos(angle)
    return df


# month and sampling-gap features are intentionally NOT used: they describe when/how often a household
# was sampled, not how it behaves, and make households separable from one another (see ml/diagnose.py).
FEATURES = [f"{k}_{s}" for k in ("power", "flow")
            for s in ("on", "z", "hour_dev", "hour_on_rate", "run_log", "delta", "roll_mean", "roll_on")] + [
    "hour_sin", "hour_cos", "day_sin", "day_cos", "is_weekend"]


# --------------------------------------------------------------------------- models + calibration
def score_households(df: pd.DataFrame, features: list[str]):
    """One Isolation Forest per household, one score fence per household.

    Why per household: behaviour, sparsity and scale differ a lot between homes, and a pooled model
    judges a household against the others, which is exactly what we want to avoid. A pooled fence on
    pooled scores lets one unusual household consume the whole anomaly budget.

    Calibration: for household h, s = -score_samples. Statistical anomaly if s > Q3_h + 1.5*IQR_h
    (Tukey's fence on that household's own scores). No contamination value and no target share is
    used: a household without a heavy score tail is not forced to have anomalies. Tukey fences on
    right-skewed score distributions still flag a small tail, which is why a statistical anomaly is
    only a *candidate* and the evidence layer decides whether it is a warning."""
    df = df.copy()
    models = {}
    for col in ("anomaly_score", "fence", "far_fence", "iqr"):
        df[col] = np.nan
    for hid, g in df.groupby("installation"):
        m = IsolationForest(n_estimators=300, contamination="auto", random_state=SEED, n_jobs=-1).fit(g[features])
        s = pd.Series(-m.score_samples(g[features]), index=g.index)
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = max(float(q3 - q1), 1e-9)
        df.loc[g.index, "anomaly_score"] = s
        df.loc[g.index, "fence"] = q3 + FENCE_K * iqr
        df.loc[g.index, "far_fence"] = q3 + FAR_K * iqr
        df.loc[g.index, "iqr"] = iqr
        models[hid] = m
    df["is_anomaly"] = df["anomaly_score"] > df["fence"]
    return df, models


# --------------------------------------------------------------------------- evidence + risk
def _evidence(df: pd.DataFrame, k: str) -> pd.Series:
    """Excess above this household's typical ACTIVE level for the hour. Only upward deviation counts:
    zero or low use is unusual but is not excess consumption."""
    ev = np.maximum(0.0, np.minimum(df[f"{k}_z"], df[f"{k}_hour_dev"]))
    rare = (df[f"{k}_on"] == 1) & (df[f"{k}_hour_on_rate"] < RARE_HOUR_RATE)
    return ev + np.where(rare, TIMING_BONUS, 0.0)


def _prior_count(flag: pd.Series, installation: pd.Series) -> pd.Series:
    return (flag.astype(float).groupby(installation)
            .transform(lambda x: x.shift(1).rolling(PERSIST_WINDOW, min_periods=1).sum()).fillna(0))


def risk_engine(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["power_ev"] = _evidence(df, "power")
    df["flow_ev"] = _evidence(df, "flow").where(df["flow_meaningful"], 0.0)   # tiny flow is never evidence
    act_p = df["power_ev"] >= EV_LOW                      # electricity logic unchanged
    water_strong = df["flow_ev"] >= EV_WATER_MIN
    water_sustained = ((df["volumeFlow"] >= WATER_BASELINE_RATIO * df["volumeFlow_hour_baseline"])
                       & (df["flow_meaningful_samples"] >= RUN_CONTINUOUS))
    act_f = df["flow_meaningful"] & (water_strong | (water_sustained & (df["flow_ev"] >= EV_LOW)))
    df["flow_abnormal"] = act_f
    df["is_warning"] = df["is_anomaly"] & (act_p | act_f)

    inst = df["installation"]
    prior_p = _prior_count(act_p, inst)
    prior_f = np.maximum(_prior_count(act_f, inst), (df["flow_meaningful_samples"] - 1).clip(0, PERSIST_WINDOW))
    df["persist_count"] = np.select([act_p & ~act_f, act_f & ~act_p], [prior_p, prior_f],
                                    default=np.maximum(prior_p, prior_f)).clip(0, PERSIST_WINDOW).astype(int)

    # "combined" needs real excess in BOTH resources. Electricity evidence that comes only from the rare-hour
    # timing bonus (e.g. low power at an unusual hour) does not count as electricity abnormality here.
    power_excess = np.maximum(0.0, np.minimum(df["power_z"], df["power_hour_dev"]))
    both = act_p & act_f & (power_excess >= EV_LOW)
    ev = np.maximum(np.where(act_p, df["power_ev"], 0), np.where(act_f, df["flow_ev"], 0))
    up = np.maximum(np.where(act_p, df["power_delta"].clip(lower=0), 0), np.where(act_f, df["flow_delta"].clip(lower=0), 0))

    s_part = ((df["anomaly_score"] - df["fence"]) / (df["far_fence"] - df["fence"]).clip(lower=1e-9)).clip(0, 1)
    m_part = ((ev - EV_LOW) / (6.0 - EV_LOW)).clip(0, 1)
    c_part = (up / 6).clip(0, 1)
    p_part = df["persist_count"] / PERSIST_WINDOW
    raw = 0.30 * s_part + 0.35 * m_part + 0.10 * c_part + 0.15 * p_part + 0.10 * both.astype(float)
    idx = 40 + 60 * raw
    # Evidence gates: a level needs the evidence that level stands for, whatever the other terms say.
    idx = np.where(ev < EV_MED, np.minimum(idx, LOW_MAX - 0.1), idx)
    idx = np.where((ev < EV_HIGH) | ((df["persist_count"] < 1) & ~both), np.minimum(idx, MEDIUM_MAX - 0.1), idx)

    calm = 39 * (df["anomaly_score"] / df["fence"]).clip(0, 1) ** 2
    df["risk_index"] = np.where(df["is_warning"], idx, calm).round(1)
    df["risk_level"] = np.select([~df["is_warning"], df["risk_index"] < LOW_MAX, df["risk_index"] < MEDIUM_MAX],
                                 ["NORMAL", "LOW", "MEDIUM"], default="HIGH")

    quiet = (df["power_on"] == 0) & (df["power_hour_on_rate"] >= 0.8)
    low = (df["power_z"] <= -2) | (df["flow_z"] <= -2)
    df["problem_type"] = np.select(
        [~df["is_anomaly"], df["is_warning"] & both, df["is_warning"] & act_p & ~act_f, df["is_warning"] & act_f, quiet, low],
        ["none", "combined", "electricity", "water", "inactivity", "low_activity"], default="contextual")
    return df


# --------------------------------------------------------------------------- explanations
HEADLINE = {
    "electricity": "Possible abnormal electricity usage",
    "water": "Possible abnormal water flow",
    "combined": "Unusual electricity and water behaviour",
    "inactivity": "Unusually quiet period (informational)",
    "low_activity": "Unusually low activity (informational)",
    "contextual": "Unusual pattern, no excess usage (informational)",
    "none": "Within this household's learned normal behaviour",
}
RECOMMENDATION = {
    "electricity": "Check whether a high-power appliance is operating and monitor whether the unusual consumption continues.",
    "water": "Check taps, toilets and visible water connections for unexpected continuous flow.",
    "combined": "Review recent electricity and water use together; check running appliances, taps and visible connections.",
    "none": "No action needed.",
}
INFO_RECOMMENDATION = "No action needed. Reduced or unusual-but-not-excessive activity is not treated as a warning (for example when nobody is home)."
LEVEL_PREFIX = {"LOW": "Worth monitoring. ", "MEDIUM": "Attention recommended. ", "HIGH": "Inspection recommended soon. "}


def _bullets(r: pd.Series) -> list[str]:
    if not r["is_warning"]:
        first = {"inactivity": "No electricity is being drawn although this household is normally active at this hour.",
                 "low_activity": "Usage is well below this household's usual level."}.get(
            r["problem_type"], "The combination of activity and timing is rare for this household, but nothing shows excess usage.")
        return [first, "This is unusual, but reduced activity is not treated as a warning."]
    items = []
    shown = {"electricity": ("power",), "water": ("flow",), "combined": ("power", "flow")}[r["problem_type"]]
    for k, raw, label in (("power", "powerW", "Electricity usage"), ("flow", "volumeFlow", "Water flow")):
        if k not in shown:
            continue
        fmt = (lambda v: f"{v:.0f} W") if k == "power" else (lambda v: f"{v:.3f}")
        lo = min(r[f"{k}_z"], r[f"{k}_hour_dev"])
        if lo >= 2:
            items.append(f"{label} ({fmt(r[raw])}) is well above this household's typical level for this hour (about {fmt(r[raw + '_hour_baseline'])}).")
        elif lo >= EV_LOW:
            items.append(f"{label} ({fmt(r[raw])}) is above this household's typical level for this hour (about {fmt(r[raw + '_hour_baseline'])}).")
        if r[f"{k}_on"] == 1 and r[f"{k}_hour_on_rate"] < RARE_HOUR_RATE:
            items.append(f"This household is rarely active at {int(r['hour']):02d}:00.")
        if r[f"{k}_delta"] >= 2:
            items.append(f"{label} rose sharply compared with the previous observation.")
    if "flow" in shown and r["flow_persistence_hours"] > 0:
        hours = r["flow_persistence_hours"]
        span = f"{hours:.0f}" if hours >= 10 else f"{hours:.1f}"
        note = ", which may indicate continuous water usage" if r["flow_meaningful_samples"] >= RUN_CONTINUOUS else ""
        items.append(f"Meaningful water flow has persisted for approximately {span} hours "
                     f"(present in {int(r['flow_meaningful_samples'])} consecutive samples){note}.")
    if r["persist_count"] >= 1:
        items.append(f"A similar deviation was already present in {int(r['persist_count'])} of the previous {PERSIST_WINDOW} observations.")
    return list(dict.fromkeys(items)) or ["Activity is higher than this household's learned pattern."]


def explain(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["headline"] = df["problem_type"].map(HEADLINE)
    df["recommendation"] = [
        (LEVEL_PREFIX[lvl] + RECOMMENDATION[t]) if w else (RECOMMENDATION["none"] if t == "none" else INFO_RECOMMENDATION)
        for lvl, t, w in zip(df["risk_level"], df["problem_type"], df["is_warning"])]
    normal = ["Electricity and water behaviour are within this household's learned normal range."]
    df["explanation"] = [json.dumps(_bullets(r) if r["is_anomaly"] else normal) for _, r in df.iterrows()]
    return df


# --------------------------------------------------------------------------- orchestration
def run(data_path: Path = DATA_PATH, results_dir: Path = RESULTS_DIR) -> dict:
    results_dir.mkdir(parents=True, exist_ok=True)
    print(f"Reading {Path(data_path).resolve()}")
    df = engineer(load(data_path))
    df, models = score_households(df, FEATURES)
    df = explain(risk_engine(df))

    df["anomaly_id"] = (df["installation"].str.replace("installation_", "H", regex=False) + "-"
                        + df.groupby("installation").cumcount().astype(str).str.zfill(4))
    df["temperature"] = np.nan   # not part of the processed dataset
    cols = ["anomaly_id", "installation", "ts_dt", "powerW", "volumeFlow", "temperature", "hour",
            "powerW_hour_baseline", "volumeFlow_hour_baseline", "anomaly_score", "fence", "is_anomaly", "is_warning",
            "problem_type", "risk_index", "risk_level", "persist_count", "power_ev", "flow_ev", "flow_abnormal", "flow_run",
            "flow_meaningful", "flow_meaningful_samples", "flow_persistence_hours",
            "headline", "explanation", "recommendation"]
    df[cols].to_csv(results_dir / "predictions.csv", index=False)
    joblib.dump({"models": models, "features": FEATURES}, results_dir / "isolation_forests.joblib")

    pct = lambda s: round(100 * float(s.mean()), 2)  # noqa: E731
    report = {
        "dataset": str(Path(data_path).resolve()), "rows": int(len(df)), "households": int(df["installation"].nunique()),
        "signals": {"electricity": "powerW", "water": "volumeFlow"}, "features": FEATURES,
        "model": {"type": "IsolationForest, one per household", "n_estimators": 300, "random_state": SEED},
        "calibration": {"method": f"per-household Tukey fence on anomaly score: Q3 + {FENCE_K}*IQR (no target share)"},
        "statistical_anomalies": int(df["is_anomaly"].sum()), "statistical_anomaly_rate_pct": pct(df["is_anomaly"]),
        "warnings": int(df["is_warning"].sum()), "warning_rate_pct": pct(df["is_warning"]),
        "by_household": {h: {"statistical_anomalies": int(g["is_anomaly"].sum()), "statistical_pct": pct(g["is_anomaly"]),
                             "warnings": int(g["is_warning"].sum()), "warning_pct": pct(g["is_warning"])}
                         for h, g in df.groupby("installation")},
        "min_meaningful_flow": MIN_MEANINGFUL_FLOW,
        "warnings_by_problem_type": df.loc[df["is_warning"], "problem_type"].value_counts().to_dict(),
        "by_risk_level": df["risk_level"].value_counts().to_dict(),
        "by_problem_type_among_statistical_anomalies": df.loc[df["is_anomaly"], "problem_type"].value_counts().to_dict(),
        "temperature_available": False,
    }
    (results_dir / "model_report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
