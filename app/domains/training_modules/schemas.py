from pydantic import BaseModel
from typing import Any, Dict, Optional

class TrainingModulesCreate(BaseModel):
    data: Dict[str, Any]

class TrainingModulesUpdate(BaseModel):
    data: Dict[str, Any]

class TrainingModulesRead(BaseModel):
    data: Dict[str, Any]
