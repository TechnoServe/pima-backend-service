from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reflection import get_table


class HouseholdsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.households = get_table("households")
        self.farmer_groups = get_table("farmer_groups")

    def validate_sampling_schema(self) -> None:
        required_household_cols = {
            "id",
            "farmer_group_id",
            "sampled_for_fv_aa",
            "visited_for_fv_aa",
            "fv_aa_sampling_round",
            "send_to_commcare",
            "send_to_commcare_status",
        }
        missing_household = sorted(c for c in required_household_cols if c not in self.households.c)
        if missing_household:
            raise RuntimeError(
                "households table is missing required FV/AA sampling columns: " + ", ".join(missing_household)
            )

        required_group_cols = {"id", "project_id", "fv_aa_sampling_round"}
        missing_group = sorted(c for c in required_group_cols if c not in self.farmer_groups.c)
        if missing_group:
            raise RuntimeError(
                "farmer_groups table is missing required FV/AA sampling columns: " + ", ".join(missing_group)
            )

    async def list_farmer_groups_for_project(self, project_id: UUID) -> list[dict]:
        stmt = select(self.farmer_groups).where(self.farmer_groups.c.project_id == project_id)
        rows = (await self.db.execute(stmt)).mappings().all()
        return [dict(r) for r in rows]

    async def list_households_for_farmer_groups(self, farmer_group_ids: list[UUID]) -> list[dict]:
        if not farmer_group_ids:
            return []
        stmt = select(self.households).where(self.households.c.farmer_group_id.in_(farmer_group_ids))
        rows = (await self.db.execute(stmt)).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    def group_households_by_farmer_group(households: list[dict]) -> dict[UUID, list[dict]]:
        grouped: dict[UUID, list[dict]] = defaultdict(list)
        for row in households:
            grouped[row["farmer_group_id"]].append(row)
        return grouped

    async def reset_group_households_for_new_round(
        self,
        *,
        farmer_group_id: UUID,
        target_sampling_round: int,
        current_user_id: UUID | None,
    ) -> int:
        values: dict = {
            "visited_for_fv_aa": False,
            "sampled_for_fv_aa": False,
            "fv_aa_sampling_round": target_sampling_round,
        }
        if "send_to_commcare" in self.households.c:
            values["send_to_commcare"] = False
        if "send_to_commcare_status" in self.households.c:
            values["send_to_commcare_status"] = None
        if current_user_id and "last_updated_by_id" in self.households.c:
            values["last_updated_by_id"] = current_user_id
        if "updated_at" in self.households.c:
            values["updated_at"] = datetime.now(timezone.utc)

        stmt = (
            update(self.households)
            .where(self.households.c.farmer_group_id == farmer_group_id)
            .values(**values)
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def mark_households_as_sampled(
        self,
        *,
        household_ids: list[UUID],
        sampling_round: int,
        current_user_id: UUID | None,
    ) -> int:
        if not household_ids:
            return 0

        values: dict = {
            "sampled_for_fv_aa": True,
            "visited_for_fv_aa": False,
            "fv_aa_sampling_round": sampling_round,
            "send_to_commcare": True,
            "send_to_commcare_status": "Pending",
        }
        if current_user_id and "last_updated_by_id" in self.households.c:
            values["last_updated_by_id"] = current_user_id
        if "updated_at" in self.households.c:
            values["updated_at"] = datetime.now(timezone.utc)

        stmt = update(self.households).where(self.households.c.id.in_(household_ids)).values(**values)
        result = await self.db.execute(stmt)
        return result.rowcount or 0
