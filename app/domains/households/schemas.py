from pydantic import BaseModel
from typing import Any, Dict, Optional

class HouseholdsCreate(BaseModel):
    data: Dict[str, Any]

class HouseholdsUpdate(BaseModel):
    data: Dict[str, Any]

class HouseholdsRead(BaseModel):
    data: Dict[str, Any]
