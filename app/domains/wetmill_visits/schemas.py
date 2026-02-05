from pydantic import BaseModel
from typing import Any, Dict, Optional

class WetmillVisitsCreate(BaseModel):
    data: Dict[str, Any]

class WetmillVisitsUpdate(BaseModel):
    data: Dict[str, Any]

class WetmillVisitsRead(BaseModel):
    data: Dict[str, Any]
