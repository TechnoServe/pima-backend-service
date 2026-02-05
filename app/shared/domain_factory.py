from __future__ import annotations
from typing import Any, Dict, Optional, Iterable, Callable
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.reflection import get_table
from app.shared.crud import CRUDRepository
from app.shared.exceptions import Forbidden, BadRequest
from app.auth.deps import get_current_user, get_accessible_project_ids
from app.auth.rbac import is_admin
from app.shared.project_resolution import resolve_project_id_from_payload

# Hook signatures
BeforeUpdateHook = Callable[[Dict[str, Any], str], Dict[str, Any]]
AfterTrainingModuleUpdateHook = Callable[[AsyncSession, str], None]

def build_crud_router(
    *,
    entity: str,
    tags: list[str],
    require_project_scope: bool = False,
    before_update: Optional[BeforeUpdateHook] = None,
    after_update_training_module: Optional[Callable[[AsyncSession, str], None]] = None,
) -> APIRouter:
    router = APIRouter(prefix=f"/{entity}", tags=tags)
    table = lambda: get_table(entity)
    repo = lambda: CRUDRepository(table())

    @router.get("")
    async def list_items(
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        search: Optional[str] = Query(None),
        sort: Optional[str] = Query(None),
        order: str = Query("desc"),
        session: AsyncSession = Depends(get_session),
        current_user: Dict[str, Any] = Depends(get_current_user),
        accessible_projects: Optional[list[str]] = Depends(get_accessible_project_ids),
    ):
        allowed = None if is_admin(current_user.get("user_role")) else (accessible_projects or [])
        return await repo().list(
            session,
            page=page,
            page_size=page_size,
            search=search,
            sort=sort,
            order=order,
            allowed_project_ids=allowed,
        )

    @router.get("/{item_id}")
    async def get_item(
        item_id: str,
        session: AsyncSession = Depends(get_session),
        current_user: Dict[str, Any] = Depends(get_current_user),
        accessible_projects: Optional[list[str]] = Depends(get_accessible_project_ids),
    ):
        allowed = None if is_admin(current_user.get("user_role")) else (accessible_projects or [])
        return await repo().get(session, item_id, allowed_project_ids=allowed)

    @router.post("")
    async def create_item(
        payload: Dict[str, Any] = Body(...),
        session: AsyncSession = Depends(get_session),
        current_user: Dict[str, Any] = Depends(get_current_user),
        accessible_projects: Optional[list[str]] = Depends(get_accessible_project_ids),
    ):
        # Enforce project assignment if entity is project-scoped
        if not is_admin(current_user.get("user_role")):
            allowed = accessible_projects or []
            project_id = await resolve_project_id_from_payload(entity, payload, session)
            if project_id and project_id not in allowed:
                raise Forbidden("You do not have access to this project")
            if require_project_scope and not project_id:
                raise BadRequest("Unable to resolve project_id for this record")
        return await repo().create(session, payload)

    @router.patch("/{item_id}")
    async def update_item(
        item_id: str,
        payload: Dict[str, Any] = Body(...),
        session: AsyncSession = Depends(get_session),
        current_user: Dict[str, Any] = Depends(get_current_user),
        accessible_projects: Optional[list[str]] = Depends(get_accessible_project_ids),
    ):
        allowed = None if is_admin(current_user.get("user_role")) else (accessible_projects or [])
        data = payload
        if before_update:
            data = before_update(payload, entity)

        updated = await repo().update(session, item_id, data, allowed_project_ids=allowed)

        # special hook: training_modules cascade to commcare flags
        if entity == "training_modules" and after_update_training_module:
            # Determine project_id from updated record
            proj = updated.get("project_id")
            if proj:
                await after_update_training_module(session, str(proj))

        return updated

    @router.delete("/{item_id}")
    async def delete_item(
        item_id: str,
        session: AsyncSession = Depends(get_session),
        current_user: Dict[str, Any] = Depends(get_current_user),
        accessible_projects: Optional[list[str]] = Depends(get_accessible_project_ids),
    ):
        # allow delete only for Super Admin / CI Leadership / Project Manager
        role = (current_user.get("user_role") or "")
        if role not in {"Super Admin", "CI Leadership", "Project Manager"}:
            raise Forbidden("You do not have permission to delete records")
        allowed = None if is_admin(role) else (accessible_projects or [])
        await repo().delete(session, item_id, allowed_project_ids=allowed)
        return {"status": "deleted"}

    return router
