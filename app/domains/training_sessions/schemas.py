from pydantic import BaseModel
from typing import Any, Dict, Optional
from uuid import UUID

class TrainingSessionsCreate(BaseModel):
    data: Dict[str, Any]

class TrainingSessionsUpdate(BaseModel):
    data: Dict[str, Any]

class TrainingSessionsRead(BaseModel):
    data: Dict[str, Any]


class RunWeeklySamplingRequest(BaseModel):
    project_id: Optional[UUID] = None


class RunWeeklySamplingResponse(BaseModel):
    week_start: str
    week_end: str
    active_projects_considered: int
    skipped_projects_with_existing_samples: int
    sampled_sessions: int
    sampled_trainers: int
