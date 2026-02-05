from pydantic import BaseModel
from typing import Any, Dict, Optional

class LocationsCreate(BaseModel):
    data: Dict[str, Any]

class LocationsUpdate(BaseModel):
    data: Dict[str, Any]

class LocationsRead(BaseModel):
    data: Dict[str, Any]
