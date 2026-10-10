import { useMemo, useState } from "react";
import SignalFunnel from "../components/SignalFunnel";
import WarningTimeline from "../components/WarningTimeline";
import { Loading, Problem } from "../components/States";
import { SectionHeader } from "../components/ui";
import { Level, useWarnings } from "../lib/api";
import { homeName } from "../lib/format";
import type { Ctx } from "./ctx";

type Filter = "ALL" | Level;
const FILTERS: [Filter, string][] = [["ALL", "All"], ["HIGH", "High"], ["MEDIUM", "Medium"], ["LOW", "Low"]];

export default function Warnings({ c }: { c: Ctx }) {
  const [level, setLevel] = useState<Filter>("ALL");
  const [scope, setScope] = useState<"all" | "home">("all");
  const { data, error, loading, reload } = useWarnings();
  const shown = useMemo(() => (data ?? []).filter((w) => (level === "ALL" || w.risk_level === level) && (scope === "all" || w.installation === c.home)), [data, level, scope, c.home]);
  const counts = scope === "all" ? c.summary : c.detail.summary;
  return (
    <>
      <section className="section" style={{ paddingTop: 36 }}>
        <SectionHeader kicker="Early warnings" title="Warnings">
          Readings that were unusual for their house and also showed signs of excess usage.
        </SectionHeader>
        <SignalFunnel counts={counts} scope={scope === "all" ? "all homes" : homeName(c.home)} />
      </section>
      <section className="section">
        <div className="controls">
          <div className="seg" role="group" aria-label="Risk level">
            {FILTERS.map(([k, l]) => <button key={k} aria-pressed={level === k} onClick={() => setLevel(k)}>{l}</button>)}
          </div>
          <div className="seg" role="group" aria-label="Scope">
            <button aria-pressed={scope === "all"} onClick={() => setScope("all")}>All homes</button>
            <button aria-pressed={scope === "home"} onClick={() => setScope("home")}>{homeName(c.home)}</button>
          </div>
          <span className="muted mono" aria-live="polite">{shown.length} shown</span>
        </div>
        {loading ? <Loading height={320} label="Loading warnings" /> : error ? <Problem error={error} onRetry={reload} /> :
          <div key={`${level}-${scope}-${c.home}`}><WarningTimeline items={shown} selectedId={c.selectedId} onSelect={(w) => c.open({ id: w.id })} showHome={scope === "all"} /></div>}
      </section>
    </>
  );
}
