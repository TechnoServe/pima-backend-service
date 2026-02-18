from __future__ import annotations

import inspect
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.db.session import get_session
from app.shared.api_errors import DomainError

from .schemas import (
    UserDetailResponse,
    UsersCreate,
    UsersFiltersResponse,
    UsersListResponse,
    UsersStatsResponse,
    UsersUpdate,
)
from .service import UsersService


router = APIRouter(prefix="/users", tags=["users"])


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


@router.get("", response_model=UsersListResponse)
async def list_users(
    q: str | None = None,
    status: str | None = Query(None, pattern="^(Active|Inactive)$"),
    role: str | None = None,
    project_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    sort_by: str = Query("updated_at"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await _service_call(
        UsersService(db).list_users(
            q=q,
            status=status,
            role=role,
            project_id=project_id,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    )


@router.get("/stats", response_model=UsersStatsResponse)
async def users_stats(
    q: str | None = None,
    status: str | None = Query(None, pattern="^(Active|Inactive)$"),
    role: str | None = None,
    project_id: UUID | None = None,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await _service_call(UsersService(db).stats(q=q, status=status, role=role, project_id=project_id))


@router.get("/filters", response_model=UsersFiltersResponse)
async def users_filters(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await _service_call(UsersService(db).filters())


@router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await _service_call(UsersService(db).get_user(user_id))


@router.post("", response_model=UserDetailResponse)
async def create_user(
    payload: UsersCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await _service_call(UsersService(db).create_user(payload))


@router.patch("/{user_id}", response_model=UserDetailResponse)
async def update_user(
    user_id: UUID,
    payload: UsersUpdate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await _service_call(UsersService(db).update_user(user_id, payload))
