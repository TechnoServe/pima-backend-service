from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, cast, func, literal_column, select, update
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
        week_start = current_week_monday - timedelta(days=7)
        week_end = week_start + timedelta(days=6)
        return week_start, week_end

    async def run_weekly_sampling(
        self,
        *,
        project_id: Optional[UUID] = None,
        reference_date: Optional[date] = None,
    ) -> WeeklySamplingResult:
        week_start, week_end = self.previous_week_window(reference_date)

        projects = get_table("projects")
        project_staff_roles = get_table("project_staff_roles")
        training_sessions = get_table("training_sessions")
        farmer_groups = get_table("farmer_groups")

        training_date = training_sessions.c.date_session_1

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

        skipped_projects = 0
        sampled_session_ids: list[UUID] = []
        sampled_trainer_ids: set[UUID] = set()

        for pid in active_project_ids:
            any_sampled_stmt = (
                select(func.count())
                .select_from(
                    training_sessions.join(farmer_groups, training_sessions.c.farmer_group_id == farmer_groups.c.id)
                )
                .where(farmer_groups.c.project_id == pid)
                .where(training_sessions.c.sampled.is_(True))
                .where(cast(training_date, Date) >= week_start)
                .where(cast(training_date, Date) <= week_end)
            )
            any_sampled = int((await self.db.execute(any_sampled_stmt)).scalar() or 0) > 0
            if any_sampled:
                skipped_projects += 1
                continue

            trainer_ids_stmt = (
                select(func.distinct(project_staff_roles.c.staff_id))
                .where(project_staff_roles.c.project_id == pid)
                .where(project_staff_roles.c.status == "Active")
            )
            trainer_ids = list((await self.db.execute(trainer_ids_stmt)).scalars().all())
            if not trainer_ids:
                print(f"No active trainers found for project {pid}, skipping sampling")
                continue

            for trainer_id in trainer_ids:
                print("processing for trainer ", trainer_id)
                pick_one_stmt = (
                    select(training_sessions.c.id)
                    .select_from(
                        training_sessions.join(farmer_groups, training_sessions.c.farmer_group_id == farmer_groups.c.id)
                    )
                    .where(farmer_groups.c.project_id == pid)
                    .where(training_sessions.c.trainer_id == trainer_id)
                    .where(training_sessions.c.sampled.is_(False))
                    .where(training_date >= week_start)
                    .where(training_date <= week_end)
                    .order_by(func.random())
                    .limit(1)
                )
            
                session_id = (await self.db.execute(pick_one_stmt)).scalar_one_or_none()
                
                print("picked session id ", session_id)
                if session_id is None:
                    continue

                sampled_session_ids.append(session_id)
                sampled_trainer_ids.add(trainer_id)

        if sampled_session_ids:
            values = {"sampled": True, "review_status": "not_reviewed"}
            if "updated_at" in training_sessions.c:
                values["updated_at"] = datetime.utcnow()

            await self.db.execute(
                update(training_sessions)
                .where(training_sessions.c.id.in_(sampled_session_ids))
                .values(**values)
            )

        await self.db.commit()

        return WeeklySamplingResult(
            week_start=week_start,
            week_end=week_end,
            active_projects_considered=len(active_project_ids),
            skipped_projects_with_existing_samples=skipped_projects,
            sampled_sessions=len(sampled_session_ids),
            sampled_trainers=len(sampled_trainer_ids),
        )