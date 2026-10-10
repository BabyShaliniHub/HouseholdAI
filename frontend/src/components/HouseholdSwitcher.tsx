import type { HouseholdSummary } from "../lib/api";
import { homeName } from "../lib/format";

/** Pick a house. Shows each house's warning count; the installation id stays internal. */
export default function HouseholdSwitcher({ homes, current, onPick }: { homes: HouseholdSummary[]; current: string; onPick: (id: string) => void }) {
  return (
    <div className="switcher" role="radiogroup" aria-label="Choose a house">
      {homes.map((h) => (
        <button key={h.installation} className="home-pill" role="radio" aria-checked={h.installation === current} onClick={() => onPick(h.installation)}
          aria-label={`${homeName(h.installation)}, ${h.actionable_warnings} warnings`}>
          {homeName(h.installation)}
          <span className={`n ${h.actionable_warnings ? "" : "zero"}`}>{h.actionable_warnings}</span>
        </button>
      ))}
    </div>
  );
}
