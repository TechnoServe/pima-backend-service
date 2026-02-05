from __future__ import annotations
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_session
from app.db.reflection import get_table
from app.auth.security import decode_token
from app.shared.exceptions import Unauthorized
from app.core.config import settings
from app.auth.rbac import is_admin

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")

# Get current user from token, and verify against DB
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
):
    # First decode the token to get user ID and role (if present)
    try:
        payload = decode_token(token)
    except Exception:
        raise Unauthorized("Invalid token")

    # Get user ID from payload and fetch user from DB to verify token is valid and user still exists
    user_id = payload.get("sub")
    if not user_id:
        raise Unauthorized("Invalid token")

    users = get_table("users")
    res = await session.execute(select(users).where(users.c.id == user_id))
    row = res.first()
    if not row:
        raise Unauthorized("User not found")

    # Convert SQLAlchemy row to dict
    user = row[0] if isinstance(row, tuple) else row
    user_dict = dict(user._mapping) if hasattr(user, "_mapping") else dict(user)
    return user_dict

async def get_accessible_project_ids(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if is_admin(current_user.get("user_role")):
        return None  # means unrestricted
    psr = get_table("project_staff_roles")
    # status might be enum; assume 'Active'
    stmt = select(psr.c.project_id).where(psr.c.user_id == current_user["id"])
    if "status" in psr.c:
        stmt = stmt.where(psr.c.status == "Active")
    res = await session.execute(stmt)
    return [r[0] for r in res.fetchall()]

async def require_write_access(
    current_user=Depends(get_current_user),
):
    from app.auth.rbac import ensure_can_write
    ensure_can_write(current_user.get("user_role"))
    return current_user
