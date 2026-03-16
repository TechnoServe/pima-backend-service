from __future__ import annotations

from sqlalchemy import and_, func, or_, select
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

    def _base_predicates(
        self,
        *,
        programme: str,
        country: str | None,
        search: str | None,
        exporting_status: str | None,
        mill_status: str | None,
    ):
        predicates = [
            self.wetmills.c.is_deleted.is_(False),
            self.wetmills.c.programme == programme,
        ]

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

        ownership_exists = "ownership_type" in self.wetmills.c

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

        if ownership_exists:
            cols.append(self.wetmills.c.ownership_type.label("ownership_type"))

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
        return rows, int(total), ownership_exists

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

        ownership_exists = "ownership_type" in self.wetmills.c

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

        if ownership_exists:
            cols.append(self.wetmills.c.ownership_type.label("ownership_type"))

        query = (
            select(*cols)
            .select_from(self.wetmills)
            .where(and_(*predicates))
            .order_by(self.wetmills.c.created_at.desc())
        )

        rows = list((await self.db.execute(query)).mappings().all())
        return rows, ownership_exists

    async def list_survey_export_payload(
        self,
        *,
        programme: str,
        country: str | None,
        search: str | None,
        exporting_status: str | None,
        mill_status: str | None,
        survey_type: str,
    ) -> list[dict]:
        wetmill_predicates = self._base_predicates(
            programme=programme,
            country=country,
            search=search,
            exporting_status=exporting_status,
            mill_status=mill_status,
        )

        user_display_col = (
            self.users.c.user_name
            if "user_name" in self.users.c
            else self.users.c.username
            if "username" in self.users.c
            else self.users.c.id
        )

        parent_query = (
            select(
                self.survey_responses.c.id.label("survey_response_id"),
                self.wetmills.c.name.label("wetmill_name"),
                self.wetmill_visits.c.visit_date.label("visit_date"),
                self.users.c.first_name.label("first_name"),
                self.users.c.last_name.label("last_name"),
                user_display_col.label("submitted_by"),
                self.survey_responses.c.completed_date.label("completed_date"),
                self.survey_responses.c.general_feedback.label("general_feedback"),
            )
            .select_from(self.survey_responses)
            .join(
                self.wetmill_visits,
                self.survey_responses.c.form_visit_id == self.wetmill_visits.c.id,
            )
            .join(
                self.wetmills,
                self.wetmill_visits.c.wetmill_id == self.wetmills.c.id,
            )
            .outerjoin(
                self.users,
                self.wetmill_visits.c.visiting_staff_id == self.users.c.id,
            )
            .where(
                and_(
                    *wetmill_predicates,
                    self.survey_responses.c.is_deleted.is_(False),
                    self.wetmill_visits.c.is_deleted.is_(False),
                    self.survey_responses.c.survey_type == survey_type,
                    self.wetmill_visits.c.visiting_staff_id.is_not(None),
                )
            )
            .order_by(self.survey_responses.c.id.asc())
        )

        parent_rows = list((await self.db.execute(parent_query)).mappings().all())
        if not parent_rows:
            return []

        response_ids = [row["survey_response_id"] for row in parent_rows]

        question_query = (
            select(
                self.survey_question_responses.c.survey_response_id.label("survey_response_id"),
                self.survey_question_responses.c.question_name.label("question_name"),
                self.survey_question_responses.c.value_text.label("value_text"),
                self.survey_question_responses.c.value_number.label("value_number"),
                self.survey_question_responses.c.value_boolean.label("value_boolean"),
                self.survey_question_responses.c.value_date.label("value_date"),
                func.ST_AsText(self.survey_question_responses.c.value_gps).label("value_gps"),
            )
            .select_from(self.survey_question_responses)
            .where(
                and_(
                    self.survey_question_responses.c.is_deleted.is_(False),
                    self.survey_question_responses.c.survey_response_id.in_(response_ids),
                )
            )
            .order_by(
                self.survey_question_responses.c.survey_response_id.asc(),
                self.survey_question_responses.c.question_name.asc(),
            )
        )

        question_rows = list((await self.db.execute(question_query)).mappings().all())

        questions_by_response: dict[str, list[dict]] = {}
        for row in question_rows:
            rid = row["survey_response_id"]
            if rid not in questions_by_response:
                questions_by_response[rid] = []
            questions_by_response[rid].append(dict(row))

        payload = []
        for parent in parent_rows:
            rid = parent["survey_response_id"]
            payload.append(
                {
                    "survey_response_id": rid,
                    "wetmill_name": parent.get("wetmill_name"),
                    "visit_date": parent.get("visit_date"),
                    "submitted_by": str(parent.get("first_name")) + ' ' + str(parent.get("last_name")),
                    "completed_date": parent.get("completed_date"),
                    "general_feedback": parent.get("general_feedback"),
                    "question_responses": questions_by_response.get(rid, []),
                }
            )

        return payload

    async def filter_options(self, *, programme: str, country: str | None) -> dict:
        predicates = [
            self.wetmills.c.is_deleted.is_(False),
            self.wetmills.c.programme == programme,
        ]

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

        ownership_types: list[str] = []
        if "ownership_type" in self.wetmills.c:
            trimmed = func.nullif(func.trim(self.wetmills.c.ownership_type), "")
            query = (
                select(trimmed.label("value"))
                .select_from(self.wetmills)
                .where(and_(*predicates))
                .where(trimmed.is_not(None))
                .group_by(trimmed)
                .order_by(trimmed.asc())
            )
            ownership_types = [
                row["value"]
                for row in (await self.db.execute(query)).mappings().all()
                if row["value"] is not None
            ]

        return {
            "countries": await distinct_values("country"),
            "exporting_statuses": await distinct_values("exporting_status"),
            "mill_statuses": await distinct_values("mill_status"),
            "ownership_types": ownership_types,
        }