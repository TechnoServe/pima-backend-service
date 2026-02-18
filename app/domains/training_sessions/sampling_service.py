from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, case, cast, func, literal_column, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reflection import get_table


@dataclass
class WeeklySamplingResult:
    week_start: date
    week_end: date
    active_projects_considered: int
    skipped_projects_with_existing_samples: int
    sampled_sessions: int
    sampled_trainers: int


class TrainingSessionSamplingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def previous_week_window(reference_date: Optional[date] = None) -> tuple[date, date]:
        today = reference_date or date.today()
        current_week_monday = today - timedelta(days=today.weekday())
        previous_week_monday = current_week_monday - timedelta(days=7)
        previous_week_sunday = previous_week_monday + timedelta(days=6)
        return previous_week_monday, previous_week_sunday

    async def run_weekly_sampling(
        self,
        *,
        project_id: Optional[UUID] = None,
        reference_date: Optional[date] = None,
    ) -> WeeklySamplingResult:
        week_start, week_end = self.previous_week_window(reference_date)

        training_sessions = get_table("training_sessions")
        training_modules = get_table("training_modules")
        farmer_groups = get_table("farmer_groups")
        projects = get_table("projects")

        training_date = func.coalesce(
            training_sessions.c.date_session_1,
            training_sessions.c.date_session_2,
        )

        active_projects_stmt = (
            select(projects.c.id)
            .where(projects.c.status == "Active")
            .where(projects.c.is_deleted.is_(False) if "is_deleted" in projects.c else literal_column("TRUE"))
        )
        if project_id is not None:
            active_projects_stmt = active_projects_stmt.where(projects.c.id == project_id)

        active_project_ids = list((await self.db.execute(active_projects_stmt)).scalars().all())
        if not active_project_ids:
            return WeeklySamplingResult(
                week_start=week_start,
                week_end=week_end,
                active_projects_considered=0,
                skipped_projects_with_existing_samples=0,
                sampled_sessions=0,
                sampled_trainers=0,
            )

        base_join = (
            training_sessions.join(training_modules, training_sessions.c.module_id == training_modules.c.id)
            .join(farmer_groups, training_sessions.c.farmer_group_id == farmer_groups.c.id)
            .join(projects, farmer_groups.c.project_id == projects.c.id)
        )

        existing_samples_stmt = (
            select(func.count(func.distinct(projects.c.id)))
            .select_from(base_join)
            .where(projects.c.id.in_(active_project_ids))
            .where(training_sessions.c.sampled.is_(True))
            .where(cast(training_date, Date) >= week_start)
            .where(cast(training_date, Date) <= week_end)
        )
        skipped_projects_with_existing_samples = int((await self.db.execute(existing_samples_stmt)).scalar() or 0)

        candidate_project_ids_subquery = (
            select(projects.c.id)
            .select_from(base_join)
            .where(projects.c.id.in_(active_project_ids))
            .where(cast(training_date, Date) >= week_start)
            .where(cast(training_date, Date) <= week_end)
            .where(training_sessions.c.trainer_id.is_not(None))
            .group_by(projects.c.id)
            .having(func.sum(case((training_sessions.c.sampled.is_(True), 1), else_=0)) == 0)
            .subquery()
        )

        candidate_sessions = (
            select(
                training_sessions.c.id.label("id"),
                projects.c.id.label("project_id"),
                training_sessions.c.trainer_id.label("trainer_id"),
                func.row_number()
                .over(partition_by=(projects.c.id, training_sessions.c.trainer_id), order_by=func.random())
                .label("rn"),
            )
            .select_from(base_join)
            .where(projects.c.id.in_(select(candidate_project_ids_subquery.c.id)))
            .where(cast(training_date, Date) >= week_start)
            .where(cast(training_date, Date) <= week_end)
            .where(training_sessions.c.trainer_id.is_not(None))
            .where(training_sessions.c.sampled.is_(False))
            .subquery()
        )

        selected_ids = list(
            (
                await self.db.execute(
                    select(candidate_sessions.c.id, candidate_sessions.c.trainer_id).where(candidate_sessions.c.rn == 1)
                )
            ).all()
        )

        selected_session_ids = [row[0] for row in selected_ids]
        sampled_trainers = len(selected_ids)

        if selected_session_ids:
            values = {
                "sampled": True,
                "review_status": "not_reviewed",
            }
            if "updated_at" in training_sessions.c:
                values["updated_at"] = datetime.utcnow()

            await self.db.execute(
                update(training_sessions)
                .where(training_sessions.c.id.in_(selected_session_ids))
                .values(**values)
            )

        await self.db.commit()

        return WeeklySamplingResult(
            week_start=week_start,
            week_end=week_end,
            active_projects_considered=len(active_project_ids),
            skipped_projects_with_existing_samples=skipped_projects_with_existing_samples,
            sampled_sessions=len(selected_session_ids),
            sampled_trainers=sampled_trainers,
        )
