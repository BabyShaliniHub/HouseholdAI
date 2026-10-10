from __future__ import annotations

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    results_available: bool
    message: str | None = None


class HouseholdItem(BaseModel):
    id: str
    label: str
    observations: int
    latest_risk_index: float | None
    latest_risk_level: str
    anomalies: int
    max_risk_index: float | None


class Warning(BaseModel):
    id: str
    household: str
    household_label: str
    ts: str
    risk_level: str
    risk_index: float | None
    problem_type: str
    headline: str


class Observation(BaseModel):
    resource: str
    unit: str
    value: float | None
    baseline: float | None


class AnomalyDetail(Warning):
    resource: str
    observations: list[Observation]
    anomaly_score: float | None
    threshold: float
    explanation: list[str]
    recommendation: str
    is_anomaly: bool


class Point(BaseModel):
    id: str
    problem_type: str
    ts: str
    value: float | None
    baseline: float | None
    is_anomaly: bool
    risk_level: str
    risk_index: float | None


class Summary(BaseModel):
    id: str
    label: str
    first_ts: str
    last_ts: str
    observations: int
    anomalies: int
    risk_index: float | None
    risk_level: str
    headline: str
    recommendation: str
    explanation: list[str]
    latest_power: float | None
    power_baseline: float | None
    latest_flow: float | None
    flow_baseline: float | None
    latest_temperature: float | None
    temperature_available: bool
    latest_warning: Warning | None


class ProfileOut(BaseModel):
    id: str
    label: str
    power_normal_low: float | None
    power_normal_high: float | None
    water_active_share_pct: float | None
    water_typical_low: float | None
    water_typical_high: float | None
    power_active_hours: list[int]
    water_active_hours: list[int]
    anomalies: int
    anomaly_rate_pct: float
    risk_trend: list[dict]
    trend_direction: str
    recent_anomalies: list[Warning]


# ---------------------------------------------------------------- /api/v1 (read-only view of predictions.csv)
class ErrorResponse(BaseModel):
    error: str
    message: str


class HealthV1(BaseModel):
    status: str


class DashboardSummary(BaseModel):
    total_rows: int
    total_households: int
    statistical_anomalies: int
    actionable_warnings: int
    normal_count: int
    low_count: int
    medium_count: int
    high_count: int
    electricity_warnings: int
    water_warnings: int
    combined_warnings: int
    anomaly_percentage: float
    warning_percentage: float


class WarningResponse(BaseModel):
    id: str
    installation: str
    ts_dt: str
    powerW: float | None = None
    volumeFlow: float | None = None
    problem_type: str
    risk_level: str
    risk_score: float | None = None
    headline: str = ""
    explanation: list[str] = []
    recommendation: str = ""
    power_ev: float | None = None
    flow_ev: float | None = None
    flow_persistence_hours: float | None = None
    flow_meaningful_samples: int | None = None
    flow_abnormal: bool | None = None


class WarningDetail(WarningResponse):
    is_anomaly: bool = True
    anomaly_score: float | None = None
    persist_count: int | None = None
    flow_run: int | None = None
    hour: int | None = None
    power_baseline: float | None = None
    flow_baseline: float | None = None


class AnomalyItem(BaseModel):
    id: str
    installation: str
    ts_dt: str
    powerW: float | None = None
    volumeFlow: float | None = None
    problem_type: str
    risk_level: str
    risk_score: float | None = None
    headline: str = ""
    is_warning: bool


class HouseholdSummary(BaseModel):
    installation: str
    total_rows: int
    statistical_anomalies: int
    actionable_warnings: int
    normal_count: int
    low_count: int
    medium_count: int
    high_count: int
    electricity_warnings: int
    water_warnings: int
    combined_warnings: int
    average_power: float
    average_flow: float


class HouseholdDetailResponse(BaseModel):
    summary: HouseholdSummary
    recent_warnings: list[WarningResponse]
    recent_anomalies: list[AnomalyItem]


class SeriesPoint(BaseModel):
    id: str | None = None
    ts_dt: str
    powerW: float | None = None
    power_max: float | None = None
    volumeFlow: float | None = None
    flow_max: float | None = None
    power_baseline: float | None = None
    flow_baseline: float | None = None
    risk_score: float | None = None
    risk_level: str
    anomalies: int
    warnings: int
    n: int


class SeriesResponse(BaseModel):
    installation: str
    first_ts: str
    last_ts: str
    total_rows: int
    bucketed: bool
    points: list[SeriesPoint]
    markers: list[AnomalyItem]
    latest: WarningResponse
