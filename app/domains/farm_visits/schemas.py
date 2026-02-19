from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int


class FarmVisitListItem(BaseModel):
    id: UUID
    date_visited: Optional[date] = None
    farm_visit_type: Optional[str] = None
    visit_comments: Optional[str] = None
    location_gps_latitude: Optional[float] = None
    location_gps_longitude: Optional[float] = None
    location_gps_altitude: Optional[float] = None
    number_of_cuerdas: Optional[float] = None
    number_of_separate_coffee_fields: Optional[int] = None
    field_age: Optional[int] = None
    field_size: Optional[float] = None

    training_group_name: Optional[str] = None
    farmer_tns_id: Optional[str] = None
    farmer_full_name: Optional[str] = None
    farmer_gender: Optional[str] = None
    visiting_staff_name: Optional[str] = None


class FarmVisitsListResponse(BaseModel):
    data: list[FarmVisitListItem]
    pagination: PaginationMeta


class FarmVisitsStatsResponse(BaseModel):
    total: int
    this_month: int
    unique_farmers: int
    unique_training_groups: int


class FarmVisitsFiltersResponse(BaseModel):
    farm_visit_types: list[str]


class FarmVisitsListParams(BaseModel):
    project_id: UUID
    date_from: date | None = None
    date_to: date | None = None
    farm_visit_type: str | None = None
    search: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=200000)
    sort_by: str = "date_visited"
    sort_dir: str = "desc"
