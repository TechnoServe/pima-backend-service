from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.db.session import SessionLocal
from app.domains.farmers.models import UploadRun
from app.domains.farmers.service import FarmersService

logger = logging.getLogger(__name__)


async def run_uploads_once() -> int:
    processed = 0
    async with SessionLocal() as db:
        svc = FarmersService(db)
        await svc.queue_validated_runs_for_processing(limit=5)

        q = (
            select(UploadRun.id)
            .where(UploadRun.status == "processing")
            .order_by(UploadRun.uploaded_at.asc())
            .limit(5)
        )
        run_ids = list((await db.execute(q)).scalars().all())

    for run_id in run_ids:
        async with SessionLocal() as db:
            svc = FarmersService(db)
            try:
                await svc.process_upload_run(upload_run_id=run_id)
                processed += 1
            except Exception:
                logger.exception("Failed processing upload run %s", run_id)
    return processed


async def uploads_cron_loop(interval_seconds: int = 30):
    logger.info("Starting farmers upload cron worker with interval=%ss", interval_seconds)
    while True:
        try:
            await run_uploads_once()
        except Exception:
            logger.exception("Farmers upload cron tick failed")
        await asyncio.sleep(interval_seconds)
