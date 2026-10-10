import type { DashboardSummary, HouseholdDetail, HouseholdSummary } from "../lib/api";
import type { Range } from "../components/HouseholdPulse";
import type { Selection } from "../components/WarningDrawer";

/** Everything a view needs about the selected home. */
export interface Ctx {
  home: string;
  homes: HouseholdSummary[];
  detail: HouseholdDetail;
  summary: DashboardSummary;
  range: Range | null;
  setRange: (r: Range | null) => void;
  setHome: (id: string) => void;
  selectedId: string | null;
  open: (s: Selection) => void;
  go: (view: string) => void;
}
