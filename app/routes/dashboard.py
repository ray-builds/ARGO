"""Main dashboard route — serves the ARGO home page with live module stats."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from app.dependencies import get_current_user_optional
from app.models.user import User

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="app/templates")


async def _gather_dashboard_stats() -> dict:
    """Gather summary statistics from all modules for the dashboard.

    Each sub-query is wrapped in its own try/except so a failure in one
    module does not prevent the rest of the dashboard from loading.

    Returns:
        dict with keys: email_unread, email_urgent, position_count,
        total_notional_usd, client_count, follow_ups_due,
        research_count, econ_today_count, has_overnight_summary.
    """
    stats: dict = {
        "email_unread": 0,
        "email_urgent": 0,
        "position_count": 0,
        "total_notional_usd": 0.0,
        "client_count": 0,
        "follow_ups_due": 0,
        "research_count": 0,
        "econ_today_count": 0,
        "has_overnight_summary": False,
        "meetings_this_week": 0,
        "document_count": 0,
    }

    from app.core.database import get_db_session
    from sqlalchemy import select, func

    async with get_db_session() as db:

        # ── Emails ────────────────────────────────────────────────────────────
        try:
            from app.models.email import Email  # type: ignore[import]
            unread_result = await db.execute(
                select(func.count()).where(Email.is_read == False)  # noqa: E712
            )
            stats["email_unread"] = unread_result.scalar() or 0

            urgent_result = await db.execute(
                select(func.count()).where(
                    Email.is_read == False,  # noqa: E712
                    Email.tag == "URGENT",  # type: ignore[attr-defined]
                )
            )
            stats["email_urgent"] = urgent_result.scalar() or 0
        except Exception as exc:
            logger.debug("dashboard stats — email query failed: {}", exc)

        # ── Portfolio positions ───────────────────────────────────────────────
        try:
            from app.models.portfolio import Position
            pos_result = await db.execute(
                select(func.count()).select_from(Position)
            )
            stats["position_count"] = pos_result.scalar() or 0

            notional_result = await db.execute(
                select(func.sum(Position.notional)).select_from(Position)
            )
            stats["total_notional_usd"] = float(notional_result.scalar() or 0)
        except Exception as exc:
            logger.debug("dashboard stats — portfolio query failed: {}", exc)

        # ── Clients ───────────────────────────────────────────────────────────
        try:
            from app.models.client import Client
            from sqlalchemy import or_
            client_result = await db.execute(
                select(func.count()).where(Client.is_active == True)  # noqa: E712
            )
            stats["client_count"] = client_result.scalar() or 0

            # Follow-ups due in next 7 days (clients not contacted in 30+ days)
            cutoff = date.today() - timedelta(days=30)
            followup_result = await db.execute(
                select(func.count()).where(
                    Client.is_active == True,  # noqa: E712
                    or_(
                        Client.last_contact_date < cutoff,
                        Client.last_contact_date.is_(None),
                    ),
                    Client.tier.in_(["investor", "prospect"]),
                )
            )
            stats["follow_ups_due"] = followup_result.scalar() or 0
        except Exception as exc:
            logger.debug("dashboard stats — client query failed: {}", exc)

        # ── Research items ────────────────────────────────────────────────────
        try:
            from app.models.research import ResearchItem
            research_result = await db.execute(
                select(func.count()).select_from(ResearchItem)
            )
            stats["research_count"] = research_result.scalar() or 0
        except Exception as exc:
            logger.debug("dashboard stats — research query failed: {}", exc)

        # ── Economic events today ─────────────────────────────────────────────
        try:
            from app.models.economic import EconomicEvent
            econ_result = await db.execute(
                select(func.count()).where(
                    EconomicEvent.release_date == date.today()
                )
            )
            stats["econ_today_count"] = econ_result.scalar() or 0
        except Exception as exc:
            logger.debug("dashboard stats — econ query failed: {}", exc)

        # ── Overnight summary ─────────────────────────────────────────────────
        try:
            from app.models.summary import OvernightSummary  # type: ignore[import]
            summary_result = await db.execute(
                select(func.count()).where(
                    OvernightSummary.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
                )
            )
            stats["has_overnight_summary"] = (summary_result.scalar() or 0) > 0
        except Exception as exc:
            logger.debug("dashboard stats — overnight query failed: {}", exc)

        # ── Meetings this week ────────────────────────────────────────────────
        try:
            from app.models.meeting import Meeting  # type: ignore[import]
            week_start = datetime.now(timezone.utc) - timedelta(days=7)
            meetings_result = await db.execute(
                select(func.count()).where(
                    Meeting.created_at >= week_start
                )
            )
            stats["meetings_this_week"] = meetings_result.scalar() or 0
        except Exception as exc:
            logger.debug("dashboard stats — meetings query failed: {}", exc)

        # ── Document count ────────────────────────────────────────────────────
        try:
            from app.models.document import Document  # type: ignore[import]
            doc_result = await db.execute(
                select(func.count()).select_from(Document)
            )
            stats["document_count"] = doc_result.scalar() or 0
        except Exception as exc:
            logger.debug("dashboard stats — document query failed: {}", exc)

    return stats


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Main ARGO dashboard.

    Redirects to /login if user is not authenticated.
    Gathers stats from all modules and renders the dashboard with context.
    """
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    stats = await _gather_dashboard_stats()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Dashboard",
            "active_nav": "dashboard",
            **stats,
        },
    )


@router.get("/api/dashboard/stats")
async def dashboard_stats_api(
    current_user: User | None = Depends(get_current_user_optional),
) -> JSONResponse:
    """JSON endpoint for dashboard auto-refresh (called every 60s by the page)."""
    if not current_user:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

    stats = await _gather_dashboard_stats()
    return JSONResponse(content=stats)
