from __future__ import annotations

import random
import unittest
from uuid import uuid4

from app.domains.households.service import HouseholdSamplingService


class FakeHouseholdRepo:
    def __init__(self, farmer_groups: list[dict], households: list[dict]):
        self._farmer_groups = farmer_groups
        self._households = households
        self.resets: list[tuple] = []
        self.sample_marks: list[tuple] = []
        self.increment_calls: list = []

    def validate_sampling_schema(self) -> None:
        return None

    async def list_farmer_groups_for_project(self, project_id):
        return self._farmer_groups

    async def list_households_for_farmer_groups(self, farmer_group_ids):
        return [h for h in self._households if h["farmer_group_id"] in farmer_group_ids]

    @staticmethod
    def group_households_by_farmer_group(households):
        grouped = {}
        for row in households:
            grouped.setdefault(row["farmer_group_id"], []).append(dict(row))
        return grouped

    async def increment_farmer_group_sampling_round(self, farmer_group_id):
        self.increment_calls.append(farmer_group_id)
        for group in self._farmer_groups:
            if group["id"] == farmer_group_id:
                group["fv_aa_sampling_round"] = int(group.get("fv_aa_sampling_round") or 0) + 1
                return group["fv_aa_sampling_round"]
        return 0

    async def reset_group_households_for_new_round(self, *, farmer_group_id, target_sampling_round, current_user_id):
        self.resets.append((farmer_group_id, target_sampling_round, current_user_id))

    async def mark_households_as_sampled(self, *, household_ids, sampling_round, current_user_id):
        self.sample_marks.append((list(household_ids), sampling_round, current_user_id))


class HouseholdSamplingServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_preserves_sampled_unvisited_and_fills_to_four(self):
        g1 = uuid4()
        h_existing = uuid4()
        repo = FakeHouseholdRepo(
            farmer_groups=[{"id": g1, "fv_aa_sampling_round": 2}],
            households=[
                {"id": h_existing, "farmer_group_id": g1, "sampled_for_fv_aa": True, "visited_for_fv_aa": False, "fv_aa_sampling_round": 1},
                {"id": uuid4(), "farmer_group_id": g1, "sampled_for_fv_aa": False, "visited_for_fv_aa": False, "fv_aa_sampling_round": 1},
                {"id": uuid4(), "farmer_group_id": g1, "sampled_for_fv_aa": False, "visited_for_fv_aa": False, "fv_aa_sampling_round": 0},
                {"id": uuid4(), "farmer_group_id": g1, "sampled_for_fv_aa": False, "visited_for_fv_aa": False, "fv_aa_sampling_round": 1},
                {"id": uuid4(), "farmer_group_id": g1, "sampled_for_fv_aa": False, "visited_for_fv_aa": True, "fv_aa_sampling_round": 1},
            ],
        )
        service = HouseholdSamplingService(db=None, repo=repo, rng=random.Random(0))

        sampled = await service.sample_households_for_project(project_id=uuid4())

        self.assertEqual(len(sampled), 4)
        self.assertIn(h_existing, sampled)
        self.assertEqual(len(repo.sample_marks), 1)
        self.assertEqual(repo.sample_marks[0][1], 2)

    async def test_special_project_target_is_six(self):
        g1 = uuid4()
        households = [
            {"id": uuid4(), "farmer_group_id": g1, "sampled_for_fv_aa": False, "visited_for_fv_aa": False, "fv_aa_sampling_round": 0}
            for _ in range(8)
        ]
        repo = FakeHouseholdRepo(farmer_groups=[{"id": g1, "fv_aa_sampling_round": 1}], households=households)
        service = HouseholdSamplingService(db=None, repo=repo, rng=random.Random(1))

        sampled = await service.sample_households_for_project(project_id="a0E9J000000L53sUAC")

        self.assertEqual(len(sampled), 6)

    async def test_reset_happens_when_all_visited(self):
        g1 = uuid4()
        households = [
            {"id": uuid4(), "farmer_group_id": g1, "sampled_for_fv_aa": True, "visited_for_fv_aa": True, "fv_aa_sampling_round": 1},
            {"id": uuid4(), "farmer_group_id": g1, "sampled_for_fv_aa": False, "visited_for_fv_aa": True, "fv_aa_sampling_round": 1},
            {"id": uuid4(), "farmer_group_id": g1, "sampled_for_fv_aa": False, "visited_for_fv_aa": True, "fv_aa_sampling_round": 1},
            {"id": uuid4(), "farmer_group_id": g1, "sampled_for_fv_aa": False, "visited_for_fv_aa": True, "fv_aa_sampling_round": 1},
        ]
        repo = FakeHouseholdRepo(farmer_groups=[{"id": g1, "fv_aa_sampling_round": 2}], households=households)
        service = HouseholdSamplingService(db=None, repo=repo, rng=random.Random(2))

        sampled = await service.sample_households_for_project(project_id=uuid4())

        self.assertEqual(len(repo.resets), 1)
        self.assertEqual(repo.resets[0][1], 3)
        self.assertEqual(len(sampled), 4)

    async def test_only_project_groups_considered(self):
        project_group = uuid4()
        other_group = uuid4()
        repo = FakeHouseholdRepo(
            farmer_groups=[{"id": project_group, "fv_aa_sampling_round": 1}],
            households=[
                {"id": uuid4(), "farmer_group_id": project_group, "sampled_for_fv_aa": False, "visited_for_fv_aa": False, "fv_aa_sampling_round": 0},
                {"id": uuid4(), "farmer_group_id": other_group, "sampled_for_fv_aa": False, "visited_for_fv_aa": False, "fv_aa_sampling_round": 0},
            ],
        )
        service = HouseholdSamplingService(db=None, repo=repo, rng=random.Random(0))

        sampled = await service.sample_households_for_project(project_id=uuid4())

        self.assertEqual(len(sampled), 1)

    async def test_handles_fewer_eligible_than_target(self):
        g1 = uuid4()
        households = [
            {"id": uuid4(), "farmer_group_id": g1, "sampled_for_fv_aa": False, "visited_for_fv_aa": False, "fv_aa_sampling_round": 0},
            {"id": uuid4(), "farmer_group_id": g1, "sampled_for_fv_aa": False, "visited_for_fv_aa": False, "fv_aa_sampling_round": 0},
        ]
        repo = FakeHouseholdRepo(farmer_groups=[{"id": g1, "fv_aa_sampling_round": 1}], households=households)
        service = HouseholdSamplingService(db=None, repo=repo, rng=random.Random(0))

        sampled = await service.sample_households_for_project(project_id=uuid4())

        self.assertEqual(len(sampled), 2)


if __name__ == "__main__":
    unittest.main()
