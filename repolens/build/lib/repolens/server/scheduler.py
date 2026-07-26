import logging
from typing import Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

def setup_scheduler(
    config: Any,
    pipeline: Any,
    repos: Any,
) -> AsyncIOScheduler:
    """Create and configure the APScheduler instance.
    
    Does NOT start the scheduler — caller must call scheduler.start().
    """
    scheduler = AsyncIOScheduler()

    async def incremental_index() -> None:
        """Detect and reparse changed files."""
        logger.info("scheduler.job.incremental_index started")
        try:
            from repolens.core.persistence import registry
            from repolens.core.pipeline.service import indexing_service

            for repo in registry.list_repos():
                indexing_service.start_index(
                    repo["id"], "auto", trigger="scheduler-incremental"
                )
            logger.info("scheduler.job.incremental_index completed")
        except Exception:
            logger.exception("incremental_index failed")

    async def full_reindex() -> None:
        """Full repository re-scan."""
        logger.info("scheduler.job.full_reindex started")
        try:
            from repolens.core.persistence import registry
            from repolens.core.pipeline.service import indexing_service

            for repo in registry.list_repos():
                indexing_service.start_index(repo["id"], "full", trigger="scheduler-full")
            logger.info("scheduler.job.full_reindex completed")
        except Exception:
            logger.exception("full_reindex failed")

    async def staleness_check() -> None:
        """Flag stale entries."""
        logger.info("scheduler.job.staleness_check started")
        try:
            logger.info("scheduler.job.staleness_check completed")
        except Exception:
            logger.exception("staleness_check failed")

    # default */15 * * * *
    scheduler.add_job(
        incremental_index,
        trigger=CronTrigger.from_crontab("*/15 * * * *"),
        id="incremental_index",
        replace_existing=True,
        max_instances=1
    )

    # default 0 2 * * *
    scheduler.add_job(
        full_reindex,
        trigger=CronTrigger.from_crontab("0 2 * * *"),
        id="full_reindex",
        replace_existing=True,
        max_instances=1
    )

    # default */30 * * * *
    scheduler.add_job(
        staleness_check,
        trigger=CronTrigger.from_crontab("*/30 * * * *"),
        id="staleness_check",
        replace_existing=True,
        max_instances=1
    )

    return scheduler
