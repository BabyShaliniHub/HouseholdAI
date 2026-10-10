import { num } from "../lib/format";

/** A live reading against this home's normal level for the hour (the white tick). */
export default function SignalMeter({ name, color, value, baseline, unit, digits = 0 }: { name: string; color: string; value: number | null; baseline: number | null; unit: string; digits?: number }) {
  const top = Math.max(value ?? 0, baseline ?? 0, 1e-9) * 1.25;
  const pct = (v: number | null) => `${Math.min(100, ((v ?? 0) / top) * 100)}%`;
  return (
    <div className="signal">
      <div className="row"><span className="name"><i style={{ background: color }} />{name}</span><span className="val">{num(value, digits, unit)}</span></div>
      <div className="track" role="img" aria-label={`${name} ${num(value, digits, unit)}, normal for this hour ${num(baseline, digits, unit)}`}>
        <div className="fill" style={{ width: pct(value), background: color, color }} />
        {baseline !== null && <div className="tick" style={{ left: pct(baseline) }} />}
      </div>
      <small>Normal for this hour: {num(baseline, digits, unit)}</small>
    </div>
  );
}
