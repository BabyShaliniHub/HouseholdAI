import type { Counts } from "../lib/api";
import { num } from "../lib/format";

/** Observations -> statistically unusual -> actionable warnings. Makes the difference between the last two explicit. */
export default function SignalFunnel({ counts, scope }: { counts: Counts; scope: string }) {
  const total = Math.max(1, counts.total_rows);
  const rows = [
    { label: "Observations checked", n: counts.total_rows, color: "var(--faint)" },
    { label: "Unusual for the house", n: counts.statistical_anomalies, color: "var(--elec)" },
    { label: "Raised as warnings", n: counts.actionable_warnings, color: "var(--medium)" },
  ];
  return (
    <div className="funnel" role="group" aria-label={`${scope}: ${counts.total_rows} observations, ${counts.statistical_anomalies} unusual, ${counts.actionable_warnings} raised as warnings`}>
      {rows.map((r) => (
        <div className="funnel-row" key={r.label}>
          <span>{r.label}</span>
          <span className="bar"><i style={{ width: `${Math.max((r.n / total) * 100, r.n ? 0.6 : 0)}%`, background: r.color }} /></span>
          <b className="mono">{num(r.n)}</b>
        </div>
      ))}
      <p className="funnel-note">
        {counts.statistical_anomalies.toLocaleString("en-US")} observations in {scope} were unusual for their house, but only {counts.actionable_warnings.toLocaleString("en-US")} also showed
        signs of excess usage and became warnings. Being unusual, such as quieter than normal, is not a problem in itself.
      </p>
    </div>
  );
}
