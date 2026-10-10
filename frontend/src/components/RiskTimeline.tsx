import { useMemo } from "react";
import type { AnomalyItem, Series } from "../lib/api";
import { fmtFull, fmtShort, levelColor, levelText, msOf, num } from "../lib/format";
import { useWidth } from "./useWidth";

const H = 170, PX = 12, PT = 12, PB = 24;

/** Risk index over time. The dashed line at 40 is where an observation starts counting as statistically unusual. */
export default function RiskTimeline({ series, selectedId, onSelect }: { series: Series; selectedId: string | null; onSelect: (m: AnomalyItem) => void }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const g = useMemo(() => {
    const pts = series.points;
    if (!pts.length) return null;
    const t0 = msOf(pts[0].ts_dt), span = Math.max(1, msOf(pts[pts.length - 1].ts_dt) - t0);
    const x = (ts: string) => PX + ((msOf(ts) - t0) / span) * (width - 2 * PX);
    const y = (v: number | null) => PT + (1 - Math.min(100, Math.max(0, v ?? 0)) / 100) * (H - PT - PB);
    const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.ts_dt).toFixed(1)} ${y(p.risk_score).toFixed(1)}`).join(" ");
    return { x, y, path, first: pts[0].ts_dt, last: pts[pts.length - 1].ts_dt, lastX: x(pts[pts.length - 1].ts_dt), firstX: x(pts[0].ts_dt) };
  }, [series.points, width]);
  if (!g) return <div ref={ref}><p className="muted" role="status">No observations in this date range.</p></div>;
  const warnings = series.markers.filter((m) => m.is_warning);
  return (
    <div ref={ref}>
      <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="group" aria-label={`Risk timeline with ${warnings.length} warnings`}>
        <defs><linearGradient id="gR" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#9a92ff" stopOpacity=".28" /><stop offset="1" stopColor="#9a92ff" stopOpacity="0" /></linearGradient></defs>
        <path d={`${g.path} L${g.lastX} ${H - PB} L${g.firstX} ${H - PB} Z`} fill="url(#gR)" />
        <line x1={PX} x2={width - PX} y1={g.y(40)} y2={g.y(40)} stroke="var(--muted)" strokeDasharray="4 5" opacity={0.6} />
        <text x={width - PX} y={g.y(40) - 5} textAnchor="end" fontSize="11" fill="var(--muted)">statistically unusual from 40</text>
        <path d={g.path} fill="none" stroke="var(--elec)" strokeWidth={1.4} strokeLinejoin="round" />
        {warnings.map((m) => (
          <g key={m.id} className="marker" tabIndex={0} role="button" onClick={() => onSelect(m)}
            onKeyDown={(k) => { if (k.key === "Enter" || k.key === " ") { k.preventDefault(); onSelect(m); } }}
            aria-label={`${levelText(m.risk_level)} warning, risk index ${num(m.risk_score)}, ${fmtFull(m.ts_dt)}`}>
            <circle className="ring" cx={g.x(m.ts_dt)} cy={g.y(m.risk_score)} r={m.id === selectedId ? 8 : 5.5} fill={levelColor(m.risk_level)} stroke="var(--bg)" strokeWidth={2} />
            <circle cx={g.x(m.ts_dt)} cy={g.y(m.risk_score)} r={12} fill="transparent" />
          </g>
        ))}
        <text x={PX} y={H - 6} fontSize="11" fill="var(--muted)">{fmtShort(g.first)}</text>
        <text x={width - PX} y={H - 6} fontSize="11" fill="var(--muted)" textAnchor="end">{fmtShort(g.last)}</text>
      </svg>
    </div>
  );
}
