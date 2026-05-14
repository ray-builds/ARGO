"""Email Intelligence router — API and HTML page endpoints.

API prefix: /api/v1/emails  (registered in main.py)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from app.dependencies import get_access_token, get_current_user
from app.models.user import User

router = APIRouter(tags=["Email Intelligence"])
templates = Jinja2Templates(directory="app/templates")


class EmailTagPatchBody(BaseModel):
    tag: str = Field(..., min_length=1, max_length=32)


# ── API endpoints ─────────────────────────────────────────────────────────────

@router.get("/sync", response_class=JSONResponse)
async def sync_inbox(
    hours_back: int = Query(default=24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
    access_token: str = Depends(get_access_token),
) -> dict[str, Any]:
    """Trigger a mailbox sync for the current user.

    Fetches emails from Microsoft Graph (last `hours_back` hours) and
    classifies them with Claude.
    """
    from app.core.database import get_db_session
    from app.modules.email_intelligence.service import EmailIntelligenceService

    async with get_db_session() as db:
        service = EmailIntelligenceService(db)
        new_count = await service.sync_mailbox(
            access_token=access_token,
            user_email=current_user.email,
            hours_back=hours_back,
        )

    logger.info("Sync triggered by {}: {} new emails", current_user.email, new_count)
    return {"new_emails": new_count, "user_email": current_user.email}


@router.get("/inbox", response_class=JSONResponse)
async def get_inbox(
    tag: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return paginated email list for the current user's inbox."""
    from app.core.database import get_db_session
    from app.modules.email_intelligence.service import EmailIntelligenceService

    async with get_db_session() as db:
        service = EmailIntelligenceService(db)
        emails = await service.get_inbox(
            user_email=current_user.email,
            tag_filter=tag,
            limit=limit,
            offset=offset,
        )
        # Serialize inside the session to avoid DetachedInstanceError on relationships
        return [_email_to_dict(e) for e in emails]


@router.get("/ceo-boxes", response_class=JSONResponse)
async def get_ceo_boxes(
    current_user: User = Depends(get_current_user),
) -> dict[str, list[dict[str, Any]]]:
    """Return CEO emails grouped by tag."""
    from app.core.database import get_db_session
    from app.modules.email_intelligence.service import EmailIntelligenceService

    async with get_db_session() as db:
        service = EmailIntelligenceService(db)
        grouped = await service.get_ceo_emails(user_email=current_user.email)
        return {tag: [_email_to_dict(e) for e in emails] for tag, emails in grouped.items()}


@router.get("/stats", response_class=JSONResponse)
async def get_stats(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return email statistics for the current user."""
    from app.core.database import get_db_session
    from app.modules.email_intelligence.service import EmailIntelligenceService

    async with get_db_session() as db:
        service = EmailIntelligenceService(db)
        stats = await service.get_email_stats(user_email=current_user.email)

    return stats


@router.post("/archive", response_class=JSONResponse)
async def archive_emails(
    body: dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Archive specific emails.

    Request body: {"email_ids": ["id1", "id2", ...]}
    """
    email_ids: list[str] = body.get("email_ids", [])
    if not email_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="email_ids must be a non-empty list",
        )

    from app.core.database import get_db_session
    from app.modules.email_intelligence.service import EmailIntelligenceService

    async with get_db_session() as db:
        service = EmailIntelligenceService(db)
        count = await service.archive_emails(email_ids=email_ids)

    return {"archived": count}


@router.post("/archive-skip", response_class=JSONResponse)
async def archive_skip_emails(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Bulk-archive all SKIP-tagged emails for the current user."""
    from app.core.database import get_db_session
    from app.modules.email_intelligence.service import EmailIntelligenceService

    async with get_db_session() as db:
        service = EmailIntelligenceService(db)
        count = await service.archive_skip_emails(user_email=current_user.email)

    logger.info("Archive-skip for {}: {} emails archived", current_user.email, count)
    return {"archived": count}


@router.post("/{email_id}/read", response_class=JSONResponse)
async def mark_email_read_endpoint(
    email_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark an email as read (local DB; syncs to Microsoft Graph when a token is present)."""
    from app.core.database import get_db_session
    from app.modules.email_intelligence.service import EmailIntelligenceService

    token = getattr(current_user, "graph_access_token", None) or None

    async with get_db_session() as db:
        service = EmailIntelligenceService(db)
        email = await service.mark_email_read(
            email_id=email_id,
            user_email=current_user.email,
            access_token=token,
        )
        if email is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")

    return _email_to_dict(email)


@router.patch("/{email_id}/tag", response_class=JSONResponse)
async def patch_email_tag(
    email_id: str,
    body: EmailTagPatchBody,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update the AI classification tag for an email (local DB only)."""
    from app.core.database import get_db_session
    from app.modules.email_intelligence.prompts import VALID_TAGS
    from app.modules.email_intelligence.service import EmailIntelligenceService

    if body.tag not in VALID_TAGS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid tag. Must be one of: {', '.join(VALID_TAGS)}",
        )

    async with get_db_session() as db:
        service = EmailIntelligenceService(db)
        email = await service.set_email_tag(
            email_id=email_id,
            user_email=current_user.email,
            tag=body.tag,
        )
        if email is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")

    return _email_to_dict(email)


# ── HTML page views ───────────────────────────────────────────────────────────

@router.get("/view/inbox", response_class=HTMLResponse)
async def view_inbox(
    request: Request,
    tag: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """Render the email inbox HTML page."""
    from app.core.database import get_db_session
    from app.modules.email_intelligence.service import EmailIntelligenceService

    async with get_db_session() as db:
        service = EmailIntelligenceService(db)
        emails = await service.get_inbox(
            user_email=current_user.email,
            tag_filter=tag,
            limit=100,
        )
        stats = await service.get_email_stats(user_email=current_user.email)
        emails_payload = [_email_to_dict(e) for e in emails]

    return templates.TemplateResponse(
        "email/inbox.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "email",
            "page_title": "Email Inbox",
            "emails": emails_payload,
            "stats": stats,
            "active_tag": tag or "ALL",
        },
    )


@router.get("/view/ceo-boxes", response_class=HTMLResponse)
async def view_ceo_boxes(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """Render the CEO email boxes HTML page."""
    from app.core.database import get_db_session
    from app.modules.email_intelligence.service import EmailIntelligenceService

    async with get_db_session() as db:
        service = EmailIntelligenceService(db)
        grouped = await service.get_ceo_emails(user_email=current_user.email)
        stats = await service.get_email_stats(user_email=current_user.email)
        # Flatten for card grid; client-side filters by tag
        emails_payload = [
            _email_to_dict(email)
            for emails in grouped.values()
            for email in emails
        ]

    return templates.TemplateResponse(
        "email/ceo_boxes.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "email",
            "page_title": "CEO Inbox Intelligence",
            "emails": emails_payload,
            "stats": stats,
        },
    )


# ── Serialisation helper ──────────────────────────────────────────────────────

def _email_to_dict(email: Any) -> dict[str, Any]:
    """Serialise an Email ORM object to a plain dict for JSON/template use."""
    highlights = []
    if hasattr(email, "highlights") and email.highlights:
        for h in email.highlights:
            highlights.append(
                {
                    "id": h.id,
                    "highlight_text": h.highlight_text,
                    "action_required": h.action_required,
                    "key_conclusion": h.key_conclusion,
                    "model_used": h.model_used,
                    "created_at": h.created_at.isoformat() if h.created_at else None,
                }
            )

    return {
        "id": email.id,
        "graph_message_id": email.graph_message_id,
        "mailbox_user_email": email.mailbox_user_email,
        "sender_email": email.sender_email,
        "sender_name": email.sender_name,
        "subject": email.subject,
        "body_preview": email.body_preview,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "is_read": email.is_read,
        "relevance_score": email.relevance_score,
        "tag": email.tag,
        "is_from_ceo": email.is_from_ceo,
        "is_archived": email.is_archived,
        "processed_at": email.processed_at.isoformat() if email.processed_at else None,
        "highlights": highlights,
        # Convenience fields used by templates
        "ai_summary": highlights[0]["highlight_text"] if highlights else None,
        "action_required": highlights[0]["action_required"] if highlights else None,
        "key_conclusion": highlights[0]["key_conclusion"] if highlights else None,
    }
