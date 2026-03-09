from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.db.session import get_session
from .schemas import (
    DistributionResponse,
    SustainabilitySummaryOverviewResponse,
    WetmillVisitsPerWeekResponse,
)
from .service import SustainabilityService

router = APIRouter(prefix="/sustainability", tags=["sustainability"])


@router.get("/summary/overview", response_model=SustainabilitySummaryOverviewResponse)
async def summary_overview(
    programme: str = Query(...),
    country: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await SustainabilityService(db).overview(programme=programme, country=country)


@router.get("/summary/wetmill-visits-per-week", response_model=WetmillVisitsPerWeekResponse)
async def wetmill_visits_per_week(
    programme: str = Query(...),
    country: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await SustainabilityService(db).wetmill_visits_per_week(
        programme=programme,
        country=country,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/summary/ownership-distribution", response_model=DistributionResponse)
async def ownership_distribution(
    programme: str = Query(...),
    country: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await SustainabilityService(db).ownership_distribution(programme=programme, country=country)


@router.get("/summary/exporter-status-distribution", response_model=DistributionResponse)
async def exporter_status_distribution(
    programme: str = Query(...),
    country: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await SustainabilityService(db).exporter_status_distribution(programme=programme, country=country)
