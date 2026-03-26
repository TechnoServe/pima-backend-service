"""Service layer for `households`."""
from __future__ import annotations

import random
from collections.abc import MutableSequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .repository import HouseholdsRepository

_SPECIAL_TARGET_PROJECT_ID = "a0E9J000000L53sUAC"


class HouseholdSamplingService:
    def __init__(self, db: AsyncSession, *, rng: random.Random | None = None, repo: HouseholdsRepository | None = None):
        self.db = db
        self.repo = repo or HouseholdsRepository(db)
        self.rng = rng or random.Random()

    @staticmethod
    def _sampling_target(project_id: UUID | str) -> int:
        return 6 if str(project_id) == _SPECIAL_TARGET_PROJECT_ID else 4

    def _shuffle_in_place(self, values: MutableSequence[dict]) -> None:
        self.rng.shuffle(values)

    async def sample_households_for_project(
        self,
        *,
        project_id: UUID,
        current_user_id: UUID | None = None,
    ) -> list[UUID]:
        self.repo.validate_sampling_schema()

        # 1. Get all farmer groups for the project, and all their households
        farmer_groups = await self.repo.list_farmer_groups_for_project(project_id) # Get all farmer groups for the project
        farmer_group_ids = [fg["id"] for fg in farmer_groups]
        households = await self.repo.list_households_for_farmer_groups(farmer_group_ids) # Get all households for those farmer groups
        households_by_group = self.repo.group_households_by_farmer_group(households) # Group households by their farmer group

        target = self._sampling_target(project_id) # Sampling Target by group
        sampled_household_ids: list[UUID] = [] # This will hold the final list of sampled household

        # 2. For each farmer group, determine which households to sample based on the sampling logic
        for farmer_group in farmer_groups:
            farmer_group_id = farmer_group["id"]
            group_round = int(farmer_group.get("fv_aa_sampling_round") or 0)
            group_households = households_by_group.get(farmer_group_id, [])
            if not group_households: # If there are no households in the group, skip it
                continue

            # 2. 1 If all households in the group have been visited, 
            # increment the group's sampling round and reset all households 
            # to be eligible for sampling in the new round
            all_visited = all(bool(h.get("visited_for_fv_aa")) for h in group_households)
            if all_visited:
                group_round = await self.repo.increment_farmer_group_sampling_round(farmer_group_id)
                await self.repo.reset_group_households_for_new_round(
                    farmer_group_id=farmer_group_id,
                    target_sampling_round=group_round,
                    current_user_id=current_user_id,
                )
                for household in group_households:
                    household["visited_for_fv_aa"] = False
                    household["sampled_for_fv_aa"] = False
                    household["fv_aa_sampling_round"] = group_round


            # 2.2 Sample households for the group, prioritizing those that have been sampled but not visited yet,
            already_sampled_unvisited = [
                h for h in group_households if bool(h.get("sampled_for_fv_aa")) and not bool(h.get("visited_for_fv_aa"))
            ]
            
            # 2.3 If more households need to be sampled to meet the target, 
            # sample from the remaining eligible households that have not been sampled yet, 
            # ensuring that households that have been sampled in previous rounds are prioritized 
            # over those that have never been sampled.
            eligible = [
                h
                for h in group_households
                if int(h.get("fv_aa_sampling_round") or 0) < group_round
                and not bool(h.get("sampled_for_fv_aa"))
                and not bool(h.get("visited_for_fv_aa"))
            ]

            final_sample = list(already_sampled_unvisited)
            if len(final_sample) < target: # If we still need more households to meet the target, and there are eligible households to sample from
                remaining = target - len(final_sample)
                self._shuffle_in_place(eligible)
                final_sample.extend(eligible[:remaining])

            # 3. Mark the selected households as sampled in the database, 
            # and add their IDs to the final list of sampled household IDs
            selected_ids = [h["id"] for h in final_sample]
            if selected_ids:
                samples = await self.repo.mark_households_as_sampled(
                    household_ids=selected_ids,
                    sampling_round=group_round,
                    current_user_id=current_user_id,
                )
                sampled_household_ids.extend(selected_ids)

        return sampled_household_ids
