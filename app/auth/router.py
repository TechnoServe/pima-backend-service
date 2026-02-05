from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.db.session import get_session
from app.db.reflection import get_table
from app.auth.security import verify_password, hash_password, create_access_token
from app.shared.exceptions import Unauthorized
from app.auth.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict | None = None

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)):
    users = get_table("users")
    res = await session.execute(select(users).where(users.c.email == payload.email))
    row = res.first()
    if not row:
        raise Unauthorized("Invalid credentials")
    user = row[0] if isinstance(row, tuple) else row
    user_dict = dict(user._mapping) if hasattr(user, "_mapping") else dict(user)

    stored = user_dict.get("password") or ""
    if not verify_password(payload.password, stored):
        raise Unauthorized("Invalid credentials")

    # If plain password, upgrade to bcrypt
    if stored and not (stored.startswith("$argon2$")):
        hashed = hash_password(payload.password)
        await session.execute(update(users).where(users.c.id == user_dict["id"]).values(password=hashed))
        await session.commit()

    token = create_access_token(str(user_dict["id"]), extra={"role": user_dict.get("user_role")})
    safe_user = {k: v for k, v in user_dict.items() if k not in {"password"}}
    return TokenResponse(access_token=token, user=safe_user)

# Endpoint to verify token and return user info
@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    # Return user info without sensitive fields
    safe_user = {k: v for k, v in current_user.items() if k not in {"password"}}
    return safe_user
