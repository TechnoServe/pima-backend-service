from pydantic import BaseModel
from typing import Any, Dict, Optional

class ChecksCreate(BaseModel):
    data: Dict[str, Any]

class ChecksUpdate(BaseModel):
    data: Dict[str, Any]

class ChecksRead(BaseModel):
    data: Dict[str, Any]
