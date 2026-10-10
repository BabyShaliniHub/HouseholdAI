"""Insights, profiles and comparisons, all computed from the ML results."""
from __future__ import annotations

import json
import math

import pandas as pd

from .schemas import ProfileOut, Warning


def _n(x) -> float | None:
    try:
        return round(float(x), 4) if math.isfinite(float(x)) else None
    except (TypeError, ValueError):
        return None


def _label(hid: str) -> str:
    return f"Household {int(hid.split('_')[1]):02d}"


def _warning(r: pd.Series) -> Warning:
    return Warning(id=r["anomaly_id"], household=r["installation"], household_label=_label(r["installation"]),
                   ts=r["ts_dt"].isoformat(), risk_level=r["risk_level"], risk_index=_n(r["risk_index"]),
                   problem_type=r["problem_type"], headline=r["headline"])


def _top_hours(rows: pd.DataFrame, col: str, n: int = 3) -> list[int]:
    if rows.empty:
        return []
    return sorted(int(h) for h in rows.groupby("hour")[col].mean().nlargest(n).index)


def profile(hid: str, rows: pd.DataFrame, label: str) -> ProfileOut:
    normal = rows[~rows["is_anomaly"]]
    flowing = normal[normal["volumeFlow"] > 0]
    monthly = rows.groupby(rows["ts_dt"].dt.to_period("M")).agg(mean_risk=("risk_index", "mean"), anomalies=("is_anomaly", "sum"))
    trend = [{"month": str(p), "mean_risk": _n(r.mean_risk), "anomalies": int(r.anomalies)} for p, r in monthly.iterrows()]
    half = len(rows) // 2
    diff = rows["risk_index"].iloc[half:].mean() - rows["risk_index"].iloc[:half].mean() if half else 0
    direction = "rising" if diff > 2 else "falling" if diff < -2 else "steady"
    flow_active = rows.assign(active=(rows["volumeFlow"] > 0).astype(float))
    return ProfileOut(
        id=hid, label=label,
        power_normal_low=_n(normal["powerW"].quantile(0.10)) if len(normal) else None,
        power_normal_high=_n(normal["powerW"].quantile(0.90)) if len(normal) else None,
        water_active_share_pct=_n(100 * (rows["volumeFlow"] > 0).mean()),
        water_typical_low=_n(flowing["volumeFlow"].quantile(0.25)) if len(flowing) else None,
        water_typical_high=_n(flowing["volumeFlow"].quantile(0.90)) if len(flowing) else None,
        power_active_hours=_top_hours(normal, "powerW"),
        water_active_hours=_top_hours(flow_active, "active"),
        anomalies=int(rows["is_anomaly"].sum()), anomaly_rate_pct=_n(100 * rows["is_anomaly"].mean()) or 0.0,
        risk_trend=trend, trend_direction=direction,
        recent_anomalies=[_warning(r) for _, r in rows[rows["is_anomaly"]].tail(5).iloc[::-1].iterrows()])


def compare(df: pd.DataFrame) -> list[dict]:
    out = []
    for hid, rows in df.groupby("installation"):
        out.append({"id": hid, "label": _label(hid), "anomaly_rate_pct": _n(100 * rows["is_anomaly"].mean()),
                    "mean_risk_index": _n(rows["risk_index"].mean()), "median_power": _n(rows["powerW"].median()),
                    "water_active_share_pct": _n(100 * (rows["volumeFlow"] > 0).mean()),
                    "anomalies": int(rows["is_anomaly"].sum())})
    return sorted(out, key=lambda d: int(d["id"].split("_")[1]))


def _hours(start: int, span: int = 3) -> str:
    return f"{start % 24:02d}:00-{(start + span) % 24:02d}:00"


def _household_insights(df: pd.DataFrame, hid: str) -> list[dict]:
    rows = df[df["installation"] == hid]
    name, out = _label(hid), []
    last = rows.iloc[-1]
    if last["risk_level"] == "NORMAL":
        out.append({"kind": "status", "household": hid, "text": f"The most recent observation for {name} is within its learned baseline."})
    else:
        out.append({"kind": "status", "household": hid, "text": f"The most recent observation for {name} shows a {last['risk_level'].lower()}-risk deviation: {last['headline'].lower()}."})

    overall_active = (rows["volumeFlow"] > 0).mean()
    evening = rows[rows["hour"].between(18, 22)]
    if len(evening) >= 30 and overall_active > 0:
        ratio = (evening["volumeFlow"] > 0).mean() / overall_active
        if ratio >= 1.3:
            out.append({"kind": "water", "household": hid, "text": f"{name} shows higher-than-usual water activity during evening periods (flow in {100 * (evening['volumeFlow'] > 0).mean():.0f}% of evening observations vs {100 * overall_active:.0f}% overall)."})

    an = rows[rows["is_anomaly"]]
    if len(an) >= 3:
        counts = an["hour"].value_counts()
        best, best_n = max(((h, sum(counts.get((h + k) % 24, 0) for k in range(3))) for h in range(24)), key=lambda t: t[1])
        if best_n / len(an) >= 0.4:
            out.append({"kind": "timing", "household": hid, "text": f"Anomalies for {name} are concentrated between {_hours(best)} ({best_n} of {len(an)})."})
        top = an["problem_type"].value_counts()
        out.append({"kind": "type", "household": hid, "text": f"The most frequent anomaly type for {name} is {top.index[0]} ({int(top.iloc[0])} of {len(an)})."})
    elif len(an) == 0:
        out.append({"kind": "type", "household": hid, "text": f"No anomalies were detected for {name} in this dataset."})

    run = best_run = 0
    for flag in rows["is_anomaly"]:
        run = run + 1 if flag else 0
        best_run = max(best_run, run)
    if best_run >= 3:
        out.append({"kind": "persistence", "household": hid, "text": f"{name} has a run of {best_run} consecutive anomalous observations, which suggests persistent rather than one-off behaviour."})
    return out


def generate(df: pd.DataFrame, household: str | None) -> list[dict]:
    if household:
        return _household_insights(df, household)
    cmp = compare(df)
    top = max(cmp, key=lambda d: d["anomaly_rate_pct"] or 0)
    overall = 100 * df["is_anomaly"].mean()
    out = [{"kind": "fleet", "household": None, "text": f"{int(df['is_anomaly'].sum())} of {len(df):,} observations ({overall:.1f}%) were flagged as anomalous across {len(cmp)} households."}]
    if top["anomaly_rate_pct"]:
        out.append({"kind": "fleet", "household": top["id"], "text": f"{top['label']} has the highest anomaly rate at {top['anomaly_rate_pct']:.1f}%."})
    types = df.loc[df["is_anomaly"], "problem_type"].value_counts()
    if len(types):
        out.append({"kind": "fleet", "household": None, "text": f"The most common anomaly type is {types.index[0]} ({int(types.iloc[0])} observations)."})
    return out


def demo_script(df: pd.DataFrame) -> dict | None:
    an = df[df["is_anomaly"]]
    if an.empty:
        return None
    top = an.sort_values("risk_index", ascending=False).iloc[0]
    hid = top["installation"]
    rows = df[df["installation"] == hid]
    before = rows[(rows["ts_dt"] < top["ts_dt"]) & (~rows["is_anomaly"])]
    calm = before.iloc[-1] if len(before) else rows[~rows["is_anomaly"]].iloc[0]
    others = an[an["installation"] != hid]["installation"].value_counts()
    other = others.index[0] if len(others) else next(h for h in df["installation"].unique() if h != hid)
    return {"household": hid, "household_label": _label(hid), "calm_ts": calm["ts_dt"].isoformat(),
            "anomaly_id": top["anomaly_id"], "anomaly_ts": top["ts_dt"].isoformat(),
            "compare_household": other, "compare_label": _label(other)}
