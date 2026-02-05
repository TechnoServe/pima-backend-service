from pydantic import BaseModel
from typing import Any, Dict, Optional

class WetmillsCreate(BaseModel):
    data: Dict[str, Any]

class WetmillsUpdate(BaseModel):
    data: Dict[str, Any]

class WetmillsRead(BaseModel):
    data: Dict[str, Any]
