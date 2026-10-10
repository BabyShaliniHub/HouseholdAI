"""/api/v1: read-only dashboard API over the frozen ML output. All data comes from prediction_service."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from .errors import ApiError
from .prediction_service import LEVELS, service
from .schemas import (DashboardSummary, HealthV1, HouseholdDetailResponse, HouseholdSummary,
                      SeriesResponse, WarningDetail, WarningResponse)

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthV1)
def health():
    return {"status": "UP"}


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary():
    return service.summary()


@router.get("/warnings", response_model=list[WarningResponse])
def warnings(installation: str | None = None,
             risk_level: str | None = None,
             limit: Annotated[int | None, Query(ge=1, le=10000)] = None):
    if risk_level and risk_level.upper() not in LEVELS:
        raise ApiError(422, "INVALID_RISK_LEVEL", f"risk_level must be one of {', '.join(LEVELS)}.")
    return service.warnings(installation, risk_level, limit)


@router.get("/warnings/{warning_id}", response_model=WarningDetail)
def warning_detail(warning_id: str):
    found = service.warning(warning_id)
    if found is None:
        raise ApiError(404, "WARNING_NOT_FOUND", f"No warning with id '{warning_id}'.")
    return found


@router.get("/households", response_model=list[HouseholdSummary])
def households():
    return service.households()


@router.get("/households/{installation}", response_model=HouseholdDetailResponse)
def household_detail(installation: str, recent: Annotated[int, Query(ge=1, le=100)] = 10):
    found = service.household(installation, recent)
    if found is None:
        raise ApiError(404, "HOUSEHOLD_NOT_FOUND", f"No household '{installation}'.")
    return found


@router.get("/households/{installation}/series", response_model=SeriesResponse)
def household_series(installation: str, start: datetime | None = None, end: datetime | None = None,
                     max_points: Annotated[int, Query(ge=10, le=2000)] = 600):
    found = service.series(installation, start, end, max_points)
    if found is None:
        raise ApiError(404, "HOUSEHOLD_NOT_FOUND", f"No household '{installation}'.")
    return found
