from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


async def run_interval_scheduler(
    job: Callable[[], Awaitable[None]],
    *,
    interval_minutes: int,
    job_id: str = "match_checker",
) -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        job,
        trigger="interval",
        minutes=interval_minutes,
        id=job_id,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info("Scheduler started. Checking every %s minutes.", interval_minutes)

    await job()

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
        scheduler.shutdown()
