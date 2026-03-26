from __future__ import annotations

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_project_access
from app.db.session import get_session
from app.shared.domain_factory import build_crud_router

from .service import HouseholdSamplingService

router = build_crud_router(
    entity="households",
    tags=["households"],
    require_project_scope=False,
)


@router.post("/projects/{project_id}/sample-fv-aa")
async def trigger_project_household_sampling(
    project_id: UUID,
    db: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    await require_project_access(db, user, project_id)
    try:
        sampled_household_ids = await HouseholdSamplingService(db).sample_households_for_project(
            project_id=project_id,
            current_user_id=UUID(str(user["id"])),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {
        "project_id": project_id,
        "sampled_count": len(sampled_household_ids),
        "sampled_household_ids": sampled_household_ids,
        "message": "FV/AA household sampling completed successfully.",
    }
