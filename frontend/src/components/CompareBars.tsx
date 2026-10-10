import type { HouseholdSummary } from "../lib/api";
import { homeName, num } from "../lib/format";

/** Share of observations that were unusual per house, with its warning count. Pick a row to switch. */
export default function CompareBars({ homes, current, onPick }: { homes: HouseholdSummary[]; current: string; onPick: (id: string) => void }) {
  const rate = (h: HouseholdSummary) => (h.total_rows ? (100 * h.statistical_anomalies) / h.total_rows : 0);
  const max = Math.max(1e-9, ...homes.map(rate));
  return (
    <div className="bars" role="group" aria-label="Share of unusual observations by house">
      {homes.map((h) => (
        <button key={h.installation} className="bar-row" aria-current={h.installation === current} onClick={() => onPick(h.installation)}
          aria-label={`${homeName(h.installation)}: ${num(rate(h), 1)} percent unusual, ${h.actionable_warnings} warnings`}>
          <span>{homeName(h.installation)}</span>
          <span className="bar"><i style={{ width: `${(rate(h) / max) * 100}%` }} /></span>
          <span className="v">{num(rate(h), 1, "%")} · {h.actionable_warnings} w</span>
        </button>
      ))}
    </div>
  );
}
