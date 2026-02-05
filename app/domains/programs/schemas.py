from typing import Any, Dict, Literal

from pydantic import BaseModel


class ProgramsCreate(BaseModel):
    data: Dict[str, Any]


class ProgramsUpdate(BaseModel):
    data: Dict[str, Any]


class ProgramsRead(BaseModel):
    data: Dict[str, Any]


class ProgramSummaryRead(BaseModel):
    id: str
    name: str
    description: str
    status: Literal["active", "inactive"]
    wetmillsCount: int
    startDate: str
