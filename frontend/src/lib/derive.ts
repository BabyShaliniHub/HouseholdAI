/** Everything computed in the browser is a plain aggregation of v1 API data. Nothing here is a model or a score. */
import type { Counts, HouseholdSummary, Series, SeriesPoint, WarningItem } from "./api";
import { dayOf, hourLabel, hourOf, homeName } from "./format";

export function percentile(values: number[], p: number): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const i = (s.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
  return s[lo] + (s[hi] - s[lo]) * (i - lo);
}

/** Raw rows only (n === 1). Rows the model did not flag are the "normal rhythm". */
export const rawRows = (s: Series): SeriesPoint[] => s.points.filter((p) => p.n === 1);
export const calmRows = (rows: SeriesPoint[]) => rows.filter((p) => p.anomalies === 0);

export function hourProfile(rows: SeriesPoint[]) {
  return Array.from({ length: 24 }, (_, h) => {
    const r = calmRows(rows).filter((p) => hourOf(p.ts_dt) === h);
    return {
      hour: h, samples: r.length,
      power: r.length ? r.reduce((a, p) => a + (p.powerW ?? 0), 0) / r.length : 0,
      waterShare: r.length ? r.filter((p) => (p.volumeFlow ?? 0) > 0).length / r.length : 0,
    };
  });
}

export function monthly(rows: SeriesPoint[]) {
  const map = new Map<string, { risk: number; n: number; warnings: number; anomalies: number }>();
  for (const p of rows) {
    const k = dayOf(p.ts_dt).slice(0, 7);
    const m = map.get(k) ?? { risk: 0, n: 0, warnings: 0, anomalies: 0 };
    m.risk += p.risk_score ?? 0; m.n += 1; m.warnings += p.warnings; m.anomalies += p.anomalies;
    map.set(k, m);
  }
  return [...map.entries()].sort().map(([month, m]) => ({ month, meanRisk: m.risk / m.n, warnings: m.warnings, anomalies: m.anomalies }));
}

export function periodStats(rows: SeriesPoint[], start: string, end: string) {
  const r = rows.filter((p) => dayOf(p.ts_dt) >= start && dayOf(p.ts_dt) <= end);
  if (!r.length) return null;
  const mean = (f: (p: SeriesPoint) => number) => r.reduce((a, p) => a + f(p), 0) / r.length;
  return {
    n: r.length, meanPower: mean((p) => p.powerW ?? 0), peakPower: Math.max(...r.map((p) => p.powerW ?? 0)),
    meanFlow: mean((p) => p.volumeFlow ?? 0), flowShare: (100 * r.filter((p) => (p.volumeFlow ?? 0) > 0).length) / r.length,
    anomalies: r.reduce((a, p) => a + p.anomalies, 0), warnings: r.reduce((a, p) => a + p.warnings, 0),
  };
}

/** Plain-language observations, each one a direct reading of API numbers. */
export function insights(home: HouseholdSummary, all: Counts | null, warnings: WarningItem[]): string[] {
  const out: string[] = [];
  const name = homeName(home.installation);
  const pct = (a: number, b: number) => (b ? ((100 * a) / b).toFixed(1) : "0.0");
  out.push(`${home.statistical_anomalies} of ${home.total_rows.toLocaleString("en-US")} observations in ${name} (${pct(home.statistical_anomalies, home.total_rows)}%) were unusual compared with its normal pattern.`);
  out.push(home.actionable_warnings === 0
    ? `None of them showed signs of excess usage, so ${name} has no warnings.`
    : `${home.actionable_warnings} of them also showed signs of excess usage and were raised as warnings.`);
  if (warnings.length >= 2) {
    const counts = new Map<number, number>();
    for (const w of warnings) counts.set(hourOf(w.ts_dt), (counts.get(hourOf(w.ts_dt)) ?? 0) + 1);
    const [h, n] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
    if (n >= 2) out.push(`${n} of ${warnings.length} warnings in ${name} happened around ${hourLabel(h)}.`);
  }
  if (all && all.actionable_warnings > 0 && all.water_warnings === 0)
    out.push("No warnings concern water flow in the available observations. Every warning so far is about electricity use.");
  return out;
}
