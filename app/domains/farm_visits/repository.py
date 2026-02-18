from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reflection import get_table


def T(name: str):
    return get_table(name)


def maybe_col(tbl, *names: str):
    for name in names:
        if name in tbl.c:
            return tbl.c[name]
    return None


def full_name_expr(tbl):
    first = maybe_col(tbl, "first_name", "firstname", "given_name")
    middle = maybe_col(tbl, "middle_name", "middlename")
    last = maybe_col(tbl, "last_name", "lastname", "family_name", "surname")
    parts = [p for p in (first, middle, last) if p is not None]
    return func.trim(func.concat_ws(" ", *parts)) if parts else literal("")


@dataclass
class FarmVisitFilters:
    project_id: UUID
    date_from: date | None = None
    date_to: date | None = None
    farm_visit_type: str | None = None
    search: str | None = None


class FarmVisitsRepository:
    SORT_ALLOWLIST = {
        "date_visited",
        "training_group_name",
        "farmer_full_name",
        "farmer_tns_id",
        "visiting_staff_name",
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.fv = T("farm_visits")
        self.fg = T("farmer_groups")
        self.farmers = T("farmers")
        self.users = T("users")
        self.households = T("households")

    def _columns_and_from(self):
        hh_farmer_group_id = maybe_col(self.households, "farmer_group_id")

        fv_primary_farmer_id = maybe_col(self.fv, "visited_primary_farmer_id", "farmer_id")
        fv_visiting_staff_id = maybe_col(self.fv, "visiting_staff_id", "staff_id", "user_id")

        from_expr = (
            self.fv.outerjoin(self.households, self.fv.c.visited_household_id == self.households.c.id)
            .outerjoin(self.fg, hh_farmer_group_id == self.fg.c.id)
        )

        if fv_primary_farmer_id is not None:
            from_expr = from_expr.outerjoin(self.farmers, fv_primary_farmer_id == self.farmers.c.id)

        if fv_visiting_staff_id is not None:
            from_expr = from_expr.outerjoin(self.users, fv_visiting_staff_id == self.users.c.id)

        date_col = maybe_col(self.fv, "date_visited", "visit_date", "created_at")
        group_name = maybe_col(self.fg, "name", "farmer_group_name")
        farmer_tns_id = maybe_col(self.farmers, "tns_id", "sf_id")
        farmer_name = full_name_expr(self.farmers)
        staff_name = full_name_expr(self.users)

        cols = {
            "id": self.fv.c.id,
            "date_visited": date_col,
            "farm_visit_type": maybe_col(self.fv, "farm_visit_type"),
            "visit_comments": maybe_col(self.fv, "visit_comments", "comments"),
            "location_gps_latitude": maybe_col(self.fv, "location_gps_latitude", "gps_latitude"),
            "location_gps_longitude": maybe_col(self.fv, "location_gps_longitude", "gps_longitude"),
            "location_gps_altitude": maybe_col(self.fv, "location_gps_altitude", "gps_altitude"),
            "number_of_cuerdas": maybe_col(self.fv, "number_of_cuerdas"),
            "number_of_separate_coffee_fields": maybe_col(self.fv, "number_of_separate_coffee_fields"),
            "field_age": maybe_col(self.fv, "field_age"),
            "field_size": maybe_col(self.fv, "field_size"),
            "training_group_name": group_name,
            "farmer_tns_id": farmer_tns_id,
            "farmer_full_name": farmer_name,
            "farmer_gender": maybe_col(self.farmers, "gender"),
            "visiting_staff_name": staff_name,
            "group_project_id": maybe_col(self.fg, "project_id"),
            "primary_farmer_id": fv_primary_farmer_id,
        }
        return from_expr, cols

    def _apply_filters(self, stmt, filters: FarmVisitFilters, cols: dict):
        if cols.get("group_project_id") is not None:
            pass 
            #stmt = stmt.where(cols["group_project_id"] == filters.project_id)

        if filters.date_from and cols["date_visited"] is not None:
            stmt = stmt.where(func.date(cols["date_visited"]) >= filters.date_from)

        if filters.date_to and cols["date_visited"] is not None:
            stmt = stmt.where(func.date(cols["date_visited"]) <= filters.date_to)

        if filters.farm_visit_type and cols["farm_visit_type"] is not None:
            stmt = stmt.where(cols["farm_visit_type"] == filters.farm_visit_type)

        if filters.search:
            q = f"%{filters.search.strip()}%"
            predicates = []

            if cols["farmer_full_name"] is not None:
                predicates.append(cols["farmer_full_name"].ilike(q))
            if cols["visiting_staff_name"] is not None:
                predicates.append(cols["visiting_staff_name"].ilike(q))
            if cols["farmer_tns_id"] is not None:
                predicates.append(cols["farmer_tns_id"].ilike(q))
            if cols["training_group_name"] is not None:
                predicates.append(cols["training_group_name"].ilike(q))

            if predicates:
                stmt = stmt.where(or_(*predicates))

        return stmt

    def _select_label(self, col):
        return col.label(col.key) if hasattr(col, "key") else col

    async def list(
        self,
        *,
        filters: FarmVisitFilters,
        page: int,
        page_size: int,
        sort_by: str,
        sort_dir: str,
    ):
        from_expr, cols = self._columns_and_from()

        select_cols = [
            cols["id"].label("id"),
            (cols["date_visited"] if cols["date_visited"] is not None else literal(None)).label("date_visited"),
            (cols["farm_visit_type"] if cols["farm_visit_type"] is not None else literal(None)).label("farm_visit_type"),
            (cols["visit_comments"] if cols["visit_comments"] is not None else literal(None)).label("visit_comments"),
            (cols["location_gps_latitude"] if cols["location_gps_latitude"] is not None else literal(None)).label(
                "location_gps_latitude"
            ),
            (cols["location_gps_longitude"] if cols["location_gps_longitude"] is not None else literal(None)).label(
                "location_gps_longitude"
            ),
            (cols["location_gps_altitude"] if cols["location_gps_altitude"] is not None else literal(None)).label(
                "location_gps_altitude"
            ),
            (cols["number_of_cuerdas"] if cols["number_of_cuerdas"] is not None else literal(None)).label(
                "number_of_cuerdas"
            ),
            (cols["number_of_separate_coffee_fields"] if cols["number_of_separate_coffee_fields"] is not None else literal(None)).label(
                "number_of_separate_coffee_fields"
            ),
            (cols["field_age"] if cols["field_age"] is not None else literal(None)).label("field_age"),
            (cols["field_size"] if cols["field_size"] is not None else literal(None)).label("field_size"),
            (cols["training_group_name"] if cols["training_group_name"] is not None else literal(None)).label(
                "training_group_name"
            ),
            (cols["farmer_tns_id"] if cols["farmer_tns_id"] is not None else literal(None)).label("farmer_tns_id"),
            cols["farmer_full_name"].label("farmer_full_name"),
            (cols["farmer_gender"] if cols["farmer_gender"] is not None else literal(None)).label("farmer_gender"),
            cols["visiting_staff_name"].label("visiting_staff_name"),
        ]

        stmt = select(*select_cols).select_from(from_expr)
        stmt = self._apply_filters(stmt, filters, cols)

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.db.execute(total_stmt)).scalar_one())

        requested = sort_by if sort_by in self.SORT_ALLOWLIST else "date_visited"
        sort_col = cols.get(requested)

        if sort_col is None:
            sort_col = cols["date_visited"] if cols["date_visited"] is not None else self.fv.c.id

        order_expr = sort_col.asc() if sort_dir == "asc" else sort_col.desc()

        stmt = (
            stmt.order_by(order_expr, self.fv.c.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        rows = (await self.db.execute(stmt)).mappings().all()
        return [dict(r) for r in rows], total

    async def stats(self, *, filters: FarmVisitFilters):
        from_expr, cols = self._columns_and_from()

        base_cols = [
            self.fv.c.id.label("id"),
            (cols["date_visited"] if cols["date_visited"] is not None else literal(None)).label("date_visited"),
            (cols["primary_farmer_id"] if cols["primary_farmer_id"] is not None else literal(None)).label("farmer_id"),
            self.fg.c.id.label("group_id"),
        ]

        base_stmt = select(*base_cols).select_from(from_expr)
        base_stmt = self._apply_filters(base_stmt, filters, cols)
        base = base_stmt.subquery()

        total = int((await self.db.execute(select(func.count()).select_from(base))).scalar_one())

        month_start = datetime.now().date().replace(day=1)
        this_month = int(
            (await self.db.execute(
                select(func.count())
                .select_from(base)
                .where(base.c.date_visited.is_not(None))
                .where(func.date(base.c.date_visited) >= month_start)
            )).scalar_one()
        )

        unique_farmers = int(
            (await self.db.execute(
                select(func.count(func.distinct(base.c.farmer_id)))
                .select_from(base)
                .where(base.c.farmer_id.is_not(None))
            )).scalar_one()
        )

        unique_training_groups = int(
            (await self.db.execute(
                select(func.count(func.distinct(base.c.group_id))).select_from(base)
            )).scalar_one()
        )

        return {
            "total": total,
            "this_month": this_month,
            "unique_farmers": unique_farmers,
            "unique_training_groups": unique_training_groups,
        }

    async def filter_types(self, *, filters: FarmVisitFilters):
        from_expr, cols = self._columns_and_from()
        if cols["farm_visit_type"] is None:
            return []

        stmt = select(func.distinct(cols["farm_visit_type"]).label("farm_visit_type")).select_from(from_expr)
        stmt = self._apply_filters(stmt, filters, cols).order_by(cols["farm_visit_type"].asc())
        rows = (await self.db.execute(stmt)).all()
        return [r[0] for r in rows if r[0]]