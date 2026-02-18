from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, distinct, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.projects.models import table as projects_table

from .models import table as project_staff_roles_table


def maybe_col(tbl, *names: str):
    for n in names:
        if n in tbl.c:
            return tbl.c[n]
    return None


class ProjectStaffRolesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.psr = project_staff_roles_table()
        self.projects = projects_table()
        self.user_col = maybe_col(self.psr, "user_id", "staff_id")

    async def list_by_user(self, *, user_id: UUID, status: str | None) -> list[dict[str, Any]]:
        project_name_col = maybe_col(self.projects, "name", "project_name")
        created_col = maybe_col(self.psr, "created_at", "updated_at")
        role_col = maybe_col(self.psr, "role", "staff_role")

        stmt = (
            select(
                self.psr.c.id,
                self.user_col.label("user_id") if self.user_col is not None else literal(None).label("user_id"),
                self.projects.c.id.label("project_id"),
                (project_name_col.label("project_name") if project_name_col is not None else literal(None).label("project_name")),
                role_col.label("role") if role_col is not None else literal(None).label("role"),
                self.psr.c.status if "status" in self.psr.c else literal(None).label("status"),
                created_col.label("created_at") if created_col is not None else literal(None).label("created_at"),
            )
            .select_from(self.psr)
            .join(self.projects, self.projects.c.id == self.psr.c.project_id)
            .where(self.user_col == user_id)
            .order_by(desc(created_col) if created_col is not None else desc(self.psr.c.id))
        )
        if status and status != "All" and "status" in self.psr.c:
            stmt = stmt.where(self.psr.c.status == status)
        return [dict(r) for r in (await self.db.execute(stmt)).mappings().all()]

    async def get_active_duplicate(self, *, user_id: UUID, project_id: UUID, role: str) -> dict[str, Any] | None:
        role_col = maybe_col(self.psr, "role", "staff_role")
        stmt = select(self.psr).where(
            self.user_col == user_id,
            self.psr.c.project_id == project_id,
            role_col == role,
            self.psr.c.status == "Active",
        )
        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else None

    async def get_inactive_duplicate(self, *, user_id: UUID, project_id: UUID, role: str) -> dict[str, Any] | None:
        role_col = maybe_col(self.psr, "role", "staff_role")
        stmt = select(self.psr).where(
            self.user_col == user_id,
            self.psr.c.project_id == project_id,
            role_col == role,
            self.psr.c.status == "Inactive",
        )
        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else None

    async def create_role(self, *, user_id: UUID, project_id: UUID, role: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        role_col = maybe_col(self.psr, "role", "staff_role")
        data = {
            str(self.user_col.name): user_id,
            "project_id": project_id,
            str(role_col.name): role,
            "status": "Active",
        }
        if "created_at" in self.psr.c:
            data["created_at"] = now
        if "updated_at" in self.psr.c:
            data["updated_at"] = now
        stmt = self.psr.insert().values(**data).returning(self.psr)
        row = (await self.db.execute(stmt)).mappings().one()
        await self.db.commit()
        return dict(row)

    async def reactivate_role(self, role_id: UUID) -> dict[str, Any] | None:
        values = {"status": "Active"}
        if "updated_at" in self.psr.c:
            values["updated_at"] = datetime.now(timezone.utc)
        stmt = self.psr.update().where(self.psr.c.id == role_id).values(**values).returning(self.psr)
        row = (await self.db.execute(stmt)).mappings().first()
        await self.db.commit()
        return dict(row) if row else None

    async def deactivate_role(self, role_id: UUID) -> dict[str, Any] | None:
        values = {"status": "Inactive"}
        if "updated_at" in self.psr.c:
            values["updated_at"] = datetime.now(timezone.utc)
        stmt = self.psr.update().where(self.psr.c.id == role_id).values(**values).returning(self.psr)
        row = (await self.db.execute(stmt)).mappings().first()
        await self.db.commit()
        return dict(row) if row else None

    async def get_role(self, role_id: UUID) -> dict[str, Any] | None:
        stmt = select(self.psr).where(self.psr.c.id == role_id)
        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else None

    async def distinct_roles(self) -> list[str]:
        role_col = maybe_col(self.psr, "role", "staff_role")
        if role_col is None:
            return []
        stmt = select(distinct(role_col)).where(role_col.is_not(None)).order_by(role_col)
        return [r[0] for r in (await self.db.execute(stmt)).all() if r[0]]
