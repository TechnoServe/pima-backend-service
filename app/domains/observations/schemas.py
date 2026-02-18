from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int


class DemoPlotObservationItem(BaseModel):
    id: UUID
    observation_type: Optional[str] = None
    observation_date: Optional[date] = None
    location_gps_latitude: Optional[float] = None
    location_gps_longitude: Optional[float] = None
    location_gps_altitude: Optional[float] = None
    female_attendees: Optional[int] = None
    male_attendees: Optional[int] = None
    total_attendees: Optional[int] = None
    training_group_name: Optional[str] = None
    observer_name: Optional[str] = None
    trainer_name: Optional[str] = None
    results_count: int = 0


class DemoPlotObservationsResponse(BaseModel):
    data: list[DemoPlotObservationItem]
    pagination: PaginationMeta


class DemoPlotObservationStatsResponse(BaseModel):
    total: int
    this_month: int
    unique_training_groups: int
    pct_with_results: float


class DemoPlotObservationFiltersResponse(BaseModel):
    observation_types: list[str]


class ObservationResultItem(BaseModel):
    id: UUID
    criterion: Optional[str] = None
    question_key: Optional[str] = None
    result_text: Optional[str] = None
    result_numeric: Optional[float] = None
    result_boolean: Optional[bool] = None
    result_url: Optional[str] = None


class DemoPlotObservationDetail(BaseModel):
    id: UUID
    observation_type: Optional[str] = None
    observation_date: Optional[date] = None
    location_gps_latitude: Optional[float] = None
    location_gps_longitude: Optional[float] = None
    location_gps_altitude: Optional[float] = None
    female_attendees: Optional[int] = None
    male_attendees: Optional[int] = None
    total_attendees: Optional[int] = None
    training_group_name: Optional[str] = None
    observer_name: Optional[str] = None
    trainer_name: Optional[str] = None


class DemoPlotObservationDetailResponse(BaseModel):
    observation: DemoPlotObservationDetail
    results: list[ObservationResultItem]


class DemoPlotObservationListParams(BaseModel):
    project_id: UUID
    date_from: date | None = None
    date_to: date | None = None
    observation_type: str | None = None
    search: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=200)
    sort_by: str = "observation_date"
    sort_dir: str = "desc"
