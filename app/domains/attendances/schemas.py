from pydantic import BaseModel
from typing import Any, Dict, Optional

class AttendancesCreate(BaseModel):
    data: Dict[str, Any]

class AttendancesUpdate(BaseModel):
    data: Dict[str, Any]

class AttendancesRead(BaseModel):
    data: Dict[str, Any]
