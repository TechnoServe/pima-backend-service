from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.api_errors import ConflictError, NotFoundError, ValidationError

from .repository import ProjectStaffRolesRepository
from .schemas import ProjectStaffRoleCreate


class ProjectStaffRolesService:
    def __init__(self, db: AsyncSession):
        self.repo = ProjectStaffRolesRepository(db)
        if self.repo.user_col is None:
            raise ValidationError("project_staff_roles table is missing user reference column")

    async def list_roles(self, *, user_id: UUID, status: str) -> dict:
        if status not in {"Active", "Inactive", "All"}:
            raise ValidationError("Invalid status", details={"allowed": ["Active", "Inactive", "All"]})
        rows = await self.repo.list_by_user(user_id=user_id, status=status)
        data = [
            {
                "id": r.get("id"),
                "user_id": r.get("user_id"),
                "project": {"id": r.get("project_id"), "name": r.get("project_name")},
                "role": r.get("role"),
                "status": r.get("status") or "Active",
                "created_at": r.get("created_at"),
            }
            for r in rows
        ]
        return {"data": data}

    async def create_role(self, payload: ProjectStaffRoleCreate) -> dict:
        active_dup = await self.repo.get_active_duplicate(
            user_id=payload.user_id,
            project_id=payload.project_id,
            role=payload.role,
        )
        if active_dup:
            raise ConflictError("Active project role already exists for this user/project/role")

        inactive_dup = await self.repo.get_inactive_duplicate(
            user_id=payload.user_id,
            project_id=payload.project_id,
            role=payload.role,
        )
        if inactive_dup:
            saved = await self.repo.reactivate_role(inactive_dup["id"])
        else:
            saved = await self.repo.create_role(
                user_id=payload.user_id,
                project_id=payload.project_id,
                role=payload.role,
            )

        return {
            "id": saved.get("id"),
            "user_id": saved.get("user_id") or saved.get("staff_id"),
            "project": {"id": saved.get("project_id"), "name": None},
            "role": saved.get("role") or saved.get("staff_role"),
            "status": saved.get("status"),
            "created_at": saved.get("created_at"),
        }

    async def deactivate_role(self, role_id: UUID) -> dict:
        existing = await self.repo.get_role(role_id)
        if not existing:
            raise NotFoundError("Project staff role not found")
        updated = await self.repo.deactivate_role(role_id)
        return {
            "id": updated.get("id"),
            "user_id": updated.get("user_id") or updated.get("staff_id"),
            "project": {"id": updated.get("project_id"), "name": None},
            "role": updated.get("role") or updated.get("staff_role"),
            "status": updated.get("status"),
            "created_at": updated.get("created_at"),
        }

    async def filters(self) -> dict:
        roles = await self.repo.distinct_roles()
        return {"roles": roles, "statuses": ["Active", "Inactive"]}
