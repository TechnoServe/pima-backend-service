from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, case, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import alias

from app.db.reflection import get_table


def T(name: str):
    return get_table(name)


def col(tbl, *candidates: str):
    for c in candidates:
        if c in tbl.c:
            return tbl.c[c]
    raise KeyError(f"{tbl.name}: none of {candidates} found. Have: {list(tbl.c.keys())}")


def maybe_col(tbl, *candidates: str):
    for c in candidates:
        if c in tbl.c:
            return tbl.c[c]
    return None


def name_expr(users_tbl):
    first = maybe_col(users_tbl, "first_name", "firstname", "given_name")
    last = maybe_col(users_tbl, "last_name", "lastname", "family_name", "surname")

    if first is None and last is None:
        return literal(None)
    if first is None:
        return last
    if last is None:
        return first

    return func.trim(func.concat_ws(" ", first, last))


class DataVerificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _selected_image_id_expr(self, training_sessions, images):
        image_id_col = maybe_col(training_sessions, "image_id")
        if image_id_col is not None:
            return image_id_col

        order_col = maybe_col(images, "created_at", "updated_at")
        order_expr = order_col.desc() if order_col is not None else images.c.id.desc()

        if "training_session_id" in images.c:
            return (
                select(images.c.id)
                .where(images.c.training_session_id == training_sessions.c.id)
                .order_by(order_expr, images.c.id.desc())
                .limit(1)
                .scalar_subquery()
            )

        if "entity_id" in images.c:
            predicates = [images.c.entity_id == training_sessions.c.id]
            if "entity_type" in images.c:
                predicates.append(images.c.entity_type.in_(["training_session", "training_sessions"]))
            return (
                select(images.c.id)
                .where(and_(*predicates))
                .order_by(order_expr, images.c.id.desc())
                .limit(1)
                .scalar_subquery()
            )

        return literal(None)

    def _base_rows_query(self, project_id: UUID):
        training_sessions = T("training_sessions")
        training_modules = T("training_modules")
        users = T("users")
        images = T("images")

        trainer_alias = alias(users, name="trainer_user")

        module_name_col = col(training_modules, "module_name", "name", "title")
        trainer_name_col = name_expr(trainer_alias)
        training_date_col = maybe_col(training_sessions, "training_date", "session_date", "date")
        image_url_col = maybe_col(images, "url", "image_url", "public_url")
        image_verdict_col = maybe_col(images, "verdict", "review_verdict")
        image_object_name_col = maybe_col(images, "gcs_object_name", "object_name")

        selected_image_id = self._selected_image_id_expr(training_sessions, images)

        query = (
            select(
                training_sessions.c.id.label("id"),
                maybe_col(training_sessions, "sf_id").label("sf_id")
                if maybe_col(training_sessions, "sf_id") is not None
                else literal(None).label("sf_id"),
                maybe_col(training_sessions, "module_id").label("module_id")
                if maybe_col(training_sessions, "module_id") is not None
                else literal(None).label("module_id"),
                module_name_col.label("module_name"),
                maybe_col(training_sessions, "trainer_id").label("trainer_id")
                if maybe_col(training_sessions, "trainer_id") is not None
                else literal(None).label("trainer_id"),
                trainer_name_col.label("trainer_name"),
                training_date_col.label("training_date") if training_date_col is not None else literal(None).label("training_date"),
                maybe_col(training_sessions, "sampled").label("sampled")
                if maybe_col(training_sessions, "sampled") is not None
                else literal(False).label("sampled"),
                maybe_col(training_sessions, "review_status").label("review_status")
                if maybe_col(training_sessions, "review_status") is not None
                else literal("not_reviewed").label("review_status"),
                maybe_col(training_sessions, "total_attendance").label("total_attendance")
                if maybe_col(training_sessions, "total_attendance") is not None
                else literal(None).label("total_attendance"),
                maybe_col(training_sessions, "male_attendance").label("male_attendance")
                if maybe_col(training_sessions, "male_attendance") is not None
                else literal(None).label("male_attendance"),
                maybe_col(training_sessions, "female_attendance").label("female_attendance")
                if maybe_col(training_sessions, "female_attendance") is not None
                else literal(None).label("female_attendance"),
                images.c.id.label("image_id"),
                image_url_col.label("image_url") if image_url_col is not None else literal(None).label("image_url"),
                image_verdict_col.label("image_verdict") if image_verdict_col is not None else literal(None).label("image_verdict"),
                image_object_name_col.label("image_object_name") if image_object_name_col is not None else literal(None).label("image_object_name"),
            )
            .select_from(training_sessions)
            .join(training_modules, training_sessions.c.module_id == training_modules.c.id)
            .outerjoin(images, images.c.id == selected_image_id)
        )

        trainer_id_col = maybe_col(training_sessions, "trainer_id")
        if trainer_id_col is not None:
            query = query.outerjoin(trainer_alias, trainer_id_col == trainer_alias.c.id)

        if "project_id" in training_sessions.c:
            query = query.where(training_sessions.c.project_id == project_id)
        elif "project_id" in training_modules.c:
            query = query.where(training_modules.c.project_id == project_id)
        else:
            farmer_groups = T("farmer_groups")
            query = query.join(farmer_groups, training_sessions.c.farmer_group_id == farmer_groups.c.id)
            query = query.where(farmer_groups.c.project_id == project_id)

        is_deleted_col = maybe_col(training_sessions, "is_deleted")
        if is_deleted_col is not None:
            query = query.where(is_deleted_col.is_(False))

        return query

    async def list_training_sessions(self, *, project_id: UUID, page: int, page_size: int, review_status: str, verdict: str, date_from: Optional[date], date_to: Optional[date], trainer_id: Optional[UUID]) -> tuple[list[dict], int]:
        base = self._base_rows_query(project_id).subquery()
        filtered = select(base).where(base.c.sampled.is_(True))

        if review_status != "all":
            filtered = filtered.where(base.c.review_status == review_status)
        if verdict != "all":
            filtered = filtered.where(base.c.image_verdict == verdict)
        if trainer_id:
            filtered = filtered.where(base.c.trainer_id == trainer_id)
        if date_from:
            filtered = filtered.where(base.c.training_date >= date_from)
        if date_to:
            filtered = filtered.where(base.c.training_date <= date_to)

        total = (await self.db.execute(select(func.count()).select_from(filtered.subquery()))).scalar_one() or 0
        paged = filtered.order_by(base.c.training_date.desc().nullslast(), base.c.id.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(paged)).mappings().all()
        return list(rows), int(total)

    async def list_training_sessions_for_export(self, *, project_id: UUID, review_status: str, verdict: str, date_from: Optional[date], date_to: Optional[date], trainer_id: Optional[UUID]) -> list[dict]:
        base = self._base_rows_query(project_id).subquery()
        filtered = select(base).where(base.c.sampled.is_(True))

        if review_status != "all":
            filtered = filtered.where(base.c.review_status == review_status)
        if verdict != "all":
            filtered = filtered.where(base.c.image_verdict == verdict)
        if trainer_id:
            filtered = filtered.where(base.c.trainer_id == trainer_id)
        if date_from:
            filtered = filtered.where(base.c.training_date >= date_from)
        if date_to:
            filtered = filtered.where(base.c.training_date <= date_to)

        filtered = filtered.order_by(base.c.training_date.desc().nullslast(), base.c.id.desc())
        return list((await self.db.execute(filtered)).mappings().all())

    async def stats(self, *, project_id: UUID) -> dict:
        base = self._base_rows_query(project_id).subquery()
        stats_query = select(
            func.count().label("total_sampled"),
            func.sum(case((base.c.review_status == "reviewed", 1), else_=0)).label("total_reviewed"),
            func.sum(case((or_(base.c.review_status.is_(None), base.c.review_status != "reviewed"), 1), else_=0)).label("not_reviewed"),
            func.sum(case((base.c.image_verdict == "correct", 1), else_=0)).label("correct"),
            func.sum(case((base.c.image_verdict == "incorrect", 1), else_=0)).label("incorrect"),
            func.sum(case((base.c.image_verdict == "unclear", 1), else_=0)).label("unclear"),
        ).where(base.c.sampled.is_(True))

        row = (await self.db.execute(stats_query)).mappings().first()
        return {
            "total_sampled": int(row.get("total_sampled") or 0),
            "total_reviewed": int(row.get("total_reviewed") or 0),
            "not_reviewed": int(row.get("not_reviewed") or 0),
            "correct": int(row.get("correct") or 0),
            "incorrect": int(row.get("incorrect") or 0),
            "unclear": int(row.get("unclear") or 0),
        }

    async def get_training_session(self, training_session_id: UUID) -> Optional[dict]:
        training_sessions = T("training_sessions")
        row = (await self.db.execute(select(training_sessions).where(training_sessions.c.id == training_session_id))).mappings().first()
        return dict(row) if row else None

    async def get_selected_image_for_session(self, training_session_id: UUID) -> Optional[dict]:
        training_sessions = T("training_sessions")
        images = T("images")

        image_id_col = maybe_col(training_sessions, "image_id")
        if image_id_col is not None:
            session_image_id = (
                await self.db.execute(select(image_id_col).where(training_sessions.c.id == training_session_id))
            ).scalar_one_or_none()
            if session_image_id is not None:
                row = (await self.db.execute(select(images).where(images.c.id == session_image_id))).mappings().first()
                return dict(row) if row else None

        order_col = maybe_col(images, "created_at", "updated_at")
        order_expr = order_col.desc() if order_col is not None else images.c.id.desc()

        if "training_session_id" in images.c:
            row = (
                await self.db.execute(
                    select(images)
                    .where(images.c.training_session_id == training_session_id)
                    .order_by(order_expr, images.c.id.desc())
                    .limit(1)
                )
            ).mappings().first()
            return dict(row) if row else None

        if "entity_id" in images.c:
            predicates = [images.c.entity_id == training_session_id]
            if "entity_type" in images.c:
                predicates.append(images.c.entity_type.in_(["training_session", "training_sessions"]))

            row = (
                await self.db.execute(select(images).where(and_(*predicates)).order_by(order_expr, images.c.id.desc()).limit(1))
            ).mappings().first()
            return dict(row) if row else None

        return None

    async def get_training_session_project_id(self, training_session_id: UUID) -> Optional[UUID]:
        training_sessions = T("training_sessions")
        if "project_id" in training_sessions.c:
            return (
                await self.db.execute(select(training_sessions.c.project_id).where(training_sessions.c.id == training_session_id))
            ).scalar_one_or_none()

        farmer_groups = T("farmer_groups")
        return (
            await self.db.execute(
                select(farmer_groups.c.project_id)
                .select_from(training_sessions.join(farmer_groups, training_sessions.c.farmer_group_id == farmer_groups.c.id))
                .where(training_sessions.c.id == training_session_id)
            )
        ).scalar_one_or_none()

    async def mark_reviewed_and_update_image_verdict(self, *, training_session_id: UUID, image_id: UUID, verdict: str) -> None:
        training_sessions = T("training_sessions")
        images = T("images")

        await self.db.execute(update(training_sessions).where(training_sessions.c.id == training_session_id).values(review_status="reviewed"))

        image_verdict_col = maybe_col(images, "verdict", "review_verdict")
        if image_verdict_col is not None:
            await self.db.execute(update(images).where(images.c.id == image_id).values({image_verdict_col.name: verdict}))
