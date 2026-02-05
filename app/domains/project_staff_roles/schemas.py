from pydantic import BaseModel
from typing import Any, Dict, Optional

class ProjectStaffRolesCreate(BaseModel):
    data: Dict[str, Any]

class ProjectStaffRolesUpdate(BaseModel):
    data: Dict[str, Any]

class ProjectStaffRolesRead(BaseModel):
    data: Dict[str, Any]
