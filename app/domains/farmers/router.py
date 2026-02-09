from __future__ import annotations

import inspect
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

from app.auth.deps import get_current_user, require_project_access

from app.shared.domain_factory import build_crud_router
from app.shared.api_errors import DomainError
from .service import FarmersService, before_update

from .schemas import (
    PaginatedFarmersResponse,
    FarmersFilterOptions,
    FarmersSummaryResponse,
    UploadValidationResult,
    UploadJob,
    UploadHistoryResponse,
    RetryUploadRequest,
    FailedRow,
    SendToCommcareResponse,
)


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


crud_router = build_crud_router(
    entity="farmers",
    tags=["farmers"],
    require_project_scope=True,
    before_update=before_update,
)

farmers_ext_router = APIRouter(prefix="/projects/{project_id}/farmers", tags=["farmers"])


@farmers_ext_router.get("", response_model=PaginatedFarmersResponse)
async def list_farmers(
    project_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    search: str | None = None,
    gender: str | None = None,
    location_id: UUID | None = None,
    farmer_group_id: UUID | None = None,
    farmer_trainer_id: UUID | None = None,
    business_advisor_id: UUID | None = None,
    has_pending_commcare: bool | None = None,
    sort_by: str = Query("updated_at"),
    sort_order: str = Query("desc"),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    return await _service_call(FarmersService(db).list_farmers(
        project_id=project_id,
        page=page,
        page_size=page_size,
        search=search,
        gender=gender,
        location_id=location_id,
        farmer_group_id=farmer_group_id,
        farmer_trainer_id=farmer_trainer_id,
        business_advisor_id=business_advisor_id,
        has_pending_commcare=has_pending_commcare,
        sort_by=sort_by,
        sort_order=sort_order,
    ))


@farmers_ext_router.get("/summary", response_model=FarmersSummaryResponse)
async def farmers_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    return await _service_call(FarmersService(db).summary(project_id=project_id))


@farmers_ext_router.get("/filters", response_model=FarmersFilterOptions)
async def farmers_filters(
    project_id: UUID,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    return await _service_call(FarmersService(db).filter_options(project_id=project_id))


@farmers_ext_router.get("/export.xlsx")
async def export_farmers_excel(
    project_id: UUID,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    data = await _service_call(FarmersService(db).export_excel(project_id=project_id))

    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="participants_export_{project_id}.xlsx"'},
    )


@farmers_ext_router.post("/uploads/validate", response_model=UploadValidationResult)
async def validate_upload(
    project_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be .xlsx")
    content = await file.read()
    return await _service_call(FarmersService(db).validate_upload(file_bytes=content))


@farmers_ext_router.post("/uploads", response_model=UploadJob)
async def upload_changes(
    project_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be .xlsx")

    content = await file.read()
    return await _service_call(
        FarmersService(db).start_upload(
            project_id=project_id,
            file_name=file.filename,
            content_type=file.content_type,
            file_bytes=content,
            uploaded_by_id=user["id"],
        )
    )


@farmers_ext_router.get("/uploads/active", response_model=UploadJob | None)
async def active_upload(
    project_id: UUID,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    return await _service_call(FarmersService(db).active_upload(project_id=project_id))


@farmers_ext_router.get("/uploads/history", response_model=UploadHistoryResponse)
async def uploads_history(
    project_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    return await _service_call(FarmersService(db).upload_history(project_id=project_id, page=page, page_size=page_size))


@farmers_ext_router.get("/send-to-commcare/count")
async def pending_commcare_count(
    project_id: UUID,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    pending = await _service_call(FarmersService(db).pending_commcare_count(project_id=project_id))
    return {"pending": pending}


@farmers_ext_router.post("/send-to-commcare", response_model=SendToCommcareResponse)
async def send_to_commcare(
    project_id: UUID,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    flagged = await _service_call(FarmersService(db).send_to_commcare(project_id=project_id))
    return SendToCommcareResponse(flagged_count=flagged)


uploads_router = APIRouter(prefix="/farmers/uploads", tags=["farmers"])


@uploads_router.get("/{upload_id}", response_model=UploadJob)
async def get_upload(upload_id: UUID, db: AsyncSession = Depends(get_session), user=Depends(get_current_user)):
    svc = FarmersService(db)
    job = await _service_call(svc.get_upload_job(upload_id))
    await _maybe_await(require_project_access(db, user, job.project_id))
    return job


@uploads_router.get("/{upload_id}/failed-rows", response_model=list[FailedRow])
async def get_failed_rows(upload_id: UUID, db: AsyncSession = Depends(get_session), user=Depends(get_current_user)):
    svc = FarmersService(db)
    job = await _service_call(svc.get_upload_job(upload_id))
    await _maybe_await(require_project_access(db, user, job.project_id))
    return await _service_call(svc.failed_rows(upload_id))




@uploads_router.post("/{upload_id}/reupload", response_model=UploadJob)
async def reupload_file(
    upload_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be .xlsx")

    svc = FarmersService(db)
    parent = await _service_call(svc.get_upload_job(upload_id))
    await _maybe_await(require_project_access(db, user, parent.project_id))

    content = await file.read()
    return await _service_call(
        svc.reupload_to_run(
            upload_id=upload_id,
            file_name=file.filename,
            content_type=file.content_type,
            file_bytes=content,
            uploaded_by_id=user["id"],
        )
    )


@uploads_router.post("/{upload_id}/retry", response_model=UploadJob)
async def retry_failed(upload_id: UUID, body: RetryUploadRequest, db: AsyncSession = Depends(get_session), user=Depends(get_current_user)):
    svc = FarmersService(db)
    job = await _service_call(svc.get_upload_job(upload_id))
    # await _maybe_await(require_project_access(db, user, job.project_id))
    return await _service_call(svc.retry_upload(upload_id=upload_id, mode=body.mode))


router = APIRouter()
router.include_router(crud_router)
router.include_router(farmers_ext_router)
router.include_router(uploads_router)