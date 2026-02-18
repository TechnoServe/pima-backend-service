from __future__ import annotations

import inspect
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_project_access
from app.db.session import get_session
from app.shared.api_errors import DomainError

from .schemas import (
    PaginatedTrainingSessionVerificationResponse,
    SubmitTrainingSessionReviewRequest,
    SubmitTrainingSessionReviewResponse,
    TrainingSessionVerificationStatsResponse,
)
from .service import DataVerificationService


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


router = APIRouter(prefix="/data-verification/training-sessions", tags=["data_verification"])


@router.get("", response_model=PaginatedTrainingSessionVerificationResponse)
async def list_training_sessions(
    project_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=10),
    review_status: str = Query("not_reviewed"),
    verdict: str = Query("all"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    trainer_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    service = DataVerificationService(db)
    
    
    print(f"Listing training sessions for project {project_id} with filters - page: {page}, page_size: {page_size}, review_status: {review_status}, verdict: {verdict}, date_from: {date_from}, date_to: {date_to}, trainer_id: {trainer_id}")
    return await _service_call(
        service.list_training_sessions(
            project_id=project_id,
            page=page,
            page_size=page_size,
            review_status=review_status,
            verdict=verdict,
            date_from=date_from,
            date_to=date_to,
            trainer_id=trainer_id,
        )
    )


@router.get("/stats", response_model=TrainingSessionVerificationStatsResponse)
async def training_sessions_stats(
    project_id: UUID,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    service = DataVerificationService(db)
    return await _service_call(service.stats(project_id=project_id))


@router.post("/{training_session_id}/review", response_model=SubmitTrainingSessionReviewResponse)
async def submit_training_session_review(
    training_session_id: UUID,
    payload: SubmitTrainingSessionReviewRequest,
    project_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    if project_id is not None:
        await _maybe_await(require_project_access(db, user, project_id))

    service = DataVerificationService(db)
    return await _service_call(
        service.submit_review(
            training_session_id=training_session_id,
            verdict=payload.verdict,
            reviewed=payload.reviewed,
            project_id=project_id,
        )
    )


@router.get("/image/{commcare_image_name}")
async def fetch_training_session_image(
    commcare_image_name: str,
    project_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    if project_id is not None:
        await _maybe_await(require_project_access(db, user, project_id))

    service = DataVerificationService(db)
    commcare_image_id = commcare_image_name.rsplit(".", 1)[0]
    payload, content_type = await _service_call(
        service.fetch_commcare_image(commcare_image_id=commcare_image_id, project_id=project_id)
    )
    return Response(content=payload, media_type=content_type)


@router.get("/export")
async def export_training_sessions(
    project_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=10),
    review_status: str = Query("not_reviewed"),
    verdict: str = Query("all"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    trainer_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    del page, page_size
    await _maybe_await(require_project_access(db, user, project_id))

    service = DataVerificationService(db)
    content = await _service_call(
        service.export_training_sessions_excel(
            project_id=project_id,
            review_status=review_status,
            verdict=verdict,
            date_from=date_from,
            date_to=date_to,
            trainer_id=trainer_id,
        )
    )

    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="training_sessions_verification_{project_id}.xlsx"'},
    )
