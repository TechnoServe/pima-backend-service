from __future__ import annotations

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.crud import CRUDRepository
from .models import table


def get_repository() -> CRUDRepository:
    return CRUDRepository(table())


class ObservationResultsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.tbl = table()

    def results_count_subquery(self):
        return (
            select(
                self.tbl.c.observation_id.label("observation_id"),
                func.count().label("results_count"),
            )
            .group_by(self.tbl.c.observation_id)
            .subquery("observation_results_counts")
        )

    async def list_for_observation(self, observation_id):
        sort_col = self.tbl.c.created_at if "created_at" in self.tbl.c else self.tbl.c.id
        rows = (
            await self.db.execute(
                select(
                    self.tbl.c.id,
                    self.tbl.c.criterion if "criterion" in self.tbl.c else literal(None),
                    self.tbl.c.question_key if "question_key" in self.tbl.c else literal(None),
                    self.tbl.c.result_text if "result_text" in self.tbl.c else literal(None),
                    self.tbl.c.result_numeric if "result_numeric" in self.tbl.c else literal(None),
                    self.tbl.c.result_boolean if "result_boolean" in self.tbl.c else literal(None),
                    self.tbl.c.result_url if "result_url" in self.tbl.c else literal(None),
                )
                .where(self.tbl.c.observation_id == observation_id)
                .order_by(sort_col.asc(), self.tbl.c.id.asc())
            )
        ).mappings().all()
        return [dict(r) for r in rows]
