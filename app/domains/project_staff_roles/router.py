from __future__ import annotations

import inspect
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.db.session import get_session
from app.shared.api_errors import DomainError

from .schemas import (
    ProjectStaffRoleCreate,
    ProjectStaffRoleFiltersResponse,
    ProjectStaffRoleItem,
    ProjectStaffRoleListResponse,
)
from .service import ProjectStaffRolesService


router = APIRouter(prefix="/project-staff-roles", tags=["project_staff_roles"])


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


@router.get("", response_model=ProjectStaffRoleListResponse)
async def list_project_staff_roles(
    user_id: UUID,
    status: str = Query("Active", pattern="^(Active|Inactive|All)$"),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await _service_call(ProjectStaffRolesService(db).list_roles(user_id=user_id, status=status))


@router.post("", response_model=ProjectStaffRoleItem)
async def create_project_staff_role(
    payload: ProjectStaffRoleCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await _service_call(ProjectStaffRolesService(db, _user).create_role(payload))


@router.patch("/{role_id}/deactivate", response_model=ProjectStaffRoleItem)
async def deactivate_project_staff_role(
    role_id: UUID,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await _service_call(ProjectStaffRolesService(db, _user).deactivate_role(role_id))


@router.get("/filters", response_model=ProjectStaffRoleFiltersResponse)
async def project_staff_role_filters(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    return await _service_call(ProjectStaffRolesService(db).filters())
