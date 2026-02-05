from pydantic import BaseModel
from typing import Any, Dict, Optional

class ObservationsCreate(BaseModel):
    data: Dict[str, Any]

class ObservationsUpdate(BaseModel):
    data: Dict[str, Any]

class ObservationsRead(BaseModel):
    data: Dict[str, Any]
