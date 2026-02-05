from pydantic import BaseModel
from typing import Any, Dict, Optional

class UsersCreate(BaseModel):
    data: Dict[str, Any]

class UsersUpdate(BaseModel):
    data: Dict[str, Any]

class UsersRead(BaseModel):
    data: Dict[str, Any]
