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

    def _base_rows_query(self, project_id: UUID):
        training_sessions = T("training_sessions")
        training_modules = T("training_modules")
        users = T("users")
        images = T("images")

        trainer_alias = alias(users, name="trainer_user")

        module_name_col = col(training_modules, "module_name", "name", "title")
        trainer_name_col = name_expr(trainer_alias)
        training_date_col = maybe_col(training_sessions, "date_session_1")
        image_url_col = maybe_col(images, "image_url")
        image_verdict_col = maybe_col(images, "verdict")
        image_object_name_col = maybe_col(images, "gcs_object_name", "object_name")

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
                training_date_col.label("training_date"),
                maybe_col(training_sessions, "sampled").label("sampled")
                if maybe_col(training_sessions, "sampled") is not None
                else literal(False).label("sampled"),
                maybe_col(training_sessions, "review_status").label("review_status")
                if maybe_col(training_sessions, "review_status") is not None
                else literal("not_reviewed").label("review_status"),
                maybe_col(training_sessions, "total_attendees_session_1").label("total_attendance"),
                maybe_col(training_sessions, "male_attendees_session_1").label("male_attendance"),
                maybe_col(training_sessions, "female_attendees_session_1").label("female_attendance"),
                images.c.id.label("image_id"),
                image_url_col.label("image_url"),
                image_verdict_col.label("image_verdict"),
                image_object_name_col.label("image_object_name") if image_object_name_col is not None else literal(None).label("image_object_name"),
            )
            .select_from(training_sessions)
            .join(training_modules, training_sessions.c.module_id == training_modules.c.id)
            .outerjoin(images, images.c.image_reference_id == training_sessions.c.id)
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
        filtered = select(base).where(base.c.sampled.is_(True)).where(base.c.trainer_id != None)
        
        vals = await self.db.execute(
            select(base.c.review_status, func.count())
            .where(base.c.sampled.is_(True))
            .where(base.c.trainer_id != None)
            .group_by(base.c.review_status)
            .order_by(func.count().desc())
        )
        print(vals.all())
        
        total_sampled = (await self.db.execute(
            select(func.count()).select_from(base).where(base.c.sampled.is_(True))
        )).scalar_one()

        total_with_status = (await self.db.execute(
            select(func.count()).select_from(base)
            .where(base.c.sampled.is_(True))
            .where(base.c.review_status == review_status)
        )).scalar_one()

        total_null_status = (await self.db.execute(
            select(func.count()).select_from(base)
            .where(base.c.sampled.is_(True))
            .where(base.c.review_status.is_(None))
        )).scalar_one()

        print("sampled total:", total_sampled)
        print("status match:", total_with_status)
        print("status NULL:", total_null_status)
        
        print(filtered.where(base.c.review_status == review_status)
        .compile(compile_kwargs={"literal_binds": True}))
        
        print("-----------------------------------------------------------------")

        if review_status != "all":
            filtered = filtered.where(base.c.review_status == review_status)
        # if verdict != "all":
        #     filtered = filtered.where(base.c.image_verdict == verdict)
        if trainer_id:
            filtered = filtered.where(base.c.trainer_id == trainer_id)
        if date_from:
            filtered = filtered.where(base.c.training_date >= date_from)
        if date_to:
            filtered = filtered.where(base.c.training_date <= date_to)
            
        print("-----------------------------------------------------------------")
        print(f"Constructed SQL query for listing training sessions: {filtered}")

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

        image_id_col = maybe_col(training_sessions, "image_reference_id")
        if image_id_col is not None:
            session_image_id = (
                await self.db.execute(select(image_id_col).where(training_sessions.c.id == training_session_id))
            ).scalar_one_or_none()
            if session_image_id is not None:
                row = (await self.db.execute(select(images).where(images.c.id == session_image_id))).mappings().first()
                return dict(row) if row else None

        order_col = maybe_col(images, "created_at", "updated_at")
        order_expr = order_col.desc() if order_col is not None else images.c.id.desc()

        if "image_reference_id" in images.c:
            row = (
                await self.db.execute(
                    select(images)
                    .where(images.c.image_reference_id == training_session_id)
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

    async def get_image_by_commcare_image_id(self, *, commcare_image_id: str, project_id: Optional[UUID] = None) -> Optional[dict]:
        images = T("images")
        training_sessions = T("training_sessions")
        image_url_col = maybe_col(images, "image_url")
        if image_url_col is None:
            return None

        stmt = (
            select(images)
            .join(training_sessions, images.c.image_reference_id == training_sessions.c.id)
            .where(image_url_col.is_not(None))
            .where(image_url_col.ilike(f"%/{commcare_image_id}%"))
            .order_by(images.c.id.desc())
            .limit(1)
        )

        if project_id is not None:
            if "project_id" in training_sessions.c:
                stmt = stmt.where(training_sessions.c.project_id == project_id)
            else:
                farmer_groups = T("farmer_groups")
                stmt = stmt.join(farmer_groups, training_sessions.c.farmer_group_id == farmer_groups.c.id)
                stmt = stmt.where(farmer_groups.c.project_id == project_id)

        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else None

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

        image_verdict_col = maybe_col(images, "verdict")
        if image_verdict_col is not None:
            await self.db.execute(update(images).where(images.c.id == image_id)
                                  .values({image_verdict_col.name: verdict, images.c.verification_status: 'reviewed'}))

    async def project_exists(self, project_id: UUID) -> bool:
        projects = T("projects")
        exists_query = select(func.count()).select_from(projects).where(projects.c.id == project_id)
        total = (await self.db.execute(exists_query)).scalar_one() or 0
        return bool(total)

    async def training_group_belongs_to_project(self, project_id: UUID, training_group_id: UUID) -> bool:
        farmer_groups = T("farmer_groups")
        exists_query = (
            select(func.count())
            .select_from(farmer_groups)
            .where(farmer_groups.c.id == training_group_id)
            .where(farmer_groups.c.project_id == project_id)
        )
        total = (await self.db.execute(exists_query)).scalar_one() or 0
        return bool(total)

    async def get_latest_checks_for_attendance_cross_check(
        self,
        *,
        project_id: UUID,
        search: str | None,
        training_group_id: UUID | None,
        verification_source: str,
    ) -> list[dict]:
        checks = T("checks")
        farmers = T("farmers")
        farmer_groups = T("farmer_groups")
        training_sessions = T("training_sessions")
        training_modules = T("training_modules")

        created_at_col = maybe_col(checks, "created_at")
        date_completed_col = maybe_col(checks, "date_completed")
        order_by_columns = [
            date_completed_col.desc().nullslast() if date_completed_col is not None else checks.c.id.desc(),
            created_at_col.desc().nullslast() if created_at_col is not None else checks.c.id.desc(),
            checks.c.id.desc(),
        ]

        ranked_checks = (
            select(
                checks.c.id.label("check_id"),
                checks.c.farmer_id,
                checks.c.submission_id,
                checks.c.checker_id,
                checks.c.observation_id,
                checks.c.farm_visit_id,
                checks.c.training_session_id,
                maybe_col(checks, "date_completed").label("date_completed"),
                maybe_col(checks, "attended_trainings").label("attended_trainings"),
                maybe_col(checks, "number_of_trainings_attended").label("number_of_trainings_attended"),
                maybe_col(checks, "attended_last_months_training").label("attended_last_months_training"),
                maybe_col(checks, "check_type").label("check_type"),
                func.row_number().over(partition_by=checks.c.farmer_id, order_by=order_by_columns).label("rn"),
            )
            .select_from(checks)
            .join(training_sessions, checks.c.training_session_id == training_sessions.c.id)
            .join(farmer_groups, training_sessions.c.farmer_group_id == farmer_groups.c.id)
            .where(farmer_groups.c.project_id == project_id)
        ).subquery()

        query = (
            select(
                ranked_checks.c.check_id.label("id"),
                ranked_checks.c.farmer_id,
                ranked_checks.c.observation_id,
                ranked_checks.c.farm_visit_id,
                ranked_checks.c.training_session_id,
                ranked_checks.c.date_completed,
                ranked_checks.c.attended_trainings,
                ranked_checks.c.number_of_trainings_attended,
                ranked_checks.c.attended_last_months_training,
                ranked_checks.c.check_type,
                farmers.c.first_name,
                maybe_col(farmers, "middle_name").label("middle_name"),
                farmers.c.last_name,
                maybe_col(farmers, "tns_id").label("tns_id"),
                farmer_groups.c.id.label("training_group_id"),
                farmer_groups.c.ffg_name.label("training_group_name"),
                training_modules.c.id.label("training_module_id"),
                maybe_col(training_modules, "module_name").label("training_module_name"),
                maybe_col(training_modules, "module_number").label("training_module_number"),
            )
            .select_from(ranked_checks)
            .join(farmers, ranked_checks.c.farmer_id == farmers.c.id)
            .join(training_sessions, ranked_checks.c.training_session_id == training_sessions.c.id)
            .join(farmer_groups, training_sessions.c.farmer_group_id == farmer_groups.c.id)
            .outerjoin(training_modules, training_sessions.c.module_id == training_modules.c.id)
            .where(ranked_checks.c.rn == 1)
        )

        if training_group_id is not None:
            query = query.where(farmer_groups.c.id == training_group_id)

        trimmed = (search or "").strip()
        if trimmed:
            pattern = f"%{trimmed}%"
            search_conditions = [farmers.c.first_name.ilike(pattern), farmers.c.last_name.ilike(pattern)]
            middle_name_col = maybe_col(farmers, "middle_name")
            if middle_name_col is not None:
                search_conditions.append(middle_name_col.ilike(pattern))
            tns_id_col = maybe_col(farmers, "tns_id")
            if tns_id_col is not None:
                search_conditions.append(tns_id_col.ilike(pattern))
            query = query.where(
                or_(*search_conditions)
            )

        if verification_source == "farm_visit":
            query = query.where(ranked_checks.c.farm_visit_id.is_not(None))
        elif verification_source == "training_observation":
            query = query.where(ranked_checks.c.observation_id.is_not(None)).where(ranked_checks.c.farm_visit_id.is_(None))
        elif verification_source == "none":
            query = query.where(ranked_checks.c.farm_visit_id.is_(None)).where(ranked_checks.c.observation_id.is_(None))

        query = query.order_by(farmers.c.last_name.asc().nullslast(), farmers.c.first_name.asc().nullslast(), ranked_checks.c.check_id.asc())
        return list((await self.db.execute(query)).mappings().all())

    async def get_attendance_evidence_for_farmers(
        self,
        *,
        project_id: UUID,
        farmer_ids: list[UUID],
    ) -> dict[UUID, list[dict]]:
        if not farmer_ids:
            return {}

        attendances = T("attendances")
        training_sessions = T("training_sessions")
        training_modules = T("training_modules")
        farmer_groups = T("farmer_groups")

        training_date_expr = func.coalesce(
            maybe_col(attendances, "date_attended"),
            maybe_col(training_sessions, "date_session_1"),
            maybe_col(training_sessions, "date_session_2"),
        )

        query = (
            select(
                attendances.c.farmer_id,
                attendances.c.id.label("attendance_id"),
                attendances.c.training_session_id,
                training_date_expr.label("training_date"),
                training_modules.c.id.label("module_id"),
                maybe_col(training_modules, "module_name").label("module_name"),
                maybe_col(training_modules, "module_number").label("module_number"),
                maybe_col(training_modules, "current_previous").label("current_previous"),
                maybe_col(attendances, "status").label("status"),
            )
            .select_from(attendances)
            .join(training_sessions, attendances.c.training_session_id == training_sessions.c.id)
            .join(farmer_groups, training_sessions.c.farmer_group_id == farmer_groups.c.id)
            .outerjoin(training_modules, training_sessions.c.module_id == training_modules.c.id)
            .where(farmer_groups.c.project_id == project_id)
            .where(attendances.c.farmer_id.in_(farmer_ids))
            .order_by(training_date_expr.asc().nullslast(), maybe_col(training_modules, "module_number").asc().nullslast(), attendances.c.id.asc())
        )

        rows = list((await self.db.execute(query)).mappings().all())
        grouped: dict[UUID, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["farmer_id"], []).append(dict(row))
        return grouped
