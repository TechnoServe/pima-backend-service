from pydantic import BaseModel
from typing import Any, Dict, Optional

class ProgramsCreate(BaseModel):
    data: Dict[str, Any]

class ProgramsUpdate(BaseModel):
    data: Dict[str, Any]

class ProgramsRead(BaseModel):
    data: Dict[str, Any]
