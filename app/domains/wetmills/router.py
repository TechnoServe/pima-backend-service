from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.auth.deps import get_current_user
from app.db.session import get_session
from .schemas import PaginatedWetmillsResponse, WetmillsFilterOptionsResponse
from .service import WetmillsService

router = APIRouter(tags=["wetmills"])


def _cleanup_file(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


@router.get("/wetmills", response_model=PaginatedWetmillsResponse)
async def list_wetmills(
    programme: str = Query(...),
    country: str | None = Query(None),
    search: str | None = Query(None),
    exporting_status: str | None = Query(None),
    mill_status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await WetmillsService(db).list_wetmills(
        programme=programme,
        country=country,
        search=search,
        exporting_status=exporting_status,
        mill_status=mill_status,
        page=page,
        page_size=page_size,
    )


@router.get("/wetmills/filter-options", response_model=WetmillsFilterOptionsResponse)
async def wetmills_filter_options(
    programme: str = Query(...),
    country: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await WetmillsService(db).filter_options(programme=programme, country=country)


@router.get("/wetmills/export/excel")
async def export_wetmills_excel(
    programme: str = Query(...),
    country: str | None = Query(None),
    search: str | None = Query(None),
    exporting_status: str | None = Query(None),
    mill_status: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    path = await WetmillsService(db).export_excel(
        programme=programme,
        country=country,
        search=search,
        exporting_status=exporting_status,
        mill_status=mill_status,
    )
    return FileResponse(
        path=path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="wetmills_export.xlsx",
        background=BackgroundTask(_cleanup_file, path),
    )


@router.get("/wetmills/export/csv")
async def export_wetmills_csv(
    programme: str = Query(...),
    country: str | None = Query(None),
    search: str | None = Query(None),
    exporting_status: str | None = Query(None),
    mill_status: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    path = await WetmillsService(db).export_csv(
        programme=programme,
        country=country,
        search=search,
        exporting_status=exporting_status,
        mill_status=mill_status,
    )
    return FileResponse(
        path=path,
        media_type="text/csv",
        filename="wetmills_export.csv",
        background=BackgroundTask(_cleanup_file, path),
    )