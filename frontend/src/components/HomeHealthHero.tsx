import type { Series, WarningItem } from "../lib/api";
import { fmtFull, homeName, homeState } from "../lib/format";
import RiskGauge from "./RiskGauge";
import SignalMeter from "./SignalMeter";

/** How is this house doing? The state, the latest reading explained, and the latest measurements, all from the API. */
export default function HomeHealthHero({ series, lastWarning, onOpen }: { series: Series; lastWarning: WarningItem | null; onOpen: (w: WarningItem) => void }) {
  const l = series.latest, last = series.points[series.points.length - 1];
  const state = homeState(l.risk_level);
  return (
    <section className="hero" aria-labelledby="hero-h">
      <RiskGauge value={l.risk_score} level={l.risk_level} />
      <div className="obs">
        <div className="kicker">{homeName(series.installation)} · latest reading</div>
        <p className="muted" style={{ marginTop: 4 }}>{state.line}</p>
        <h2 id="hero-h">{l.headline}</h2>
        <p className="meta">Most recent observation in the data: {fmtFull(l.ts_dt)}</p>
        <div className="obs-cols">
          <div><h3>{l.risk_level === "NORMAL" ? "What we see" : "Why it was flagged"}</h3><ul className="why">{l.explanation.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
          <div><h3>What to check</h3><p>{l.recommendation}</p></div>
        </div>
        {lastWarning && (
          <p style={{ marginTop: 20 }} className="muted">
            Latest warning for this house: <b style={{ color: "var(--ink)", fontWeight: 600 }}>{lastWarning.headline}</b>, {fmtFull(lastWarning.ts_dt)}.{" "}
            <button className="btn small" onClick={() => onOpen(lastWarning)}>View details</button>
          </p>
        )}
        <div className="signals" aria-label="Latest readings">
          <SignalMeter name="Electricity" color="var(--elec)" value={l.powerW} baseline={last?.power_baseline ?? null} unit="W" />
          <SignalMeter name="Water flow" color="var(--water)" value={l.volumeFlow} baseline={last?.flow_baseline ?? null} unit="" digits={3} />
        </div>
      </div>
    </section>
  );
}
