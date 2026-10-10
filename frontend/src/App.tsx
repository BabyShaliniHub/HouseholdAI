import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DemoTour from "./components/DemoTour";
import HouseholdSwitcher from "./components/HouseholdSwitcher";
import type { Range } from "./components/HouseholdPulse";
import { Empty, LoadingStages, Problem, stageOf } from "./components/States";
import WarningDrawer, { Selection } from "./components/WarningDrawer";
import { paths, prefetch, useHealth, useHousehold, useHouseholds, useSummary } from "./lib/api";
import { byHouse, homeName } from "./lib/format";
import Console from "./views/Console";
import type { Ctx } from "./views/ctx";
import Profile from "./views/Profile";
import Warnings from "./views/Warnings";

const VIEWS = [
  { id: "console", label: "Console", icon: "M2 13h4l2.5-7 4 13 3-9 1.5 3H22" },
  { id: "warnings", label: "Warnings", icon: "M6 17V11a6 6 0 1 1 12 0v6l2 2H4zM10 21h4" },
  { id: "profile", label: "Profile", icon: "M3 11l9-8 9 8M5 10v10h14V10" },
] as const;
type ViewId = (typeof VIEWS)[number]["id"];
// An old #explorer bookmark simply opens the console.
const readHash = (): ViewId => VIEWS.find((v) => `#${v.id}` === window.location.hash)?.id ?? "console";

export default function App() {
  const [view, setView] = useState<ViewId>(readHash);
  const [home, setHomeState] = useState<string | null>(null);
  const [range, setRange] = useState<Range | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    const on = () => setView(readHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = useCallback((v: string) => { window.location.hash = v; setView(VIEWS.find((x) => x.id === v)?.id ?? "console"); }, []);

  // Independent requests start together on page load instead of one after another.
  const health = useHealth();
  const homesQ = useHouseholds();
  const summaryQ = useSummary();
  const detailQ = useHousehold(home);
  const homes = useMemo(() => (homesQ.data ? [...homesQ.data].sort(byHouse) : null), [homesQ.data]);

  // As soon as a house is known, start loading its chart data alongside the house summary.
  useEffect(() => {
    if (!home) return;
    prefetch(paths.series(home, { maxPoints: 1000 }));
    prefetch(paths.series(home, { maxPoints: 480 }));
  }, [home]);

  // Choosing the house that is already open does nothing, so repeated clicks cannot trigger repeated loads.
  const homeRef = useRef<string | null>(null);
  const setHome = useCallback((id: string) => {
    if (homeRef.current === id) return;
    homeRef.current = id;
    setHomeState(id); setRange(null); setSelection(null);
  }, []);
  // Default house: the one with the most serious warnings, so the console never opens empty.
  useEffect(() => {
    if (home || !homes?.length) return;
    const weight = (h: (typeof homes)[number]) => h.high_count * 4 + h.medium_count * 2 + h.low_count;
    setHome([...homes].sort((a, b) => weight(b) - weight(a) || byHouse(a, b))[0].installation);
  }, [homes, home, setHome]);

  const open = useCallback((s: Selection) => setSelection(s), []);
  const close = useCallback(() => setSelection(null), []);
  const demoActions = useMemo(() => ({ setHome, go, setRange, open, close, select: (id: string | null) => setSelection(id ? { id } : null) }), [setHome, go, open, close]);

  const ctx: Ctx | null = home && homes && summaryQ.data && detailQ.data
    ? { home, homes, detail: detailQ.data, summary: summaryQ.data, range, setRange, setHome, selectedId: selection?.id ?? null, open, go }
    : null;
  const loadError = homesQ.error ?? summaryQ.error ?? detailQ.error;
  const retryAll = () => { health.reload(); homesQ.reload(); summaryQ.reload(); detailQ.reload(); };

  let body: React.ReactNode;
  if (health.error) body = <Problem error={health.error} onRetry={retryAll} />;
  else if (loadError) body = <Problem error={loadError} onRetry={retryAll} />;
  else if (homes && homes.length === 0) body = <Empty title="No houses found">The predictions file contains no observations.</Empty>;
  else if (!ctx) body = (
    <LoadingStages title={home ? `Loading ${homeName(home)}` : "Loading HouseholdAI"} stages={[
      { label: "Connecting to the service", state: stageOf(health) },
      { label: "List of houses", state: stageOf(homesQ) },
      { label: "Overall results", state: stageOf(summaryQ) },
      ...(home ? [{ label: `${homeName(home)} summary`, state: stageOf(detailQ) }] : []),
    ]} />
  );
  else body = (
    <div className="page" key={`${view}-${ctx.home}`}>
      {view === "console" ? <Console c={ctx} /> : view === "warnings" ? <Warnings c={ctx} /> : <Profile c={ctx} />}
    </div>
  );

  return (
    <div className="app">
      <nav className="rail" aria-label="Main">
        <svg className="logo" width="34" height="34" viewBox="0 0 32 32" aria-hidden="true"><path d="M2 17h6l3-9 5 17 4-12 2 4h8" fill="none" stroke="#9a92ff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg>
        {VIEWS.map((v) => (
          <button key={v.id} className="nav-link" aria-current={view === v.id ? "page" : undefined} onClick={() => go(v.id)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={v.icon} /></svg>
            {v.label}
          </button>
        ))}
      </nav>
      <div className="main">
        <header className="topbar">
          <div className="brand">
            <h1>HouseholdAI</h1>
            <p>Early warnings for household problems · <b>Learn. Detect. Explain. Warn.</b></p>
          </div>
          <button className="btn" aria-pressed={demo} onClick={() => setDemo((d) => !d)} disabled={!ctx}>{demo ? "Tour running" : "Take a guided tour"}</button>
        </header>
        {homes && home && <HouseholdSwitcher homes={homes} current={home} onPick={setHome} />}
        {body}
      </div>
      {selection && <WarningDrawer selection={selection} onClose={close} />}
      {demo && homes && <DemoTour homes={homes} actions={demoActions} onExit={() => { setDemo(false); close(); }} />}
    </div>
  );
}
