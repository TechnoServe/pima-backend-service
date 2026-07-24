from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from sqlalchemy import Column, Integer, MetaData, Numeric, Table

from app.domains.farmers.models import UploadRun
from app.domains.farmers.service import FarmersService


class UploadJobRepo:
    def __init__(self, run):
        self.run = run

    async def get_upload_run(self, upload_id):
        return self.run

    async def get_latest_upload_for_project(self, *, project_id):
        return self.run

    async def has_child_upload(self, *, upload_id):
        return False

    async def upload_uploader_name(self, *, uploaded_by_id):
        return "Ada Lovelace" if uploaded_by_id else None


class CommitTrackingDb:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FarmersUploadServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.households = Table(
            "households",
            MetaData(),
            Column("number_of_trees", Integer),
            Column("number_of_coffee_plots", Integer),
            Column("farm_size", Numeric),
        )

    def test_shared_household_metrics_update_all_three_fields(self):
        service = FarmersService(db=None)
        headers = {
            "number_of_trees": 0,
            "number_of_coffee_plots": 1,
            "farm_size": 2,
        }

        with patch("app.domains.farmers.service.T", return_value=self.households):
            metrics = service._household_shared_metrics(
                row=(123, 4, 100),
                header_idx=headers,
            )

        self.assertEqual(
            metrics,
            {
                "number_of_trees": 123,
                "number_of_coffee_plots": 4,
                "farm_size": Decimal("100"),
            },
        )

    def test_empty_shared_household_metrics_clear_existing_values(self):
        service = FarmersService(db=None)
        headers = {
            "number_of_trees": 0,
            "number_of_coffee_plots": 1,
            "farm_size": 2,
        }

        with patch("app.domains.farmers.service.T", return_value=self.households):
            metrics = service._household_shared_metrics(
                row=(None, "", None),
                header_idx=headers,
            )

        self.assertEqual(
            metrics,
            {
                "number_of_trees": None,
                "number_of_coffee_plots": None,
                "farm_size": None,
            },
        )

    async def test_fail_run_is_terminal_and_has_no_remaining_rows(self):
        db = CommitTrackingDb()
        service = FarmersService(db=db)
        run = SimpleNamespace(
            status="processing",
            completed_at=None,
            progress=99,
            total_rows=953,
            failed_count=1,
            remaining_count=3,
            meta={},
        )

        await service._fail_run(run, message="database error")

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.progress, 100)
        self.assertEqual(run.remaining_count, 0)
        self.assertEqual(run.meta["error"], "database error")
        self.assertEqual(db.commits, 1)

    async def test_upload_job_includes_uploader_name(self):
        run = UploadRun(
            id=uuid4(),
            project_id=uuid4(),
            filename="farmers.xlsx",
            status="completed",
            progress=100,
            total_rows=1,
            success_count=1,
            failed_count=0,
            remaining_count=0,
            uploaded_by_id=uuid4(),
            uploaded_at=datetime.utcnow(),
        )
        service = FarmersService(db=None)
        service.repo = UploadJobRepo(run)

        job = await service.get_upload_job(run.id)

        self.assertEqual(job.uploaded_by_id, run.uploaded_by_id)
        self.assertEqual(job.uploaded_by_name, "Ada Lovelace")


if __name__ == "__main__":
    unittest.main()
