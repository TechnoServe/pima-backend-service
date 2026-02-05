from pydantic import BaseModel
from typing import Any, Dict, Optional

class FarmVisitsCreate(BaseModel):
    data: Dict[str, Any]

class FarmVisitsUpdate(BaseModel):
    data: Dict[str, Any]

class FarmVisitsRead(BaseModel):
    data: Dict[str, Any]
