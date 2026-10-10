import { useEffect, useRef } from "react";
import { AnomalyItem, WarningDetail, useWarning } from "../lib/api";
import { TYPE_LABEL, fmtFull, homeName, levelColor, levelText, num } from "../lib/format";
import { Loading, Problem } from "./States";

export interface Selection { id: string; marker?: AnomalyItem }

function Evidence({ label, color, value, baseline, unit, digits }: { label: string; color: string; value: number | null; baseline: number | null; unit: string; digits: number }) {
  const top = Math.max(value ?? 0, baseline ?? 0, 1e-9) * 1.25, pct = (v: number | null) => `${Math.min(100, ((v ?? 0) / top) * 100)}%`;
  return (
    <div className="ev-row">
      <div className="top"><span style={{ color }}>{label}</span><b>{num(value, digits, unit)}</b></div>
      <div className="ev-bar"><i style={{ width: pct(value), background: color }} />{baseline !== null && <u style={{ left: pct(baseline) }} />}</div>
      <small className="muted">Normal for this hour: {num(baseline, digits, unit)}</small>
    </div>
  );
}

/** Evidence drawer. Warnings are loaded from /warnings/{id}. A marker that is only statistically unusual is not a warning,
 *  so it is described from the marker itself and says so. */
export default function WarningDrawer({ selection, onClose }: { selection: Selection; onClose: () => void }) {
  const info = selection.marker && !selection.marker.is_warning ? selection.marker : null;
  const { data, error, loading, reload } = useWarning(info ? null : selection.id);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const on = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);

  const body = (d: WarningDetail) => (
    <>
      <span className="kicker" style={{ color: levelColor(d.risk_level) }}>{levelText(d.risk_level)} · {TYPE_LABEL[d.problem_type]}</span>
      <h2>{d.headline}</h2>
      <p className="muted">{homeName(d.installation)} · {fmtFull(d.ts_dt)}</p>
      <section>
        <h3>Evidence</h3>
        <div className="evidence">
          <Evidence label="Electricity" color="var(--elec)" value={d.powerW} baseline={d.power_baseline} unit="W" digits={0} />
          <Evidence label="Water flow" color="var(--water)" value={d.volumeFlow} baseline={d.flow_baseline} unit="" digits={3} />
          {!!d.flow_persistence_hours && d.flow_persistence_hours > 0 &&
            <p className="muted">Meaningful water flow persisted for about {num(d.flow_persistence_hours, 1)} hours ({num(d.flow_meaningful_samples)} samples).</p>}
        </div>
      </section>
      <section><h3>Why it was flagged</h3><ul className="why">{d.explanation.map((x, i) => <li key={i}>{x}</li>)}</ul></section>
      <section><h3>Risk</h3><div className="risk-line"><b style={{ color: levelColor(d.risk_level) }}>{num(d.risk_score, 0)}</b><span>{levelText(d.risk_level)} on a 0 to 100 index</span></div></section>
      <section><h3>What to check</h3><p>{d.recommendation}</p></section>
      <p className="disclaimer">HouseholdAI points out unusual patterns early. It cannot confirm a leak, a fault or an appliance failure.</p>
      <details>
        <summary>Technical details</summary>
        <dl>
          <dt>Observation ID (internal)</dt><dd>{d.id}</dd>
          <dt>Anomaly score</dt><dd>{num(d.anomaly_score, 3)}</dd>
          <dt>Electricity evidence</dt><dd>{num(d.power_ev, 2)}</dd>
          <dt>Water evidence</dt><dd>{num(d.flow_ev, 2)}</dd>
          <dt>Similar earlier observations</dt><dd>{num(d.persist_count)} of the previous 4</dd>
        </dl>
      </details>
    </>
  );

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Observation details">
        <button ref={closeRef} className="btn small close" onClick={onClose}>Close</button>
        {info && (
          <>
            <span className="kicker">Statistically unusual · not a warning</span>
            <h2>{info.headline}</h2>
            <p className="muted">{homeName(info.installation)} · {fmtFull(info.ts_dt)}</p>
            <section><h3>What was measured</h3>
              <div className="evidence"><p>Electricity {num(info.powerW, 0, "W")}, water flow {num(info.volumeFlow, 3)}.</p></div></section>
            <section><h3>Why this is not a warning</h3>
              <p>This reading differs from the house's usual pattern, but it showed no sign of excess usage, so it was not raised as a warning. Being quieter than usual, or an unusual mix of timing, is not treated as a household problem.</p></section>
            <p className="disclaimer">Unusual does not mean urgent.</p>
          </>
        )}
        {!info && loading && <Loading height={320} label="Loading warning" />}
        {!info && error && <Problem error={error} onRetry={reload} />}
        {!info && data && body(data)}
      </aside>
    </>
  );
}
