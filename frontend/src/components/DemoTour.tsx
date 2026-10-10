import { useEffect, useMemo, useState } from "react";
import { HouseholdSummary, WarningItem, useWarnings } from "../lib/api";
import { addDays, dayOf, homeName } from "../lib/format";
import type { Range } from "./HouseholdPulse";
import type { Selection } from "./WarningDrawer";

interface Actions {
  setHome: (id: string) => void; go: (v: string) => void; setRange: (r: Range | null) => void;
  open: (s: Selection) => void; close: () => void; select: (id: string | null) => void;
}

/** Guided walkthrough. It only navigates and highlights: the target is the highest-risk warning in the real data. */
export default function DemoTour({ homes, actions, onExit }: { homes: HouseholdSummary[]; actions: Actions; onExit: () => void }) {
  const { data, error, loading } = useWarnings({ limit: 1 });
  const top: WarningItem | undefined = data?.[0];
  const other = useMemo(() => [...homes].filter((h) => h.installation !== top?.installation).sort((a, b) => b.actionable_warnings - a.actionable_warnings)[0], [homes, top]);
  const [step, setStep] = useState(0);

  const steps = top ? [
    { text: `Start with ${homeName(top.installation)}, the house with the highest-risk warning in the data.`, run: () => { actions.close(); actions.setHome(top.installation); actions.go("console"); actions.setRange(null); actions.select(null); } },
    { text: "This is the Household Pulse of an earlier stretch. The dashed line is what has been usual for each hour.", run: () => { actions.close(); actions.setRange({ start: addDays(dayOf(top.ts_dt), -60), end: addDays(dayOf(top.ts_dt), -20) }); } },
    { text: "Move forward in time. The highlighted ring is the warning.", run: () => { actions.close(); actions.select(top.id); actions.setRange({ start: addDays(dayOf(top.ts_dt), -10), end: addDays(dayOf(top.ts_dt), 10) }); } },
    { text: "Open it to see the reading next to what is usual for that hour.", run: () => actions.open({ id: top.id }) },
    { text: "It explains why this was flagged and what to check. It points out unusual behaviour; it does not confirm a fault.", run: () => actions.open({ id: top.id }) },
    ...(other ? [{ text: `Compare with ${homeName(other.installation)} in its profile, which has the house-against-house comparison.`, run: () => { actions.close(); actions.select(null); actions.setHome(other.installation); actions.setRange(null); actions.go("profile"); } }] : []),
  ] : [];

  useEffect(() => { steps[step]?.run(); }, [step, top?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const last = step === steps.length - 1;
  return (
    <div className="demo" role="region" aria-label="Demo tour">
      {loading && <p>Preparing the tour from real warnings…</p>}
      {error && <p>{error.message}</p>}
      {!loading && !error && !top && <p>There are no warnings in the data to tour.</p>}
      {top && <p aria-live="polite"><b>Step {step + 1} of {steps.length}.</b> {steps[step].text}</p>}
      {top && <button className="btn" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</button>}
      {top && !last && <button className="btn primary" onClick={() => setStep(step + 1)}>Next</button>}
      <button className="btn" onClick={onExit}>{last ? "Finish" : "Exit tour"}</button>
    </div>
  );
}
