"""Prints the validation report from data/results/predictions.csv.   Run: python -m ml.report"""
from __future__ import annotations

import json

import pandas as pd

from .pipeline import RESULTS_DIR

COLS = ["installation", "ts_dt", "powerW", "volumeFlow", "anomaly_score", "risk_level", "risk_index", "problem_type"]


def show(rows: pd.DataFrame) -> None:
    for _, r in rows.iterrows():
        print(f"- {r.installation} {r.ts_dt}  powerW={r.powerW:.0f}  volumeFlow={r.volumeFlow:.3f}  score={r.anomaly_score:.3f}  "
              f"{r.risk_level} ({r.risk_index})  {r.problem_type}")
        for b in json.loads(r.explanation):
            print(f"    * {b}")


def main() -> None:
    rep = json.loads((RESULTS_DIR / "model_report.json").read_text())
    df = pd.read_csv(RESULTS_DIR / "predictions.csv", parse_dates=["ts_dt"])
    print(f"Dataset: {rep['dataset']}\n")
    print(f"1. Total rows: {rep['rows']}\n2. Households: {rep['households']}")
    print(f"3. Statistical anomalies: {rep['statistical_anomalies']}   Actionable warnings: {rep['warnings']}")
    print(f"4. Statistical anomaly %: {rep['statistical_anomaly_rate_pct']}   Warning %: {rep['warning_rate_pct']}")
    print("5. Per household")
    print(pd.DataFrame(rep["by_household"]).T.to_string())
    print("\n6. Risk distribution (all rows):", {k: rep["by_risk_level"].get(k, 0) for k in ("NORMAL", "LOW", "MEDIUM", "HIGH")})
    print("7. Problem types among statistical anomalies:", rep["by_problem_type_among_statistical_anomalies"])
    w = df[df.is_warning]
    print("\n8. Representative warnings (one strongest per level, then per type)")
    picks = [w[w.risk_level == lvl].sort_values("risk_index", ascending=False).head(2) for lvl in ("HIGH", "MEDIUM", "LOW")]
    picks += [w[w.problem_type == t].sort_values("risk_index", ascending=False).head(1) for t in ("electricity", "water", "combined")]
    show(pd.concat(picks).drop_duplicates("anomaly_id"))
    info = df[df.is_anomaly & ~df.is_warning]
    print(f"\n9. Statistically unusual but NOT actionable: {len(info)} rows")
    print(info.problem_type.value_counts().to_dict())
    show(pd.concat([info[info.problem_type == t].head(2) for t in info.problem_type.unique()]))
    print("\nSanity checks")
    print("  warnings with powerW<=100 and volumeFlow==0:", int(((w.powerW <= 100) & (w.volumeFlow == 0)).sum()))
    print("  warnings where neither resource is above its typical level:", int(((w.power_ev < 1.5) & (w.flow_ev < 1.5)).sum()))


if __name__ == "__main__":
    main()
