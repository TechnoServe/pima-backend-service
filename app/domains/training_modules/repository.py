from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import String, desc, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reflection import get_table
from app.domains.farmers.repository import col, name_expr


class TrainingModulesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.training_modules = get_table("training_modules")
        self.training_sessions = get_table("training_sessions")
        self.farmer_groups = get_table("farmer_groups")
        self.projects = get_table("projects")
        self.users = get_table("users")
        self.project_staff_roles = get_table("project_staff_roles")

    async def get_project(self, project_id: UUID) -> dict | None:
        stmt = select(self.projects).where(self.projects.c.id == project_id)
        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else None

    async def get_module_by_id(self, module_id: UUID) -> dict | None:
        stmt = select(self.training_modules).where(self.training_modules.c.id == module_id)
        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else None

    async def get_module_by_project_and_number(self, project_id: UUID, module_number: int) -> dict | None:
        stmt = select(self.training_modules).where(
            self.training_modules.c.project_id == project_id,
            self.training_modules.c.module_number == module_number,
        )
        if "is_deleted" in self.training_modules.c:
            stmt = stmt.where(self.training_modules.c.is_deleted.is_(False))
        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else None

    async def list_training_modules(
        self,
        *,
        project_id: UUID,
        page: int,
        page_size: int,
        search: str | None,
        status: str | None,
        current_previous: str | None,
        current_module: bool | None,
    ) -> tuple[list[dict], int]:
        tm = self.training_modules
        ts = self.training_sessions

        sessions_count_sq = (
            select(ts.c.module_id.label("module_id"), func.count().label("sessions_count"))
            .select_from(ts)
            .group_by(ts.c.module_id)
            .subquery()
        )

        stmt = (
            select(tm, func.coalesce(sessions_count_sq.c.sessions_count, 0).label("sessions_count"))
            .select_from(tm)
            .outerjoin(sessions_count_sq, sessions_count_sq.c.module_id == tm.c.id)
            .where(tm.c.project_id == project_id)
        )
        if "is_deleted" in tm.c:
            stmt = stmt.where(tm.c.is_deleted.is_(False))
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(tm.c.module_name.ilike(like), func.cast(tm.c.module_number, String).ilike(like)))
        if status:
            stmt = stmt.where(tm.c.status == status)
        if current_previous:
            stmt = stmt.where(tm.c.current_previous == current_previous)
        if current_module is not None:
            stmt = stmt.where(tm.c.current_module == current_module)

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(total_stmt)).scalar_one() or 0

        stmt = stmt.order_by(desc(tm.c.updated_at) if "updated_at" in tm.c else desc(tm.c.id))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(stmt)).mappings().all()
        return [dict(r) for r in rows], total

    async def get_module_details(self, module_id: UUID) -> dict | None:
        tm = self.training_modules
        ts = self.training_sessions

        sessions_count_sq = (
            select(ts.c.module_id.label("module_id"), func.count().label("sessions_count"))
            .select_from(ts)
            .group_by(ts.c.module_id)
            .subquery()
        )
        stmt = (
            select(tm, func.coalesce(sessions_count_sq.c.sessions_count, 0).label("sessions_count"))
            .select_from(tm)
            .outerjoin(sessions_count_sq, sessions_count_sq.c.module_id == tm.c.id)
            .where(tm.c.id == module_id)
        )
        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else None

    async def get_module_sessions(self, module_id: UUID) -> list[dict]:
        ts = self.training_sessions
        fg = self.farmer_groups
        users = self.users

        trainer_name = name_expr(users).label("trainer_name")
        farmer_group_name = col(fg, "ffg_name", "name", "group_name").label("farmer_group_name")

        stmt = (
            select(ts, farmer_group_name, trainer_name)
            .select_from(ts)
            .join(fg, fg.c.id == ts.c.farmer_group_id)
            .outerjoin(users, users.c.id == ts.c.trainer_id)
            .where(ts.c.module_id == module_id)
            .order_by(farmer_group_name.asc())
        )
        rows = (await self.db.execute(stmt)).mappings().all()
        return [dict(r) for r in rows]

    async def list_project_farmer_groups(self, project_id: UUID) -> list[dict]:
        fg = self.farmer_groups
        stmt = select(fg).where(fg.c.project_id == project_id)
        if "status" in fg.c:
            stmt = stmt.where(fg.c.status == "Active")
        if "is_deleted" in fg.c:
            stmt = stmt.where(fg.c.is_deleted.is_(False))
        rows = (await self.db.execute(stmt)).mappings().all()
        return [dict(r) for r in rows]

    async def create_module(self, data: dict) -> dict:
        filtered = {k: v for k, v in data.items() if k in self.training_modules.c}
        stmt = self.training_modules.insert().values(**filtered).returning(self.training_modules)
        row = (await self.db.execute(stmt)).mappings().one()
        return dict(row)

    async def existing_session_farmer_group_ids(self, module_id: UUID, farmer_group_ids: list[UUID]) -> set[UUID]:
        if not farmer_group_ids:
            return set()
        stmt = select(self.training_sessions.c.farmer_group_id).where(
            self.training_sessions.c.module_id == module_id,
            self.training_sessions.c.farmer_group_id.in_(farmer_group_ids),
        )
        return {r[0] for r in (await self.db.execute(stmt)).all()}

    async def create_training_sessions_for_module(self, *, module_id: UUID, sessions_payload: list[dict]) -> int:
        if not sessions_payload:
            return 0
        filtered_payload = [{k: v for k, v in row.items() if k in self.training_sessions.c} for row in sessions_payload]
        stmt = self.training_sessions.insert().values(filtered_payload)
        result = await self.db.execute(stmt)
        return result.rowcount or 0


    async def normalize_project_current_previous_for_current(
        self,
        *,
        project_id: UUID,
        current_user_id: UUID,
        exclude_module_id: UUID | None = None,
    ) -> None:
        values = {}
        if "current_previous" in self.training_modules.c:
            values["current_previous"] = None
        if "last_updated_by_id" in self.training_modules.c:
            values["last_updated_by_id"] = current_user_id
        if "updated_at" in self.training_modules.c:
            values["updated_at"] = datetime.now(timezone.utc)

        if values:
            clear_previous_stmt = update(self.training_modules).where(
                self.training_modules.c.project_id == project_id,
                self.training_modules.c.current_previous == "Previous",
            )
            if exclude_module_id is not None:
                clear_previous_stmt = clear_previous_stmt.where(self.training_modules.c.id != exclude_module_id)
            await self.db.execute(clear_previous_stmt.values(**values))

            set_previous_values = dict(values)
            set_previous_values["current_previous"] = "Previous"
            demote_current_stmt = update(self.training_modules).where(
                self.training_modules.c.project_id == project_id,
                self.training_modules.c.current_previous == "Current",
            )
            if exclude_module_id is not None:
                demote_current_stmt = demote_current_stmt.where(self.training_modules.c.id != exclude_module_id)
            await self.db.execute(demote_current_stmt.values(**set_previous_values))

    async def update_module_current_previous(self, module_id: UUID, current_previous: str | None, current_user_id: UUID) -> dict:
        values = {"current_previous": current_previous}
        if "last_updated_by_id" in self.training_modules.c:
            values["last_updated_by_id"] = current_user_id
        if "updated_at" in self.training_modules.c:
            values["updated_at"] = datetime.now(timezone.utc)
        stmt = (
            update(self.training_modules)
            .where(self.training_modules.c.id == module_id)
            .values(**values)
            .returning(self.training_modules)
        )
        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else {}

    async def mark_module_sessions_for_commcare(self, module_id: UUID, current_user_id: UUID) -> int:
        values = {}
        if "send_to_commcare" in self.training_sessions.c:
            values["send_to_commcare"] = True
        if "send_to_commcare_status" in self.training_sessions.c:
            values["send_to_commcare_status"] = "Pending"
        if "last_updated_by_id" in self.training_sessions.c:
            values["last_updated_by_id"] = current_user_id
        if not values:
            return 0
        stmt = (
            update(self.training_sessions)
            .where(self.training_sessions.c.module_id == module_id)
            .values(**values)
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def mark_project_roles_for_commcare(self, project_id: UUID, current_user_id: UUID) -> int:
        values = {}
        if "send_to_commcare" in self.project_staff_roles.c:
            values["send_to_commcare"] = True
        if "send_to_commcare_status" in self.project_staff_roles.c:
            values["send_to_commcare_status"] = "Pending"
        if "last_updated_by_id" in self.project_staff_roles.c:
            values["last_updated_by_id"] = current_user_id
        if not values:
            return 0
        stmt = (
            update(self.project_staff_roles)
            .where(self.project_staff_roles.c.project_id == project_id)
            .values(**values)
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    @staticmethod
    def build_module_create_data(payload: dict, current_user_id: UUID) -> dict:
        now = datetime.now(timezone.utc)
        module_id = uuid4()
        data = {
            "id": module_id,
            "project_id": payload["project_id"],
            "module_name": payload["module_name"],
            "module_number": payload["module_number"],
            "current_module": payload.get("current_module"),
            "sample_fv_aa_households": payload.get("sample_fv_aa_households"),
            "sample_fv_aa_households_status": payload.get("sample_fv_aa_households_status"),
            "status": payload.get("status"),
            "current_previous": payload.get("current_previous"),
            "module_date": payload.get("module_date"),
        }
        data["created_by_id"] = current_user_id
        data["last_updated_by_id"] = current_user_id
        data["created_at"] = now
        data["updated_at"] = now
        return data

    @staticmethod
    def build_training_session_create_data(
        *,
        module_id: UUID,
        farmer_group_id: UUID,
        trainer_id: UUID | None,
        current_user_id: UUID,
    ) -> dict:
        now = datetime.now(timezone.utc)
        session_id = uuid4()
        return {
            "id": session_id,
            "module_id": module_id,
            "farmer_group_id": farmer_group_id,
            # "trainer_id": trainer_id,
            "commcare_case_id": str(session_id),
            "send_to_commcare": True,
            "send_to_commcare_status": "New",
            "created_by_id": current_user_id,
            "last_updated_by_id": current_user_id,
            "created_at": now,
            "updated_at": now,
        }
