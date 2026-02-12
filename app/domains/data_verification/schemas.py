from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

ReviewStatus = Literal["not_reviewed", "reviewed", "all"]
VerdictFilter = Literal["correct", "incorrect", "unclear", "all"]
VerdictValue = Literal["correct", "incorrect", "unclear"]


class DataVerificationImage(BaseModel):
    id: UUID
    url: Optional[str] = None
    verdict: Optional[VerdictValue] = None


class TrainingSessionVerificationItem(BaseModel):
    id: UUID
    sf_id: Optional[str] = None
    module_id: Optional[UUID] = None
    module_name: Optional[str] = None
    trainer_id: Optional[UUID] = None
    trainer_name: Optional[str] = None
    training_date: Optional[date] = None
    sampled: bool
    review_status: str
    total_attendance: Optional[int] = None
    male_attendance: Optional[int] = None
    female_attendance: Optional[int] = None
    image: Optional[DataVerificationImage] = None


class PaginatedTrainingSessionVerificationResponse(BaseModel):
    items: list[TrainingSessionVerificationItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class TrainingSessionVerificationStatsResponse(BaseModel):
    total_sampled: int
    total_reviewed: int
    not_reviewed: int
    correct: int
    incorrect: int
    unclear: int


class SubmitTrainingSessionReviewRequest(BaseModel):
    verdict: VerdictValue
    reviewed: bool


class SubmitTrainingSessionReviewResponse(BaseModel):
    success: bool
    training_session_id: UUID
    review_status: Literal["reviewed"]
    image: Optional[DataVerificationImage] = None
