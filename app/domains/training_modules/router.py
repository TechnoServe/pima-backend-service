from __future__ import annotations

import inspect
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_project_access
from app.auth.rbac import is_admin
from app.db.session import get_session
from app.shared.api_errors import DomainError
from app.shared.exceptions import Forbidden

from .schemas import (
    ChangeCurrentPreviousRequest,
    ChangeCurrentPreviousResponse,
    CreateTrainingModuleRequest,
    CreateTrainingModuleResponse,
    SendTrainingSessionsToCommCareResponse,
    TrainingModuleDetailsResponse,
    TrainingModulesListResponse,
)
from .service import TrainingModulesService

router = APIRouter(prefix="/training-modules", tags=["training_modules"])


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


def _require_super_admin(current_user: dict) -> None:
    if not is_admin(current_user.get("user_role")):
        raise Forbidden("Only Super Admin can perform this action")


@router.get("", response_model=TrainingModulesListResponse)
async def list_training_modules(
    project_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    search: str | None = None,
    status: str | None = None,
    current_previous: str | None = None,
    current_module: bool | None = None,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await _maybe_await(require_project_access(db, user, project_id))
    return await _service_call(
        TrainingModulesService(db).list_training_modules(
            project_id=project_id,
            page=page,
            page_size=page_size,
            search=search,
            status=status,
            current_previous=current_previous,
            current_module=current_module,
        )
    )


@router.get("/{module_id}", response_model=TrainingModuleDetailsResponse)
async def get_training_module_details(
    module_id: UUID,
    project_id: UUID | None = None,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    if project_id is not None:
        await _maybe_await(require_project_access(db, user, project_id))
    return await _service_call(
        TrainingModulesService(db).get_training_module_details(
            module_id=module_id,
            project_id=project_id,
            current_user=user,
        )
    )


@router.post("", response_model=CreateTrainingModuleResponse)
async def create_training_module(
    payload: CreateTrainingModuleRequest,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    _require_super_admin(user)
    return await _service_call(TrainingModulesService(db).create_training_module(payload=payload, current_user=user))


@router.patch("/{module_id}/current-previous", response_model=ChangeCurrentPreviousResponse)
async def change_current_previous(
    module_id: UUID,
    payload: ChangeCurrentPreviousRequest,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    _require_super_admin(user)
    return await _service_call(
        TrainingModulesService(db).change_current_previous(
            module_id=module_id,
            current_previous=payload.current_previous,
            current_user=user,
        )
    )


@router.post(
    "/{module_id}/send-training-sessions-to-commcare",
    response_model=SendTrainingSessionsToCommCareResponse,
)
async def send_training_sessions_to_commcare(
    module_id: UUID,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    _require_super_admin(user)
    return await _service_call(
        TrainingModulesService(db).send_training_sessions_to_commcare(module_id=module_id, current_user=user)
    )
