from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.api_errors import ConflictError, NotFoundError, ValidationError

from .repository import UsersRepository, VALID_USER_SORTS
from .schemas import UsersCreate, UsersUpdate


class UsersService:
    def __init__(self, db: AsyncSession):
        self.repo = UsersRepository(db)

    async def list_users(
        self,
        *,
        q: str | None,
        status: str | None,
        role: str | None,
        project_id: UUID | None,
        page: int,
        page_size: int,
        sort_by: str,
        sort_dir: str,
    ) -> dict:
        if sort_by not in VALID_USER_SORTS:
            raise ValidationError("Invalid sort_by", details={"allowed": sorted(VALID_USER_SORTS)})
        if sort_dir not in {"asc", "desc"}:
            raise ValidationError("Invalid sort_dir", details={"allowed": ["asc", "desc"]})
        return await self.repo.list_users(
            q=q,
            status=status,
            role=role,
            project_id=project_id,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

    async def stats(self, *, q: str | None, status: str | None, role: str | None, project_id: UUID | None) -> dict:
        return await self.repo.stats(q=q, status=status, role=role, project_id=project_id)

    async def get_user(self, user_id: UUID) -> dict:
        user = await self.repo.get_user(user_id)
        user['role'] = user.get('user_role')  # add role field for backward compatibility
        if not user:
            raise NotFoundError("User not found")
        return user

    async def create_user(self, payload: UsersCreate) -> dict:
        existing = await self.repo.get_user_by_email(payload.email)
        if existing:
            raise ConflictError("User with this email already exists")
        return await self.repo.create_user(payload.model_dump(exclude_none=True))

    async def update_user(self, user_id: UUID, payload: UsersUpdate) -> dict:
        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise ValidationError("No fields provided for update")

        if "email" in data:
            existing = await self.repo.get_user_by_email(data["email"])
            if existing and str(existing.get("id")) != str(user_id):
                raise ConflictError("User with this email already exists")

        updated = await self.repo.update_user(user_id, data)
        if not updated:
            raise NotFoundError("User not found")
        return updated

    async def filters(self) -> dict:
        roles = await self.repo.distinct_roles()
        return {"roles": roles, "statuses": ["Active", "Inactive"]}
