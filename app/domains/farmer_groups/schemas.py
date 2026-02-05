from pydantic import BaseModel
from typing import Any, Dict, Optional

class FarmerGroupsCreate(BaseModel):
    data: Dict[str, Any]

class FarmerGroupsUpdate(BaseModel):
    data: Dict[str, Any]

class FarmerGroupsRead(BaseModel):
    data: Dict[str, Any]
