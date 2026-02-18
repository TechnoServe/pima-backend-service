from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reflection import get_table
from app.domains.observation_results.repository import ObservationResultsRepository


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
class DemoPlotObservationFilters:
    project_id: UUID
    date_from: date | None = None
    date_to: date | None = None
    observation_type: str | None = None
    search: str | None = None


class ObservationsRepository:
    SORT_ALLOWLIST = {"observation_date", "training_group_name", "observer_name", "trainer_name", "results_count"}

    def __init__(self, db: AsyncSession):
        self.db = db
        self.obs = T("observations")
        self.fg = T("farmer_groups")
        self.users = T("users")
        self.result_repo = ObservationResultsRepository(db)

    def _columns_and_from(self):
        obs_fg_id = maybe_col(self.obs, "farmer_group_id")
        obs_observer_id = maybe_col(self.obs, "observer_id", "staff_id", "user_id")
        obs_trainer_id = maybe_col(self.obs, "trainer_id")

        observer_tbl = self.users.alias("observer_user")
        trainer_tbl = self.users.alias("trainer_user")
        from_expr = self.obs.join(self.fg, obs_fg_id == self.fg.c.id)
        from_expr = from_expr.outerjoin(observer_tbl, obs_observer_id == observer_tbl.c.id) if obs_observer_id is not None else from_expr
        from_expr = from_expr.outerjoin(trainer_tbl, obs_trainer_id == trainer_tbl.c.id) if obs_trainer_id is not None else from_expr

        results_counts = self.result_repo.results_count_subquery()
        from_expr = from_expr.outerjoin(results_counts, results_counts.c.observation_id == self.obs.c.id)

        observation_date = maybe_col(self.obs, "observation_date", "date_observed", "created_at")
        observation_type = maybe_col(self.obs, "observation_type", "type")

        cols = {
            "id": self.obs.c.id,
            "observation_type": observation_type,
            "observation_date": observation_date,
            "location_gps_latitude": maybe_col(self.obs, "location_gps_latitude", "gps_latitude"),
            "location_gps_longitude": maybe_col(self.obs, "location_gps_longitude", "gps_longitude"),
            "location_gps_altitude": maybe_col(self.obs, "location_gps_altitude", "gps_altitude"),
            "female_attendees": maybe_col(self.obs, "female_attendees"),
            "male_attendees": maybe_col(self.obs, "male_attendees"),
            "total_attendees": maybe_col(self.obs, "total_attendees"),
            "training_group_name": maybe_col(self.fg, "name", "farmer_group_name"),
            "observer_name": full_name_expr(observer_tbl),
            "trainer_name": full_name_expr(trainer_tbl),
            "results_count": func.coalesce(results_counts.c.results_count, 0),
        }
        return from_expr, cols

    def _apply_filters(self, stmt, filters: DemoPlotObservationFilters, cols):
        stmt = stmt.where(self.fg.c.project_id == filters.project_id)
        default_types = ["Demo Plot", "Training"]
        if filters.observation_type and cols["observation_type"] is not None:
            stmt = stmt.where(cols["observation_type"] == filters.observation_type)
        elif cols["observation_type"] is not None:
            stmt = stmt.where(cols["observation_type"].in_(default_types))

        if filters.date_from and cols["observation_date"] is not None:
            stmt = stmt.where(func.date(cols["observation_date"]) >= filters.date_from)
        if filters.date_to and cols["observation_date"] is not None:
            stmt = stmt.where(func.date(cols["observation_date"]) <= filters.date_to)

        if filters.search:
            q = f"%{filters.search.strip()}%"
            preds = [cols["observer_name"].ilike(q), cols["trainer_name"].ilike(q)]
            if cols["training_group_name"] is not None:
                preds.append(cols["training_group_name"].ilike(q))
            stmt = stmt.where(or_(*preds))
        return stmt

    async def list(self, *, filters: DemoPlotObservationFilters, page: int, page_size: int, sort_by: str, sort_dir: str):
        from_expr, cols = self._columns_and_from()
        stmt = select(
            cols["id"].label("id"),
            cols["observation_type"].label("observation_type") if cols["observation_type"] is not None else literal(None).label("observation_type"),
            cols["observation_date"].label("observation_date") if cols["observation_date"] is not None else literal(None).label("observation_date"),
            cols["location_gps_latitude"].label("location_gps_latitude") if cols["location_gps_latitude"] is not None else literal(None).label("location_gps_latitude"),
            cols["location_gps_longitude"].label("location_gps_longitude") if cols["location_gps_longitude"] is not None else literal(None).label("location_gps_longitude"),
            cols["location_gps_altitude"].label("location_gps_altitude") if cols["location_gps_altitude"] is not None else literal(None).label("location_gps_altitude"),
            cols["female_attendees"].label("female_attendees") if cols["female_attendees"] is not None else literal(None).label("female_attendees"),
            cols["male_attendees"].label("male_attendees") if cols["male_attendees"] is not None else literal(None).label("male_attendees"),
            cols["total_attendees"].label("total_attendees") if cols["total_attendees"] is not None else literal(None).label("total_attendees"),
            cols["training_group_name"].label("training_group_name") if cols["training_group_name"] is not None else literal(None).label("training_group_name"),
            cols["observer_name"].label("observer_name"),
            cols["trainer_name"].label("trainer_name"),
            cols["results_count"].label("results_count"),
        ).select_from(from_expr)
        stmt = self._apply_filters(stmt, filters, cols)

        total = int((await self.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())

        key = sort_by if sort_by in self.SORT_ALLOWLIST else "observation_date"
        # sort_col = cols.get(key) or cols["observation_date"] or self.obs.c.id
        sort_col = cols["observation_date"]
        order_expr = sort_col.asc() if sort_dir == "asc" else sort_col.desc()
        stmt = stmt.order_by(order_expr, self.obs.c.id.desc()).offset((page - 1) * page_size).limit(page_size)

        rows = (await self.db.execute(stmt)).mappings().all()
        return [dict(r) for r in rows], total

    async def stats(self, *, filters: DemoPlotObservationFilters):
        from_expr, cols = self._columns_and_from()
        base = self._apply_filters(
            select(
                self.obs.c.id.label("id"),
                cols["observation_date"].label("observation_date") if cols["observation_date"] is not None else literal(None).label("observation_date"),
                self.fg.c.id.label("group_id"),
                cols["results_count"].label("results_count"),
            ).select_from(from_expr),
            filters,
            cols,
        ).subquery()

        total = int((await self.db.execute(select(func.count()).select_from(base))).scalar_one())
        month_start = datetime.now().date().replace(day=1)
        this_month = int((await self.db.execute(select(func.count()).select_from(base).where(func.date(base.c.observation_date) >= month_start))).scalar_one())
        unique_training_groups = int((await self.db.execute(select(func.count(func.distinct(base.c.group_id))).select_from(base))).scalar_one())
        with_results = int((await self.db.execute(select(func.count()).select_from(base).where(base.c.results_count > 0))).scalar_one())
        pct = float(with_results / total) if total else 0.0

        return {"total": total, "this_month": this_month, "unique_training_groups": unique_training_groups, "pct_with_results": pct}

    async def filter_types(self, *, filters: DemoPlotObservationFilters):
        from_expr, cols = self._columns_and_from()
        if cols["observation_type"] is None:
            return ["DemoPlot", "TrainingObservation"]
        stmt = select(func.distinct(cols["observation_type"]).label("observation_type")).select_from(from_expr)
        stmt = stmt.where(self.fg.c.project_id == filters.project_id).order_by(cols["observation_type"].asc())
        rows = (await self.db.execute(stmt)).all()
        return [r[0] for r in rows if r[0]]

    async def get_detail(self, *, observation_id: UUID, project_id: UUID):
        from_expr, cols = self._columns_and_from()
        stmt = (
            select(
                cols["id"].label("id"),
                cols["observation_type"].label("observation_type") if cols["observation_type"] is not None else literal(None).label("observation_type"),
                cols["observation_date"].label("observation_date") if cols["observation_date"] is not None else literal(None).label("observation_date"),
                cols["location_gps_latitude"].label("location_gps_latitude") if cols["location_gps_latitude"] is not None else literal(None).label("location_gps_latitude"),
                cols["location_gps_longitude"].label("location_gps_longitude") if cols["location_gps_longitude"] is not None else literal(None).label("location_gps_longitude"),
                cols["location_gps_altitude"].label("location_gps_altitude") if cols["location_gps_altitude"] is not None else literal(None).label("location_gps_altitude"),
                cols["female_attendees"].label("female_attendees") if cols["female_attendees"] is not None else literal(None).label("female_attendees"),
                cols["male_attendees"].label("male_attendees") if cols["male_attendees"] is not None else literal(None).label("male_attendees"),
                cols["total_attendees"].label("total_attendees") if cols["total_attendees"] is not None else literal(None).label("total_attendees"),
                cols["training_group_name"].label("training_group_name") if cols["training_group_name"] is not None else literal(None).label("training_group_name"),
                cols["observer_name"].label("observer_name"),
                cols["trainer_name"].label("trainer_name"),
            )
            .select_from(from_expr)
            .where(self.obs.c.id == observation_id)
            .where(self.fg.c.project_id == project_id)
        )
        row = (await self.db.execute(stmt)).mappings().first()
        return dict(row) if row else None
