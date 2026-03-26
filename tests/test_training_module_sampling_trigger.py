from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.domains.training_modules.schemas import CreateTrainingModuleRequest
from app.domains.training_modules.service import TrainingModulesService


class FakeDB:
    def __init__(self):
        self._in_tx = True

    def in_transaction(self):
        return self._in_tx

    async def commit(self):
        return None

    async def rollback(self):
        return None


class FakeRepo:
    def __init__(self, *, sample_flag: bool):
        self.sample_flag = sample_flag
        self.status_updates = []

    async def get_project(self, project_id):
        return {"id": project_id}

    async def get_module_by_project_and_number(self, project_id, module_number):
        return None

    async def normalize_project_current_previous_for_current(self, **kwargs):
        return None

    def build_module_create_data(self, payload_data, user_id):
        return {
            "id": uuid4(),
            "project_id": payload_data["project_id"],
            "sample_fv_aa_households": self.sample_flag,
            "module_name": payload_data["module_name"],
            "module_number": payload_data["module_number"],
        }

    async def create_module(self, module_data):
        return dict(module_data)

    async def list_project_farmer_groups(self, project_id):
        return []

    async def existing_session_farmer_group_ids(self, module_id, group_ids):
        return set()

    def build_training_session_create_data(self, **kwargs):
        return {}

    async def create_training_sessions_for_module(self, *, module_id, sessions_payload):
        return 0

    async def update_sample_fv_aa_households_status(self, *, module_id, status, current_user_id):
        self.status_updates.append(status)


class TrainingModuleSamplingTriggerTests(unittest.IsolatedAsyncioTestCase):
    async def test_sampling_not_triggered_when_flag_false(self):
        db = FakeDB()
        service = TrainingModulesService(db)
        service.repo = FakeRepo(sample_flag=False)

        payload = CreateTrainingModuleRequest(
            project_id=uuid4(),
            module_name="Module",
            module_number=1,
            sample_fv_aa_households=False,
        )

        with patch("app.domains.training_modules.service.HouseholdSamplingService") as sampling_service_cls:
            result = await service.create_training_module(payload=payload, current_user={"id": str(uuid4())})

        self.assertEqual(result["created_sessions_count"], 0)
        sampling_service_cls.assert_not_called()

    async def test_sampling_triggered_when_flag_true(self):
        db = FakeDB()
        service = TrainingModulesService(db)
        service.repo = FakeRepo(sample_flag=True)

        payload = CreateTrainingModuleRequest(
            project_id=uuid4(),
            module_name="Module",
            module_number=1,
            sample_fv_aa_households=True,
        )

        with patch("app.domains.training_modules.service.HouseholdSamplingService") as sampling_service_cls:
            sampling_service = sampling_service_cls.return_value
            sampling_service.sample_households_for_project = AsyncMock(return_value=[])

            await service.create_training_module(payload=payload, current_user={"id": str(uuid4())})

        sampling_service_cls.assert_called_once()
        sampling_service.sample_households_for_project.assert_awaited_once()
        self.assertEqual(service.repo.status_updates, ["Pending", "Complete"])


if __name__ == "__main__":
    unittest.main()
