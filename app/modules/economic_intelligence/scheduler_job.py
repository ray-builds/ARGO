"""Section 8 scheduler jobs."""
from __future__ import annotations

from loguru import logger

from app.services.economic_calendar_service import track_central_bank_language


async def run_econ_alert() -> int:
    """Existing morning econ alert job placeholder."""
    logger.info("Section 8 econ alert heartbeat")
    return 0


async def run_central_bank_tracker() -> dict:
    """Weekly central bank language tracking job."""
    result = await track_central_bank_language()
    logger.info("Section 8 central bank tracker completed for {} banks", len(result))
    return result

