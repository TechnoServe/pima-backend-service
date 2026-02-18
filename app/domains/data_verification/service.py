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
from app.shared.api_errors import NotFoundError, ValidationError
from .repository import DataVerificationRepository
from .schemas import (
    DataVerificationImage,
    PaginatedTrainingSessionVerificationResponse,
    SubmitTrainingSessionReviewResponse,
    TrainingSessionVerificationItem,
    TrainingSessionVerificationStatsResponse,
)

ALLOWED_REVIEW_STATUS = {"not_reviewed", "reviewed", "all"}
ALLOWED_VERDICT_FILTER = {"correct", "incorrect", "unclear", "all"}
ALLOWED_VERDICT_VALUE = {"correct", "incorrect", "unclear"}


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
