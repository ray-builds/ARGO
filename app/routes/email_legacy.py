"""Legacy singular-prefix email routes (e.g. POST /api/v1/email/fetch).

Clients and docs historically used ``/api/v1/email/*`` while the main
router is mounted at ``/api/v1/emails``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from loguru import logger

from app.dependencies import get_access_token, get_current_user
from app.models.user import User

router = APIRouter(tags=["Email Intelligence (legacy)"])


@router.post("/fetch", response_class=JSONResponse)
async def legacy_fetch_emails(
    hours_back: int = Query(default=24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
    access_token: str = Depends(get_access_token),
) -> dict[str, Any]:
    """Same behaviour as ``GET /api/v1/emails/sync`` (mailbox sync from Graph)."""
    from app.core.database import get_db_session
    from app.modules.email_intelligence.service import EmailIntelligenceService

    async with get_db_session() as db:
        service = EmailIntelligenceService(db)
        new_count = await service.sync_mailbox(
            access_token=access_token,
            user_email=current_user.email,
            hours_back=hours_back,
        )

    logger.info(
        "Legacy POST /email/fetch by {}: {} new emails",
        current_user.email,
        new_count,
    )
    return {
        "new_emails": new_count,
        "user_email": current_user.email,
        "fetched": new_count,
        "new": new_count,
        "processed": new_count,
    }
