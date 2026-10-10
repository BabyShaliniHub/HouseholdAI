import type { SeriesPoint } from "../lib/api";
import { fmtFull, num } from "../lib/format";

/** Raw observations, collapsed by default. Shows the first 100 rows. */
export default function DataDetails({ rows }: { rows: SeriesPoint[] }) {
  return (
    <details style={{ marginTop: 44 }}>
      <summary>Data details ({rows.length} observations, first 100 shown)</summary>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Time</th><th>Electricity (W)</th><th>Water flow</th><th>Risk</th><th>Status</th></tr></thead>
          <tbody>
            {rows.slice(0, 100).map((p) => (
              <tr key={p.id ?? p.ts_dt}><td>{fmtFull(p.ts_dt)}</td><td>{num(p.powerW, 0)}</td><td>{num(p.volumeFlow, 3)}</td><td>{num(p.risk_score, 1)}</td>
                <td>{p.warnings ? "Warning" : p.anomalies ? "Unusual" : "Normal"}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
