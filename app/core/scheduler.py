"""APScheduler setup and job registration for ARGO cron jobs."""
from __future__ import annotations

from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger


_TIMEZONE = "Europe/London"

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the module-level APScheduler instance.

    Returns:
        Singleton AsyncIOScheduler configured for Europe/London.
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=_TIMEZONE)
        logger.info("APScheduler created (timezone: {})", _TIMEZONE)
    return _scheduler


def register_overnight_summary_job() -> None:
    """Register the overnight summary cron job.

    Scheduled for 03:30 AM Europe/London daily. Imports the job function
    lazily so partial module implementations don't prevent startup.
    """
    from app.config import get_settings
    settings = get_settings()

    if not settings.enable_overnight_cron:
        logger.info("Overnight cron disabled via ENABLE_OVERNIGHT_CRON setting")
        return

    from app.modules.overnight_summary.scheduler_job import run_overnight_summary

    scheduler = get_scheduler()
    scheduler.add_job(
        run_overnight_summary,
        trigger=CronTrigger(hour=3, minute=30, timezone=_TIMEZONE),
        id="overnight_summary",
        name="Overnight Market Summary",
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )
    logger.info("Overnight summary job registered: daily 03:30 {}", _TIMEZONE)


def register_econ_alert_job() -> None:
    """Register the daily economic calendar alert job at 07:00 London."""
    try:
        from app.modules.economic_intelligence.scheduler_job import run_econ_alert  # noqa: F401
    except ImportError:
        logger.warning("Economic intelligence scheduler_job not found — econ alert not registered")
        return

    scheduler = get_scheduler()
    scheduler.add_job(
        run_econ_alert,
        trigger=CronTrigger(hour=7, minute=0, timezone=_TIMEZONE),
        id="econ_morning_alert",
        name="Economic Calendar Morning Alert",
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )
    logger.info("Econ alert job registered: daily 07:00 {}", _TIMEZONE)


async def start_scheduler() -> None:
    """Start the APScheduler. Called during FastAPI lifespan startup."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started")
    else:
        logger.debug("APScheduler already running")


async def stop_scheduler() -> None:
    """Shutdown APScheduler gracefully. Called during FastAPI lifespan shutdown."""
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")


def get_scheduler_status() -> dict[str, Any]:
    """Return the current scheduler status and registered jobs.

    Returns:
        Dict with keys:
            - running (bool): whether the scheduler is active.
            - jobs (list[dict]): each job's id, name, and next_run_time.
    """
    scheduler = get_scheduler()
    jobs: list[dict[str, Any]] = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
            }
        )
    return {"running": scheduler.running, "jobs": jobs}
