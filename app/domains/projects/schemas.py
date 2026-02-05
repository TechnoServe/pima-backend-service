from pydantic import BaseModel
from typing import Any, Dict, Optional

class ProjectsCreate(BaseModel):
    data: Dict[str, Any]

class ProjectsUpdate(BaseModel):
    data: Dict[str, Any]

class ProjectsRead(BaseModel):
    data: Dict[str, Any]
