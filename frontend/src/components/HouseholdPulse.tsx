import { useMemo, useRef, useState } from "react";
import type { AnomalyItem, Level, Series, SeriesPoint } from "../lib/api";
import { dayOf, fmtFull, fmtShort, levelColor, levelText, msOf, num } from "../lib/format";
import { ResourceLegend } from "./ui";
import { useWidth } from "./useWidth";

export type Resource = "both" | "electricity" | "water";
export interface Range { start: string; end: string }

interface Props {
  series: Series; resource: Resource; levels: Level[]; showUnusual: boolean; selectedId: string | null;
  onSelect: (m: AnomalyItem) => void; onZoom?: (r: Range) => void; height?: number;
}

const PX = 12, PT = 16, PB = 28;
const iso = (ms: number) => new Date(ms).toISOString().slice(0, 19);

type Hover = { kind: "marker"; m: AnomalyItem; x: number } | { kind: "point"; p: SeriesPoint; x: number };

/** Household Pulse. Electricity rises above the centre line, water flow falls below it. The dashed line is the home's
 *  normal rhythm for that hour. Warnings are rings you can open; unusual-but-not-a-warning observations are small
 *  diamonds. Drag across the chart to zoom in. Long periods arrive pre-aggregated, with every anomaly kept as a marker. */
export default function HouseholdPulse({ series, resource, levels, showUnusual, selectedId, onSelect, onZoom, height = 340 }: Props) {
  const [wrapRef, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<Hover | null>(null);
  const [brush, setBrush] = useState<{ a: number; b: number } | null>(null);
  const drag = useRef<number | null>(null);
  const pts = series.points;

  const g = useMemo(() => {
    if (!pts.length) return null;
    const t0 = msOf(pts[0].ts_dt), span = Math.max(1, msOf(pts[pts.length - 1].ts_dt) - t0);
    const xOf = (ts: string) => PX + ((msOf(ts) - t0) / span) * (width - 2 * PX);
    const xs = pts.map((p) => xOf(p.ts_dt));
    const both = resource === "both";
    const inner = height - PT - PB, lane = both ? inner / 2 - 10 : inner - 10;
    const eBase = both ? PT + inner / 2 - 5 : height - PB, wBase = both ? PT + inner / 2 + 5 : height - PB;
    const top = (vals: (number | null)[]) => Math.max(1e-9, ...vals.map((v) => v ?? 0));
    const eMax = top([...pts.map((p) => p.power_max), ...pts.map((p) => p.power_baseline), ...series.markers.map((m) => m.powerW)]);
    const wMax = top([...pts.map((p) => p.flow_max), ...pts.map((p) => p.flow_baseline), ...series.markers.map((m) => m.volumeFlow)]);
    const h = (v: number | null, max: number) => Math.sqrt(Math.max(0, Math.min(v ?? 0, max)) / max) * lane;
    const yE = (v: number | null) => eBase - h(v, eMax);
    const yW = (v: number | null) => (both ? wBase + h(v, wMax) : wBase - h(v, wMax));
    const line = (f: (p: SeriesPoint) => number | null, y: (v: number | null) => number) =>
      pts.map((p, i) => `${i ? "L" : "M"}${xs[i].toFixed(1)} ${y(f(p)).toFixed(1)}`).join(" ");
    const area = (f: (p: SeriesPoint) => number | null, y: (v: number | null) => number, base: number) =>
      `${line(f, y)} L${xs[xs.length - 1].toFixed(1)} ${base} L${xs[0].toFixed(1)} ${base} Z`;
    return { t0, span, xs, xOf, eBase, wBase, yE, yW, line, area, both };
  }, [pts, series.markers, width, height, resource]);

  const markers = useMemo(() => {
    if (!g) return [];
    return series.markers.flatMap((m) => {
      const visible = m.is_warning ? levels.includes(m.risk_level) : showUnusual;
      const t = m.problem_type;
      const onWater = resource === "water" || (resource === "both" && t === "water");
      // A single-resource view only shows markers that concern that resource (electricity warnings stay off the water view).
      const relevant = resource === "both" || (resource === "water" ? t === "water" || t === "combined" || t === "contextual" : t !== "water");
      if (!visible || !relevant) return [];
      return [{ m, x: g.xOf(m.ts_dt), y: onWater ? g.yW(m.volumeFlow) : g.yE(m.powerW) }];
    });
  }, [series.markers, g, levels, showUnusual, resource]);

  if (!g) return <div ref={wrapRef}><p className="muted" role="status">No observations in this date range.</p></div>;

  const local = (ev: React.PointerEvent<SVGRectElement>) => ev.clientX - ev.currentTarget.getBoundingClientRect().left;
  const onMove = (ev: React.PointerEvent<SVGRectElement>) => {
    const x = local(ev);
    if (drag.current !== null) setBrush({ a: drag.current, b: x });
    let nearM: (typeof markers)[number] | null = null;
    for (const k of markers) if (Math.abs(k.x - x) < 12 && (!nearM || Math.abs(k.x - x) < Math.abs(nearM.x - x))) nearM = k;
    if (nearM) { setHover({ kind: "marker", m: nearM.m, x: nearM.x }); return; }
    let best = 0;
    for (let i = 1; i < g.xs.length; i++) if (Math.abs(g.xs[i] - x) < Math.abs(g.xs[best] - x)) best = i;
    setHover({ kind: "point", p: pts[best], x: g.xs[best] });
  };
  const onDown = (ev: React.PointerEvent<SVGRectElement>) => {
    if (!onZoom) return;
    ev.currentTarget.setPointerCapture(ev.pointerId);
    drag.current = local(ev); setBrush({ a: drag.current, b: drag.current });
  };
  const onUp = () => {
    if (drag.current !== null && brush && onZoom && Math.abs(brush.b - brush.a) > 14) {
      const at = (x: number) => g.t0 + ((Math.min(Math.max(x, PX), width - PX) - PX) / (width - 2 * PX)) * g.span;
      const [lo, hi] = [Math.min(brush.a, brush.b), Math.max(brush.a, brush.b)];
      onZoom({ start: dayOf(iso(at(lo))), end: dayOf(iso(at(hi))) });
    }
    drag.current = null; setBrush(null);
  };

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => ({ x: PX + f * (width - 2 * PX), label: fmtShort(iso(g.t0 + f * g.span)) }));
  const showE = resource !== "water", showW = resource !== "electricity";
  const E = "var(--elec)", W = "var(--water)";

  const tip = (() => {
    if (!hover) return null;
    const left = Math.min(Math.max(hover.x + 14, 4), width - 260);
    if (hover.kind === "marker") {
      const m = hover.m;
      return (
        <div className="tip" style={{ left }}>
          <b style={{ color: m.is_warning ? levelColor(m.risk_level) : undefined }}>{m.is_warning ? `${levelText(m.risk_level)} warning` : "Unusual, not a warning"}</b>
          <div><span>Time</span><span>{fmtFull(m.ts_dt)}</span></div>
          <div><span>Electricity</span><span>{num(m.powerW, 0, "W")}</span></div>
          <div><span>Water flow</span><span>{num(m.volumeFlow, 3)}</span></div>
          <div><span>Risk index</span><span>{num(m.risk_score, 1)}</span></div>
          <div><span>Status</span><span>Click for details</span></div>
        </div>
      );
    }
    const p = hover.p;
    return (
      <div className="tip" style={{ left }}>
        <b>{fmtFull(p.ts_dt)}{p.n > 1 ? ` (+${p.n - 1} more)` : ""}</b>
        {showE && <div><span>Electricity</span><span>{num(p.powerW, 0, "W")} · normal {num(p.power_baseline, 0)}</span></div>}
        {showW && <div><span>Water flow</span><span>{num(p.volumeFlow, 3)} · normal {num(p.flow_baseline, 3)}</span></div>}
        <div><span>Risk index</span><span>{num(p.risk_score, 1)}</span></div>
        <div><span>Status</span><span>{p.warnings ? "Warning" : p.anomalies ? "Unusual, not a warning" : "Normal rhythm"}</span></div>
      </div>
    );
  })();

  return (
    <div className="pulse" ref={wrapRef}>
      {tip}
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="group"
        aria-label={`Household Pulse with ${markers.length} markers. Markers can be reached with the keyboard.`}>
        <defs>
          <linearGradient id="gE" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={E} stopOpacity=".38" /><stop offset="1" stopColor={E} stopOpacity="0" /></linearGradient>
          <linearGradient id="gW" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stopColor={W} stopOpacity=".34" /><stop offset="1" stopColor={W} stopOpacity="0" /></linearGradient>
        </defs>
        {g.both && <line x1={PX} x2={width - PX} y1={g.eBase + 5} y2={g.eBase + 5} stroke="var(--line)" />}
        {showE && <>
          <path d={g.area((p) => p.powerW, g.yE, g.eBase)} fill="url(#gE)" />
          <path d={g.line((p) => p.power_baseline, g.yE)} fill="none" stroke={E} strokeWidth={1} strokeDasharray="3 5" opacity={0.6} />
          <path className="trace" pathLength={1} d={g.line((p) => p.powerW, g.yE)} stroke={E} />
        </>}
        {showW && <>
          <path d={g.area((p) => p.volumeFlow, g.yW, g.wBase)} fill="url(#gW)" />
          <path d={g.line((p) => p.flow_baseline, g.yW)} fill="none" stroke={W} strokeWidth={1} strokeDasharray="3 5" opacity={0.6} />
          <path className="trace" pathLength={1} d={g.line((p) => p.volumeFlow, g.yW)} stroke={W} />
        </>}
        {ticks.map((t, i) => <text key={i} x={t.x} y={height - 8} fontSize="11" fill="var(--muted)" textAnchor={i === 0 ? "start" : i === 4 ? "end" : "middle"}>{t.label}</text>)}
        {hover && <line x1={hover.x} x2={hover.x} y1={PT} y2={height - PB} stroke="var(--muted)" opacity={0.45} />}
        {brush && <rect x={Math.min(brush.a, brush.b)} y={PT} width={Math.abs(brush.b - brush.a)} height={height - PT - PB} fill="var(--elec)" opacity={0.14} />}
        <rect x={0} y={0} width={width} height={height - PB} fill="transparent" style={{ cursor: onZoom ? "crosshair" : "default" }}
          onPointerMove={onMove} onPointerLeave={() => !drag.current && setHover(null)} onPointerDown={onDown} onPointerUp={onUp} />
        {markers.map(({ m, x, y }) => {
          const sel = m.id === selectedId, c = m.is_warning ? levelColor(m.risk_level) : "var(--muted)";
          const act = () => onSelect(m);
          return (
            <g key={m.id} className="marker" tabIndex={0} role="button" onClick={act}
              onKeyDown={(k) => { if (k.key === "Enter" || k.key === " ") { k.preventDefault(); act(); } }}
              aria-label={m.is_warning ? `${levelText(m.risk_level)} warning, ${fmtFull(m.ts_dt)}. Open details.` : `Unusual observation, not a warning, ${fmtFull(m.ts_dt)}. Open details.`}>
              <line x1={x} x2={x} y1={PT} y2={height - PB} stroke={c} strokeWidth={sel ? 2 : 1} opacity={sel ? 0.8 : m.is_warning ? 0.28 : 0.12} />
              {m.is_warning ? (
                <>
                  <circle className="halo" cx={x} cy={y} r={8} fill={c} />
                  <circle className="ring" cx={x} cy={y} r={sel ? 11 : 9} fill="var(--bg)" stroke={c} strokeWidth={2.2} />
                  <text x={x} y={y + 3.5} textAnchor="middle" fontSize="10" fontWeight="700" fill={c}>{m.risk_level[0]}</text>
                </>
              ) : (
                <rect className="ring" x={x - 4} y={y - 4} width={8} height={8} transform={`rotate(45 ${x} ${y})`} fill="var(--bg)" stroke={c} strokeWidth={sel ? 2.4 : 1.4} />
              )}
              <circle cx={x} cy={y} r={14} fill="transparent" />
            </g>
          );
        })}
      </svg>
      <ResourceLegend electricity={showE} water={showW} />
    </div>
  );
}
