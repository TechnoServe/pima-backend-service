from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_accessible_project_ids, get_current_user
from app.auth.rbac import is_admin
from app.db.session import get_session
from app.shared.domain_factory import build_crud_router
from app.shared.exceptions import Forbidden
from .sampling_service import TrainingSessionSamplingService
from .schemas import RunWeeklySamplingRequest, RunWeeklySamplingResponse
from .service import before_update

router = APIRouter(tags=["training_sessions"])

crud_router = build_crud_router(
    entity="training_sessions",
    tags=["training_sessions"],
    require_project_scope=True,
    before_update=before_update,
)

router.include_router(crud_router)


@router.post("/training_sessions/sampling/run", response_model=RunWeeklySamplingResponse)
async def run_training_session_sampling(
    payload: RunWeeklySamplingRequest,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
    accessible_projects: list[str] | None = Depends(get_accessible_project_ids),
):
    if not is_admin(current_user.get("user_role")):
        if payload.project_id is None:
            raise Forbidden("project_id is required for non-admin users")
        allowed = set(accessible_projects or [])
        if str(payload.project_id) not in allowed:
            raise Forbidden("You do not have access to this project")

    service = TrainingSessionSamplingService(session)
    result = await service.run_weekly_sampling(project_id=payload.project_id)

    return RunWeeklySamplingResponse(
        week_start=result.week_start.isoformat(),
        week_end=result.week_end.isoformat(),
        active_projects_considered=result.active_projects_considered,
        skipped_projects_with_existing_samples=result.skipped_projects_with_existing_samples,
        sampled_sessions=result.sampled_sessions,
        sampled_trainers=result.sampled_trainers,
    )
