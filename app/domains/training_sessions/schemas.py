from pydantic import BaseModel
from typing import Any, Dict, Optional

class TrainingSessionsCreate(BaseModel):
    data: Dict[str, Any]

class TrainingSessionsUpdate(BaseModel):
    data: Dict[str, Any]

class TrainingSessionsRead(BaseModel):
    data: Dict[str, Any]
