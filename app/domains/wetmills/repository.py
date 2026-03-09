from __future__ import annotations

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reflection import get_table
from .models import table


class WetmillsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.wetmills = table()
        self.wetmill_visits = get_table("wetmill_visits")
        self.survey_responses = get_table("wv_survey_responses")
        self.survey_question_responses = get_table("wv_survey_question_responses")
        self.users = get_table("users")

    @staticmethod
    def _maybe_col(tbl, *names: str):
        for name in names:
            if name in tbl.c:
                return tbl.c[name]
        return None

    def _ownership_column(self):
        for candidate in ("ownership_type", "ownership", "owner_type"):
            if candidate in self.wetmills.c:
                return self.wetmills.c[candidate]
        return None

    def _base_predicates(
        self,
        *,
        programme: str,
        country: str | None,
        exporting_status: str | None,
        mill_status: str | None,
        search: str | None,
    ):
        predicates = [self.wetmills.c.is_deleted.is_(False), self.wetmills.c.programme == programme]
        if country:
            predicates.append(self.wetmills.c.country == country)
        if exporting_status:
            predicates.append(self.wetmills.c.exporting_status == exporting_status)
        if mill_status:
            predicates.append(self.wetmills.c.mill_status == mill_status)
        if search:
            like = f"%{search.strip()}%"
            predicates.append(
                or_(
                    self.wetmills.c.wet_mill_unique_id.ilike(like),
                    self.wetmills.c.name.ilike(like),
                )
            )
        return predicates

    async def list_wetmills(
        self,
        *,
        programme: str,
        country: str | None,
        search: str | None,
        exporting_status: str | None,
        mill_status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int, bool]:
        predicates = self._base_predicates(
            programme=programme,
            country=country,
            search=search,
            exporting_status=exporting_status,
            mill_status=mill_status,
        )
        ownership_col = self._ownership_column()

        cols = [
            self.wetmills.c.id,
            self.wetmills.c.wet_mill_unique_id,
            self.wetmills.c.commcare_case_id,
            self.wetmills.c.name,
            self.wetmills.c.mill_status,
            self.wetmills.c.exporting_status,
            self.wetmills.c.programme,
            self.wetmills.c.country,
            self.wetmills.c.manager_name,
            self.wetmills.c.manager_role,
            self.wetmills.c.registration_date,
            self.wetmills.c.created_at,
            self.wetmills.c.updated_at,
        ]
        if ownership_col is not None:
            cols.append(ownership_col.label("ownership_type"))

        total_q = select(func.count()).select_from(self.wetmills).where(and_(*predicates))
        data_q = (
            select(*cols)
            .select_from(self.wetmills)
            .where(and_(*predicates))
            .order_by(self.wetmills.c.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        total = (await self.db.execute(total_q)).scalar_one() or 0
        rows = list((await self.db.execute(data_q)).mappings().all())
        return rows, int(total), ownership_col is not None

    async def list_for_export(
        self,
        *,
        programme: str,
        country: str | None,
        search: str | None,
        exporting_status: str | None,
        mill_status: str | None,
    ) -> tuple[list[dict], bool]:
        predicates = self._base_predicates(
            programme=programme,
            country=country,
            search=search,
            exporting_status=exporting_status,
            mill_status=mill_status,
        )
        ownership_col = self._ownership_column()
        cols = [
            self.wetmills.c.id,
            self.wetmills.c.wet_mill_unique_id,
            self.wetmills.c.name,
            self.wetmills.c.country,
            self.wetmills.c.programme,
            self.wetmills.c.exporting_status,
            self.wetmills.c.mill_status,
            self.wetmills.c.manager_name,
            self.wetmills.c.manager_role,
            self.wetmills.c.registration_date,
            self.wetmills.c.created_at,
            self.wetmills.c.updated_at,
        ]
        if ownership_col is not None:
            cols.append(ownership_col.label("ownership_type"))

        query = (
            select(*cols)
            .select_from(self.wetmills)
            .where(and_(*predicates))
            .order_by(self.wetmills.c.created_at.desc())
        )
        return list((await self.db.execute(query)).mappings().all()), ownership_col is not None

    async def list_survey_data_for_export(
        self,
        *,
        programme: str,
        country: str | None,
        search: str | None,
        exporting_status: str | None,
        mill_status: str | None,
        allowed_surveys: list[str],
    ) -> list[dict]:
        predicates = self._base_predicates(
            programme=programme,
            country=country,
            search=search,
            exporting_status=exporting_status,
            mill_status=mill_status,
        )

        survey_type_col = self._maybe_col(self.survey_responses, "survey_type", "form_name")
        form_visit_id_col = self._maybe_col(self.survey_responses, "form_visit_id", "wetmill_visit_id")
        survey_completed_col = self._maybe_col(self.survey_responses, "completed_date", "submitted_at", "created_at")
        survey_feedback_col = self._maybe_col(self.survey_responses, "general_feedback", "feedback", "comments")

        if survey_type_col is None or form_visit_id_col is None:
            return []

        question_name_col = self._maybe_col(self.survey_question_responses, "question_name")
        question_text_col = self._maybe_col(self.survey_question_responses, "value_text")
        question_number_col = self._maybe_col(self.survey_question_responses, "value_number")
        question_boolean_col = self._maybe_col(self.survey_question_responses, "value_boolean")
        question_date_col = self._maybe_col(self.survey_question_responses, "value_date")
        question_gps_col = self._maybe_col(self.survey_question_responses, "value_gps")

        survey_response_fk_col = self._maybe_col(
            self.survey_question_responses,
            "survey_response_id",
            "wv_survey_response_id",
            "response_id",
        )
        if question_name_col is None or survey_response_fk_col is None:
            return []

        visit_date_col = self._maybe_col(self.wetmill_visits, "visit_date")
        visit_id_col = self._maybe_col(self.wetmill_visits, "id")
        visit_user_id_col = self._maybe_col(self.wetmill_visits, "user_id")

        if visit_id_col is None:
            return []

        user_name_col = self._maybe_col(self.users, "user_name", "username", "name")

        query = (
            select(
                survey_type_col.label("survey_type"),
                self.wetmills.c.name.label("wetmill_name"),
                visit_date_col.label("visit_date") if visit_date_col is not None else literal(None).label("visit_date"),
                user_name_col.label("submitted_by") if user_name_col is not None else literal(None).label("submitted_by"),
                survey_completed_col.label("completed_date") if survey_completed_col is not None else literal(None).label("completed_date"),
                survey_feedback_col.label("general_feedback") if survey_feedback_col is not None else literal(None).label("general_feedback"),
                question_name_col.label("question_name"),
                question_text_col.label("value_text") if question_text_col is not None else literal(None).label("value_text"),
                question_number_col.label("value_number") if question_number_col is not None else literal(None).label("value_number"),
                question_boolean_col.label("value_boolean") if question_boolean_col is not None else literal(None).label("value_boolean"),
                question_date_col.label("value_date") if question_date_col is not None else literal(None).label("value_date"),
                question_gps_col.label("value_gps") if question_gps_col is not None else literal(None).label("value_gps"),
            )
            .select_from(self.survey_responses)
            .join(self.wetmill_visits, form_visit_id_col == visit_id_col)
            .join(self.wetmills, self.wetmills.c.id == self.wetmill_visits.c.wetmill_id)
            .outerjoin(
                self.survey_question_responses,
                survey_response_fk_col == self.survey_responses.c.id,
            )
            .where(and_(*predicates))
            .where(survey_type_col.in_(allowed_surveys))
            .where(self.survey_responses.c.is_deleted.is_(False))
            .where(self.wetmill_visits.c.is_deleted.is_(False))
            .order_by(survey_type_col.asc(), visit_date_col.asc() if visit_date_col is not None else self.survey_responses.c.created_at.asc())
        )
        if visit_user_id_col is not None and user_name_col is not None:
            query = query.outerjoin(self.users, visit_user_id_col == self.users.c.id)

        return list((await self.db.execute(query)).mappings().all())

    async def filter_options(self, *, programme: str, country: str | None) -> dict:
        predicates = [self.wetmills.c.is_deleted.is_(False), self.wetmills.c.programme == programme]
        if country:
            predicates.append(self.wetmills.c.country == country)

        async def distinct_values(column_name: str) -> list[str]:
            col = self.wetmills.c[column_name]
            trimmed = func.nullif(func.trim(col), "")
            query = (
                select(trimmed.label("value"))
                .select_from(self.wetmills)
                .where(and_(*predicates))
                .where(trimmed.is_not(None))
                .group_by(trimmed)
                .order_by(trimmed.asc())
            )
            rows = (await self.db.execute(query)).mappings().all()
            return [row["value"] for row in rows if row["value"] is not None]

        ownership_col = self._ownership_column()
        ownership_values: list[str] = []
        if ownership_col is not None:
            trimmed = func.nullif(func.trim(ownership_col), "")
            query = (
                select(trimmed.label("value"))
                .select_from(self.wetmills)
                .where(and_(*predicates))
                .where(trimmed.is_not(None))
                .group_by(trimmed)
                .order_by(trimmed.asc())
            )
            ownership_values = [row["value"] for row in (await self.db.execute(query)).mappings().all() if row["value"] is not None]

        return {
            "countries": await distinct_values("country"),
            "exporting_statuses": await distinct_values("exporting_status"),
            "mill_statuses": await distinct_values("mill_status"),
            "ownership_types": ownership_values,
        }
