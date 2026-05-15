"""Section 9 morning briefing trigger and status endpoints."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.dependencies import get_current_user
from app.models.summary import OvernightSummary
from app.models.user import User
from app.core.scheduler import get_scheduler_status
from app.core.database import get_db_session
from app.services.morning_briefing_service import generate_morning_briefing

router = APIRouter(prefix="/api/v1/morning-briefing", tags=["morning-briefing"])


@router.post("/run")
async def run_morning_briefing(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Run Section 9 briefing pipeline immediately."""
    token = current_user.graph_access_token or "service-token-placeholder"
    brief = await generate_morning_briefing(datetime.now(UTC), token)
    return {"ok": True, "brief": brief, "requested_by": current_user.email}


@router.get("/status")
async def morning_briefing_status(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return scheduler + latest generated morning brief status."""
    scheduler = get_scheduler_status()
    section9_job = next((j for j in scheduler.get("jobs", []) if j.get("id") == "section9_morning_brief"), None)

    latest = None
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(OvernightSummary).order_by(OvernightSummary.created_at.desc()).limit(1)
            )
            row = result.scalar_one_or_none()
            if row is not None:
                latest = {
                    "id": row.id,
                    "summary_date": row.summary_date.isoformat() if row.summary_date else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
    except RuntimeError:
        latest = None

    return {
        "scheduler_running": scheduler.get("running", False),
        "job": section9_job,
        "latest_summary": latest,
        "requested_by": current_user.email,
    }
