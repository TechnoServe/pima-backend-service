from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field

class FarmersCreate(BaseModel):
    data: Dict[str, Any]

class FarmersUpdate(BaseModel):
    data: Dict[str, Any]

class FarmersRead(BaseModel):
    data: Dict[str, Any]

# --- Farmers table responses ---

class FarmerListItem(BaseModel):
    id: UUID
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    full_name: str

    gender: Optional[str] = None
    age: Optional[int] = None
    phone_number: Optional[str] = None

    tns_id: Optional[str] = None

    farmer_group_id: UUID
    farmer_group_name: Optional[str] = None

    household_id: Optional[UUID] = None
    household_number: Optional[int] = None

    is_primary_household_member: Optional[bool] = None

    location_id: Optional[UUID] = None
    location_name: Optional[str] = None

    farmer_trainer_id: Optional[UUID] = None
    farmer_trainer_name: Optional[str] = None

    business_advisor_id: Optional[UUID] = None
    business_advisor_name: Optional[str] = None

    send_to_commcare: bool
    send_to_commcare_status: Optional[str] = None

    updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

class PaginatedFarmersResponse(BaseModel):
    items: List[FarmerListItem]
    total: int
    page: int
    page_size: int
    total_pages: int

class FarmersSummaryResponse(BaseModel):
    total: int
    pending_commcare: int

# --- Filter options ---
class FilterOption(BaseModel):
    value: str
    label: str

class FarmersFilterOptions(BaseModel):
    genders: List[FilterOption]
    locations: List[FilterOption]
    farmer_groups: List[FilterOption]
    farmer_trainers: List[FilterOption]
    business_advisors: List[FilterOption]

# --- Uploads ---
UploadStatus = Literal["uploading","validating","processing","completed","failed","cancelled"]

class UploadJob(BaseModel):
    id: UUID
    project_id: UUID
    filename: str
    status: UploadStatus
    progress: int

    total_rows: int
    success_count: int
    failed_count: int
    remaining_count: int

    uploaded_by_id: Optional[UUID] = None
    uploaded_by_name: Optional[str] = None
    uploaded_at: datetime
    completed_at: Optional[datetime] = None

    can_retry: bool = False
    parent_upload_id: Optional[UUID] = None

    original_file_url: Optional[str] = None
    error_report_url: Optional[str] = None

class UploadHistoryResponse(BaseModel):
    items: List[UploadJob]
    total: int
    page: int
    page_size: int
    total_pages: int

class FailedRow(BaseModel):
    row_number: int
    farmer_id: Optional[UUID] = None
    farmer_name: Optional[str] = None
    tns_id: Optional[str] = None
    error_type: str
    error_message: str

class UploadValidationWarning(BaseModel):
    type: str
    message: str
    column: Optional[str] = None
    severity: Literal["warning","error"] = "warning"

class UploadValidationResult(BaseModel):
    is_valid: bool
    total_rows: int
    preview_rows: List[Dict[str, Any]]
    warnings: List[UploadValidationWarning] = []
    errors: List[UploadValidationWarning] = []

class RetryUploadRequest(BaseModel):
    mode: Literal["failed_only","all"] = "failed_only"

# --- CommCare flagging ---
class SendToCommcareResponse(BaseModel):
    flagged_count: int
