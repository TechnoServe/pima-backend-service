from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class TrainingModuleItem(BaseModel):
    id: UUID
    project_id: UUID
    module_name: str | None = None
    module_number: int | None = None
    current_module: bool | None = None
    sample_fv_aa_households: bool | None = None
    sample_fv_aa_households_status: str | None = None
    status: str | None = None
    current_previous: str | None = None
    module_date: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    sessions_count: int | None = None


class TrainingSessionItem(BaseModel):
    id: UUID
    module_id: UUID
    farmer_group_id: UUID
    farmer_group_name: str | None = None
    trainer_id: UUID | None = None
    trainer_name: str | None = None
    commcare_case_id: str | None = None
    date_session_1: date | None = None
    date_session_2: date | None = None
    male_attendees_session_1: int | None = None
    female_attendees_session_1: int | None = None
    total_attendees_session_1: int | None = None
    male_attendees_session_2: int | None = None
    female_attendees_session_2: int | None = None
    total_attendees_session_2: int | None = None
    male_attendees_agg: int | None = None
    female_attendees_agg: int | None = None
    total_attendees_agg: int | None = None
    send_to_commcare: bool | None = None
    send_to_commcare_status: str | None = None
    sampled: bool | None = None
    review_status: str | None = None


class TrainingModulesListResponse(BaseModel):
    items: list[TrainingModuleItem]
    page: int
    page_size: int
    total: int
    pages: int


class TrainingModuleDetailsResponse(BaseModel):
    module: TrainingModuleItem
    training_sessions: list[TrainingSessionItem]


class CreateTrainingModuleRequest(BaseModel):
    project_id: UUID
    module_name: str
    module_number: int
    current_module: bool = False
    sample_fv_aa_households: bool = False
    status: str | None = "Active"
    current_previous: Literal["Current", "Previous", ""] | None = None
    module_date: date | None = None


class CreateTrainingModuleResponse(BaseModel):
    module: TrainingModuleItem
    created_sessions_count: int
    message: str


class ChangeCurrentPreviousRequest(BaseModel):
    current_previous: Literal["Current", "Previous", ""] | None = None


class ChangeCurrentPreviousResponse(BaseModel):
    success: bool
    module_id: UUID
    current_previous: Literal["Current", "Previous", ""] | None = None
    message: str


class SendTrainingSessionsToCommCareResponse(BaseModel):
    success: bool
    module_id: UUID
    project_id: UUID
    affected_sessions: int
    affected_project_roles: int
    message: str
