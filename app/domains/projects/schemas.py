from typing import Any, Dict, Literal

from pydantic import BaseModel


class ProjectsCreate(BaseModel):
    data: Dict[str, Any]


class ProjectsUpdate(BaseModel):
    data: Dict[str, Any]


class ProjectsRead(BaseModel):
    data: Dict[str, Any]


class ProjectSummaryRead(BaseModel):
    id: str
    name: str
    country: str
    status: Literal["active", "inactive"]
    startDate: str
    endDate: str | None = None
    farmersCount: int
    trainersCount: int
