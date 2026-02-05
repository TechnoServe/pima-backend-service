from pydantic import BaseModel
from typing import Any, Dict, Optional

class UsersTempCreate(BaseModel):
    data: Dict[str, Any]

class UsersTempUpdate(BaseModel):
    data: Dict[str, Any]

class UsersTempRead(BaseModel):
    data: Dict[str, Any]
