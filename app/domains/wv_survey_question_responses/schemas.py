from pydantic import BaseModel
from typing import Any, Dict, Optional

class WvSurveyQuestionResponsesCreate(BaseModel):
    data: Dict[str, Any]

class WvSurveyQuestionResponsesUpdate(BaseModel):
    data: Dict[str, Any]

class WvSurveyQuestionResponsesRead(BaseModel):
    data: Dict[str, Any]
