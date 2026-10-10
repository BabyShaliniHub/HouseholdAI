"""HouseholdAI API. Serves only what the ML pipeline wrote to predictions.csv."""
from __future__ import annotations

import json
import math
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from . import insights as ins
from .errors import ApiError, api_error_handler, unexpected_error_handler
from .routes_v1 import router as v1_router
from .schemas import (AnomalyDetail, Health, HouseholdItem, Observation, Point, ProfileOut,
                      Warning, Summary)

RESULTS_DIR = Path(os.getenv("HOUSEHOLDAI_RESULTS", Path(__file__).resolve().parents[2] / "data/results"))
LEVEL_ORDER = {"NORMAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
HOUSEHOLD_RE = re.compile(r"^installation_\d+$")
RESOURCE = {"electricity": "Electricity", "water": "Water", "combined": "Electricity and water",
            "contextual": "Activity pattern"}


def load_results() -> tuple[pd.DataFrame | None, dict | None]:
    pred, report = RESULTS_DIR / "predictions.csv", RESULTS_DIR / "model_report.json"
    if not pred.exists() or not report.exists():
        return None, None
    df = pd.read_csv(pred, parse_dates=["ts_dt"]).sort_values(["installation", "ts_dt"]).reset_index(drop=True)
    df["is_anomaly"] = df["is_anomaly"].astype(bool)
    return df, json.loads(report.read_text())


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.df, app.state.report = load_results()
    yield


app = FastAPI(title="HouseholdAI API", version="1.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
                   allow_methods=["GET"], allow_headers=["*"])


app.include_router(v1_router)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)


def get_df(request: Request) -> pd.DataFrame:
    df = request.app.state.df
    if df is None:
        raise HTTPException(503, "ML results are not available. Run `python -m ml.pipeline` first.")
    return df


Df = Annotated[pd.DataFrame, Depends(get_df)]


def household_rows(df: pd.DataFrame, hid: str) -> pd.DataFrame:
    if not HOUSEHOLD_RE.match(hid) or hid not in set(df["installation"]):
        raise HTTPException(404, f"Unknown household '{hid}'.")
    return df[df["installation"] == hid]


def num(x) -> float | None:
    try:
        return None if x is None or not math.isfinite(float(x)) else float(x)
    except (TypeError, ValueError):
        return None


def label(hid: str) -> str:
    return f"Household {int(hid.split('_')[1]):02d}"


def window(rows: pd.DataFrame, start: datetime | None, end: datetime | None) -> pd.DataFrame:
    if start is not None:
        rows = rows[rows["ts_dt"] >= start]
    if end is not None:
        rows = rows[rows["ts_dt"] <= end]
    return rows


def observations(r: pd.Series) -> list[Observation]:
    out = []
    if r["problem_type"] in ("electricity", "combined", "contextual", "none"):
        out.append(Observation(resource="Electricity", unit="W", value=num(r["powerW"]), baseline=num(r["powerW_hour_baseline"])))
    if r["problem_type"] in ("water", "combined", "contextual", "none"):
        out.append(Observation(resource="Water flow", unit="", value=num(r["volumeFlow"]), baseline=num(r["volumeFlow_hour_baseline"])))
    return out


def to_warning(r: pd.Series) -> Warning:
    return Warning(id=r["anomaly_id"], household=r["installation"], household_label=label(r["installation"]),
                   ts=r["ts_dt"].isoformat(), risk_level=r["risk_level"], risk_index=num(r["risk_index"]),
                   problem_type=r["problem_type"], headline=r["headline"])


def to_detail(r: pd.Series, threshold: float) -> AnomalyDetail:
    return AnomalyDetail(**to_warning(r).model_dump(), resource=RESOURCE.get(r["problem_type"], "Household"),
                         observations=observations(r), anomaly_score=num(r["anomaly_score"]), threshold=threshold,
                         explanation=json.loads(r["explanation"]), recommendation=r["recommendation"],
                         is_anomaly=bool(r["is_anomaly"]))


def series(rows: pd.DataFrame, value_col: str, baseline_col: str) -> list[Point]:
    return [Point(id=r.anomaly_id, problem_type=r.problem_type, ts=r.ts_dt.isoformat(), value=num(getattr(r, value_col)),
                  baseline=num(getattr(r, baseline_col)), is_anomaly=bool(r.is_anomaly),
                  risk_level=r.risk_level, risk_index=num(r.risk_index))
            for r in rows.itertuples()]


# --------------------------------------------------------------------------- routes
@app.get("/api/health", response_model=Health)
def health(request: Request):
    ok = request.app.state.df is not None
    return Health(status="ok" if ok else "degraded", results_available=ok,
                  message=None if ok else "ML results not found. Run `python -m ml.pipeline`.")


@app.get("/api/model")
def model_report(request: Request):
    if request.app.state.report is None:
        raise HTTPException(503, "ML results are not available.")
    return request.app.state.report


@app.get("/api/households", response_model=list[HouseholdItem])
def households(df: Df):
    items = []
    for hid, rows in df.groupby("installation"):
        last = rows.iloc[-1]
        items.append(HouseholdItem(id=hid, label=label(hid), observations=len(rows),
                                   latest_risk_index=num(last["risk_index"]), latest_risk_level=last["risk_level"],
                                   anomalies=int(rows["is_anomaly"].sum()),
                                   max_risk_index=num(rows["risk_index"].max())))
    return sorted(items, key=lambda h: int(h.id.split("_")[1]))


@app.get("/api/households/{hid}/summary", response_model=Summary)
def summary(hid: str, df: Df, request: Request):
    rows = household_rows(df, hid)
    last = rows.iloc[-1]
    anomalies = rows[rows["is_anomaly"]]
    return Summary(
        id=hid, label=label(hid), first_ts=rows["ts_dt"].iloc[0].isoformat(), last_ts=last["ts_dt"].isoformat(),
        observations=len(rows), anomalies=len(anomalies),
        risk_index=num(last["risk_index"]), risk_level=last["risk_level"], headline=last["headline"],
        recommendation=last["recommendation"], explanation=json.loads(last["explanation"]),
        latest_power=num(last["powerW"]), power_baseline=num(last["powerW_hour_baseline"]),
        latest_flow=num(last["volumeFlow"]), flow_baseline=num(last["volumeFlow_hour_baseline"]),
        latest_temperature=num(last["temperature"]),
        temperature_available=bool(request.app.state.report.get("temperature_available")),
        latest_warning=to_warning(anomalies.iloc[-1]) if len(anomalies) else None)


@app.get("/api/households/{hid}/electricity", response_model=list[Point])
def electricity(hid: str, df: Df, start: datetime | None = None, end: datetime | None = None):
    return series(window(household_rows(df, hid), start, end), "powerW", "powerW_hour_baseline")


@app.get("/api/households/{hid}/water", response_model=list[Point])
def water(hid: str, df: Df, start: datetime | None = None, end: datetime | None = None):
    return series(window(household_rows(df, hid), start, end), "volumeFlow", "volumeFlow_hour_baseline")


def filter_levels(rows: pd.DataFrame, levels: str | None) -> pd.DataFrame:
    if not levels:
        return rows
    wanted = {x.strip().upper() for x in levels.split(",")}
    if not wanted <= set(LEVEL_ORDER):
        raise HTTPException(422, "levels must be a comma-separated subset of NORMAL, LOW, MEDIUM, HIGH.")
    return rows[rows["risk_level"].isin(wanted)]


@app.get("/api/households/{hid}/anomalies", response_model=list[Warning])
def household_anomalies(hid: str, df: Df, levels: str | None = None,
                        start: datetime | None = None, end: datetime | None = None):
    rows = window(household_rows(df, hid), start, end)
    rows = filter_levels(rows[rows["is_anomaly"]], levels)
    return [to_warning(r) for _, r in rows.iterrows()]


@app.get("/api/households/{hid}/risk")
def risk(hid: str, df: Df, start: datetime | None = None, end: datetime | None = None):
    rows = window(household_rows(df, hid), start, end)
    return [{"ts": r.ts_dt.isoformat(), "risk_index": num(r.risk_index), "risk_level": r.risk_level, "id": r.anomaly_id}
            for r in rows.itertuples()]


@app.get("/api/households/{hid}/profile", response_model=ProfileOut)
def profile(hid: str, df: Df):
    return ins.profile(hid, household_rows(df, hid), label(hid))


@app.get("/api/alerts", response_model=list[Warning])
def alerts(df: Df, household: str | None = None, levels: str | None = None,
           limit: Annotated[int, Query(ge=1, le=500)] = 50):
    rows = household_rows(df, household) if household else df
    rows = filter_levels(rows[rows["is_anomaly"]], levels).sort_values("ts_dt", ascending=False).head(limit)
    return [to_warning(r) for _, r in rows.iterrows()]


@app.get("/api/anomalies/{anomaly_id}", response_model=AnomalyDetail)
def anomaly(anomaly_id: str, df: Df, request: Request):
    hit = df[df["anomaly_id"] == anomaly_id]
    if hit.empty:
        raise HTTPException(404, f"Unknown observation '{anomaly_id}'.")
    return to_detail(hit.iloc[0], request.app.state.report["calibration"]["threshold"])


@app.get("/api/insights")
def insights(df: Df, household: str | None = None):
    if household:
        household_rows(df, household)
    return ins.generate(df, household)


@app.get("/api/compare")
def compare(df: Df):
    return ins.compare(df)


@app.get("/api/demo")
def demo(df: Df):
    """Guided tour built from real results: calm period -> top anomaly -> another household."""
    script = ins.demo_script(df)
    if script is None:
        raise HTTPException(404, "No anomalies were detected, so there is nothing to demonstrate.")
    return script
