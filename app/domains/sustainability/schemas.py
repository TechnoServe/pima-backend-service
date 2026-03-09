from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SustainabilitySummaryOverviewResponse(BaseModel):
    total_registered_wetmills: int
    total_bas: int


class WetmillVisitsPerWeekItem(BaseModel):
    label: str
    week_start: date
    week_end: date
    visits_count: int


class WetmillVisitsPerWeekResponse(BaseModel):
    items: list[WetmillVisitsPerWeekItem]


class DistributionItem(BaseModel):
    label: str
    value: int


class DistributionResponse(BaseModel):
    items: list[DistributionItem]


class WetmillListItem(BaseModel):
    id: UUID
    wet_mill_unique_id: Optional[str] = None
    commcare_case_id: Optional[str] = None
    name: Optional[str] = None
    mill_status: Optional[str] = None
    exporting_status: Optional[str] = None
    programme: Optional[str] = None
    country: Optional[str] = None
    manager_name: Optional[str] = None
    manager_role: Optional[str] = None
    registration_date: Optional[date] = None
    ownership_type: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PaginatedWetmillsResponse(BaseModel):
    items: list[WetmillListItem]
    total: int
    page: int
    page_size: int


class WetmillsFilterOptionsResponse(BaseModel):
    countries: list[str]
    exporting_statuses: list[str]
    mill_statuses: list[str]
    ownership_types: list[str]
