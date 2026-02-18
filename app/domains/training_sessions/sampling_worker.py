from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.db.session import SessionLocal
from app.domains.training_sessions.sampling_service import TrainingSessionSamplingService

logger = logging.getLogger(__name__)


async def run_training_session_sampling_once() -> dict:
    async with SessionLocal() as db:
        service = TrainingSessionSamplingService(db)
        result = await service.run_weekly_sampling()

    return {
        "week_start": result.week_start.isoformat(),
        "week_end": result.week_end.isoformat(),
        "active_projects_considered": result.active_projects_considered,
        "skipped_projects_with_existing_samples": result.skipped_projects_with_existing_samples,
        "sampled_sessions": result.sampled_sessions,
        "sampled_trainers": result.sampled_trainers,
    }


async def training_session_sampling_cron_loop(poll_interval_seconds: int = 60):
    logger.info("Starting training session weekly sampling worker")
    last_processed_week_start: str | None = None

    while True:
        try:
            now = datetime.now()
            if now.weekday() == 0 and now.hour == 1:
                async with SessionLocal() as db:
                    service = TrainingSessionSamplingService(db)
                    week_start, _ = service.previous_week_window()
                    week_key = week_start.isoformat()
                    if week_key != last_processed_week_start:
                        result = await service.run_weekly_sampling()
                        last_processed_week_start = week_key
                        logger.info(
                            "Weekly training session sampling completed: week=%s..%s sampled_sessions=%s sampled_trainers=%s",
                            result.week_start,
                            result.week_end,
                            result.sampled_sessions,
                            result.sampled_trainers,
                        )
        except Exception:
            logger.exception("Training session sampling cron tick failed")

        await asyncio.sleep(poll_interval_seconds)
