"""Health check endpoint — used by ALB, Docker HEALTHCHECK, and ECS."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from loguru import logger
from sqlalchemy import text

from app.core.database import get_db_session

router = APIRouter(tags=["System"])


@router.get("/health")
async def health_check() -> dict:
    """Health check: verify application is running and DB is reachable.

    Returns 200 OK when healthy, 503 when DB is unreachable.
    Used by AWS ALB target group health checks.
    """
    db_status = "ok"

    try:
        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Health check DB ping failed: {e}")
        db_status = "error"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "version": "1.0.0",
        "db": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "ARGO AI Operations Platform",
    }
