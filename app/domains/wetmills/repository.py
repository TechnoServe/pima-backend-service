from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import table


class WetmillsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.wetmills = table()

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
