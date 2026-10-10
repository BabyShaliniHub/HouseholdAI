import type { Level } from "../lib/api";
import { LEVELS, addDays, dayOf, levelColor, levelWord } from "../lib/format";
import type { Range, Resource } from "./HouseholdPulse";

export function ResourceToggle({ value, onChange }: { value: Resource; onChange: (r: Resource) => void }) {
  const opts: [Resource, string][] = [["both", "Both"], ["electricity", "Electricity"], ["water", "Water"]];
  return (
    <div className="seg" role="group" aria-label="Resource">
      {opts.map(([k, l]) => <button key={k} aria-pressed={value === k} onClick={() => onChange(k)}>{l}</button>)}
    </div>
  );
}

export function LevelChips({ value, onChange, unusual, onUnusual }: {
  value: Level[]; onChange: (l: Level[]) => void; unusual?: boolean; onUnusual?: (v: boolean) => void;
}) {
  const toggle = (l: Level) => onChange(value.includes(l) ? value.filter((x) => x !== l) : [...value, l]);
  return (
    <div className="chips" role="group" aria-label="Show on the pulse">
      {LEVELS.map((l) => (
        <button key={l} className="chip" aria-pressed={value.includes(l)} onClick={() => toggle(l)}>
          <i style={{ background: levelColor(l) }} />{levelWord(l)}
        </button>
      ))}
      {onUnusual && (
        <button className="chip" aria-pressed={!!unusual} onClick={() => onUnusual(!unusual)} title="Statistically unusual observations that did not become warnings">
          <i style={{ background: "transparent", border: "1px solid var(--muted)", borderRadius: 2, transform: "rotate(45deg)", width: 7, height: 7 }} />Unusual, not a warning
        </button>
      )}
    </div>
  );
}

/** Date range limited to the days the household's data covers. null = the whole period. */
export function RangeControl({ first, last, range, onChange }: { first: string; last: string; range: Range | null; onChange: (r: Range | null) => void }) {
  const min = dayOf(first), max = dayOf(last);
  const cur = range ?? { start: min, end: max };
  const set = (patch: Partial<Range>) => {
    const next = { ...cur, ...patch };
    if (next.start > next.end) return;
    onChange(next.start === min && next.end === max ? null : next);
  };
  return (
    <div className="range">
      <label>From <input type="date" min={min} max={max} value={cur.start} onChange={(e) => e.target.value && set({ start: e.target.value })} /></label>
      <label>To <input type="date" min={min} max={max} value={cur.end} onChange={(e) => e.target.value && set({ end: e.target.value })} /></label>
      <button className="btn small" onClick={() => onChange({ start: addDays(max, -30), end: max })}>Last 30 days</button>
      <button className="btn small" onClick={() => onChange({ start: addDays(max, -90), end: max })}>Last 90 days</button>
      <button className="btn small" disabled={!range} onClick={() => onChange(null)}>Full period</button>
    </div>
  );
}
