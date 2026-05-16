"""APScheduler integration: post the daily report at a configured time."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from trading_bot.config import Settings

logger = logging.getLogger(__name__)


def build_scheduler(
    settings: Settings,
    job: Callable[[], Awaitable[None]],
) -> AsyncIOScheduler:
    """Build a scheduler that fires ``job`` daily at the configured time."""
    sched = AsyncIOScheduler(timezone=settings.tz)
    when = settings.schedule_hour_minute
    trigger = CronTrigger(hour=when.hour, minute=when.minute, timezone=settings.tz)
    sched.add_job(
        job,
        trigger=trigger,
        id="daily_report",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 30,
        replace_existing=True,
    )
    logger.info(
        "Scheduled daily_report at %02d:%02d %s",
        when.hour,
        when.minute,
        settings.schedule_tz,
    )
    return sched
