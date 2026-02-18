from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectRef(BaseModel):
    id: UUID
    name: str | None = None


class ProjectStaffRoleItem(BaseModel):
    id: UUID
    user_id: UUID
    project: ProjectRef
    role: str
    status: str
    created_at: datetime | None = None


class ProjectStaffRoleListResponse(BaseModel):
    data: list[ProjectStaffRoleItem]


class ProjectStaffRoleCreate(BaseModel):
    user_id: UUID
    project_id: UUID
    role: str = Field(min_length=1)


class ProjectStaffRoleFiltersResponse(BaseModel):
    roles: list[str]
    statuses: list[str]


ProjectStaffRoleStatusFilter = Literal["Active", "Inactive", "All"]
