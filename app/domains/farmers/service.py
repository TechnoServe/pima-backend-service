from __future__ import annotations

import io
from datetime import datetime
from typing import Optional, Dict, List
from uuid import UUID

from openpyxl import load_workbook, Workbook
from sqlalchemy import select, update, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.gcs import upload_bytes, signed_get_url
from app.db.reflection import get_table
from app.domains.farmers.repository import FarmersRepository
from app.domains.farmers.models import UploadRun, UploadRowError
from app.domains.farmers.schemas import (
    PaginatedFarmersResponse,
    FarmerListItem,
    FarmersFilterOptions,
    FilterOption,
    FarmersSummaryResponse,
    UploadValidationResult,
    UploadValidationWarning,
    UploadJob,
    UploadHistoryResponse,
    FailedRow,
)

from .models import table


def before_update(payload: dict, entity: str) -> dict:
    data = dict(payload or {})
    if "send_to_commcare" in table().c:
        data["send_to_commcare"] = True
    if "send_to_commcare_status" in table().c:
        data["send_to_commcare_status"] = "Pending"
    return data


def T(name: str):
    return get_table(name)


class FarmersService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = FarmersRepository(db)

    # ---------------- List Farmers ----------------
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
    ) -> PaginatedFarmersResponse:
        rows, total = await self.repo.list_farmers(
            project_id=project_id,
            page=page,
            page_size=page_size,
            search=search,
            gender=gender,
            location_id=location_id,
            farmer_group_id=farmer_group_id,
            farmer_trainer_id=farmer_trainer_id,
            business_advisor_id=business_advisor_id,
            has_pending_commcare=has_pending_commcare,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        items: list[FarmerListItem] = []
        for r in rows:
            f = r["farmer"]
            m = getattr(f, "_mapping", f)

            full_name = " ".join([x for x in [m.get("first_name"), m.get("middle_name"), m.get("last_name")] if x])

            items.append(
                FarmerListItem(
                    id=m.get("id"),
                    first_name=m.get("first_name"),
                    middle_name=m.get("middle_name"),
                    last_name=m.get("last_name"),
                    full_name=full_name,
                    gender=str(m.get("gender")) if m.get("gender") else None,
                    age=m.get("age"),
                    phone_number=m.get("phone_number"),
                    tns_id=m.get("tns_id"),
                    farmer_group_id=m.get("farmer_group_id"),
                    farmer_group_name=r["farmer_group_name"],
                    household_id=m.get("household_id"),
                    household_number=r["household_number"],
                    is_primary_household_member=bool(m.get("is_primary_household_member")),
                    farmer_trainer_id=r.get("farmer_trainer_id"),
                    farmer_trainer_name=r.get("farmer_trainer_name"),
                    business_advisor_id=r.get("business_advisor_id"),
                    business_advisor_name=r.get("business_advisor_name"),
                    location_id=r["location_id"],
                    location_name=r["location_name"],
                    send_to_commcare=bool(m.get("send_to_commcare")),
                    send_to_commcare_status=str(m.get("send_to_commcare_status")) if m.get("send_to_commcare_status") else None,
                    updated_at=m.get("updated_at"),
                    created_at=m.get("created_at"),
                )
            )

        total_pages = (total + page_size - 1) // page_size
        return PaginatedFarmersResponse(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)

    async def summary(self, *, project_id: UUID) -> FarmersSummaryResponse:
        s = await self.repo.summary(project_id=project_id)
        return FarmersSummaryResponse(total=s["total"], pending_commcare=s["pending_commcare"])

    async def filter_options(self, *, project_id: UUID) -> FarmersFilterOptions:
        FarmerGroup = T("farmer_groups")
        Location = T("locations")

        genders = [FilterOption(value="Male", label="Male"), FilterOption(value="Female", label="Female")]

        q_loc = (
            select(Location.c.id, (Location.c.location_name if "location_name" in Location.c else Location.c.name))
            .select_from(FarmerGroup)
            .join(Location, FarmerGroup.c.location_id == Location.c.id)
            .where(FarmerGroup.c.project_id == project_id)
            .distinct()
            .order_by((Location.c.location_name if "location_name" in Location.c else Location.c.name))
        )
        loc_rows = (await self.db.execute(q_loc)).all()

        fg_name_col = FarmerGroup.c.ffg_name if "ffg_name" in FarmerGroup.c else (FarmerGroup.c.name if "name" in FarmerGroup.c else FarmerGroup.c.id)
        q_fg = select(FarmerGroup.c.id, fg_name_col).where(FarmerGroup.c.project_id == project_id).order_by(fg_name_col)
        fg_rows = (await self.db.execute(q_fg)).all()

        return FarmersFilterOptions(
            genders=genders,
            locations=[FilterOption(value=str(r[0]), label=str(r[1])) for r in loc_rows],
            farmer_groups=[FilterOption(value=str(r[0]), label=str(r[1])) for r in fg_rows],
            farmer_trainers=[],
            business_advisors=[],
        )

    # ---------------- Export XLSX (mirrors your CSV exactly) ----------------
    async def export_excel(self, *, project_id: UUID) -> bytes:
        modules = await self.repo.export_training_modules(project_id)
        base_rows = await self.repo.export_farmers_base_rows(project_id)

        # EXACT columns (same as your uploaded CSV) + farmer_status added after status
        base_headers = [
            "num",
            "Project",
            "first_name",
            "middle_name",
            "last_name",
            "gender",
            "age",
            "coffee_tree_numbers",
            "number_of_coffee_plots",
            "phone_number",
            "coop_membership_number",
            "location",
            "farmer_sf_id",
            "tns_id",
            "hh_number",
            "sf_household_id",
            "farmer_number",
            "ffg_id",
            "training_group",
            "status",
            "farmer_status",
            "farmer_trainer",
            "business_advisor",
            "create_in_commcare",
        ]

        module_headers: List[str] = []
        for m in modules:
            module_number = m.get("module_number") or ""
            module_name = m.get("module_name") or ""
            module_key = m.get("sf_id") or m.get("id")  # key in header end
            module_headers.append(f"{module_number}-{module_name}-{module_key}")

        farmer_sf_ids = [str(r.get("farmer_sf_id") or "").strip() for r in base_rows if r.get("farmer_sf_id")]
        att_map = await self.repo.export_attendance_map(
            project_id=project_id,
            farmer_sf_ids=farmer_sf_ids,
            training_modules=modules,
        )

        wb = Workbook()
        ws = wb.active
        ws.title = "Farmers"
        ws.append(base_headers + module_headers)

        for i, r in enumerate(base_rows, start=1):
            row = [
                i,
                r.get("Project") or "",
                r.get("first_name") or "",
                r.get("middle_name") or "",
                r.get("last_name") or "",
                r.get("gender") or "",
                r.get("age") if r.get("age") is not None else "",
                r.get("coffee_tree_numbers") if r.get("coffee_tree_numbers") is not None else "",
                r.get("number_of_coffee_plots") if r.get("number_of_coffee_plots") is not None else "",
                r.get("phone_number") if r.get("phone_number") is not None else "",
                r.get("coop_membership_number") if r.get("coop_membership_number") is not None else "",
                r.get("location") or "",
                r.get("farmer_sf_id") or "",
                r.get("tns_id") or "",
                r.get("hh_number") if r.get("hh_number") is not None else "",
                r.get("sf_household_id") or "",
                r.get("farmer_number") if r.get("farmer_number") is not None else "",
                r.get("ffg_id") or "",
                r.get("training_group") or "",
                r.get("status") or "",
                r.get("farmer_status") or "",
                r.get("farmer_trainer") or "",
                r.get("business_advisor") or "",
                bool(r.get("create_in_commcare")) if r.get("create_in_commcare") is not None else "",
            ]

            module_vals = []
            sfid = str(r.get("farmer_sf_id") or "").strip()
            for m in modules:
                key = str(m.get("sf_id") or m.get("id"))
                module_vals.append(att_map.get((sfid, key), 0))
            ws.append(row + module_vals)

        bio = io.BytesIO()
        wb.save(bio)
        return bio.getvalue()

    # ---------------- Upload validate + run (refactored to accept same exported XLSX) ----------------
    def validate_upload(self, *, file_bytes: bytes) -> UploadValidationResult:
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb.active

        headers = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
        header_set = {h.lower(): i for i, h in enumerate(headers)}

        # REQUIRED columns to match exported file
        required = ["farmer_sf_id", "tns_id", "first_name", "last_name"]
        errors: list[UploadValidationWarning] = []
        for k in required:
            if k not in header_set:
                errors.append(
                    UploadValidationWarning(
                        type="missing_column",
                        message=f'Required column "{k}" is missing',
                        column=k,
                        severity="error",
                    )
                )

        total_rows = ws.max_row - 1 if ws.max_row else 0

        preview = []
        for row in ws.iter_rows(min_row=2, max_row=min(11, ws.max_row), values_only=True):
            obj = {}
            for i, h in enumerate(headers):
                obj[h] = row[i] if i < len(row) else None
            preview.append(obj)

        return UploadValidationResult(
            is_valid=len(errors) == 0,
            total_rows=max(total_rows, 0),
            preview_rows=preview,
            warnings=[],
            errors=errors,
        )

    async def start_upload(
        self,
        *,
        project_id: UUID,
        file_name: str,
        content_type: str | None,
        file_bytes: bytes,
        uploaded_by_id: UUID | None,
    ) -> UploadJob:
        active = await self.repo.get_active_upload(project_id=project_id)
        if active:
            raise ValueError("An upload is already in progress for this project.")
        
        print(f"Uploading file to GCS for project {project_id} with filename {file_name}")  # debug

        # gcs = upload_bytes(
        #     project_id=str(project_id),
        #     category="farmer-uploads",
        #     filename=file_name,
        #     content=file_bytes,
        #     content_type=content_type,
        # )
        
        print("---------------------------------------------------------------------------------")
        
        # print(f"File uploaded to GCS: bucket={gcs['bucket']} object={gcs['object_name']}")  # debug

        run = UploadRun(
            project_id=project_id,
            filename=file_name,
            content_type=content_type,
            file_size_bytes=len(file_bytes),
            #gcs_bucket=gcs["bucket"],
            #gcs_object_name=gcs["object_name"],
            # gcs_uri=gcs["gcs_uri"],
            status="processing",
            progress=0,
            total_rows=0,
            success_count=0,
            failed_count=0,
            remaining_count=0,
            uploaded_by_id=uploaded_by_id,
            uploaded_at=datetime.utcnow(),
        )
        run = await self.repo.create_upload_run(run)

        await self._process_upload_run(upload_run_id=run.id, project_id=project_id, file_bytes=file_bytes)
        return await self.get_upload_job(run.id)

    async def _process_upload_run(self, *, upload_run_id: UUID, project_id: UUID, file_bytes: bytes):
        run = await self.repo.get_upload_run(upload_run_id)
        if not run:
            return

        Farmer = T("farmers")
        FarmerGroup = T("farmer_groups")
        Attendance = T("attendances")
        TrainingModule = T("training_modules")
        TrainingSession = T("training_sessions")

        # columns
        farmer_sf_col = Farmer.c.sf_id if "sf_id" in Farmer.c else None
        if farmer_sf_col is None:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            await self.db.commit()
            return

        att_farmer_id_col = Attendance.c.farmer_id if "farmer_id" in Attendance.c else None
        att_session_id_col = Attendance.c.training_session_id if "training_session_id" in Attendance.c else None
        if att_farmer_id_col is None or att_session_id_col is None:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            await self.db.commit()
            return

        try:
            run.status = "processing"
            await self.db.commit()

            wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
            ws = wb.active

            headers = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
            header_idx = {h.strip().lower(): i for i, h in enumerate(headers)}

            def cell(row, key: str):
                i = header_idx.get(key)
                return row[i] if i is not None and i < len(row) else None

            # module columns by header "...-...-<id>"
            module_cols: list[tuple[int, str]] = []
            for i, h in enumerate(headers):
                parts = (h or "").strip().split("-")
                if len(parts) >= 3:
                    module_cols.append((i, parts[-1].strip()))

            total_rows = ws.max_row - 1 if ws.max_row else 0
            run.total_rows = max(total_rows, 0)
            run.remaining_count = run.total_rows
            run.progress = 10
            await self.db.commit()

            row_errors: list[UploadRowError] = []
            success = 0
            failed = 0

            # prefetch module key->module_uuid
            modules = await self.repo.export_training_modules(project_id)
            module_uuid_by_key: Dict[str, UUID] = {}
            for m in modules:
                mid = m["id"]
                key = str(m.get("sf_id") or mid)
                module_uuid_by_key[key] = mid

            for row_number, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                print(f"Processing row {row_number}...")  # debug
                farmer_id_uuid: Optional[UUID] = None
                # try:
                farmer_sf_id = str(cell(row, "farmer_sf_id") or "").strip()
                if not farmer_sf_id:
                    raise ValueError("Missing farmer_sf_id")

                # resolve farmer local uuid & group
                q_farmer = (
                    select(Farmer.c.id, Farmer.c.farmer_group_id)
                    .select_from(Farmer)
                    .join(FarmerGroup, Farmer.c.farmer_group_id == FarmerGroup.c.id)
                    .where(
                        Farmer.c.sf_id == farmer_sf_id,
                        FarmerGroup.c.project_id == project_id,
                        Farmer.c.is_deleted.is_(False),
                    )
                    .limit(1)
                )
                fr = (await self.db.execute(q_farmer)).first()
                if not fr:
                    raise ValueError("Farmer not found for this project")
                farmer_id_uuid = fr[0]
                farmer_group_id = fr[1]

                # farmer updates (only the columns that exist)
                farmer_updates = {}
                for colname in [
                    "tns_id",
                    "first_name",
                    "middle_name",
                    "last_name",
                    "gender",
                    "age",
                    "phone_number",
                    "number_of_coffee_plots",
                    "coop_membership_number",
                    "status",
                    "farmer_status",
                    "create_in_commcare",
                ]:
                    if colname not in Farmer.c:
                        continue
                    v = cell(row, colname)
                    if v is None or v == "":
                        continue
                    if colname == "age":
                        try:
                            v = int(v)
                        except Exception:
                            continue
                    if colname in ("create_in_commcare",):
                        v = str(v).strip().lower() in ("1", "true", "yes")
                    farmer_updates[colname] = v

                # always mark send_to_commcare on any update
                if farmer_updates:
                    if "updated_at" in Farmer.c:
                        farmer_updates["updated_at"] = datetime.utcnow()
                    if "send_to_commcare" in Farmer.c:
                        farmer_updates["send_to_commcare"] = True
                    if "send_to_commcare_status" in Farmer.c:
                        farmer_updates["send_to_commcare_status"] = "Pending"

                    await self.db.execute(update(Farmer).where(Farmer.c.id == farmer_id_uuid).values(**farmer_updates))

                # Attendance updates:
                # file gives module key -> we pick latest training_session for (farmer_group_id, module_id)
                for idx, module_key in module_cols:
                    if idx >= len(row):
                        continue
                    v = row[idx]
                    if v is None or v == "":
                        continue

                    attended = str(v).strip().lower() in ("1", "true", "yes")

                    module_uuid = module_uuid_by_key.get(module_key)
                    if not module_uuid:
                        # unknown module in header -> ignore (or error)
                        continue

                    # find latest session for this group+module
                    q_sess = (
                        select(TrainingSession.c.id)
                        .where(
                            TrainingSession.c.training_module_id == module_uuid,
                            TrainingSession.c.farmer_group_id == farmer_group_id if "farmer_group_id" in TrainingSession.c else True,
                        )
                        .order_by(TrainingSession.c.training_date.desc() if "training_date" in TrainingSession.c else TrainingSession.c.created_at.desc())
                        .limit(1)
                    )
                    sess_id = (await self.db.execute(q_sess)).scalar_one_or_none()
                    if not sess_id:
                        row_errors.append(
                            UploadRowError(
                                upload_run_id=upload_run_id,
                                row_number=row_number,
                                farmer_id=farmer_id_uuid,
                                tns_id=str(cell(row, "tns_id") or ""),
                                error_type="attendance_error",
                                error_message=f"No training_session found for module {module_key} in this farmer_group",
                                raw_row={headers[i]: row[i] for i in range(min(len(headers), len(row)))},
                            )
                        )
                        continue

                    # upsert attendance row (project+farmer+session)
                    q_att = (
                        select(Attendance.c.id)
                        .where(
                            Attendance.c.project_id == project_id if "project_id" in Attendance.c else True,
                            Attendance.c.farmer_id == farmer_id_uuid,
                            Attendance.c.training_session_id == sess_id,
                        )
                        .limit(1)
                    )
                    att_id = (await self.db.execute(q_att)).scalar_one_or_none()

                    values = {}
                    if "attended" in Attendance.c:
                        values["attended"] = attended
                    elif "status" in Attendance.c:
                        values["status"] = "Present" if attended else "Absent"

                    if att_id:
                        if values:
                            await self.db.execute(update(Attendance).where(Attendance.c.id == att_id).values(**values))
                    else:
                        ins = {
                            "farmer_id": farmer_id_uuid,
                            "training_session_id": sess_id,
                        }
                        if "project_id" in Attendance.c:
                            ins["project_id"] = project_id
                        if values:
                            ins.update(values)
                        await self.db.execute(insert(Attendance).values(**ins))

                success += 1

                # except Exception as e:
                #     failed += 1
                #     row_errors.append(
                #         UploadRowError(
                #             upload_run_id=upload_run_id,
                #             row_number=row_number,
                #             farmer_id=farmer_id_uuid,
                #             tns_id=str(cell(row, "tns_id") or ""),
                #             error_type="validation_error",
                #             error_message=str(e),
                #             raw_row={headers[i]: row[i] for i in range(min(len(headers), len(row)))},
                #         )
                #     )

                if (row_number % 50) == 0:
                    run.progress = min(90, int((row_number / max(ws.max_row, 2)) * 80) + 10)
                    await self.db.commit()

            if row_errors:
                await self.repo.bulk_add_row_errors(row_errors)

            run.success_count = success
            run.failed_count = failed
            run.remaining_count = 0
            run.progress = 100
            run.status = "failed" if (failed > 0) else "completed"
            run.completed_at = datetime.utcnow()
            await self.db.commit()

        except Exception:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            await self.db.commit()

    # ---------------- Upload queries ----------------
    async def get_upload_job(self, upload_id: UUID) -> UploadJob:
        run = await self.repo.get_upload_run(upload_id)
        if not run:
            raise ValueError("Upload not found")

        original_url = signed_get_url(run.gcs_object_name) if run.gcs_object_name else None
        error_url = signed_get_url(run.error_gcs_object_name) if run.error_gcs_object_name else None

        return UploadJob(
            id=run.id,
            project_id=run.project_id,
            filename=run.filename,
            status=run.status,
            progress=run.progress,
            total_rows=run.total_rows,
            success_count=run.success_count,
            failed_count=run.failed_count,
            remaining_count=run.remaining_count,
            uploaded_by_id=run.uploaded_by_id,
            uploaded_by_name=None,
            uploaded_at=run.uploaded_at,
            completed_at=run.completed_at,
            can_retry=run.failed_count > 0,
            parent_upload_id=run.parent_upload_id,
            original_file_url=original_url,
            error_report_url=error_url,
        )

    async def active_upload(self, *, project_id: UUID) -> UploadJob | None:
        run = await self.repo.get_active_upload(project_id=project_id)
        if not run:
            return None
        return await self.get_upload_job(run.id)

    async def upload_history(self, *, project_id: UUID, page: int, page_size: int) -> UploadHistoryResponse:
        items, total = await self.repo.list_upload_history(project_id=project_id, page=page, page_size=page_size)
        jobs = [await self.get_upload_job(x.id) for x in items]
        total_pages = (total + page_size - 1) // page_size
        return UploadHistoryResponse(items=jobs, total=total, page=page, page_size=page_size, total_pages=total_pages)

    async def failed_rows(self, upload_id: UUID) -> list[FailedRow]:
        errs = await self.repo.list_failed_rows(upload_id)
        return [
            FailedRow(
                row_number=e.row_number,
                farmer_id=e.farmer_id,
                farmer_name=None,
                tns_id=e.tns_id,
                error_type=e.error_type,
                error_message=e.error_message,
            )
            for e in errs
        ]

    # ---------------- CommCare flagging ----------------
    async def send_to_commcare(self, *, project_id: UUID) -> int:
        return await self.repo.flag_farmers_send_to_commcare(project_id=project_id)

    async def pending_commcare_count(self, *, project_id: UUID) -> int:
        s = await self.repo.summary(project_id=project_id)
        return s["pending_commcare"]