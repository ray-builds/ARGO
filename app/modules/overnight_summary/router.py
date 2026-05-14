"""Overnight Summary router — API and HTML page endpoints.

API prefix: /api/v1/overnight
HTML pages: /overnight (registered separately in routes/)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import get_current_user, require_dev_lead
from app.models.user import User

router = APIRouter(tags=["Overnight Summary"])
templates = Jinja2Templates(directory="app/templates")


class OvernightGenerateBody(BaseModel):
    """Optional body for manual summary generation (matches overnight UI)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    briefing_date: Optional[date] = Field(default=None, alias="date")
    send_whatsapp: bool = False


# ── API endpoints ─────────────────────────────────────────────────────────────

@router.get("/summaries", response_class=JSONResponse)
async def list_summaries(
    limit: int = 30,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return paginated list of overnight summaries (newest first)."""
    from app.core.database import get_db_session
    from app.modules.overnight_summary.service import OvernightSummaryService

    async with get_db_session() as db:
        service = OvernightSummaryService(db)
        summaries = await service.get_summaries(limit=limit, offset=offset)

    return [_summary_to_dict(s) for s in summaries]


@router.get("/summaries/{summary_id}", response_class=JSONResponse)
async def get_summary(
    summary_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a single overnight summary by ID."""
    from app.core.database import get_db_session
    from app.modules.overnight_summary.service import OvernightSummaryService

    async with get_db_session() as db:
        service = OvernightSummaryService(db)
        summary = await service.get_summary(summary_id)

    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    return _summary_to_dict(summary, full=True)


@router.post("/generate", response_class=JSONResponse)
async def generate_summary(
    current_user: User = Depends(require_dev_lead),
    body: Optional[OvernightGenerateBody] = Body(default=None),
) -> JSONResponse:
    """Trigger summary generation for a date (defaults to today UTC).

    Idempotent: if a summary already exists for that date, returns it with
    ``was_new: false``. When ``send_whatsapp`` is true, delivery runs only for
    a newly created summary (avoids duplicate sends for existing rows).
    """
    from app.core.database import get_db_session
    from app.modules.overnight_summary.service import OvernightSummaryService

    target_date = (
        body.briefing_date
        if body and body.briefing_date is not None
        else datetime.now(timezone.utc).date()
    )
    send_whatsapp = bool(body and body.send_whatsapp)

    async with get_db_session() as db:
        service = OvernightSummaryService(db)
        existing_before = await service._get_by_date(target_date)
        was_new = existing_before is None
        summary = await service.generate_summary(target_date)

        delivered = False
        if send_whatsapp and was_new:
            delivered = await service.deliver_summary(summary.id)

    logger.info(
        "Manual overnight generate by {}: id={} date={} was_new={} delivered={}",
        current_user.email,
        summary.id,
        target_date,
        was_new,
        delivered,
    )
    payload = _summary_to_dict(summary, full=True)
    payload["was_new"] = was_new
    payload["delivered"] = delivered if send_whatsapp and was_new else False
    return JSONResponse(content=payload)


@router.post("/deliver/{summary_id}", response_class=JSONResponse)
async def deliver_summary(
    summary_id: str,
    current_user: User = Depends(require_dev_lead),
) -> dict[str, Any]:
    """Re-deliver an existing summary via WhatsApp / email."""
    from app.core.database import get_db_session
    from app.modules.overnight_summary.service import OvernightSummaryService

    async with get_db_session() as db:
        service = OvernightSummaryService(db)
        summary = await service.get_summary(summary_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Summary not found")
        delivered = await service.deliver_summary(summary_id)

    return {"delivered": delivered, "summary_id": summary_id}


@router.get("/latest", response_class=JSONResponse)
async def get_latest_summary(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the most recent overnight summary."""
    from app.core.database import get_db_session
    from app.modules.overnight_summary.service import OvernightSummaryService

    async with get_db_session() as db:
        service = OvernightSummaryService(db)
        summary = await service.get_latest_summary()
        if summary is None:
            raise HTTPException(status_code=404, detail="No summaries found")

    return _summary_to_dict(summary, full=True)


@router.get("/status", response_class=JSONResponse)
async def scheduler_status(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return scheduler status and last delivery info."""
    from app.core.database import get_db_session
    from app.modules.overnight_summary.service import OvernightSummaryService
    from app.core.scheduler import get_scheduler

    async with get_db_session() as db:
        service = OvernightSummaryService(db)
        latest = await service.get_latest_summary()

    scheduler = get_scheduler()
    scheduler_running = scheduler is not None and scheduler.running if scheduler else False

    last_delivery: dict[str, Any] | None = None
    if latest is not None:
        last_delivery = {
            "id": latest.id,
            "date": latest.summary_date.isoformat(),
            "whatsapp_delivered": latest.whatsapp_delivered,
            "email_delivered": latest.email_delivered,
            "whatsapp_error": latest.whatsapp_error,
            "email_error": latest.email_error,
        }

    return {
        "scheduler_running": scheduler_running,
        "cron_schedule": "03:30 Europe/London daily",
        "last_delivery": last_delivery,
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
    }


# ── HTML page ─────────────────────────────────────────────────────────────────

@router.get("/view", response_class=HTMLResponse)
async def overnight_view(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """Render the overnight summaries HTML page."""
    from app.core.database import get_db_session
    from app.modules.overnight_summary.service import OvernightSummaryService

    async with get_db_session() as db:
        service = OvernightSummaryService(db)
        summaries = await service.get_summaries(limit=30)

    return templates.TemplateResponse(
        "overnight/summaries.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "overnight",
            "page_title": "Morning Briefing",
            "summaries": [_summary_to_dict(s, full=True) for s in summaries],
        },
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _summary_to_dict(summary: Any, full: bool = False) -> dict[str, Any]:
    """Serialise an OvernightSummary ORM object to a plain dict."""
    d: dict[str, Any] = {
        "id": summary.id,
        "summary_date": summary.summary_date.isoformat(),
        "executive_summary": summary.executive_summary,
        "whatsapp_delivered": summary.whatsapp_delivered,
        "email_delivered": summary.email_delivered,
        "created_at": summary.created_at.isoformat() if summary.created_at else None,
    }
    if full:
        d.update(
            {
                "coverage_start": summary.coverage_start.isoformat(),
                "coverage_end": summary.coverage_end.isoformat(),
                "full_briefing_text": summary.full_briefing_text,
                "email_section": _parse_json_field(summary.email_section),
                "market_moves_section": _parse_json_field(summary.market_moves_section),
                "news_section": _parse_json_field(summary.news_section),
                "macro_section": summary.macro_section,
                "whatsapp_error": summary.whatsapp_error,
                "email_error": summary.email_error,
                "model_used": summary.model_used,
                "whatsapp_delivered_at": (
                    summary.whatsapp_delivered_at.isoformat()
                    if summary.whatsapp_delivered_at
                    else None
                ),
                "email_delivered_at": (
                    summary.email_delivered_at.isoformat()
                    if summary.email_delivered_at
                    else None
                ),
            }
        )
    return d


def _parse_json_field(value: str | None) -> Any:
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
