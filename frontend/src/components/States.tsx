import { ApiError } from "../lib/api";

export function Loading({ height = 240, label = "Loading" }: { height?: number; label?: string }) {
  return <div className="skeleton" style={{ height }} role="status" aria-label={label} />;
}

export function Problem({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const title = error.status === 0 ? "The service is not reachable"
    : error.code === "PREDICTIONS_FILE_NOT_FOUND" || error.code === "PREDICTIONS_FILE_EMPTY" ? "Results are not ready yet"
    : error.status === 404 ? "Not found" : "Something went wrong";
  const body = error.status === 0
    ? "HouseholdAI could not reach its backend. Check that it is running on port 8000, then try again."
    : error.code.startsWith("PREDICTIONS_FILE")
      ? `${error.message} Run the ML pipeline (py -m ml.pipeline) and restart the backend.`
      : error.message;
  return (
    <div className="state" role="alert">
      <h2>{title}</h2><p>{body}</p>
      {onRetry && <button className="btn primary" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return <div className="state" role="status"><h2>{title}</h2><p>{children}</p></div>;
}

export type StageState = "loading" | "done" | "failed";
const MARK: Record<StageState, string> = { loading: "…", done: "✓", failed: "✕" };

/** Lists the requests actually in progress. Each row mirrors a real network call; there are no invented percentages. */
export function LoadingStages({ title, stages }: { title: string; stages: { label: string; state: StageState }[] }) {
  return (
    <div className="stages" role="status" aria-live="polite">
      <div className="kicker">{title}</div>
      <ul>
        {stages.map((s) => (
          <li key={s.label} data-state={s.state}><span aria-hidden="true" className="mark">{MARK[s.state]}</span>{s.label}
            <span className="sr-only"> {s.state === "done" ? "done" : s.state === "failed" ? "failed" : "loading"}</span></li>
        ))}
      </ul>
      <div className="skeleton" style={{ height: 120, marginTop: 18 }} />
    </div>
  );
}

export const stageOf = (q: { data: unknown; error: unknown }): StageState => (q.error ? "failed" : q.data ? "done" : "loading");
