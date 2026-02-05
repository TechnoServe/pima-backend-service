from pydantic import BaseModel
from typing import Any, Dict, Optional

class FarmersCreate(BaseModel):
    data: Dict[str, Any]

class FarmersUpdate(BaseModel):
    data: Dict[str, Any]

class FarmersRead(BaseModel):
    data: Dict[str, Any]
