from pydantic import BaseModel
from typing import Any, Dict, Optional

class FvBestPracticesCreate(BaseModel):
    data: Dict[str, Any]

class FvBestPracticesUpdate(BaseModel):
    data: Dict[str, Any]

class FvBestPracticesRead(BaseModel):
    data: Dict[str, Any]
