"""APScheduler job for the daily overnight briefing.

Scheduled at 03:30 Europe/London by app.core.scheduler.
Never crashes — all exceptions are caught and a failure alert is attempted.
"""
from __future__ import annotations

from loguru import logger


async def run_overnight_summary() -> None:
    """Generate and deliver the overnight briefing.

    Called by APScheduler at 03:30 Europe/London (daily).
    On any unhandled exception: logs the traceback and attempts a
    best-effort failure-alert email to the CEO.
    """
    from app.core.database import get_db_session
    from app.modules.overnight_summary.service import OvernightSummaryService

    logger.info("Overnight summary job starting...")

    try:
        async with get_db_session() as db:
            service = OvernightSummaryService(db)
            summary = await service.generate_summary()
            delivered = await service.deliver_summary(summary.id)

        logger.info(
            "Overnight summary job completed: id={} delivered={}",
            summary.id,
            delivered,
        )

    except Exception as exc:
        logger.exception("Overnight summary job FAILED: {}", exc)

        # Best-effort failure alert — never let this raise
        try:
            await _send_failure_alert(str(exc))
        except Exception as alert_exc:
            logger.error("Failure alert also failed: {}", alert_exc)


async def _send_failure_alert(error_message: str) -> None:
    """Send a failure notification email to the CEO.

    Uses the first available Graph-authenticated user as sender.
    Silently exits if no token is available.
    """
    from datetime import datetime, timezone

    from app.config import get_settings
    from app.core.database import get_db_session
    from app.models.user import User
    from sqlalchemy import select

    settings = get_settings()

    async with get_db_session() as db:
        result = await db.execute(
            select(User)
            .where(User.graph_access_token.isnot(None))
            .limit(1)
        )
        sender_user = result.scalar_one_or_none()

    if sender_user is None or not sender_user.graph_access_token:
        logger.warning("No Graph token available for failure alert")
        return

    from app.core.graph_client import GraphClient

    graph = GraphClient(sender_user.graph_access_token)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    await graph.send_email(
        from_email=sender_user.email,
        to_email=settings.ceo_email,
        subject=f"ARGO ALERT: Overnight summary failed — {ts}",
        body_html=(
            f"<p>The ARGO overnight summary job failed at {ts}.</p>"
            f"<p><strong>Error:</strong> {error_message}</p>"
            "<p>Please check the application logs for full details.</p>"
        ),
    )
    logger.info("Failure alert sent to {}", settings.ceo_email)
