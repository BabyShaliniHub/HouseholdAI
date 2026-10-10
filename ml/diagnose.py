"""Evidence-gathering for the v1 results. Reads ONLY the processed dataset and reproduces v1 in memory.

Run from the project root:   python -m ml.diagnose
Writes data/results/diagnosis.json and prints a readable report.

Hypotheses tested (nothing is assumed):
  A  data audit: sampling interval, time span, zero-inflation per household
  B  global model + global fence: per-household score distributions and exceedance of the pooled fence
  C  household identifiability: can a classifier tell households apart from the v1 features? (feature leakage)
  D  ablation: how do per-household rates change when suspect features are removed / when scores are centred per household
  E  inactive HIGH rows: which risk component drove them, and were they driven by *below*-baseline values
  F  why LOW is absent and why electricity-only is absent
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.model_selection import cross_val_score

from . import legacy_v1 as v1

OUT = v1.RESULTS_DIR / "diagnosis.json"


def rates(df: pd.DataFrame, flag: pd.Series) -> dict:
    return (100 * flag.groupby(df["installation"]).mean()).round(2).to_dict()


def fit_flag(df: pd.DataFrame, feats: list[str]) -> tuple[pd.Series, float]:
    m = IsolationForest(n_estimators=200, random_state=v1.SEED, n_jobs=-1).fit(df[feats])
    s = pd.Series(-m.score_samples(df[feats]), index=df.index)
    q1, q3 = s.quantile([0.25, 0.75])
    return s, float(q3 + v1.FENCE_K * (q3 - q1))


def main() -> dict:
    expected = (v1.ROOT / "data" / "processed" / "household_final_10000.csv").resolve()
    if v1.DATA_PATH.resolve() != expected:
        raise SystemExit(f"Refusing to run: dataset must be exactly {expected}, got {v1.DATA_PATH.resolve()}")
    print(f"Dataset: {expected}")
    raw = v1.load(v1.DATA_PATH)
    rep: dict = {"dataset": str(v1.DATA_PATH.resolve()), "rows": len(raw)}

    # ---- A. data audit
    audit = {}
    for hid, g in raw.groupby("installation"):
        gap = g["ts_dt"].diff().dt.total_seconds().div(3600).dropna()
        pos_p, pos_f = g.loc[g.powerW > 0, "powerW"], g.loc[g.volumeFlow > 0, "volumeFlow"]
        audit[hid] = {
            "first": str(g.ts_dt.iloc[0]), "last": str(g.ts_dt.iloc[-1]),
            "gap_h_median": round(float(gap.median()), 2), "gap_h_p95": round(float(gap.quantile(.95)), 2),
            "months_covered": int(g.ts_dt.dt.month.nunique()),
            "power_zero_pct": round(100 * float((g.powerW == 0).mean()), 1),
            "flow_zero_pct": round(100 * float((g.volumeFlow == 0).mean()), 1),
            "power_pos_p50_p95": [round(float(pos_p.quantile(q)), 1) for q in (.5, .95)] if len(pos_p) else None,
            "flow_pos_p50_p95": [round(float(pos_f.quantile(q)), 3) for q in (.5, .95)] if len(pos_f) else None,
        }
    rep["A_audit"] = audit
    print("\nA. Data audit (per household)")
    print(pd.DataFrame(audit).T.to_string())

    # ---- B. reproduce v1
    df = v1.engineer(raw)
    model, score, thr = v1.score_and_calibrate(df, v1.FEATURES)
    df = v1.risk_engine(df, score, thr)
    by_h = score.groupby(df["installation"])
    B = {"pooled_fence": round(thr, 4), "v1_rate_pct": rates(df, df.is_anomaly),
         "score_median": by_h.median().round(4).to_dict(), "score_p95": by_h.quantile(.95).round(4).to_dict()}
    rep["B_v1_reproduction"] = B
    print(f"\nB. v1 reproduced: {int(df.is_anomaly.sum())} anomalies ({100 * df.is_anomaly.mean():.2f}%), pooled fence {thr:.4f}")
    print(pd.DataFrame({"rate_%": B["v1_rate_pct"], "score_median": B["score_median"], "score_p95": B["score_p95"]}).to_string())
    print("   -> if a household's *median* score already sits near the fence, the pooled fence is the problem, not its anomalies.")

    # ---- C. leakage / identifiability
    sample = df.sample(min(len(df), 4000), random_state=v1.SEED)
    groups = {
        "all v1 features": v1.FEATURES,
        "time-structure only (gap_log, month_*)": ["gap_log", "month_sin", "month_cos"],
        "behaviour only (z / hour_dev / delta / rolling)": [f for f in v1.FEATURES if f not in ("gap_log", "month_sin", "month_cos", "hour_sin", "hour_cos", "day_sin", "day_cos", "is_weekend")],
    }
    C = {}
    for name, feats in groups.items():
        acc = cross_val_score(RandomForestClassifier(150, random_state=v1.SEED, n_jobs=-1), sample[feats], sample["installation"], cv=3).mean()
        C[name] = round(float(acc), 3)
    rep["C_household_identifiability_accuracy"] = C
    print("\nC. Household identifiability (chance = 0.10). High accuracy means the features are NOT household-neutral:")
    for k, v in C.items():
        print(f"   {k}: {v}")
    med = df.groupby("installation")[v1.FEATURES].median()
    spread = ((med - med.median()) / (med.std() + 1e-9)).abs().max().sort_values(ascending=False)
    rep["C_most_household_specific_features"] = spread.head(6).round(2).to_dict()
    print("   features whose per-household median differs most:", rep["C_most_household_specific_features"])

    # ---- D. ablation
    D = {"baseline (v1)": rates(df, df.is_anomaly)}
    drop_sets = {"without gap_log": ["gap_log"], "without month_*": ["month_sin", "month_cos"],
                 "without gap_log and month_*": ["gap_log", "month_sin", "month_cos"]}
    for name, drop in drop_sets.items():
        s, t = fit_flag(df, [f for f in v1.FEATURES if f not in drop])
        D[name] = rates(df, s > t)
    s_all, _ = fit_flag(df, v1.FEATURES)
    q = s_all.groupby(df["installation"])
    q1, q3 = q.transform(lambda x: x.quantile(.25)), q.transform(lambda x: x.quantile(.75))
    D["pooled model, per-household fence"] = rates(df, s_all > q3 + v1.FENCE_K * (q3 - q1))
    rep["D_ablation_rate_pct"] = D
    print("\nD. Ablation: anomaly rate % per household")
    print(pd.DataFrame(D).to_string())

    # ---- E. inactive HIGH rows
    high = df[df.risk_level == "HIGH"]
    inactive = high[(high.powerW <= 100)]
    p_ev = df[["power_z", "power_hour_dev"]].abs().max(axis=1)
    f_ev = df[["flow_z", "flow_hour_dev"]].abs().max(axis=1)
    below = ((df.power_z <= -v1.EVIDENCE_MIN) | (df.flow_z <= -v1.EVIDENCE_MIN))
    E = {
        "HIGH rows": int(len(high)), "HIGH with powerW <= 100": int(len(inactive)),
        "HIGH where power_z is strongly NEGATIVE (below baseline)": int((high.power_z <= -v1.EVIDENCE_MIN).sum()),
        "HIGH where power evidence comes only from below-baseline values":
            int(((high.power_z <= -v1.EVIDENCE_MIN) & (high.power_z.abs() >= high.power_hour_dev.abs() - 1e-9)).sum()),
        "anomalies with power_z <= -2 or flow_z <= -2": int((df.is_anomaly & below).sum()),
        "mean power_z of inactive HIGH rows": round(float(inactive.power_z.mean()), 2) if len(inactive) else None,
        "mean |power_delta| of inactive HIGH rows": round(float(inactive.power_delta.abs().mean()), 2) if len(inactive) else None,
    }
    comp = pd.DataFrame({
        "s_part": ((df.anomaly_score - thr) / max(df.anomaly_score.max() - thr, 1e-9)).clip(0, 1),
        "m_part": (np.maximum(p_ev, f_ev) / 8).clip(0, 1),
        "c_part": (df[["power_delta", "flow_delta"]].abs().max(axis=1) / 6).clip(0, 1),
        "p_part": df.persist_count / v1.PERSIST_WINDOW})
    E["mean risk components, inactive HIGH rows"] = comp.loc[inactive.index].mean().round(2).to_dict() if len(inactive) else None
    ex = inactive.head(5)[["installation", "ts_dt", "powerW", "volumeFlow", "power_z", "flow_z", "power_delta", "risk_index"]]
    rep["E_inactive_high"] = E
    print("\nE. Inactive-looking HIGH rows")
    for k, v in E.items():
        print(f"   {k}: {v}")
    if len(ex):
        print(ex.to_string(index=False, float_format=lambda v: f'{v:.2f}'))

    # ---- F. LOW absent / electricity-only absent
    an = df[df.is_anomaly]
    F = {
        "minimum risk_index among anomalies": round(float(an.risk_index.min()), 1),
        "share of anomalies whose magnitude term alone puts them >= LOW_MAX": round(100 * float(((np.maximum(p_ev, f_ev)[an.index] / 8).clip(0, 1) * 0.3 * 60 + 40 >= v1.LOW_MAX).mean()), 1),
        "share of anomalies with magnitude >= 6.7 robust z (=> cannot be LOW)": round(100 * float((np.maximum(p_ev, f_ev)[an.index] >= 6.67).mean()), 1),
        "anomalies with flow>0": int((an.volumeFlow > 0).sum()),
        "of those, flow evidence >= power evidence (=> labelled water/combined, never electricity)": int(((f_ev >= p_ev)[an.index] & (an.volumeFlow > 0)).sum()),
        "anomalies with power_z >= +2 (genuinely HIGH electricity)": int((an.power_z >= 2).sum()),
        "anomalies with power_z <= -2 (LOW electricity)": int((an.power_z <= -2).sum()),
    }
    rep["F_low_and_electricity"] = F
    print("\nF. Why no LOW and no electricity-only")
    for k, v in F.items():
        print(f"   {k}: {v}")

    # ---- G. verdicts: each rule is stated, then applied to the numbers above. SUPPORTED = measured in this dataset.
    base = D["baseline (v1)"]
    worst = max(base, key=base.get)
    def cut(name: str) -> float:   # relative drop of the worst household's rate under an ablation
        return round(100 * (1 - D[name][worst] / base[worst]), 1) if base[worst] else 0.0
    others_zero = [h for h, r in base.items() if r == 0]
    anom_n = int(df.is_anomaly.sum())
    neg = E["anomalies with power_z <= -2 or flow_z <= -2"]
    masked = int((df.is_anomaly & (df.power_z >= 2) & (df.problem_type != "electricity")).sum())
    zero_sh = {h: a["power_zero_pct"] for h, a in audit.items()}
    G = {
        "worst household under v1": f"{worst} ({base[worst]}%)",
        "households at exactly 0% under v1": others_zero,
        "pooled fence (rule: worst household's rate falls >50% with per-household fences)":
            ("SUPPORTED" if cut("pooled model, per-household fence") > 50 else "NOT SUPPORTED") + f" (drop {cut('pooled model, per-household fence')}%)",
        "gap_log (rule: worst rate falls >50% when removed)":
            ("SUPPORTED" if cut("without gap_log") > 50 else "NOT SUPPORTED") + f" (drop {cut('without gap_log')}%)",
        "month features (rule: worst rate falls >50% when removed)":
            ("SUPPORTED" if cut("without month_*") > 50 else "NOT SUPPORTED") + f" (drop {cut('without month_*')}%)",
        "household identifiability (rule: all-features accuracy > 0.5)":
            ("SUPPORTED, features are not household-neutral" if C["all v1 features"] > 0.5 else "NOT SUPPORTED") + f" ({C['all v1 features']})",
        "zero-inflation / downward deviation (rule: >50% of HIGH rows are below-baseline driven)":
            ("SUPPORTED" if E["HIGH rows"] and E["HIGH where power evidence comes only from below-baseline values"] / E["HIGH rows"] > 0.5 else "NOT SUPPORTED")
            + f" ({E['HIGH where power evidence comes only from below-baseline values']} of {E['HIGH rows']})",
        "downward deviations among all v1 anomalies": f"{neg} of {anom_n}",
        "electricity masked by water evidence (power_z>=2 but not labelled electricity)": f"{masked} rows",
        "power zero share by household (%)": zero_sh,
        "NOT testable here": "which of several overlapping causes is dominant when more than one is SUPPORTED; "
                             "the ablations show each cause alone, not their interaction",
    }
    rep["G_verdicts"] = G
    print("\nG. Verdicts (SUPPORTED = measured on this dataset by the stated rule; everything else is a hypothesis)")
    for k, v in G.items():
        print(f"   {k}: {v}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2, default=str))
    print(f"\nSaved {OUT}")
    return rep


if __name__ == "__main__":
    main()
