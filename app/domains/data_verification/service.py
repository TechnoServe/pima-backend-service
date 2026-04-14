from __future__ import annotations

import asyncio
import io
from datetime import date, datetime
from typing import Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import UUID

from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.gcs import signed_get_url
from app.shared.api_errors import DomainError, NotFoundError, ValidationError
from .repository import DataVerificationRepository
from .schemas import (
    AttendanceCrossCheckAttendance,
    AttendanceCrossCheckEvidenceItem,
    AttendanceCrossCheckFilters,
    AttendanceCrossCheckItem,
    AttendanceCrossCheckLatestCheck,
    AttendanceCrossCheckMatches,
    AttendanceCrossCheckPagination,
    AttendanceCrossCheckResponse,
    AttendanceCrossCheckTotals,
    DataVerificationImage,
    PaginatedTrainingSessionVerificationResponse,
    SubmitTrainingSessionReviewResponse,
    TrainingSessionVerificationItem,
    TrainingSessionVerificationStatsResponse,
)

ALLOWED_REVIEW_STATUS = {"not_reviewed", "reviewed", "all"}
ALLOWED_VERDICT_FILTER = {"correct", "incorrect", "unclear", "all"}
ALLOWED_VERDICT_VALUE = {"correct", "incorrect", "unclear"}
ALLOWED_VERIFICATION_SOURCE = {"all", "farm_visit", "training_observation", "none"}
ALLOWED_EXPORT_SCOPE = {"all", "mismatches"}


def _extract_commcare_image_id(image_url: str | None) -> str | None:
    if not image_url:
        return None

    path = urlparse(image_url).path or ""
    filename = path.rsplit("/", 1)[-1]
    if not filename:
        return None

    return filename.rsplit(".", 1)[0]


def _commcare_proxy_url(commcare_image_id: str) -> str:
    return f"{settings.base_url}{settings.api_prefix}/data-verification/training-sessions/image/{commcare_image_id}.jpg"


class DataVerificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = DataVerificationRepository(db)

    def _normalize_review_status(self, value: str) -> str:
        normalized = (value or "not_reviewed").strip().lower()
        if normalized not in ALLOWED_REVIEW_STATUS:
            raise ValidationError("Invalid review_status", details={"allowed": sorted(ALLOWED_REVIEW_STATUS)})
        return normalized

    def _normalize_verdict_filter(self, value: str) -> str:
        normalized = (value or "all").strip().lower()
        if normalized not in ALLOWED_VERDICT_FILTER:
            raise ValidationError("Invalid verdict", details={"allowed": sorted(ALLOWED_VERDICT_FILTER)})
        return normalized

    def _normalize_verdict_value(self, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in ALLOWED_VERDICT_VALUE:
            raise ValidationError("Invalid verdict", details={"allowed": sorted(ALLOWED_VERDICT_VALUE)})
        return normalized

    def _build_image_response(self, row: dict) -> Optional[DataVerificationImage]:
        image_id = row.get("image_id")
        if image_id is None:
            return None

        image_url = row.get("image_url")
        url = None
        commcare_image_id = _extract_commcare_image_id(image_url)
        if commcare_image_id:
            url = _commcare_proxy_url(commcare_image_id)
        elif image_url:
            url = image_url
        else:
            object_name = row.get("image_object_name")
            if object_name:
                url = signed_get_url(object_name) or None

        verdict = row.get("image_verdict")
        return DataVerificationImage(id=image_id, url=url, verdict=verdict)

    def _build_item(self, row: dict) -> TrainingSessionVerificationItem:
        review_status = (row.get("review_status") or "not_reviewed").strip().lower()
        return TrainingSessionVerificationItem(
            id=row.get("id"),
            sf_id=row.get("sf_id"),
            module_id=row.get("module_id"),
            module_name=row.get("module_name"),
            trainer_id=row.get("trainer_id"),
            trainer_name=row.get("trainer_name"),
            training_date=row.get("training_date"),
            sampled=bool(row.get("sampled")),
            review_status=review_status,
            total_attendance=row.get("total_attendance"),
            male_attendance=row.get("male_attendance"),
            female_attendance=row.get("female_attendance"),
            image=self._build_image_response(row),
        )

    def _normalize_verification_source(self, value: str) -> str:
        normalized = (value or "all").strip().lower()
        if normalized not in ALLOWED_VERIFICATION_SOURCE:
            raise ValidationError("Invalid verification source", details={"allowed": sorted(ALLOWED_VERIFICATION_SOURCE)})
        return normalized

    def _normalize_export_scope(self, value: str) -> str:
        normalized = (value or "all").strip().lower()
        if normalized not in ALLOWED_EXPORT_SCOPE:
            raise ValidationError("Invalid export scope", details={"allowed": sorted(ALLOWED_EXPORT_SCOPE)})
        return normalized

    @staticmethod
    def _map_attended_last_months_training(value: str | None) -> bool | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized == "yes":
            return True
        if normalized == "no":
            return False
        return None

    @staticmethod
    def _format_full_name(first_name: str | None, middle_name: str | None, last_name: str | None) -> str:
        return " ".join(part for part in [first_name, middle_name, last_name] if part and part.strip())

    @staticmethod
    def _yes_no_na(value: bool | None) -> str:
        if value is None:
            return "N/A"
        return "Yes" if value else "No"

    async def _collect_attendance_cross_check_items(
        self,
        *,
        project_id: UUID,
        search: str | None,
        training_group_id: UUID | None,
        verification_source: str,
        only_mismatches: bool,
    ) -> list[AttendanceCrossCheckItem]:
        verification_source_value = self._normalize_verification_source(verification_source)

        if not await self.repo.project_exists(project_id):
            raise NotFoundError("Project not found")

        if training_group_id is not None:
            belongs = await self.repo.training_group_belongs_to_project(project_id=project_id, training_group_id=training_group_id)
            if not belongs:
                raise DomainError(
                    message="Training group does not belong to project",
                    status_code=422,
                    code="validation_error",
                )

        latest_checks = await self.repo.get_latest_checks_for_attendance_cross_check(
            project_id=project_id,
            search=search,
            training_group_id=training_group_id,
            verification_source=verification_source_value,
        )

        farmer_ids = [row["farmer_id"] for row in latest_checks]
        attendance_by_farmer = await self.repo.get_attendance_evidence_for_farmers(project_id=project_id, farmer_ids=farmer_ids)

        items: list[AttendanceCrossCheckItem] = []
        for row in latest_checks:
            evidence_rows = attendance_by_farmer.get(row["farmer_id"], [])
            evidence: list[AttendanceCrossCheckEvidenceItem] = []
            count_attended = 0
            for evidence_row in evidence_rows:
                status = evidence_row.get("status")
                attended = (status or "").strip().lower() == "present"
                if attended:
                    count_attended += 1
                evidence.append(
                    AttendanceCrossCheckEvidenceItem(
                        attendance_id=evidence_row["attendance_id"],
                        training_session_id=evidence_row.get("training_session_id"),
                        training_date=evidence_row.get("training_date"),
                        module_id=evidence_row.get("module_id"),
                        module_name=evidence_row.get("module_name"),
                        module_number=evidence_row.get("module_number"),
                        current_previous=evidence_row.get("current_previous"),
                        attended=attended,
                        status=status,
                    )
                )

            any_attended = count_attended > 0
            module_number = row.get("training_module_number")
            previous_module_number = module_number - 1 if isinstance(module_number, int) else None
            attended_previous_module = False
            if previous_module_number is not None and previous_module_number >= 1:
                attended_previous_module = any(
                    item.attended and item.module_number == previous_module_number for item in evidence
                )

            check_previous = self._map_attended_last_months_training(row.get("attended_last_months_training"))
            previous_module_equal = (
                None if check_previous is None else (check_previous == attended_previous_module)
            )

            check_any = row.get("attended_trainings")
            check_count = row.get("number_of_trainings_attended")
            has_farm_visit = row.get("farm_visit_id") is not None
            has_observation = row.get("observation_id") is not None

            if has_farm_visit:
                comparison_rule = "farm_visit"
                matches = AttendanceCrossCheckMatches(
                    count_equal=None,
                    any_equal=(check_any == any_attended) if check_any is not None else False,
                    previous_module_equal=previous_module_equal,
                )
            elif has_observation:
                comparison_rule = "training_observation"
                matches = AttendanceCrossCheckMatches(
                    count_equal=None,
                    any_equal=None,
                    previous_module_equal=previous_module_equal,
                )
            else:
                comparison_rule = "full"
                matches = AttendanceCrossCheckMatches(
                    count_equal=(check_count == count_attended) if check_count is not None else False,
                    any_equal=(check_any == any_attended) if check_any is not None else False,
                    previous_module_equal=previous_module_equal,
                )

            evaluated_values = [value for value in [matches.count_equal, matches.any_equal, matches.previous_module_equal] if value is not None]
            is_match = all(evaluated_values) if evaluated_values else True
            if only_mismatches and is_match:
                continue

            item = AttendanceCrossCheckItem(
                farmer_id=row["farmer_id"],
                tns_id=row.get("tns_id"),
                first_name=row.get("first_name"),
                middle_name=row.get("middle_name"),
                last_name=row.get("last_name"),
                full_name=self._format_full_name(row.get("first_name"), row.get("middle_name"), row.get("last_name")),
                training_group_id=row.get("training_group_id"),
                training_group_name=row.get("training_group_name"),
                latest_check=AttendanceCrossCheckLatestCheck(
                    id=row["id"],
                    check_type=row.get("check_type"),
                    date_completed=row.get("date_completed"),
                    training_session_id=row.get("training_session_id"),
                    training_module_id=row.get("training_module_id"),
                    training_module_name=row.get("training_module_name"),
                    training_module_number=row.get("training_module_number"),
                    number_of_trainings_attended=check_count,
                    attended_trainings=check_any,
                    attended_last_months_training=row.get("attended_last_months_training"),
                    has_farm_visit=has_farm_visit,
                    has_observation=has_observation,
                ),
                attendance=AttendanceCrossCheckAttendance(
                    count_attended=count_attended,
                    any_attended=any_attended,
                    attended_previous_module=attended_previous_module,
                    evidence=evidence,
                ),
                matches=matches,
                comparison_rule=comparison_rule,
                is_match=is_match,
            )
            items.append(item)
        return items

    async def list_training_sessions(
        self,
        *,
        project_id: UUID,
        page: int,
        page_size: int,
        review_status: str,
        verdict: str,
        date_from: Optional[date],
        date_to: Optional[date],
        trainer_id: Optional[UUID],
    ) -> PaginatedTrainingSessionVerificationResponse:
        review_status_value = self._normalize_review_status(review_status)
        verdict_value = self._normalize_verdict_filter(verdict)

        if date_from and date_to and date_from > date_to:
            raise ValidationError("date_from cannot be after date_to")

        rows, total = await self.repo.list_training_sessions(
            project_id=project_id,
            page=page,
            page_size=page_size,
            review_status=review_status_value,
            verdict=verdict_value,
            date_from=date_from,
            date_to=date_to,
            trainer_id=trainer_id,
        )

        items = [self._build_item(row) for row in rows]
        total_pages = (total + page_size - 1) // page_size
        return PaginatedTrainingSessionVerificationResponse(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        )

    async def stats(self, *, project_id: UUID) -> TrainingSessionVerificationStatsResponse:
        stats = await self.repo.stats(project_id=project_id)
        return TrainingSessionVerificationStatsResponse(**stats)

    async def submit_review(
        self,
        *,
        training_session_id: UUID,
        verdict: str,
        reviewed: bool,
        project_id: Optional[UUID] = None,
    ) -> SubmitTrainingSessionReviewResponse:
        if not reviewed:
            raise ValidationError("reviewed must be true")

        verdict_value = self._normalize_verdict_value(verdict)

        training_session = await self.repo.get_training_session(training_session_id)
        if not training_session:
            raise NotFoundError("Training session not found")

        if project_id is not None:
            row_project_id = await self.repo.get_training_session_project_id(training_session_id)
            if row_project_id != project_id:
                raise NotFoundError("Training session not found for project")

        image = await self.repo.get_selected_image_for_session(training_session_id)
        if not image:
            raise ValidationError("No image found for training session")

        await self.repo.mark_reviewed_and_update_image_verdict(
            training_session_id=training_session_id,
            image_id=image["id"],
            verdict=verdict_value,
        )
        await self.db.commit()

        return SubmitTrainingSessionReviewResponse(
            success=True,
            training_session_id=training_session_id,
            review_status="reviewed",
            image=DataVerificationImage(id=image["id"], verdict=verdict_value, url=image.get("url")),
        )


    async def fetch_commcare_image(self, *, commcare_image_id: str, project_id: UUID | None = None) -> tuple[bytes, str]:
        if not settings.commcare_api_key:
            raise ValidationError("CommCare API key is not configured")

        image = await self.repo.get_image_by_commcare_image_id(commcare_image_id=commcare_image_id, project_id=project_id)
        if not image:
            raise NotFoundError("Image not found")

        image_url = image.get("image_url")
        if not image_url:
            raise NotFoundError("Image URL not found")

        if settings.commcare_base_url:
            image_host = (urlparse(image_url).hostname or "").lower()
            allowed_host = (urlparse(settings.commcare_base_url).hostname or "").lower()
            if not image_host or image_host != allowed_host:
                raise ValidationError("Image URL does not match configured CommCare host")

        def _download() -> tuple[bytes, str]:
            req = Request(image_url, headers={"Authorization": f"ApiKey {settings.commcare_api_key}"})
            with urlopen(req, timeout=30) as response:
                content_type = response.headers.get("Content-Type", "image/jpeg")
                return response.read(), content_type

        try:
            return await asyncio.to_thread(_download)
        except Exception as exc:
            raise ValidationError("Unable to fetch image from CommCare") from exc

    async def export_training_sessions_excel(
        self,
        *,
        project_id: UUID,
        review_status: str,
        verdict: str,
        date_from: Optional[date],
        date_to: Optional[date],
        trainer_id: Optional[UUID],
    ) -> bytes:
        review_status_value = self._normalize_review_status(review_status)
        verdict_value = self._normalize_verdict_filter(verdict)

        rows = await self.repo.list_training_sessions_for_export(
            project_id=project_id,
            review_status=review_status_value,
            verdict=verdict_value,
            date_from=date_from,
            date_to=date_to,
            trainer_id=trainer_id,
        )

        wb = Workbook()
        ws = wb.active
        ws.title = "training_sessions_verification"
        ws.append(
            [
                "Module",
                "Trainer",
                "Training date",
                "Total attendance",
                "Male attendance",
                "Female attendance",
                "Review status",
                "Verdict",
                "Image URL",
            ]
        )

        for row in rows:
            image = self._build_image_response(row)
            training_date = row.get("training_date")
            if isinstance(training_date, datetime):
                training_date = training_date.date()
            ws.append(
                [
                    row.get("module_name") or "",
                    row.get("trainer_name") or "",
                    training_date.isoformat() if isinstance(training_date, date) else "",
                    row.get("total_attendance"),
                    row.get("male_attendance"),
                    row.get("female_attendance"),
                    (row.get("review_status") or "not_reviewed"),
                    row.get("image_verdict") or "",
                    image.url if image else "",
                ]
            )

        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return out.read()

    async def list_attendance_cross_check(
        self,
        *,
        project_id: UUID,
        page: int,
        page_size: int,
        search: str | None,
        training_group_id: UUID | None,
        verification_source: str,
        only_mismatches: bool,
    ) -> AttendanceCrossCheckResponse:
        trimmed_search = search.strip() if search else None
        items = await self._collect_attendance_cross_check_items(
            project_id=project_id,
            search=trimmed_search,
            training_group_id=training_group_id,
            verification_source=verification_source,
            only_mismatches=only_mismatches,
        )
        total_items = len(items)
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        start = (page - 1) * page_size
        end = start + page_size
        paged_items = items[start:end]
        matches = sum(1 for item in items if item.is_match)
        mismatches = total_items - matches

        return AttendanceCrossCheckResponse(
            totals=AttendanceCrossCheckTotals(total=total_items, matches=matches, mismatches=mismatches),
            pagination=AttendanceCrossCheckPagination(
                page=page,
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
            filters=AttendanceCrossCheckFilters(
                project_id=project_id,
                training_group_id=training_group_id,
                verification_source=self._normalize_verification_source(verification_source),
                search=trimmed_search,
                only_mismatches=only_mismatches,
            ),
            items=paged_items,
        )

    async def export_attendance_cross_check(
        self,
        *,
        project_id: UUID,
        search: str | None,
        training_group_id: UUID | None,
        verification_source: str,
        only_mismatches: bool,
        export_scope: str,
    ) -> bytes:
        scope = self._normalize_export_scope(export_scope)
        items = await self._collect_attendance_cross_check_items(
            project_id=project_id,
            search=search.strip() if search else None,
            training_group_id=training_group_id,
            verification_source=verification_source,
            only_mismatches=only_mismatches or scope == "mismatches",
        )

        wb = Workbook()
        ws = wb.active
        ws.title = "attendance_cross_check"
        ws.append(
            [
                "Farmer Name",
                "TNS ID",
                "Training Group",
                "Check Type",
                "Check Date",
                "Check Module",
                "Check Module Number",
                "Check Count",
                "Check Any",
                "Check Previous",
                "Has Farm Visit",
                "Has Observation",
                "Attendance Count",
                "Attendance Any",
                "Attendance Previous Module",
                "Rule",
                "Count Match",
                "Any Match",
                "Previous Match",
                "Overall Match",
            ]
        )

        for item in items:
            ws.append(
                [
                    item.full_name,
                    item.tns_id or "",
                    item.training_group_name or "",
                    item.latest_check.check_type or "",
                    item.latest_check.date_completed.isoformat() if item.latest_check.date_completed else "",
                    item.latest_check.training_module_name or "",
                    item.latest_check.training_module_number,
                    item.latest_check.number_of_trainings_attended,
                    self._yes_no_na(item.latest_check.attended_trainings),
                    self._yes_no_na(self._map_attended_last_months_training(item.latest_check.attended_last_months_training)),
                    self._yes_no_na(item.latest_check.has_farm_visit),
                    self._yes_no_na(item.latest_check.has_observation),
                    item.attendance.count_attended,
                    self._yes_no_na(item.attendance.any_attended),
                    self._yes_no_na(item.attendance.attended_previous_module),
                    item.comparison_rule,
                    self._yes_no_na(item.matches.count_equal),
                    self._yes_no_na(item.matches.any_equal),
                    self._yes_no_na(item.matches.previous_module_equal),
                    self._yes_no_na(item.is_match),
                ]
            )

        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return out.read()
