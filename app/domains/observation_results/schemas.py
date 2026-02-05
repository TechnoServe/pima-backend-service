from pydantic import BaseModel
from typing import Any, Dict, Optional

class ObservationResultsCreate(BaseModel):
    data: Dict[str, Any]

class ObservationResultsUpdate(BaseModel):
    data: Dict[str, Any]

class ObservationResultsRead(BaseModel):
    data: Dict[str, Any]
