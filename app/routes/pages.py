"""HTML page routes for all ARGO modules.

Each route renders the appropriate Jinja2 template for the module's
main view. These are the browser-facing URLs linked from the sidebar.
API data is loaded client-side via JavaScript fetch() calls.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from app.dependencies import get_current_user_optional
from app.models.user import User

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def _redirect_if_unauthenticated(current_user: User | None, dest: str = "/login"):
    """Return a redirect response if user is not authenticated, else None."""
    if not current_user:
        return RedirectResponse(url=dest, status_code=302)
    return None


# ── Email Intelligence ────────────────────────────────────────────────────────

@router.get("/email", response_class=HTMLResponse)
async def email_page(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render the email inbox page."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    return templates.TemplateResponse(
        "email/inbox.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "email",
            "page_title": "Email Inbox",
        },
    )


@router.get("/email/{email_id}", response_class=HTMLResponse)
async def email_detail_page(
    email_id: str,
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render an individual email detail page."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    return templates.TemplateResponse(
        "email/detail.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "email",
            "page_title": "Email",
            "email_id": email_id,
        },
    )


# ── Overnight Summary ─────────────────────────────────────────────────────────

@router.get("/overnight", response_class=HTMLResponse)
async def overnight_page(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render the overnight summaries list page."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    summaries = []
    try:
        from app.core.database import get_db_session
        from app.modules.overnight_summary.service import OvernightSummaryService

        async with get_db_session() as db:
            service = OvernightSummaryService(db)
            summaries = await service.get_summaries(limit=30)
    except Exception as exc:
        logger.warning("overnight_page: failed to load summaries: {}", exc)

    return templates.TemplateResponse(
        "overnight/summaries.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "overnight",
            "page_title": "Morning Briefing",
            "summaries": summaries,
        },
    )


@router.get("/overnight/{summary_id}", response_class=HTMLResponse)
async def overnight_detail_page(
    summary_id: str,
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render a single overnight summary."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    summary = None
    try:
        from app.core.database import get_db_session
        from app.modules.overnight_summary.service import OvernightSummaryService

        async with get_db_session() as db:
            service = OvernightSummaryService(db)
            summary = await service.get_summary(summary_id)
    except Exception as exc:
        logger.warning("overnight_detail_page: {}", exc)

    return templates.TemplateResponse(
        "overnight/detail.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "overnight",
            "page_title": "Overnight Summary",
            "summary": summary,
        },
    )


# ── Meeting Intelligence ──────────────────────────────────────────────────────

@router.get("/meetings", response_class=HTMLResponse)
async def meetings_page(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render the meetings list page."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    return templates.TemplateResponse(
        "meetings/list.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "meetings",
            "page_title": "Meetings",
        },
    )


@router.get("/meetings/{meeting_id}", response_class=HTMLResponse)
async def meeting_detail_page(
    meeting_id: str,
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render a single meeting detail page."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    return templates.TemplateResponse(
        "meetings/detail.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "meetings",
            "page_title": "Meeting",
            "meeting_id": meeting_id,
        },
    )


# ── Research Lake ─────────────────────────────────────────────────────────────

@router.get("/datalake", response_class=HTMLResponse)
async def datalake_page(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render the research data lake page."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    return templates.TemplateResponse(
        "research_lake/list.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "datalake",
            "page_title": "Research Lake",
        },
    )


# ── Portfolio Intelligence ────────────────────────────────────────────────────

@router.get("/portfolio", response_class=HTMLResponse)
async def portfolio_page(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render the portfolio intelligence dashboard."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    return templates.TemplateResponse(
        "portfolio/dashboard.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "portfolio",
            "page_title": "Portfolio Intelligence",
        },
    )


# ── Sales / Client Intelligence ───────────────────────────────────────────────

@router.get("/clients", response_class=HTMLResponse)
async def clients_page(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render the client intelligence list page."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    return templates.TemplateResponse(
        "clients/list.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "clients",
            "page_title": "Client Intelligence",
        },
    )


@router.get("/clients/{client_id}", response_class=HTMLResponse)
async def client_detail_page(
    client_id: str,
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render a single client detail page."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    client = None
    interactions = []
    try:
        from app.core.database import get_db_session
        from app.modules.sales_intelligence.service import SalesIntelligenceService

        async with get_db_session() as db:
            service = SalesIntelligenceService(db)
            client = await service.get_client(client_id)
            interactions = await service.get_interactions(client_id, limit=50)
    except Exception as exc:
        logger.warning("client_detail_page: {}", exc)

    return templates.TemplateResponse(
        "clients/detail.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "clients",
            "page_title": "Client Profile",
            "client": client,
            "interactions": interactions,
        },
    )


# ── Research Intelligence ─────────────────────────────────────────────────────

@router.get("/research", response_class=HTMLResponse)
async def research_page(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render the research intelligence list page."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    return templates.TemplateResponse(
        "research/list.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "research",
            "page_title": "Research Intelligence",
        },
    )


@router.get("/research/{item_id}", response_class=HTMLResponse)
async def research_detail_page(
    item_id: str,
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render a single research item detail page."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    item = None
    try:
        from app.core.database import get_db_session
        from app.modules.research_intelligence.service import ResearchIntelligenceService

        async with get_db_session() as db:
            service = ResearchIntelligenceService(db)
            item = await service.get_research_item(item_id)
    except Exception as exc:
        logger.warning("research_detail_page: {}", exc)

    return templates.TemplateResponse(
        "research/detail.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "research",
            "page_title": "Research Item",
            "item": item,
        },
    )


# ── Economic Intelligence ─────────────────────────────────────────────────────

@router.get("/econ", response_class=HTMLResponse)
async def econ_page(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render the economic calendar page."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    return templates.TemplateResponse(
        "economic/calendar.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "econ",
            "page_title": "Economic Calendar",
        },
    )


# ── AI Assistant ──────────────────────────────────────────────────────────────

@router.get("/assistant", response_class=HTMLResponse)
async def assistant_page(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Render the AI assistant chat interface."""
    redir = _redirect_if_unauthenticated(current_user)
    if redir:
        return redir

    return templates.TemplateResponse(
        "chat/index.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "assistant",
            "page_title": "AI Assistant",
        },
    )
