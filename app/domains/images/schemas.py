from pydantic import BaseModel
from typing import Any, Dict, Optional

class ImagesCreate(BaseModel):
    data: Dict[str, Any]

class ImagesUpdate(BaseModel):
    data: Dict[str, Any]

class ImagesRead(BaseModel):
    data: Dict[str, Any]
