from pydantic import BaseModel
from typing import Any, Dict, Optional

class WvSurveyResponsesCreate(BaseModel):
    data: Dict[str, Any]

class WvSurveyResponsesUpdate(BaseModel):
    data: Dict[str, Any]

class WvSurveyResponsesRead(BaseModel):
    data: Dict[str, Any]
