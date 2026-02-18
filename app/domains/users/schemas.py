from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


UserStatus = Literal["Active", "Inactive"]
SortDir = Literal["asc", "desc"]


class UsersCreate(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: EmailStr
    phone_number: str | None = None
    role: str = Field(min_length=1)
    status: UserStatus = "Active"


class UsersUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone_number: str | None = None
    role: str | None = None
    status: UserStatus | None = None


class ActiveProject(BaseModel):
    id: UUID
    name: str


class UserListItem(BaseModel):
    id: UUID
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    role: str | None = None
    status: str | None = None
    active_project_roles_count: int
    active_projects: list[ActiveProject]
    updated_at: datetime | None = None


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int


class UsersListResponse(BaseModel):
    data: list[UserListItem]
    pagination: PaginationMeta


class UsersStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    assigned_to_project: int


class UserDetailResponse(BaseModel):
    id: UUID
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    role: str | None = None
    status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UsersFiltersResponse(BaseModel):
    roles: list[str]
    statuses: list[str]
