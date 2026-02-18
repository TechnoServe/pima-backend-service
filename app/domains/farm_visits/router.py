from __future__ import annotations

import inspect
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_project_access
from app.db.session import get_session
from app.shared.api_errors import DomainError
from app.shared.domain_factory import build_crud_router

from .schemas import FarmVisitsFiltersResponse, FarmVisitsListParams, FarmVisitsListResponse, FarmVisitsStatsResponse
from .service import FarmVisitsService


async def _maybe_await(x):
    if inspect.isawaitable(x):
        return await x
    return x


async def _service_call(call):
    try:
        return await _maybe_await(call)
    except DomainError as exc:
        detail = {"code": exc.code, "message": exc.message}
        if exc.details:
            detail["details"] = exc.details
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc


crud_router = build_crud_router(entity="farm_visits", tags=["farm_visits"], require_project_scope=False)
field_visits_router = APIRouter(prefix="/field-visits/farm-visits", tags=["farm_visits"])


@field_visits_router.get("", response_model=FarmVisitsListResponse)
async def list_farm_visits(
    project_id: UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    farm_visit_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    sort_by: str = Query("date_visited"),
    sort_dir: str = Query("desc"),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    params = FarmVisitsListParams(
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        farm_visit_type=farm_visit_type,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return await _service_call(FarmVisitsService(db).list_farm_visits(params))


@field_visits_router.get("/stats", response_model=FarmVisitsStatsResponse)
async def farm_visits_stats(
    project_id: UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    farm_visit_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    return await _service_call(
        FarmVisitsService(db).stats(
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
            farm_visit_type=farm_visit_type,
            search=search,
        )
    )


@field_visits_router.get("/filters", response_model=FarmVisitsFiltersResponse)
async def farm_visits_filters(
    project_id: UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    farm_visit_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    return await _service_call(
        FarmVisitsService(db).filter_options(
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
            farm_visit_type=farm_visit_type,
            search=search,
        )
    )


@field_visits_router.get("/export.xlsx")
async def export_farm_visits(
    project_id: UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    farm_visit_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str = Query("date_visited"),
    sort_dir: str = Query("desc"),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    service = FarmVisitsService(db)
    params = FarmVisitsListParams(
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        farm_visit_type=farm_visit_type,
        search=search,
        page=1,
        page_size=100000,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    data = await _service_call(service.export_excel(params))
    filename = service.export_filename(project_id)
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


router = APIRouter()
router.include_router(crud_router)
router.include_router(field_visits_router)
