from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, asc, case, desc, distinct, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.project_staff_roles.models import table as project_staff_roles_table
from app.domains.projects.models import table as projects_table

from .models import table as users_table


VALID_USER_SORTS = {"first_name", "last_name", "email", "role", "status", "updated_at", "created_at"}


def maybe_col(tbl, *names: str):
    for n in names:
        if n in tbl.c:
            return tbl.c[n]
    return None


class UsersRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.users = users_table()
        self.psr = project_staff_roles_table()
        self.projects = projects_table()

    def _active_psr_user_col(self):
        return maybe_col(self.psr, "user_id", "staff_id")

    def _updated_at(self):
        return maybe_col(self.users, "updated_at", "created_at")

    def _base_filters(self, *, q: str | None, status: str | None, role: str | None):
        filters = []
        if q:
            pattern = f"%{q.strip()}%"
            search_cols = [
                maybe_col(self.users, "first_name"),
                maybe_col(self.users, "last_name"),
                maybe_col(self.users, "email"),
                maybe_col(self.users, "phone_number"),
            ]
            predicates = [c.ilike(pattern) for c in search_cols if c is not None]
            if predicates:
                filters.append(or_(*predicates))
        if status and "status" in self.users.c:
            filters.append(self.users.c.status == status)
        if role and "role" in self.users.c:
            filters.append(self.users.c.role == role)
        return filters

    def _project_filter_exists(self, project_id: UUID):
        psr_user_col = self._active_psr_user_col()
        if psr_user_col is None:
            return literal(False)
        clauses = [psr_user_col == self.users.c.id, self.psr.c.project_id == project_id]
        if "status" in self.psr.c:
            clauses.append(self.psr.c.status == "Active")
        return exists(select(literal(1)).select_from(self.psr).where(and_(*clauses)))

    async def list_users(
        self,
        *,
        q: str | None,
        status: str | None,
        role: str | None,
        project_id: UUID | None,
        page: int,
        page_size: int,
        sort_by: str,
        sort_dir: str,
    ) -> dict[str, Any]:
        psr_user_col = self._active_psr_user_col()
        active_count_subq = (
            select(psr_user_col.label("user_id"), func.count(self.psr.c.id).label("active_project_roles_count"))
            .where(self.psr.c.status == "Active")
            .group_by(psr_user_col)
            .subquery()
            if psr_user_col is not None and "status" in self.psr.c
            else select(literal(None).label("user_id"), literal(0).label("active_project_roles_count")).where(literal(False)).subquery()
        )

        filters = self._base_filters(q=q, status=status, role=role)
        if project_id is not None:
            filters.append(self._project_filter_exists(project_id))

        total_stmt = select(func.count(self.users.c.id)).select_from(self.users)
        if filters:
            total_stmt = total_stmt.where(and_(*filters))
        total = int((await self.db.execute(total_stmt)).scalar_one() or 0)

        sort_col = self.users.c.get(sort_by) if sort_by in VALID_USER_SORTS and sort_by in self.users.c else self._updated_at()
        if sort_col is None:
            sort_col = self.users.c.id
        sort_expr = asc(sort_col) if sort_dir == "asc" else desc(sort_col)

        stmt = (
            select(
                self.users,
                func.coalesce(active_count_subq.c.active_project_roles_count, 0).label("active_project_roles_count"),
            )
            .select_from(self.users)
            .outerjoin(active_count_subq, active_count_subq.c.user_id == self.users.c.id)
            .order_by(sort_expr, self.users.c.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if filters:
            stmt = stmt.where(and_(*filters))

        rows = (await self.db.execute(stmt)).mappings().all()
        user_ids = [r["id"] for r in rows]

        active_projects_map: dict[UUID, list[dict[str, Any]]] = {uid: [] for uid in user_ids}
        if user_ids and psr_user_col is not None:
            project_name_col = maybe_col(self.projects, "name", "project_name")
            project_rows_stmt = (
                select(
                    psr_user_col.label("user_id"),
                    self.projects.c.id.label("project_id"),
                    project_name_col.label("project_name") if project_name_col is not None else literal(None).label("project_name"),
                )
                .select_from(self.psr)
                .join(self.projects, self.projects.c.id == self.psr.c.project_id)
                .where(psr_user_col.in_(user_ids), self.psr.c.status == "Active")
                .distinct(psr_user_col, self.projects.c.id)
                .order_by(psr_user_col, self.projects.c.id)
            )
            for row in (await self.db.execute(project_rows_stmt)).mappings().all():
                items = active_projects_map.setdefault(row["user_id"], [])
                if len(items) < 20:
                    items.append({"id": row["project_id"], "name": row["project_name"]})

        data = []
        for r in rows:
            obj = {k: v for k, v in r.items() if k in self.users.c}
            data.append(
                {
                    "id": obj.get("id"),
                    "first_name": obj.get("first_name"),
                    "last_name": obj.get("last_name"),
                    "email": obj.get("email"),
                    "phone_number": obj.get("phone_number"),
                    "role": obj.get("role"),
                    "status": obj.get("status"),
                    "active_project_roles_count": int(r.get("active_project_roles_count") or 0),
                    "active_projects": active_projects_map.get(obj.get("id"), []),
                    "updated_at": obj.get("updated_at"),
                }
            )

        return {
            "data": data,
            "pagination": {"page": page, "page_size": page_size, "total": total},
        }

    async def stats(
        self,
        *,
        q: str | None,
        status: str | None,
        role: str | None,
        project_id: UUID | None,
    ) -> dict[str, int]:
        filters = self._base_filters(q=q, status=status, role=role)
        if project_id is not None:
            filters.append(self._project_filter_exists(project_id))

        status_col = maybe_col(self.users, "status")
        base = select(self.users.c.id, (status_col.label("status") if status_col is not None else literal(None).label("status"))).select_from(self.users)
        if filters:
            base = base.where(and_(*filters))
        scoped_users = base.subquery()

        psr_user_col = self._active_psr_user_col()
        assigned_exists = (
            exists(
                select(literal(1)).select_from(self.psr).where(
                    and_(
                        psr_user_col == scoped_users.c.id,
                        self.psr.c.status == "Active",
                    )
                )
            )
            if psr_user_col is not None and "status" in self.psr.c
            else literal(False)
        )

        stmt = select(
            func.count(scoped_users.c.id).label("total"),
            func.sum(case((scoped_users.c.status == "Active", 1), else_=0)).label("active"),
            func.sum(case((scoped_users.c.status == "Inactive", 1), else_=0)).label("inactive"),
            func.sum(case((assigned_exists, 1), else_=0)).label("assigned_to_project"),
        )
        row = (await self.db.execute(stmt)).mappings().one()
        return {
            "total": int(row["total"] or 0),
            "active": int(row["active"] or 0),
            "inactive": int(row["inactive"] or 0),
            "assigned_to_project": int(row["assigned_to_project"] or 0),
        }

    async def get_user(self, user_id: UUID) -> dict[str, Any] | None:
        stmt = select(self.users).where(self.users.c.id == user_id)
        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else None

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        if "email" not in self.users.c:
            return None
        stmt = select(self.users).where(func.lower(self.users.c.email) == email.lower())
        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else None

    async def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        data = dict(payload)
        if "created_at" in self.users.c and "created_at" not in data:
            data["created_at"] = now
        if "updated_at" in self.users.c:
            data["updated_at"] = now
        stmt = self.users.insert().values(**data).returning(self.users)
        row = (await self.db.execute(stmt)).mappings().one()
        await self.db.commit()
        return dict(row)

    async def update_user(self, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any] | None:
        data = dict(payload)
        if "updated_at" in self.users.c:
            data["updated_at"] = datetime.now(timezone.utc)
        stmt = self.users.update().where(self.users.c.id == user_id).values(**data).returning(self.users)
        row = (await self.db.execute(stmt)).mappings().first()
        await self.db.commit()
        return dict(row) if row else None

    async def distinct_roles(self) -> list[str]:
        if "role" not in self.users.c:
            return []
        stmt = select(distinct(self.users.c.role)).where(self.users.c.role.is_not(None)).order_by(self.users.c.role)
        return [r[0] for r in (await self.db.execute(stmt)).all() if r[0]]
