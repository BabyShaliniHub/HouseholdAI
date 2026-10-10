import { useMemo } from "react";
import CompareBars from "../components/CompareBars";
import DataDetails from "../components/DataDetails";
import PeriodCompare from "../components/PeriodCompare";
import WarningTimeline from "../components/WarningTimeline";
import { Loading, Problem } from "../components/States";
import { SectionHeader, StatMetric } from "../components/ui";
import { useSeries } from "../lib/api";
import { calmRows, hourProfile, insights, monthly, percentile, rawRows } from "../lib/derive";
import { TYPE_LABEL, fmtFull, hourLabel, homeName, num } from "../lib/format";
import type { Ctx } from "./ctx";

/** 24-hour rhythm: average electricity per hour (violet, upward) and how often water flow is present (cyan, downward). */
function Rhythm({ hours }: { hours: ReturnType<typeof hourProfile> }) {
  const maxP = Math.max(1, ...hours.map((h) => h.power)), maxW = Math.max(0.01, ...hours.map((h) => h.waterShare));
  return (
    <svg className="rhythm" viewBox="0 0 480 170" width="100%" role="img" aria-label="Average electricity and water presence by hour of day">
      {hours.map((h) => {
        const x = 8 + h.hour * 19.5, up = (h.power / maxP) * 62, down = (h.waterShare / maxW) * 52;
        return (
          <g key={h.hour}>
            <rect x={x} y={78 - up} width={14} height={Math.max(up, 1)} rx={3} fill="var(--elec)" opacity={0.85} />
            <rect x={x} y={84} width={14} height={Math.max(down, 1)} rx={3} fill="var(--water)" opacity={0.85} />
            {h.hour % 3 === 0 && <text x={x + 7} y={160} textAnchor="middle">{String(h.hour).padStart(2, "0")}</text>}
          </g>
        );
      })}
      <line x1={4} x2={476} y1={81} y2={81} stroke="var(--line)" />
    </svg>
  );
}

function Evolution({ rows }: { rows: ReturnType<typeof monthly> }) {
  const max = Math.max(1, ...rows.map((r) => r.meanRisk));
  return (
    <svg className="rhythm" viewBox={`0 0 ${Math.max(rows.length, 1) * 46} 130`} width="100%" style={{ maxWidth: 600 }} role="img" aria-label="Average risk index and warnings per month">
      {rows.map((r, i) => {
        const h = (r.meanRisk / max) * 66;
        return (
          <g key={r.month} transform={`translate(${i * 46 + 6} 0)`}>
            <rect x={0} y={88 - h} width={30} height={h} rx={4} fill="var(--elec)" opacity={0.8} />
            <text x={15} y={82 - h} textAnchor="middle">{num(r.meanRisk, 0)}</text>
            <text x={15} y={104} textAnchor="middle">{r.month.slice(5)}</text>
            <text x={15} y={119} textAnchor="middle" fill={r.warnings ? "var(--medium)" : undefined}>{r.warnings} w</text>
          </g>
        );
      })}
    </svg>
  );
}

export default function Profile({ c }: { c: Ctx }) {
  const { data, error, loading, reload } = useSeries(c.home, { maxPoints: 1000 });
  const s = c.detail.summary;
  const name = homeName(c.home);
  const rows = useMemo(() => (data ? rawRows(data) : []), [data]);
  const calc = useMemo(() => {
    if (!data) return null;
    const calm = calmRows(rows), hours = hourProfile(rows);
    const flowing = calm.map((p) => p.volumeFlow ?? 0).filter((v) => v > 0);
    const top = (f: (h: (typeof hours)[number]) => number) => [...hours].filter((h) => h.samples > 0).sort((a, b) => f(b) - f(a)).slice(0, 3).map((h) => h.hour).sort((a, b) => a - b);
    return {
      hours, months: monthly(rows),
      pLow: percentile(calm.map((p) => p.powerW ?? 0), 0.1), pHigh: percentile(calm.map((p) => p.powerW ?? 0), 0.9),
      waterShare: rows.length ? (100 * rows.filter((p) => (p.volumeFlow ?? 0) > 0).length) / rows.length : null,
      fLow: percentile(flowing, 0.25), fHigh: percentile(flowing, 0.9),
      powerHours: top((h) => h.power), waterHours: top((h) => h.waterShare),
    };
  }, [data, rows]);

  // Sections that need the readings wait for them; everything else on this page renders immediately.
  const waiting = error ? <Problem error={error} onRetry={reload} /> : <Loading height={200} label="Loading readings" />;
  const ready = !loading && !!calc && !!data;
  const hoursText = (hs: number[]) => (hs.length ? hs.map(hourLabel).join(", ") : "—");
  const notes = insights(s, c.summary, c.detail.recent_warnings);
  const informational = c.detail.recent_anomalies.filter((a) => !a.is_warning).slice(0, 6);

  return (
    <>
      <section className="section" style={{ paddingTop: 40 }}>
        <div className="kicker">{name}</div>
        <h2 style={{ fontSize: "clamp(1.8rem,3.6vw,2.8rem)", margin: "8px 0 10px", maxWidth: "22ch" }}>What HouseholdAI has learned about {name}</h2>
        <p className="muted" style={{ maxWidth: "62ch" }}>
          Based on {s.total_rows.toLocaleString("en-US")} observations of this house alone. What counts as normal here is never judged against another house.
        </p>
        <ul className="notes" style={{ marginTop: 22, maxWidth: "70ch" }}>{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
      </section>

      <section className="section">
        <SectionHeader kicker="Daily rhythm" title="A typical day">Normal observations only. Violet is average electricity by hour; cyan is how often water flow is present.</SectionHeader>
        {!ready || !calc ? waiting : (
          <>
            <Rhythm hours={calc.hours} />
            <dl className="facts" style={{ marginTop: 20 }}>
              <StatMetric label="Busiest electricity hours" value={hoursText(calc.powerHours)} />
              <StatMetric label="Most frequent water activity" value={hoursText(calc.waterHours)} />
            </dl>
          </>
        )}
      </section>

      <div className="section cols">
        <section>
          <SectionHeader kicker="Electricity" title="Normal electricity use" />
          <dl className="facts">
            <StatMetric label="Normal range" value={ready && calc ? `${num(calc.pLow, 0)}–${num(calc.pHigh, 0)}` : "…"} note="W" />
            <StatMetric label="Average" value={num(s.average_power, 0)} note="W" />
            <StatMetric label="Electricity warnings" value={s.electricity_warnings} />
          </dl>
        </section>
        <section>
          <SectionHeader kicker="Water" title="Typical water flow" />
          <dl className="facts">
            <StatMetric label="Flow present in" value={ready && calc ? num(calc.waterShare, 1) : "…"} note="% of observations" />
            <StatMetric label="Typical when flowing" value={ready && calc ? `${num(calc.fLow, 3)}–${num(calc.fHigh, 3)}` : "…"} />
            <StatMetric label="Water warnings" value={s.water_warnings + s.combined_warnings} />
          </dl>
        </section>
      </div>

      <section className="section">
        <SectionHeader kicker="Over the year" title="Risk by month">Average risk index per month. “w” is the number of warnings that month.</SectionHeader>
        {ready && calc ? <Evolution rows={calc.months} /> : waiting}
      </section>

      <div className="section cols">
        <section>
          <SectionHeader kicker="Warnings" title="Recent warnings" />
          <WarningTimeline items={c.detail.recent_warnings} selectedId={c.selectedId} onSelect={(w) => c.open({ id: w.id })} showHome={false} />
        </section>
        <section>
          <SectionHeader kicker="For information" title="Unusual, no action needed" />
          <ul className="notes">
            {informational.map((a) => (
              <li key={a.id}><button style={{ textAlign: "left" }} onClick={() => c.open({ id: a.id, marker: a })}>
                <b style={{ fontWeight: 600 }}>{TYPE_LABEL[a.problem_type]}</b> · <span className="muted">{fmtFull(a.ts_dt)}</span>
              </button></li>
            ))}
            {!informational.length && <li className="muted">No recent readings of this kind.</li>}
          </ul>
        </section>
      </div>

      <section className="section">
        <SectionHeader kicker="Compare" title="Two periods of this house">Pick two stretches of {name} and see how they differed.</SectionHeader>
        {ready && data ? <PeriodCompare home={c.home} rows={rows} first={data.first_ts} last={data.last_ts} /> : waiting}
      </section>

      <section className="section">
        <SectionHeader kicker="Compare" title="House against house">
          Share of observations that were unusual, and the number of warnings (w). Select a house to switch to it.
        </SectionHeader>
        <CompareBars homes={c.homes} current={c.home} onPick={c.setHome} />
      </section>

      {ready && <DataDetails rows={rows} />}

      <section className="section">
        <SectionHeader kicker="Technical details" title="How to read this" />
        <details open>
          <summary>How HouseholdAI decides</summary>
          <dl>
            <dt>What it learns</dt><dd>Each house's own normal pattern of electricity (powerW) and water flow (volumeFlow). Houses are never compared with each other when deciding what is unusual.</dd>
            <dt>Method</dt><dd>Isolation Forest, 300 trees per house.</dd>
            <dt>Across all houses</dt><dd>{c.summary.total_rows.toLocaleString("en-US")} observations in {c.summary.total_households} houses; {c.summary.statistical_anomalies} were statistically unusual and {c.summary.actionable_warnings} became warnings.</dd>
            <dt>Unusual vs. warning</dt><dd>A warning needs signs of excess usage as well. Quieter-than-normal activity is never raised as a warning.</dd>
            <dt>Limits</dt><dd>HouseholdAI points out unusual patterns early. It cannot confirm a leak, a fault or an appliance failure.</dd>
          </dl>
        </details>
      </section>
    </>
  );
}
