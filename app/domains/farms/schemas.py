from pydantic import BaseModel
from typing import Any, Dict, Optional

class FarmsCreate(BaseModel):
    data: Dict[str, Any]

class FarmsUpdate(BaseModel):
    data: Dict[str, Any]

class FarmsRead(BaseModel):
    data: Dict[str, Any]
