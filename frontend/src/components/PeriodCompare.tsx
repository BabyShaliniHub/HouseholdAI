import { useState } from "react";
import { SeriesPoint } from "../lib/api";
import { periodStats } from "../lib/derive";
import { addDays, dayOf, homeName, num } from "../lib/format";
import { RangeControl } from "./Controls";
import type { Range } from "./HouseholdPulse";
import { StatMetric } from "./ui";

function Period({ title, range, onChange, first, last, rows }: { title: string; range: Range; onChange: (r: Range) => void; first: string; last: string; rows: SeriesPoint[] }) {
  const s = periodStats(rows, range.start, range.end);
  return (
    <div>
      <h3>{title}</h3>
      <RangeControl first={first} last={last} range={range} onChange={(r) => onChange(r ?? { start: dayOf(first), end: dayOf(last) })} />
      {s ? (
        <dl className="facts" style={{ marginTop: 16 }}>
          <StatMetric label="Observations" value={s.n} />
          <StatMetric label="Average electricity" value={num(s.meanPower, 0)} note="W" />
          <StatMetric label="Peak electricity" value={num(s.peakPower, 0)} note="W" />
          <StatMetric label="Average water flow" value={num(s.meanFlow, 3)} />
          <StatMetric label="Water flow present" value={num(s.flowShare, 1)} note="%" />
          <StatMetric label="Unusual / warnings" value={`${s.anomalies} / ${s.warnings}`} />
        </dl>
      ) : <p className="muted" role="status" style={{ marginTop: 16 }}>No observations in this period.</p>}
    </div>
  );
}

/** Two date ranges of one home, side by side. Defaults to the first and second half of the data. */
export default function PeriodCompare({ home, rows, first, last }: { home: string; rows: SeriesPoint[]; first: string; last: string }) {
  const f = dayOf(first), l = dayOf(last);
  const mid = addDays(f, Math.floor((Date.parse(l) - Date.parse(f)) / 86400000 / 2));
  const [a, setA] = useState<Range>({ start: f, end: mid });
  const [b, setB] = useState<Range>({ start: addDays(mid, 1), end: l });
  return (
    <div className="period" aria-label={`Compare two periods of ${homeName(home)}`}>
      <Period title="Period A" range={a} onChange={setA} first={first} last={last} rows={rows} />
      <Period title="Period B" range={b} onChange={setB} first={first} last={last} rows={rows} />
    </div>
  );
}
