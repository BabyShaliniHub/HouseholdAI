import { useCallback, useEffect, useRef, useState } from "react";

/** The only place API URLs live. Override with VITE_API_BASE (e.g. in frontend/.env). */
const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://127.0.0.1:8000/api/v1";

export type Level = "NORMAL" | "LOW" | "MEDIUM" | "HIGH";
export type ProblemType = "electricity" | "water" | "combined" | "inactivity" | "low_activity" | "contextual" | "none";

// ---- response shapes: mirror backend/app/schemas.py exactly ----------------------------------------
export interface Health { status: string }
export interface Counts {
  total_rows: number; statistical_anomalies: number; actionable_warnings: number;
  normal_count: number; low_count: number; medium_count: number; high_count: number;
  electricity_warnings: number; water_warnings: number; combined_warnings: number;
}
export interface DashboardSummary extends Counts {
  total_households: number; anomaly_percentage: number; warning_percentage: number;
}
export interface HouseholdSummary extends Counts { installation: string; average_power: number; average_flow: number }
export interface WarningItem {
  id: string; installation: string; ts_dt: string; powerW: number | null; volumeFlow: number | null;
  problem_type: ProblemType; risk_level: Level; risk_score: number | null; headline: string;
  explanation: string[]; recommendation: string; power_ev: number | null; flow_ev: number | null;
  flow_persistence_hours: number | null; flow_meaningful_samples: number | null; flow_abnormal: boolean | null;
}
export interface WarningDetail extends WarningItem {
  is_anomaly: boolean; anomaly_score: number | null; persist_count: number | null; flow_run: number | null;
  hour: number | null; power_baseline: number | null; flow_baseline: number | null;
}
export interface AnomalyItem {
  id: string; installation: string; ts_dt: string; powerW: number | null; volumeFlow: number | null;
  problem_type: ProblemType; risk_level: Level; risk_score: number | null; headline: string; is_warning: boolean;
}
export interface HouseholdDetail { summary: HouseholdSummary; recent_warnings: WarningItem[]; recent_anomalies: AnomalyItem[] }
export interface SeriesPoint {
  id: string | null; ts_dt: string; powerW: number | null; power_max: number | null; volumeFlow: number | null;
  flow_max: number | null; power_baseline: number | null; flow_baseline: number | null; risk_score: number | null;
  risk_level: Level; anomalies: number; warnings: number; n: number;
}
export interface Series {
  installation: string; first_ts: string; last_ts: string; total_rows: number; bucketed: boolean;
  points: SeriesPoint[]; markers: AnomalyItem[]; latest: WarningItem;
}

// ---- paths -------------------------------------------------------------------------------------------
const enc = encodeURIComponent;
export const paths = {
  health: "/health",
  summary: "/dashboard/summary",
  warnings: (o: { installation?: string; level?: Level; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (o.installation) q.set("installation", o.installation);
    if (o.level) q.set("risk_level", o.level);
    if (o.limit) q.set("limit", String(o.limit));
    const qs = q.toString();
    return `/warnings${qs ? `?${qs}` : ""}`;
  },
  warning: (id: string) => `/warnings/${enc(id)}`,
  households: "/households",
  household: (id: string) => `/households/${enc(id)}`,
  /** start/end are YYYY-MM-DD (end inclusive); omit both for the whole period. maxPoints=1000 returns raw rows. */
  series: (id: string, o: { start?: string; end?: string; maxPoints?: number } = {}) => {
    const q = new URLSearchParams({ max_points: String(o.maxPoints ?? 600) });
    if (o.start) q.set("start", `${o.start}T00:00:00`);
    if (o.end) q.set("end", `${o.end}T23:59:59`);
    return `/households/${enc(id)}/series?${q}`;
  },
};

// ---- fetching ----------------------------------------------------------------------------------------
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try { res = await fetch(`${API_BASE}${path}`); } catch { throw new ApiError(0, "API_UNREACHABLE", "The HouseholdAI API is not reachable."); }
  if (!res.ok) {
    let code = "REQUEST_FAILED", message = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.error === "string") { code = body.error; message = body.message ?? message; }
      else if (typeof body.detail === "string") message = body.detail;
    } catch { /* keep defaults */ }
    throw new ApiError(res.status, code, message);
  }
  return res.json() as Promise<T>;
}

// ---- cache ---------------------------------------------------------------------------------------------
// Results are read from precomputed predictions, so a short cache is safe. Requests for the same path that are already
// in flight share one network call, and a result is reused for CACHE_TTL_MS. Failed requests are never cached, and
// reload() always bypasses the cache.
const CACHE_TTL_MS = 60_000;
interface Entry { at: number; promise: Promise<unknown>; data?: unknown }
const cache = new Map<string, Entry>();
const isFresh = (e: Entry) => e.data !== undefined && Date.now() - e.at < CACHE_TTL_MS;

function load<T>(path: string, force = false): Promise<T> {
  const hit = cache.get(path);
  if (hit && !force && (hit.data === undefined || isFresh(hit))) return hit.promise as Promise<T>;
  const entry: Entry = { at: Date.now(), promise: Promise.resolve() };
  entry.promise = getJson<T>(path).then(
    (data) => { entry.data = data; entry.at = Date.now(); return data; },
    (err) => { if (cache.get(path) === entry) cache.delete(path); throw err; },
  );
  cache.set(path, entry);
  return entry.promise as Promise<T>;
}
const peek = <T,>(path: string): T | null => { const e = cache.get(path); return e && isFresh(e) ? (e.data as T) : null; };
/** Starts a request early so a later hook finds it already in flight or finished. */
export const prefetch = (path: string) => { void load(path).catch(() => undefined); };

export interface ApiState<T> { data: T | null; error: ApiError | null; loading: boolean; reload: () => void }
type Raw<T> = { data: T | null; error: ApiError | null; loading: boolean };
const initial = <T,>(path: string | null): Raw<T> => { const d = path ? peek<T>(path) : null; return { data: d, error: null, loading: path !== null && d === null }; };

/** Fetches `path` (null = skip). Data is cleared whenever the path changes, so another house's data is never shown. */
export function useApi<T>(path: string | null): ApiState<T> {
  const [state, setState] = useState<Raw<T>>(() => initial<T>(path));
  const [tick, setTick] = useState(0);
  const force = useRef(false);
  useEffect(() => {
    if (path === null) { setState({ data: null, error: null, loading: false }); return; }
    const bypass = force.current; force.current = false;
    const cached = bypass ? null : peek<T>(path);
    if (cached !== null) { setState({ data: cached, error: null, loading: false }); return; }
    let live = true;
    setState({ data: null, error: null, loading: true });
    load<T>(path, bypass).then(
      (data) => live && setState({ data, error: null, loading: false }),
      (e: ApiError) => live && setState({ data: null, error: e, loading: false }),
    );
    return () => { live = false; };
  }, [path, tick]);
  const reload = useCallback(() => { force.current = true; setTick((t) => t + 1); }, []);
  return { ...state, reload };
}

export const useHealth = () => useApi<Health>(paths.health);
export const useSummary = () => useApi<DashboardSummary>(paths.summary);
export const useHouseholds = (enabled = true) => useApi<HouseholdSummary[]>(enabled ? paths.households : null);
export const useHousehold = (id: string | null) => useApi<HouseholdDetail>(id ? paths.household(id) : null);
export const useWarnings = (o?: Parameters<typeof paths.warnings>[0], enabled = true) => useApi<WarningItem[]>(enabled ? paths.warnings(o) : null);
export const useWarning = (id: string | null) => useApi<WarningDetail>(id ? paths.warning(id) : null);
export const useSeries = (id: string | null, o?: Parameters<typeof paths.series>[1]) => useApi<Series>(id ? paths.series(id, o) : null);
