from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reflection import get_table


class SustainabilityRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.wetmills = get_table("wetmills")
        self.wetmill_visits = get_table("wetmill_visits")

    def _ownership_column(self):
        for candidate in ("ownership_type", "ownership", "owner_type"):
            if candidate in self.wetmills.c:
                return self.wetmills.c[candidate]
        return None

    def _wetmills_predicates(self, *, programme: str, country: str | None):
        predicates = [self.wetmills.c.is_deleted.is_(False), self.wetmills.c.programme == programme]
        if country:
            predicates.append(self.wetmills.c.country == country)
        return predicates

    async def overview_counts(self, *, programme: str, country: str | None) -> tuple[int, int]:
        predicates = self._wetmills_predicates(programme=programme, country=country)

        total_q = select(func.count()).select_from(self.wetmills).where(*predicates)
        bas_q = (
            select(func.count(func.distinct(self.wetmills.c.user_id)))
            .select_from(self.wetmills)
            .where(*predicates)
            .where(self.wetmills.c.user_id.is_not(None))
        )

        total = (await self.db.execute(total_q)).scalar_one() or 0
        total_bas = (await self.db.execute(bas_q)).scalar_one() or 0
        return int(total), int(total_bas)

    async def visits_per_week(
        self,
        *,
        programme: str,
        country: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> list[dict]:
        week_start = func.date_trunc("week", self.wetmill_visits.c.visit_date).label("week_start")

        predicates = self._wetmills_predicates(programme=programme, country=country)
        predicates.extend([
            self.wetmill_visits.c.is_deleted.is_(False),
            self.wetmill_visits.c.wetmill_id == self.wetmills.c.id,
        ])
        if date_from:
            predicates.append(self.wetmill_visits.c.visit_date >= date_from)
        if date_to:
            predicates.append(self.wetmill_visits.c.visit_date <= date_to)

        query = (
            select(
                week_start,
                func.count(self.wetmill_visits.c.id).label("visits_count"),
            )
            .select_from(self.wetmill_visits.join(self.wetmills, self.wetmill_visits.c.wetmill_id == self.wetmills.c.id))
            .where(*predicates)
            .group_by(week_start)
            .order_by(week_start.asc())
        )
        return list((await self.db.execute(query)).mappings().all())

    async def exporter_distribution(self, *, programme: str, country: str | None) -> list[dict]:
        predicates = self._wetmills_predicates(programme=programme, country=country)

        status_expr = func.coalesce(func.nullif(func.trim(self.wetmills.c.exporting_status), ""), "Unknown").label("label")
        query = (
            select(status_expr, func.count(self.wetmills.c.id).label("value"))
            .select_from(self.wetmills)
            .where(*predicates)
            .group_by(status_expr)
            .order_by(status_expr.asc())
        )
        return list((await self.db.execute(query)).mappings().all())

    async def ownership_distribution(self, *, programme: str, country: str | None) -> list[dict]:
        ownership_col = self._ownership_column()
        if ownership_col is None:
            return []

        predicates = self._wetmills_predicates(programme=programme, country=country)
        ownership_expr = func.nullif(func.trim(ownership_col), "")
        query = (
            select(ownership_expr.label("label"), func.count(self.wetmills.c.id).label("value"))
            .select_from(self.wetmills)
            .where(*predicates)
            .where(ownership_expr.is_not(None))
            .group_by(ownership_expr)
            .order_by(ownership_expr.asc())
        )
        return list((await self.db.execute(query)).mappings().all())
