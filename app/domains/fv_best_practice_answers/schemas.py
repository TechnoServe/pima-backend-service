from pydantic import BaseModel
from typing import Any, Dict, Optional

class FvBestPracticeAnswersCreate(BaseModel):
    data: Dict[str, Any]

class FvBestPracticeAnswersUpdate(BaseModel):
    data: Dict[str, Any]

class FvBestPracticeAnswersRead(BaseModel):
    data: Dict[str, Any]
