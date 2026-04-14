from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

ReviewStatus = Literal["not_reviewed", "reviewed", "all"]
VerdictFilter = Literal["correct", "incorrect", "unclear", "all"]
VerdictValue = Literal["correct", "incorrect", "unclear", "", "unverified"]


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


class AttendanceCrossCheckTotals(BaseModel):
    total: int
    matches: int
    mismatches: int


class AttendanceCrossCheckPagination(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class AttendanceCrossCheckFilters(BaseModel):
    project_id: UUID
    training_group_id: UUID | None = None
    verification_source: str = "all"
    search: str | None = None
    only_mismatches: bool = False


class AttendanceCrossCheckLatestCheck(BaseModel):
    id: UUID
    check_type: str | None = None
    date_completed: date | None = None
    training_session_id: UUID | None = None
    training_module_id: UUID | None = None
    training_module_name: str | None = None
    training_module_number: int | None = None
    number_of_trainings_attended: int | None = None
    attended_trainings: bool | None = None
    attended_last_months_training: str | None = None
    has_farm_visit: bool
    has_observation: bool


class AttendanceCrossCheckEvidenceItem(BaseModel):
    attendance_id: UUID
    training_session_id: UUID | None = None
    training_date: date | None = None
    module_id: UUID | None = None
    module_name: str | None = None
    module_number: int | None = None
    current_previous: str | None = None
    attended: bool
    status: str | None = None


class AttendanceCrossCheckAttendance(BaseModel):
    count_attended: int
    any_attended: bool
    attended_previous_module: bool
    evidence: list[AttendanceCrossCheckEvidenceItem]


class AttendanceCrossCheckMatches(BaseModel):
    count_equal: bool | None = None
    any_equal: bool | None = None
    previous_module_equal: bool | None = None


class AttendanceCrossCheckItem(BaseModel):
    farmer_id: UUID
    tns_id: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    full_name: str
    training_group_id: UUID | None = None
    training_group_name: str | None = None
    latest_check: AttendanceCrossCheckLatestCheck
    attendance: AttendanceCrossCheckAttendance
    matches: AttendanceCrossCheckMatches
    comparison_rule: Literal["farm_visit", "training_observation", "full"]
    is_match: bool


class AttendanceCrossCheckResponse(BaseModel):
    status: int = 200
    totals: AttendanceCrossCheckTotals
    pagination: AttendanceCrossCheckPagination
    filters: AttendanceCrossCheckFilters
    items: list[AttendanceCrossCheckItem]
