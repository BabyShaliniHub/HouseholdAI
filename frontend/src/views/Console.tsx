import { useState } from "react";
import HomeHealthHero from "../components/HomeHealthHero";
import HouseholdPulse, { Resource } from "../components/HouseholdPulse";
import RiskTimeline from "../components/RiskTimeline";
import SignalFunnel from "../components/SignalFunnel";
import WarningTimeline from "../components/WarningTimeline";
import { LevelChips, RangeControl, ResourceToggle } from "../components/Controls";
import { Loading, LoadingStages, Problem, stageOf } from "../components/States";
import { SectionHeader } from "../components/ui";
import { Level, useSeries } from "../lib/api";
import { insights } from "../lib/derive";
import { homeName } from "../lib/format";
import type { Ctx } from "./ctx";

/** Each section loads on its own: the summary and warnings below come from the house summary and show straight away,
 *  while the readings and the chart wait only for their own data. */
export default function Console({ c }: { c: Ctx }) {
  const [resource, setResource] = useState<Resource>("both");
  const [levels, setLevels] = useState<Level[]>(["HIGH", "MEDIUM", "LOW"]);
  const [unusual, setUnusual] = useState(true);
  const full = useSeries(c.home, { maxPoints: 1000 });
  const view = useSeries(c.home, { start: c.range?.start, end: c.range?.end, maxPoints: 480 });
  const name = homeName(c.home);
  const notes = insights(c.detail.summary, c.summary, c.detail.recent_warnings);

  return (
    <>
      {full.error ? <div className="inline-problem"><Problem error={full.error} onRetry={full.reload} /></div>
        : !full.data ? <LoadingStages title={`Loading ${name}`} stages={[
            { label: "House summary", state: "done" },
            { label: "Electricity and water readings", state: stageOf(full) },
            { label: "Chart data", state: stageOf(view) },
          ]} />
        : <HomeHealthHero series={full.data} lastWarning={c.detail.recent_warnings[0] ?? null} onOpen={(w) => c.open({ id: w.id })} />}

      <section className="section pulse-stage" aria-labelledby="pulse-h">
        <SectionHeader kicker="Household Pulse" title="Electricity and water over time">
          Electricity is drawn above the line and water flow below it. The dashed lines show what is usual for each hour. Drag across the chart to zoom in, or open a ring to see why it was flagged.
        </SectionHeader>
        <span id="pulse-h" className="sr-only">Household Pulse chart</span>
        {full.data && (
          <div className="controls">
            <ResourceToggle value={resource} onChange={setResource} />
            <LevelChips value={levels} onChange={setLevels} unusual={unusual} onUnusual={setUnusual} />
            <RangeControl first={full.data.first_ts} last={full.data.last_ts} range={c.range} onChange={c.setRange} />
          </div>
        )}
        {view.error ? <Problem error={view.error} onRetry={view.reload} /> : !view.data ? <Loading height={340} label="Loading chart" /> :
          <HouseholdPulse series={view.data} resource={resource} levels={levels} showUnusual={unusual} selectedId={c.selectedId}
            onSelect={(m) => c.open({ id: m.id, marker: m })} onZoom={c.setRange} />}
      </section>

      <section className="section">
        <SectionHeader kicker="Unusual is not the same as urgent" title={`Unusual readings in ${name}`} />
        <SignalFunnel counts={c.detail.summary} scope={name} />
      </section>

      <div className="section cols">
        <section>
          <SectionHeader kicker="Warnings" title="Recent warnings">
            <button className="btn small" onClick={() => c.go("warnings")}>All warnings</button>
          </SectionHeader>
          <WarningTimeline items={c.detail.recent_warnings} selectedId={c.selectedId} onSelect={(w) => c.open({ id: w.id })} showHome={false} />
        </section>
        <section>
          <SectionHeader kicker="From the data" title="Notes" />
          <ul className="notes">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </section>
      </div>

      <section className="section">
        <SectionHeader kicker="Risk" title="Risk index over time">Each observation scored from 0 to 100. Rings mark warnings.</SectionHeader>
        {view.data ? <RiskTimeline series={view.data} selectedId={c.selectedId} onSelect={(m) => c.open({ id: m.id, marker: m })} /> : <Loading height={170} label="Loading risk timeline" />}
      </section>
    </>
  );
}
