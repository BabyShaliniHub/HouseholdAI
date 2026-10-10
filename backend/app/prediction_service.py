"""Read-only access to the frozen ML output (predictions.csv).

Parsing uses pandas, whose CSV reader handles quoted fields (the explanation column holds a JSON list with commas).
The file is cached in memory and re-read automatically when it changes on disk. Nothing here recomputes ML logic:
counts, filters and averages are plain aggregations of the columns the pipeline wrote.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
from pathlib import Path

import numpy as np
import pandas as pd

from .errors import ApiError

log = logging.getLogger("householdai")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = "data/results/predictions.csv"
LEVELS = ("NORMAL", "LOW", "MEDIUM", "HIGH")

REQUIRED = ["anomaly_id", "installation", "ts_dt", "powerW", "volumeFlow", "is_anomaly", "is_warning",
            "problem_type", "risk_level", "risk_index"]
NUMERIC = ["powerW", "volumeFlow", "risk_index", "power_ev", "flow_ev", "flow_persistence_hours",
           "flow_meaningful_samples", "anomaly_score", "persist_count", "flow_run",
           "powerW_hour_baseline", "volumeFlow_hour_baseline", "hour"]
OPTIONAL_TEXT = {"headline": "", "recommendation": "", "explanation": "[]"}
OPTIONAL_BOOL = ["flow_abnormal"]


def predictions_path() -> Path:
    """HOUSEHOLDAI_PREDICTIONS_PATH, or data/results/predictions.csv. Relative paths are relative to the project root."""
    p = Path(os.getenv("HOUSEHOLDAI_PREDICTIONS_PATH") or DEFAULT_PATH)
    return p if p.is_absolute() else ROOT / p


def _py(v):
    """numpy / NaN -> plain JSON-safe Python values."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)) or v is pd.NaT:
        return None
    if hasattr(v, "item"):
        v = v.item()
        return None if isinstance(v, float) and not math.isfinite(v) else v
    return v


def _bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "1.0", "yes"])


def _explanation(raw) -> list[str]:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)) or str(raw).strip() == "":
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return [str(raw)]
    return [str(x) for x in parsed] if isinstance(parsed, list) else [str(parsed)]


def _counts(g: pd.DataFrame) -> dict:
    warn = g[g["is_warning"]]
    n_total = len(g)
    return {
        "total_rows": n_total,
        "statistical_anomalies": int(g["is_anomaly"].sum()),
        "actionable_warnings": int(len(warn)),
        "normal_count": int((g["risk_level"] == "NORMAL").sum()),
        "low_count": int((g["risk_level"] == "LOW").sum()),
        "medium_count": int((g["risk_level"] == "MEDIUM").sum()),
        "high_count": int((g["risk_level"] == "HIGH").sum()),
        "electricity_warnings": int((warn["problem_type"] == "electricity").sum()),
        "water_warnings": int((warn["problem_type"] == "water").sum()),
        "combined_warnings": int((warn["problem_type"] == "combined").sum()),
    }


class PredictionService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stamp: tuple | None = None
        self._df: pd.DataFrame | None = None

    # ----------------------------------------------------------------- loading
    def frame(self) -> pd.DataFrame:
        path = predictions_path()
        try:
            st = path.stat()
        except FileNotFoundError:
            raise ApiError(503, "PREDICTIONS_FILE_NOT_FOUND", "ML predictions file was not found.") from None
        except OSError:
            raise ApiError(500, "PREDICTIONS_FILE_UNREADABLE", "ML predictions file could not be read.") from None
        stamp = (str(path), st.st_mtime_ns, st.st_size)
        with self._lock:
            if self._df is None or stamp != self._stamp:
                self._df, self._stamp = self._read(path), stamp
            return self._df

    @staticmethod
    def _read(path: Path) -> pd.DataFrame:
        try:
            df = pd.read_csv(path, on_bad_lines="skip")      # rows with the wrong field count are skipped
        except pd.errors.EmptyDataError:
            raise ApiError(503, "PREDICTIONS_FILE_EMPTY", "ML predictions file is empty.") from None
        except (OSError, UnicodeDecodeError, pd.errors.ParserError):
            raise ApiError(500, "PREDICTIONS_FILE_UNREADABLE", "ML predictions file could not be parsed.") from None
        if df.empty:
            raise ApiError(503, "PREDICTIONS_FILE_EMPTY", "ML predictions file has no data rows.")
        missing = [c for c in REQUIRED if c not in df.columns]
        if missing:
            raise ApiError(500, "PREDICTIONS_FILE_INVALID", f"ML predictions file is missing required columns: {', '.join(missing)}.")

        before = len(df)
        df["ts_dt"] = pd.to_datetime(df["ts_dt"], errors="coerce")
        for c in NUMERIC:
            df[c] = pd.to_numeric(df[c], errors="coerce") if c in df.columns else float("nan")
        for c, default in OPTIONAL_TEXT.items():
            df[c] = df[c].fillna(default).astype(str) if c in df.columns else default
        df["is_anomaly"], df["is_warning"] = _bool(df["is_anomaly"]), _bool(df["is_warning"])
        for c in OPTIONAL_BOOL:
            df[c] = _bool(df[c]) if c in df.columns else None
        df["risk_level"] = df["risk_level"].astype(str).str.strip().str.upper()
        df["installation"] = df["installation"].astype(str).str.strip()
        df["anomaly_id"] = df["anomaly_id"].astype(str).str.strip()
        df = df[df["ts_dt"].notna() & df["risk_index"].notna() & df["risk_level"].isin(LEVELS)
                & df["powerW"].notna() & df["volumeFlow"].notna() & df["anomaly_id"].ne("")
                & df["installation"].ne("") & df["anomaly_id"].ne("nan")]
        dropped = before - len(df)
        if dropped:
            log.warning("Ignored %d malformed row(s) in %s", dropped, path)
        if df.empty:
            raise ApiError(503, "PREDICTIONS_FILE_EMPTY", "ML predictions file has no valid data rows.")
        return df.sort_values(["installation", "ts_dt"]).reset_index(drop=True)

    # ----------------------------------------------------------------- shaping
    @staticmethod
    def _warning(r: pd.Series, detail: bool = False) -> dict:
        out = {
            "id": r["anomaly_id"], "installation": r["installation"], "ts_dt": r["ts_dt"].isoformat(),
            "powerW": _py(r["powerW"]), "volumeFlow": _py(r["volumeFlow"]), "problem_type": r["problem_type"],
            "risk_level": r["risk_level"], "risk_score": _py(r["risk_index"]), "headline": r["headline"],
            "explanation": _explanation(r["explanation"]), "recommendation": r["recommendation"],
            "power_ev": _py(r["power_ev"]), "flow_ev": _py(r["flow_ev"]),
            "flow_persistence_hours": _py(r["flow_persistence_hours"]),
            "flow_meaningful_samples": None if _py(r["flow_meaningful_samples"]) is None else int(r["flow_meaningful_samples"]),
            "flow_abnormal": None if r["flow_abnormal"] is None or pd.isna(r["flow_abnormal"]) else bool(r["flow_abnormal"]),
        }
        if detail:
            out.update({"is_anomaly": bool(r["is_anomaly"]), "anomaly_score": _py(r["anomaly_score"]),
                        "persist_count": None if _py(r["persist_count"]) is None else int(r["persist_count"]),
                        "flow_run": None if _py(r["flow_run"]) is None else int(r["flow_run"]),
                        "hour": None if _py(r["hour"]) is None else int(r["hour"]),
                        "power_baseline": _py(r["powerW_hour_baseline"]),
                        "flow_baseline": _py(r["volumeFlow_hour_baseline"])})
        return out

    @staticmethod
    def _anomaly(r: pd.Series) -> dict:
        return {"id": r["anomaly_id"], "installation": r["installation"], "ts_dt": r["ts_dt"].isoformat(),
                "powerW": _py(r["powerW"]), "volumeFlow": _py(r["volumeFlow"]), "problem_type": r["problem_type"],
                "risk_level": r["risk_level"], "risk_score": _py(r["risk_index"]), "headline": r["headline"],
                "is_warning": bool(r["is_warning"])}

    @staticmethod
    def _ranked(df: pd.DataFrame) -> pd.DataFrame:
        return df.sort_values(["risk_index", "ts_dt"], ascending=[False, False])

    # ----------------------------------------------------------------- queries
    def summary(self) -> dict:
        df = self.frame()
        c = _counts(df)
        total = c["total_rows"]
        return {**c, "total_households": int(df["installation"].nunique()),
                "anomaly_percentage": round(100 * c["statistical_anomalies"] / total, 2),
                "warning_percentage": round(100 * c["actionable_warnings"] / total, 2)}

    def warnings(self, installation: str | None = None, risk_level: str | None = None, limit: int | None = None) -> list[dict]:
        df = self.frame()
        w = df[df["is_warning"]]
        if installation:
            w = w[w["installation"] == installation]
        if risk_level:
            w = w[w["risk_level"] == risk_level.upper()]
        w = self._ranked(w)
        if limit:
            w = w.head(limit)
        return [self._warning(r) for _, r in w.iterrows()]

    def warning(self, anomaly_id: str) -> dict | None:
        df = self.frame()
        hit = df[df["is_warning"] & (df["anomaly_id"] == anomaly_id)]
        return None if hit.empty else self._warning(hit.iloc[0], detail=True)

    def _household(self, g: pd.DataFrame, installation: str) -> dict:
        return {"installation": installation, **_counts(g),
                "average_power": round(float(g["powerW"].mean()), 2), "average_flow": round(float(g["volumeFlow"].mean()), 4)}

    def households(self) -> list[dict]:
        df = self.frame()
        return [self._household(g, h) for h, g in df.groupby("installation", sort=True)]

    def household(self, installation: str, recent: int = 10) -> dict | None:
        df = self.frame()
        g = df[df["installation"] == installation]
        if g.empty:
            return None
        newest = lambda d: d.sort_values("ts_dt", ascending=False).head(recent)       # noqa: E731
        return {"summary": self._household(g, installation),
                "recent_warnings": [self._warning(r) for _, r in newest(g[g["is_warning"]]).iterrows()],
                "recent_anomalies": [self._anomaly(r) for _, r in newest(g[g["is_anomaly"]]).iterrows()]}

    def series(self, installation: str, start=None, end=None, max_points: int = 600) -> dict | None:
        """Observations for charting. Rows are kept as they are when they fit in max_points; otherwise consecutive
        rows are averaged into max_points buckets (peaks are kept in power_max / flow_max). Every statistical anomaly is
        returned unaggregated in `markers`, so a warning can never disappear into a bucket.

        One vectorised path serves both cases: a raw row is simply a bucket of size 1."""
        df = self.frame()
        home = df[df["installation"] == installation]
        if home.empty:
            return None
        g = home
        if start is not None:
            g = g[g["ts_dt"] >= pd.Timestamp(start)]
        if end is not None:
            g = g[g["ts_dt"] <= pd.Timestamp(end)]

        n = len(g)
        points: list[dict] = []
        if n:
            sizes = np.full(n, 1) if n <= max_points else np.array([len(c) for c in np.array_split(np.arange(n), max_points)])
            starts = np.concatenate(([0], np.cumsum(sizes)[:-1]))
            col = lambda name: g[name].to_numpy(dtype=float)                                     # noqa: E731
            mean = lambda name: np.add.reduceat(col(name), starts) / sizes                       # noqa: E731
            peak = lambda name: np.maximum.reduceat(col(name), starts)                           # noqa: E731
            risk, anomalies, warnings = col("risk_index"), g["is_anomaly"].to_numpy(int), g["is_warning"].to_numpy(int)
            top = np.array([s + int(np.argmax(risk[s:s + z])) for s, z in zip(starts, sizes)])
            level = g["risk_level"].to_numpy()[top]
            ts = g["ts_dt"].dt.strftime("%Y-%m-%dT%H:%M:%S").to_numpy()[starts + sizes // 2]
            ids = g["anomaly_id"].to_numpy()[starts]
            power, power_max, flow, flow_max = mean("powerW"), peak("powerW"), mean("volumeFlow"), peak("volumeFlow")
            p_base, f_base = mean("powerW_hour_baseline"), mean("volumeFlow_hour_baseline")
            n_an, n_warn = np.add.reduceat(anomalies, starts), np.add.reduceat(warnings, starts)
            points = [{"id": str(ids[i]) if sizes[i] == 1 else None, "ts_dt": str(ts[i]),
                       "powerW": _py(power[i]), "power_max": _py(power_max[i]), "volumeFlow": _py(flow[i]), "flow_max": _py(flow_max[i]),
                       "power_baseline": _py(p_base[i]), "flow_baseline": _py(f_base[i]),
                       "risk_score": _py(risk[top[i]]), "risk_level": str(level[i]),
                       "anomalies": int(n_an[i]), "warnings": int(n_warn[i]), "n": int(sizes[i])} for i in range(len(starts))]
        return {"installation": installation, "first_ts": home["ts_dt"].iloc[0].isoformat(), "last_ts": home["ts_dt"].iloc[-1].isoformat(),
                "total_rows": int(n), "bucketed": n > max_points, "points": points,
                "markers": [self._anomaly(r) for _, r in g[g["is_anomaly"]].iterrows()],
                "latest": self._warning(home.iloc[-1])}

service = PredictionService()
