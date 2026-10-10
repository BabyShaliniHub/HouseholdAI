import type { WarningItem } from "../lib/api";
import { TYPE_LABEL, fmtDate, fmtTime, homeName, levelColor, num } from "../lib/format";
import { Empty } from "./States";

/** AI early-warning timeline: newest first. Each event opens the evidence drawer. */
export default function WarningTimeline({ items, selectedId, onSelect, showHome = true }: { items: WarningItem[]; selectedId: string | null; onSelect: (w: WarningItem) => void; showHome?: boolean }) {
  if (!items.length) return <Empty title="No warnings here">Nothing matches these filters. Readings that were unusual without signs of excess usage are not listed as warnings.</Empty>;
  return (
    <ol className="timeline" aria-label="Early warning timeline">
      {items.map((w, i) => (
        <li key={w.id} className="tl-item" style={{ "--dot": levelColor(w.risk_level), "--i": i } as React.CSSProperties}>
          <button className="tl-btn" aria-current={w.id === selectedId} onClick={() => onSelect(w)}>
            <span className="tl-when">{fmtDate(w.ts_dt)} · {fmtTime(w.ts_dt)}{showHome ? ` · ${homeName(w.installation)}` : ""}</span>
            <span className="tl-title"><span className="badge">{w.risk_level}</span>{w.headline}</span>
            <span className="tl-sub">{TYPE_LABEL[w.problem_type]} · {num(w.powerW, 0, "W")} · water flow {num(w.volumeFlow, 3)}</span>
            <span className="tl-score">{num(w.risk_score, 0)}<small>Risk index</small></span>
          </button>
        </li>
      ))}
    </ol>
  );
}
