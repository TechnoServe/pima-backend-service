from __future__ import annotations

from typing import Optional, Tuple, List, Dict
import uuid

from sqlalchemy import select, func, or_, desc, asc, update, insert, literal, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import alias

from app.db.reflection import get_table
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

    # ---------------- Farmers listing (existing) ----------------
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
            "tns_id": (Farmer.c.tns_id,) if "tns_id" in Farmer.c else (Farmer.c.id,),
            "updated_at": (Farmer.c.updated_at,) if "updated_at" in Farmer.c else (Farmer.c.id,),
            "created_at": (Farmer.c.created_at,) if "created_at" in Farmer.c else (Farmer.c.id,),
            "farmer_trainer_name": (ft_name_col,),
            "business_advisor_name": (ba_name_col,),
        }
        cols = sort_map.get(sort_by, sort_map.get("updated_at", (Farmer.c.id,)))
        order_fn = desc if (sort_order or "").lower() == "desc" else asc
        for c in cols:
            q = q.order_by(order_fn(c))

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
                func.sum(case((Farmer.c.send_to_commcare.is_(True), 1), else_=0)).label("pending_commcare"),
            )
            .select_from(Farmer)
            .join(FarmerGroup, Farmer.c.farmer_group_id == FarmerGroup.c.id)
            .where(FarmerGroup.c.project_id == project_id, Farmer.c.is_deleted.is_(False))
        )

        res = await self.db.execute(q)
        return res.mappings().first() or {"total": 0, "pending_commcare": 0}
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
    async def export_farmers_base_rows(self, project_id: UUID) -> List[dict]:
        Farmer = T("farmers")
        FarmerGroup = T("farmer_groups")
        Household = T("households")
        Location = T("locations")
        Projects = T("projects")
        Users = T("users")

        FT = alias(Users, name="ft_user")
        BA = alias(Users, name="ba_user")

        project_name_col = col(Projects, "name", "project_name", "title")

        # from your schema / csv
        farmer_sf_col = col(Farmer, "sf_id")
        farmer_tns_col = col(Farmer, "tns_id")
        first_col = col(Farmer, "first_name")
        mid_col = Farmer.c.middle_name if "middle_name" in Farmer.c else literal(None)
        last_col = col(Farmer, "last_name")
        gender_col = Farmer.c.gender if "gender" in Farmer.c else literal(None)
        age_col = Farmer.c.age if "age" in Farmer.c else literal(None)
        phone_col = Farmer.c.phone_number if "phone_number" in Farmer.c else literal(None)

        # optional fields in your csv (if missing in DB -> None)
        coffee_tree_numbers_col = (
            Farmer.c.coffee_tree_numbers
            if "coffee_tree_numbers" in Farmer.c
            else (Household.c.number_of_trees if "number_of_trees" in Household.c else literal(None))
        )
        number_of_coffee_plots_col = (
            Farmer.c.number_of_coffee_plots
            if "number_of_coffee_plots" in Farmer.c
            else (Household.c.number_of_coffee_plots if "number_of_coffee_plots" in Household.c else literal(None))
        )
        coop_membership_col = (
            Farmer.c.coop_membership_number if "coop_membership_number" in Farmer.c else literal(None)
        )

        loc_name_col = col(Location, "location_name", "name", "title")
        hh_number_col = Household.c.household_number if "household_number" in Household.c else literal(None)
        hh_sf_col = Household.c.sf_id if "sf_id" in Household.c else literal(None)

        ffg_id_col = col(FarmerGroup, "tns_id")
        tg_name_col = col(FarmerGroup, "ffg_name", "name", "title")

        status_col = Farmer.c.status if "status" in Farmer.c else literal(None)
        farmer_status_col = Farmer.c.farmer_status if "farmer_status" in Farmer.c else literal(None)

        # staff joins (your rules)
        fg_responsible_col = col(FarmerGroup, "responsible_staff_id")
        ft_id_col = col(FT, "id")
        ft_name_col = name_expr(FT).label("farmer_trainer")

        ba_id_col = col(BA, "id")
        ba_name_col = name_expr(BA).label("business_advisor")

        create_in_commcare_col = (
            Farmer.c.create_in_commcare
            if "create_in_commcare" in Farmer.c
            else (Farmer.c.create_in_commcare_flag if "create_in_commcare_flag" in Farmer.c else literal(None))
        )

        is_primary_col = Farmer.c.is_primary_household_member if "is_primary_household_member" in Farmer.c else literal(None)
        updated_at_col = Farmer.c.updated_at if "updated_at" in Farmer.c else literal(None)

        q = (
            select(
                project_name_col.label("Project"),
                first_col.label("first_name"),
                mid_col.label("middle_name"),
                last_col.label("last_name"),
                gender_col.label("gender"),
                age_col.label("age"),
                coffee_tree_numbers_col.label("coffee_tree_numbers"),
                number_of_coffee_plots_col.label("number_of_coffee_plots"),
                phone_col.label("phone_number"),
                coop_membership_col.label("coop_membership_number"),
                loc_name_col.label("location"),
                farmer_sf_col.label("farmer_sf_id"),
                Farmer.c.id.label("farmer_id"),
                (Farmer.c.from_sf if "from_sf" in Farmer.c else literal(None)).label("from_sf"),
                farmer_tns_col.label("tns_id"),
                hh_number_col.label("hh_number"),
                hh_sf_col.label("sf_household_id"),
                Household.c.id.label("household_id"),
                # farmer_number: match your historical file logic (1 = primary, 2 = secondary)
                case(
                    (is_primary_col.is_(True), literal(1)),
                    (is_primary_col.is_(False), literal(2)),
                    else_=literal(None),
                ).label("farmer_number"),
                ffg_id_col.label("ffg_id"),
                tg_name_col.label("training_group"),
                status_col.label("status"),
                farmer_status_col.label("farmer_status"),
                ft_id_col.label("farmer_trainer_id"),
                ft_name_col,
                ba_id_col.label("business_advisor_id"),
                ba_name_col,
                create_in_commcare_col.label("create_in_commcare"),
                updated_at_col.label("updated_at"),
            )
            .select_from(Farmer)
            .join(FarmerGroup, Farmer.c.farmer_group_id == FarmerGroup.c.id)
            .join(Projects, FarmerGroup.c.project_id == Projects.c.id)
            .outerjoin(Household, Farmer.c.household_id == Household.c.id)
            .outerjoin(Location, FarmerGroup.c.location_id == Location.c.id)
            .outerjoin(FT, fg_responsible_col == ft_id_col)
            .outerjoin(BA, col(FT, "manager_id") == ba_id_col)
            .where(FarmerGroup.c.project_id == project_id, Farmer.c.is_deleted.is_(False))
            .order_by(asc(farmer_tns_col))
        )

        return (await self.db.execute(q)).mappings().all()

    # ---------------- Export: attendance map via training_sessions -> training_modules ----------------
    async def export_attendance_map(
        self,
        *,
        project_id: UUID,
        farmer_sf_ids: List[str],
        training_modules: List[dict],
    ) -> Dict[tuple[str, str], int]:
        Attendance = T("attendances")
        Farmer = T("farmers")
        TrainingSession = T("training_sessions")

        if not farmer_sf_ids or not training_modules:
            return {}

        farmer_sf_col = col(Farmer, "sf_id")
        att_farmer_id_col = col(Attendance, "farmer_id")
        att_session_id_col = col(Attendance, "training_session_id")

        # training_sessions -> module id
        session_module_id_col = col(TrainingSession, "module_id")

        attended_col_exists = "attended" in Attendance.c
        status_col_exists = "status" in Attendance.c

        module_ids = [m["id"] for m in training_modules]

        q = (
            select(
                farmer_sf_col.label("farmer_sf_id"),
                session_module_id_col.label("module_id"),
                # (Attendance.c.attended if attended_col_exists else literal(None)).label("attended"),
                (Attendance.c.status if status_col_exists else literal(None)).label("status"),
            )
            .select_from(Attendance)
            .join(Farmer, att_farmer_id_col == Farmer.c.id)
            .join(TrainingSession, att_session_id_col == TrainingSession.c.id)
            .where(
                #Farmer.c.sf_id.in_(farmer_sf_ids),
                session_module_id_col.in_(module_ids),
            )
        )
        

        if "project_id" in Attendance.c:
            q = q.where(Attendance.c.project_id == project_id)

        rows = (await self.db.execute(q)).mappings().all()
        
        print(f"Attendance rows: {len(rows)}")  # debug

        # header key: prefer module.sf_id else module.id
        module_key_by_id: Dict[UUID, str] = {}
        for m in training_modules:
            module_key_by_id[m["id"]] = str(m.get("sf_id") or m["id"])

        out: Dict[tuple[str, str], int] = {}

        def to_bool(r) -> bool:
            if attended_col_exists:
                return bool(r.get("attended"))
            if status_col_exists:
                s = str(r.get("status") or "").strip().lower()
                return s in ("present", "attended", "1", "true", "yes")
            return False

        # if multiple sessions exist per module, treat any "present" as 1
        for r in rows:
            sfid = str(r.get("farmer_sf_id") or "").strip()
            mid = r.get("module_id")
            if not sfid or not mid:
                continue
            key = module_key_by_id.get(mid, str(mid))
            cur = out.get((sfid, key), 0)
            out[(sfid, key)] = 1 if (cur == 1 or to_bool(r)) else 0

        return out

    # ---------------- Upload processing helpers ----------------
    async def resolve_farmer_for_project(
        self,
        *,
        project_id: UUID,
        identifier: str,
        from_sf: bool | None,
    ) -> tuple[UUID, UUID] | None:
        Farmer = T("farmers")
        FarmerGroup = T("farmer_groups")
        def _query(match_col):
            return (
                select(Farmer.c.id, Farmer.c.farmer_group_id)
                .select_from(Farmer)
                .join(FarmerGroup, Farmer.c.farmer_group_id == FarmerGroup.c.id)
                .where(
                    match_col == identifier,
                    FarmerGroup.c.project_id == project_id,
                    Farmer.c.is_deleted.is_(False),
                )
                .limit(1)
            )

        query_order = []
        if from_sf is True and "sf_id" in Farmer.c:
            query_order = [Farmer.c.sf_id, Farmer.c.id]
        elif from_sf is False:
            query_order = [Farmer.c.id] + ([Farmer.c.sf_id] if "sf_id" in Farmer.c else [])
        else:
            query_order = ([Farmer.c.sf_id] if "sf_id" in Farmer.c else []) + [Farmer.c.id]

        for match_col in query_order:
            row = (await self.db.execute(_query(match_col))).first()
            if row:
                return row[0], row[1]
        return None

    async def resolve_household_id(self, *, identifier: str, from_sf: bool | None) -> UUID | None:
        Household = T("households")
        order = []
        if from_sf is True and "sf_id" in Household.c:
            order = [Household.c.sf_id, Household.c.id]
        elif from_sf is False:
            order = [Household.c.id] + ([Household.c.sf_id] if "sf_id" in Household.c else [])
        else:
            order = ([Household.c.sf_id] if "sf_id" in Household.c else []) + [Household.c.id]

        for col_match in order:
            q = select(Household.c.id).where(col_match == identifier).limit(1)
            val = (await self.db.execute(q)).scalar_one_or_none()
            if val:
                return val
        return None

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

    async def get_upload_run(self, upload_id: UUID) -> Optional[UploadRun]:
        return await self.db.get(UploadRun, upload_id)

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
