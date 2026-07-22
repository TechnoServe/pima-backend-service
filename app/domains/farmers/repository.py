from __future__ import annotations

from typing import Optional, Tuple, List, Dict
import uuid

from sqlalchemy import select, func, or_, desc, asc, update, insert, literal, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import alias

from app.db.reflection import get_table
from app.domains.farm_visits.repository import FarmVisitsRepository
from app.domains.farmers.models import UploadRun, UploadRowError


def T(name: str):
    return get_table(name)


def col(tbl, *candidates: str):
    for c in candidates:
        if c in tbl.c:
            return tbl.c[c]
    raise KeyError(f"{tbl.name}: none of {candidates} found. Have: {list(tbl.c.keys())}")


def name_expr(UserTbl):
    first = col(UserTbl, "first_name", "firstname", "given_name")
    last = col(UserTbl, "last_name", "lastname", "family_name", "surname")
    return func.trim(func.concat_ws(" ", first, last))


class FarmersRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------- Farmers listing ----------------
    async def list_farmers(
        self,
        *,
        project_id: UUID,
        page: int,
        page_size: int,
        search: Optional[str],
        gender: Optional[str],
        location_id: Optional[UUID],
        farmer_group_id: Optional[UUID],
        farmer_trainer_id: Optional[UUID],
        business_advisor_id: Optional[UUID],
        has_pending_commcare: Optional[bool],
        sort_by: str,
        sort_order: str,
    ) -> Tuple[List[dict], int]:
        Farmer = T("farmers")
        FarmerGroup = T("farmer_groups")
        Household = T("households")
        Location = T("locations")
        Users = T("users")

        FT = alias(Users, name="ft_user")
        BA = alias(Users, name="ba_user")

        farmer_cols = [c for c in Farmer.c]

        fg_name_col = col(FarmerGroup, "ffg_name", "name", "farmer_group_name", "group_name", "title")
        loc_name_col = col(Location, "location_name", "name", "title")

        fg_responsible_col = col(FarmerGroup, "responsible_staff_id")
        ft_id_col = col(FT, "id")
        ba_id_col = col(BA, "id")

        ft_name_col = name_expr(FT).label("farmer_trainer_name")
        ba_name_col = name_expr(BA).label("business_advisor_name")

        q = (
            select(
                *farmer_cols,
                fg_name_col.label("farmer_group_name"),
                Household.c.household_number.label("household_number")
                if "household_number" in Household.c
                else literal(None).label("household_number"),
                Location.c.id.label("location_id"),
                loc_name_col.label("location_name"),
                ft_id_col.label("farmer_trainer_id"),
                ft_name_col,
                ba_id_col.label("business_advisor_id"),
                ba_name_col,
            )
            .select_from(Farmer)
            .join(FarmerGroup, Farmer.c.farmer_group_id == FarmerGroup.c.id)
            .outerjoin(Household, Farmer.c.household_id == Household.c.id)
            .outerjoin(Location, FarmerGroup.c.location_id == Location.c.id)
            .outerjoin(FT, fg_responsible_col == ft_id_col)
            .outerjoin(BA, col(FT, "manager_id") == ba_id_col)
            .where(FarmerGroup.c.project_id == project_id, Farmer.c.is_deleted.is_(False))
        )

        if search:
            s = f"%{search.strip().lower()}%"
            clauses = []
            if "first_name" in Farmer.c:
                clauses.append(func.lower(func.coalesce(Farmer.c.first_name, "")).like(s))
            if "last_name" in Farmer.c:
                clauses.append(func.lower(func.coalesce(Farmer.c.last_name, "")).like(s))
            if "tns_id" in Farmer.c:
                clauses.append(func.lower(func.coalesce(Farmer.c.tns_id, "")).like(s))
            clauses.append(func.lower(func.coalesce(loc_name_col, "")).like(s))
            clauses.append(func.lower(func.coalesce(ft_name_col, "")).like(s))
            clauses.append(func.lower(func.coalesce(ba_name_col, "")).like(s))
            q = q.where(or_(*clauses))

        if gender and "gender" in Farmer.c:
            q = q.where(Farmer.c.gender == gender)

        if location_id:
            q = q.where(Location.c.id == location_id)

        if farmer_group_id:
            q = q.where(FarmerGroup.c.id == farmer_group_id)

        if has_pending_commcare is True and "send_to_commcare" in Farmer.c:
            q = q.where(Farmer.c.send_to_commcare.is_(True))
            if "send_to_commcare_status" in Farmer.c:
                q = q.where(Farmer.c.send_to_commcare_status == "Pending")

        if farmer_trainer_id:
            q = q.where(ft_id_col == farmer_trainer_id)

        if business_advisor_id:
            q = q.where(ba_id_col == business_advisor_id)

        sort_map = {
            "full_name": (Farmer.c.last_name, Farmer.c.first_name)
            if ("last_name" in Farmer.c and "first_name" in Farmer.c)
            else (Farmer.c.id,),
            "tns_id": Farmer.c.tns_id,
            "updated_at": (Farmer.c.updated_at,) if "updated_at" in Farmer.c else (Farmer.c.id,),
            "created_at": (Farmer.c.created_at,) if "created_at" in Farmer.c else (Farmer.c.id,),
            "farmer_trainer_name": (ft_name_col,),
            "business_advisor_name": (ba_name_col,),
        }
        cols = sort_map.get(sort_by, sort_map.get("tns_id", (Farmer.c.id,)))
        order_fn = desc if (sort_order or "").lower() == "desc" else asc
        for c in cols:
            q = q.order_by(Farmer.c.tns_id)

        total = (await self.db.execute(select(func.count()).select_from(q.subquery()))).scalar_one() or 0
        q = q.offset((page - 1) * page_size).limit(page_size)

        res = await self.db.execute(q)

        rows = []
        for m in res.mappings().all():
            farmer_dict = {c.name: m.get(c.name) for c in Farmer.c}
            rows.append(
                {
                    "farmer": farmer_dict,
                    "farmer_group_name": m.get("farmer_group_name"),
                    "household_number": m.get("household_number"),
                    "location_id": m.get("location_id"),
                    "location_name": m.get("location_name"),
                    "farmer_trainer_id": m.get("farmer_trainer_id"),
                    "farmer_trainer_name": m.get("farmer_trainer_name"),
                    "business_advisor_id": m.get("business_advisor_id"),
                    "business_advisor_name": m.get("business_advisor_name"),
                }
            )

        return rows, total

    async def summary(self, project_id: UUID) -> dict:
        Farmer = T("farmers")
        FarmerGroup = T("farmer_groups")

        q = (
            select(
                func.count().label("total"),
                func.coalesce(func.sum(case((Farmer.c.send_to_commcare.is_(True), 1), else_=0)), 0).label("pending_commcare"),
            )
            .select_from(Farmer)
            .join(FarmerGroup, Farmer.c.farmer_group_id == FarmerGroup.c.id)
            .where(FarmerGroup.c.project_id == project_id, Farmer.c.is_deleted.is_(False))
        )

        res = await self.db.execute(q)
        return res.mappings().first() or {"total": 0, "pending_commcare": 0}

    async def project_location_name(self, project_id: UUID) -> str | None:
        Projects = T("projects")
        Locations = T("locations")

        if "location_id" not in Projects.c:
            return None

        loc_name_col = col(Locations, "location_name", "name", "title")
        q = (
            select(loc_name_col)
            .select_from(Projects)
            .outerjoin(Locations, Projects.c.location_id == Locations.c.id)
            .where(Projects.c.id == project_id)
            .limit(1)
        )
        return (await self.db.execute(q)).scalar_one_or_none()

    # ---------------- Export: training modules ----------------
    async def export_training_modules(self, project_id: UUID) -> List[dict]:
        TrainingModule = T("training_modules")

        module_id_col = col(TrainingModule, "id")
        module_sf_col = TrainingModule.c.sf_id if "sf_id" in TrainingModule.c else literal(None)
        module_num_col = TrainingModule.c.module_number if "module_number" in TrainingModule.c else literal(None)
        module_name_col = col(TrainingModule, "module_name", "name", "title")

        q = (
            select(
                module_id_col.label("id"),
                module_sf_col.label("sf_id"),
                module_num_col.label("module_number"),
                module_name_col.label("module_name"),
            )
            .select_from(TrainingModule)
            .where(TrainingModule.c.project_id == project_id)
        )

        if "is_deleted" in TrainingModule.c:
            q = q.where(TrainingModule.c.is_deleted.is_(False))

        if "module_number" in TrainingModule.c:
            q = q.order_by(TrainingModule.c.module_number.asc())
        else:
            q = q.order_by(TrainingModule.c.id.asc())

        return (await self.db.execute(q)).mappings().all()

    # ---------------- Export: base rows mirroring your CSV ----------------
    async def export_farmers_base_rows(
        self,
        project_id: UUID,
        *,
        include_zimbabwe_farm_visit_data: bool = False,
    ) -> List[dict]:
        Farmer = T("farmers")
        FarmerGroup = T("farmer_groups")
        Household = T("households")
        Location = T("locations")
        Projects = T("projects")
        Users = T("users")

        # Define aliases for user tables
        FT = alias(Users, name="ft_user")
        BA = alias(Users, name="ba_user")
        LatestFarmVisit = alias(T("farm_visits"), name="latest_farm_visit")
        answer_columns = {
            "primary_farmer_consent": ("consent-primary_farmer_consent", "answer_boolean"),
            "secondary_farmer_consent": ("consent-secondary_farmer_consent", "answer_boolean"),
        }
        if include_zimbabwe_farm_visit_data:
            answer_columns.update(
                {
                    "fv_coffee_tree_numbers": ("updated_number_of_trees", "answer_numeric"),
                    "reason_for_change_in_number_of_trees": (
                        "number_of_trees_confirmation-ask_what_happened_to_most_of_the_trees",
                        "answer_text",
                    ),
                }
            )
        latest_visit_sq, visit_answers_sq = FarmVisitsRepository(
            self.db
        ).latest_visit_and_answers_subqueries(
            project_id=project_id,
            answer_columns=answer_columns,
        )

        q = (
            select(
                Projects.c.project_name.label("Project"),
                Farmer.c.first_name.label("first_name"),
                Farmer.c.middle_name.label("middle_name"),
                Farmer.c.last_name.label("last_name"),
                Farmer.c.gender.label("gender"),
                Farmer.c.age.label("age"),
                Household.c.number_of_trees.label("number_of_trees"),
                Household.c.number_of_coffee_plots.label("number_of_coffee_plots"),
                Household.c.farm_size.label("farm_size"),
                Farmer.c.phone_number.label("phone_number"),
                Farmer.c.other_id.label("other_id"),
                Location.c.location_name.label("location"),
                Farmer.c.sf_id.label("farmer_sf_id"),
                Farmer.c.id.label("farmer_id"),
                Farmer.c.from_sf.label("from_sf"),
                Farmer.c.tns_id.label("tns_id"),
                Household.c.household_number.label("hh_number"),
                Household.c.sf_id.label("sf_household_id"),
                Household.c.id.label("household_id"),
                case(
                    (Farmer.c.is_primary_household_member.is_(True), literal(1)),
                    (Farmer.c.is_primary_household_member.is_(False), literal(2)),
                    else_=literal(None),
                ).label("farmer_number"),
                FarmerGroup.c.tns_id.label("ffg_id"),
                FarmerGroup.c.ffg_name.label("training_group"),
                case(
                    (Farmer.c.is_primary_household_member.is_(True), visit_answers_sq.c.primary_farmer_consent),
                    (Farmer.c.is_primary_household_member.is_(False), visit_answers_sq.c.secondary_farmer_consent),
                    else_=literal(None),
                ).label("consent_provided"),
                (
                    visit_answers_sq.c.fv_coffee_tree_numbers
                    if include_zimbabwe_farm_visit_data
                    else literal(None)
                ).label("fv_coffee_tree_numbers"),
                (
                    LatestFarmVisit.c.date_visited
                    if include_zimbabwe_farm_visit_data
                    else literal(None)
                ).label("date_of_latest_farm_visit"),
                (
                    visit_answers_sq.c.reason_for_change_in_number_of_trees
                    if include_zimbabwe_farm_visit_data
                    else literal(None)
                ).label("reason_for_change_in_number_of_trees"),
                Farmer.c.status.label("status"),
                Farmer.c.farmer_status.label("farmer_status"),
                FT.c.id.label("farmer_trainer_id"),
                name_expr(FT).label("farmer_trainer"),
                BA.c.id.label("business_advisor_id"),
                name_expr(BA).label("business_advisor"),
                Farmer.c.send_to_commcare.label("create_in_commcare"),
                LatestFarmVisit.c.location_gps_latitude.label("location_gps_latitude"),
                LatestFarmVisit.c.location_gps_longitude.label("location_gps_longitude"),
                LatestFarmVisit.c.location_gps_altitude.label("location_gps_altitude"),
                Farmer.c.updated_at.label("updated_at"),
            )
            .select_from(Farmer)
            .join(FarmerGroup, Farmer.c.farmer_group_id == FarmerGroup.c.id)
            .join(Projects, FarmerGroup.c.project_id == Projects.c.id)
            .outerjoin(Household, Farmer.c.household_id == Household.c.id)
            .outerjoin(
                latest_visit_sq,
                (latest_visit_sq.c.visited_household_id == Household.c.id)
                & (latest_visit_sq.c.visit_rank == 1),
            )
            .outerjoin(
                LatestFarmVisit,
                LatestFarmVisit.c.id == latest_visit_sq.c.latest_visit_id,
            )
            .outerjoin(visit_answers_sq, visit_answers_sq.c.farm_visit_id == LatestFarmVisit.c.id)
            .outerjoin(Location, FarmerGroup.c.location_id == Location.c.id)
            .outerjoin(FT, FarmerGroup.c.responsible_staff_id == FT.c.id)
            .outerjoin(BA, FT.c.manager_id == BA.c.id)
            .where(
                FarmerGroup.c.project_id == project_id,
                Farmer.c.is_deleted.is_(False),
            )
            .order_by(asc(Farmer.c.tns_id))
        )

        return (await self.db.execute(q)).mappings().all()
    
    # ---------------- Export: attendance map via training_sessions -> training_modules ----------------
    async def export_attendance_map(
        self,
        *,
        project_id: UUID,
        farmer_sf_ids: List[str],
        farmer_ids: List[uuid.UUID],
        training_modules: List[dict],
    ) -> Dict[tuple[str, str], int]:
        Attendance = T("attendances")
        Farmer = T("farmers")
        FarmerGroup = T("farmer_groups")
        TrainingSession = T("training_sessions")

        if not training_modules:
            return {}

        module_ids = [m["id"] for m in training_modules]

        q = (
            select(
                Farmer.c.sf_id.label("farmer_sf_id"),
                Farmer.c.id.label("farmer_id"),
                TrainingSession.c.module_id.label("module_id"),
                Attendance.c.status.label("status"),
            )
            .select_from(Attendance)
            .join(Farmer, Attendance.c.farmer_id == Farmer.c.id)
            .join(FarmerGroup, Farmer.c.farmer_group_id == FarmerGroup.c.id)
            .join(TrainingSession, Attendance.c.training_session_id == TrainingSession.c.id)
            .where(
                FarmerGroup.c.project_id == project_id,
                Farmer.c.is_deleted.is_(False),
                Attendance.c.is_deleted.is_(False),
                TrainingSession.c.module_id.in_(module_ids),
            )
        )

        rows = (await self.db.execute(q)).mappings().all()

        module_key_by_id: Dict[UUID, str] = {
            m["id"]: str(m.get("sf_id") or m["id"])
            for m in training_modules
        }

        out: Dict[tuple[str, str], int] = {}

        def is_present(status) -> bool:
            s = str(status or "").strip().lower()
            return s in ("present", "attended", "1", "true", "yes")

        for r in rows:
            sfid = str(r.get("farmer_sf_id") or r.get("farmer_id") or "").strip()
            mid = r.get("module_id")

            if not sfid or not mid:
                continue

            key = module_key_by_id.get(mid, str(mid))
            cur = out.get((sfid, key), 0)
            out[(sfid, key)] = 1 if (cur == 1 or is_present(r.get("status"))) else 0

        return out

    @staticmethod
    def is_uuid(value) -> bool:
        if isinstance(value, uuid.UUID):
            return True
        if not isinstance(value, str):
            return False
        try:
            uuid.UUID(value)
            return True
        except (ValueError, TypeError):
            return False

    async def resolve_farmer_for_project(
        self,
        *,
        project_id,
        identifier: str,
        from_sf: bool | None,
        active_only: bool = False,
    ) -> tuple[uuid.UUID, uuid.UUID] | None:
        Farmer = T("farmers")
        FarmerGroup = T("farmer_groups")

        if not identifier:
            return None

        if self.is_uuid(identifier):
            match_col = Farmer.c.id
            match_val = uuid.UUID(str(identifier))
        else:
            if "sf_id" not in Farmer.c:
                return None
            match_col = Farmer.c.sf_id
            match_val = identifier

        conditions = [
            match_col == match_val,
            FarmerGroup.c.project_id == project_id,
            Farmer.c.is_deleted.is_(False),
        ]
        if active_only and "status" in Farmer.c:
            conditions.append(Farmer.c.status == "Active")

        q = (
            select(Farmer.c.id, Farmer.c.farmer_group_id)
            .select_from(Farmer)
            .join(FarmerGroup, Farmer.c.farmer_group_id == FarmerGroup.c.id)
            .where(*conditions)
            .limit(1)
        )

        row = (await self.db.execute(q)).first()
        if not row:
            return None
        return row[0], row[1]

    async def latest_session_id_for_group_module(self, *, farmer_group_id: UUID, module_id: UUID) -> UUID | None:
        TrainingSession = T("training_sessions")

        q = select(TrainingSession.c.id).where(TrainingSession.c.module_id == module_id)
        if "farmer_group_id" in TrainingSession.c:
            q = q.where(TrainingSession.c.farmer_group_id == farmer_group_id)

        order_col = TrainingSession.c.training_date if "training_date" in TrainingSession.c else TrainingSession.c.created_at
        q = q.order_by(order_col.desc()).limit(1)

        return (await self.db.execute(q)).scalar_one_or_none()

    async def attendance_id(self, *, project_id: UUID, farmer_id: UUID, session_id: UUID) -> UUID | None:
        Attendance = T("attendances")

        q = select(Attendance.c.id).where(
            Attendance.c.farmer_id == farmer_id,
            Attendance.c.training_session_id == session_id,
        )
        if "project_id" in Attendance.c:
            q = q.where(Attendance.c.project_id == project_id)
        return (await self.db.execute(q.limit(1))).scalar_one_or_none()

    async def update_farmer(self, *, farmer_id: UUID, values: dict) -> None:
        Farmer = T("farmers")
        await self.db.execute(update(Farmer).where(Farmer.c.id == farmer_id).values(**values))

    async def upsert_attendance(self, *, project_id: UUID, farmer_id: UUID, session_id: UUID, values: dict, attendance_id: UUID | None, updated_by) -> None:
        Attendance = T("attendances")
        if attendance_id:
            if values:
                await self.db.execute(update(Attendance).where(Attendance.c.id == attendance_id).values(**values))
            return

        ins = {
            "farmer_id":farmer_id, 
            "training_session_id": session_id, 
            **values, "id": uuid.uuid4(), 
            "created_by_id": updated_by, 
            "last_updated_by_id": updated_by,
            "created_at": func.now(),
            "updated_at": func.now(),
        }
        if "project_id" in Attendance.c:
            ins["project_id"] = project_id
        await self.db.execute(insert(Attendance).values(**ins))


    async def resolve_group_by_tns(self, *, project_id: UUID, ffg_id: str) -> UUID | None:
        FarmerGroup = T("farmer_groups")
        q = (
            select(FarmerGroup.c.id)
            .where(FarmerGroup.c.project_id == project_id, FarmerGroup.c.tns_id == ffg_id)
            .limit(1)
        )
        return (await self.db.execute(q)).scalar_one_or_none()

    async def find_household_by_group_number(self, *, farmer_group_id: UUID, household_number: int) -> UUID | None:
        Household = T("households")
        if "household_number" not in Household.c:
            return None
        q = (
            select(Household.c.id)
            .where(Household.c.farmer_group_id == farmer_group_id, Household.c.household_number == household_number)
            .limit(1)
        )
        return (await self.db.execute(q)).scalar_one_or_none()

    
    async def create_household(self, values: dict):
        Household = T("households")

        if not values.get("id"):
            values["id"] = uuid.uuid4()


        stmt = (
            insert(Household)
            .values(**values)
            .returning(Household.c.id)
        )
        res = await self.db.execute(stmt)
        household_id = res.scalar_one()
        return household_id



    async def is_farmer_active(self, *, farmer_id: UUID) -> bool:
        Farmer = T("farmers")
        if "status" not in Farmer.c:
            return True
        q = select(Farmer.c.status).where(Farmer.c.id == farmer_id).limit(1)
        status_value = (await self.db.execute(q)).scalar_one_or_none()
        return status_value == "Active"

    async def get_farmer_current_state(self, *, farmer_id: UUID) -> tuple[UUID | None, bool | None]:
        Farmer = T("farmers")
        primary_col = Farmer.c.is_primary_household_member if "is_primary_household_member" in Farmer.c else literal(None)
        q = select(Farmer.c.household_id, primary_col).where(Farmer.c.id == farmer_id).limit(1)
        row = (await self.db.execute(q)).first()
        if not row:
            return None, None
        return row[0], row[1]


    async def get_household_state(self, *, household_id: UUID) -> tuple[UUID | None, int | None]:
        Household = T("households")
        hh_num_col = Household.c.household_number if "household_number" in Household.c else literal(None)
        q = select(Household.c.farmer_group_id, hh_num_col).where(Household.c.id == household_id).limit(1)
        row = (await self.db.execute(q)).first()
        if not row:
            return None, None
        return row[0], row[1]

    async def count_household_members(self, *, household_id: UUID, exclude_farmer_id: UUID | None = None) -> int:
        Farmer = T("farmers")
        q = select(func.count()).where(Farmer.c.household_id == household_id, Farmer.c.is_deleted.is_(False))
        if "status" in Farmer.c:
            q = q.where(Farmer.c.status == "Active")
        if exclude_farmer_id:
            q = q.where(Farmer.c.id != exclude_farmer_id)
        return (await self.db.execute(q)).scalar_one() or 0

    async def count_primary_members(self, *, household_id: UUID, exclude_farmer_id: UUID | None = None) -> int:
        Farmer = T("farmers")
        if "is_primary_household_member" not in Farmer.c:
            return 0
        q = select(func.count()).where(
            Farmer.c.household_id == household_id,
            Farmer.c.is_deleted.is_(False),
            Farmer.c.is_primary_household_member.is_(True),
        )
        if "status" in Farmer.c:
            q = q.where(Farmer.c.status == "Active")
        if exclude_farmer_id:
            q = q.where(Farmer.c.id != exclude_farmer_id)
        return (await self.db.execute(q)).scalar_one() or 0

    async def update_household(self, *, household_id: UUID, values: dict) -> None:
        Household = T("households")
        await self.db.execute(update(Household).where(Household.c.id == household_id).values(**values))

    # ---------------- CommCare flagging ----------------
    async def flag_farmers_send_to_commcare(self, *, project_id: UUID) -> int:
        Farmer = T("farmers")
        FarmerGroup = T("farmer_groups")

        stmt = (
            update(Farmer)
            .where(
                Farmer.c.id.in_(
                    select(Farmer.c.id)
                    .select_from(Farmer)
                    .join(FarmerGroup, Farmer.c.farmer_group_id == FarmerGroup.c.id)
                    .where(FarmerGroup.c.project_id == project_id)
                ),
                Farmer.c.is_deleted.is_(False),
            )
            .values(send_to_commcare=True)
        )
        if "send_to_commcare_status" in Farmer.c:
            stmt = stmt.values(send_to_commcare_status="Pending")

        res = await self.db.execute(stmt)
        await self.db.commit()
        return res.rowcount or 0

    # ---------------- Upload Runs (unchanged from your existing) ----------------
    async def create_upload_run(self, run: UploadRun) -> UploadRun:
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def get_active_upload(self, *, project_id: UUID) -> Optional[UploadRun]:
        q = (
            select(UploadRun)
            .where(
                UploadRun.project_id == project_id,
                UploadRun.status.in_(["uploading", "validating", "processing"]),
            )
            .order_by(desc(UploadRun.uploaded_at))
            .limit(1)
        )
        return (await self.db.execute(q)).scalars().first()


    async def get_blocking_validation_parent(self, *, project_id: UUID) -> Optional[UploadRun]:
        q = (
            select(UploadRun)
            .where(
                UploadRun.project_id == project_id,
                UploadRun.parent_upload_id.is_(None),
                UploadRun.status == "validation_errored",
            )
            .order_by(desc(UploadRun.uploaded_at))
            .limit(1)
        )
        return (await self.db.execute(q)).scalars().first()

    async def get_upload_run(self, upload_id: UUID) -> Optional[UploadRun]:
        return await self.db.get(UploadRun, upload_id)

    async def get_latest_upload_for_project(self, *, project_id: UUID) -> Optional[UploadRun]:
        q = (
            select(UploadRun)
            .where(UploadRun.project_id == project_id)
            .order_by(desc(UploadRun.uploaded_at), desc(UploadRun.id))
            .limit(1)
        )
        return (await self.db.execute(q)).scalars().first()

    async def has_child_upload(self, *, upload_id: UUID) -> bool:
        q = select(func.count()).select_from(UploadRun).where(UploadRun.parent_upload_id == upload_id)
        return ((await self.db.execute(q)).scalar_one() or 0) > 0

    async def list_upload_history(self, *, project_id: UUID, page: int, page_size: int) -> Tuple[List[UploadRun], int]:
        q = select(UploadRun).where(UploadRun.project_id == project_id).order_by(desc(UploadRun.uploaded_at))
        total = (await self.db.execute(select(func.count()).select_from(q.subquery()))).scalar_one() or 0
        items = (await self.db.execute(q.offset((page - 1) * page_size).limit(page_size))).scalars().all()
        return items, total

    async def bulk_add_row_errors(self, errors: list[UploadRowError]) -> None:
        self.db.add_all(errors)
        await self.db.commit()

    async def list_failed_rows(self, upload_id: UUID, limit: int = 500) -> List[UploadRowError]:
        q = (
            select(UploadRowError)
            .where(UploadRowError.upload_run_id == upload_id)
            .order_by(UploadRowError.row_number.asc())
            .limit(limit)
        )
        return (await self.db.execute(q)).scalars().all()
