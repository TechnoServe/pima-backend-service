from __future__ import annotations
from typing import Any, Dict, Iterable, Optional, Tuple, List
from sqlalchemy import Table, select, func, update, insert, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.pagination import Page, compute_pages
from app.shared.responses import to_dict
from app.shared.exceptions import NotFound, BadRequest
from app.shared.scoping import apply_project_scope

def _pk_col(table: Table):
    pk_cols = list(table.primary_key.columns)
    if not pk_cols:
        # common fallback
        if "id" in table.c:
            return table.c.id
        raise RuntimeError(f"Table {table.name} has no primary key")
    return pk_cols[0]

def _soft_delete_supported(table: Table) -> bool:
    return "is_deleted" in table.c or "deleted_at" in table.c

class CRUDRepository:
    def __init__(self, table: Table):
        self.table = table
        self.pk = _pk_col(table)

    def base_select(self) -> Select:
        stmt = select(self.table)
        # Soft delete filter
        if "is_deleted" in self.table.c:
            stmt = stmt.where(self.table.c.is_deleted == False)  # noqa: E712
        return stmt

    async def list(
        self,
        session: AsyncSession,
        *,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        sort: Optional[str] = None,
        order: str = "desc",
        allowed_project_ids: Optional[Iterable[str]] = None,
    ) -> Page[Dict[str, Any]]:
        stmt = self.base_select()

        if allowed_project_ids is not None:
            stmt = apply_project_scope(stmt, self.table, allowed_project_ids)

        if search:
            # naive search on common fields if they exist
            like = f"%{search}%"
            conditions = []
            for field in ["name", "project_name", "program_name", "email", "first_name", "last_name", "tns_id", "sf_id"]:
                if field in self.table.c:
                    conditions.append(self.table.c[field].ilike(like))
            if conditions:
                from sqlalchemy import or_
                stmt = stmt.where(or_(*conditions))

        if sort and sort in self.table.c:
            col = self.table.c[sort]
            if order.lower() == "asc":
                stmt = stmt.order_by(col.asc())
            else:
                stmt = stmt.order_by(col.desc())
        else:
            # Default order by created_at if exists else pk desc
            if "created_at" in self.table.c:
                stmt = stmt.order_by(self.table.c.created_at.desc())
            else:
                stmt = stmt.order_by(self.pk.desc())

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar_one()

        stmt = stmt.limit(page_size).offset((page - 1) * page_size)
        res = await session.execute(stmt)
        rows = res.fetchall()
        items = [to_dict(r[0] if isinstance(r, tuple) else (r[0] if hasattr(r, '__len__') and len(r)==1 else r)) for r in rows]
        return Page(items=items, page=page, page_size=page_size, total=total, pages=compute_pages(total, page_size))

    async def get(
        self,
        session: AsyncSession,
        entity_id: Any,
        *,
        allowed_project_ids: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        stmt = self.base_select().where(self.pk == entity_id)
        if allowed_project_ids is not None:
            stmt = apply_project_scope(stmt, self.table, allowed_project_ids)
        res = await session.execute(stmt)
        row = res.first()
        if not row:
            raise NotFound(f"{self.table.name} not found")
        # row is a Row with one element (table row)
        return to_dict(row[0] if isinstance(row, tuple) else row)

    async def create(self, session: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise BadRequest("Invalid payload")
        stmt = insert(self.table).values(**data).returning(self.table)
        res = await session.execute(stmt)
        await session.commit()
        row = res.first()
        return to_dict(row[0] if isinstance(row, tuple) else row)

    async def update(
        self,
        session: AsyncSession,
        entity_id: Any,
        data: Dict[str, Any],
        *,
        allowed_project_ids: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise BadRequest("Invalid payload")
        # Ensure entity exists and within scope
        _ = await self.get(session, entity_id, allowed_project_ids=allowed_project_ids)

        stmt = update(self.table).where(self.pk == entity_id).values(**data).returning(self.table)
        res = await session.execute(stmt)
        await session.commit()
        row = res.first()
        return to_dict(row[0] if isinstance(row, tuple) else row)

    async def delete(
        self,
        session: AsyncSession,
        entity_id: Any,
        *,
        allowed_project_ids: Optional[Iterable[str]] = None,
    ) -> None:
        # Ensure entity exists and within scope
        _ = await self.get(session, entity_id, allowed_project_ids=allowed_project_ids)

        if "is_deleted" in self.table.c:
            stmt = update(self.table).where(self.pk == entity_id).values(is_deleted=True)
            if "deleted_at" in self.table.c:
                from sqlalchemy import func as sa_func
                stmt = stmt.values(deleted_at=sa_func.now())
        else:
            stmt = delete(self.table).where(self.pk == entity_id)

        await session.execute(stmt)
        await session.commit()
