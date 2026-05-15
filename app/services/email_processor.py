"""Single-email ingestion entry point used by the Graph webhook handler."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.graph_client import GraphClient
from app.models.email import Email, EmailHighlight
from app.models.user import User
from app.prompts.adapters import normalize_email_classification_for_storage


async def _resolve_user_token(db: AsyncSession) -> tuple[Optional[str], Optional[str]]:
    """Return (user_email, access_token) for the first user with a Graph token.

    The current ARGO deployment is single-tenant single-user; in multi-user
    deployments this should be replaced with a per-subscription lookup.
    """
    result = await db.execute(
        select(User).where(User.graph_access_token.is_not(None)).limit(1)
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None, None
    return user.email, user.graph_access_token


async def process_incoming_email(
    email_id: str,
    db: AsyncSession,
    user_email: Optional[str] = None,
    access_token: Optional[str] = None,
) -> Optional[Email]:
    """Fetch ``email_id`` from Microsoft Graph, classify it, and persist it.

    Idempotent: if the email is already stored, returns the existing row.
    Returns ``None`` when no usable Graph token is available.
    """
    # Idempotency check
    existing = await db.execute(
        select(Email).where(Email.graph_message_id == email_id)
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        return found

    if access_token is None or user_email is None:
        user_email, access_token = await _resolve_user_token(db)
    if not access_token or not user_email:
        logger.warning("process_incoming_email({}): no Graph token available", email_id)
        return None

    graph = GraphClient(access_token)
    try:
        msg: dict[str, Any] = await graph.get_message(user_email, email_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Graph fetch failed for {}: {}", email_id, exc)
        return None

    sender_obj = (msg.get("from") or msg.get("sender") or {}).get("emailAddress", {})
    sender_email: str = sender_obj.get("address", "")
    sender_name: str = sender_obj.get("name", "")
    subject: str = msg.get("subject") or "(no subject)"
    body_preview: str = msg.get("bodyPreview", "") or ""
    is_read: bool = bool(msg.get("isRead", False))

    received_raw: str = msg.get("receivedDateTime", "") or ""
    try:
        received_at = datetime.fromisoformat(received_raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        received_at = datetime.now(timezone.utc)

    settings = get_settings()

    classification = await _classify(sender_name, sender_email, subject, body_preview)

    email_obj = Email(
        graph_message_id=email_id,
        mailbox_user_email=user_email,
        sender_email=sender_email,
        sender_name=sender_name or None,
        subject=subject,
        body_preview=body_preview or None,
        received_at=received_at,
        is_read=is_read,
        relevance_score=classification.get("relevance_score"),
        tag=classification.get("tag"),
        is_from_ceo=sender_email.lower() == settings.ceo_email.lower(),
        processed_at=datetime.now(timezone.utc),
    )
    db.add(email_obj)
    await db.flush()

    ai_summary = classification.get("ai_summary")
    if ai_summary:
        from app.core.claude_client import get_claude_client

        db.add(
            EmailHighlight(
                email_id=email_obj.id,
                highlight_text=ai_summary,
                action_required=classification.get("action_required"),
                key_conclusion=classification.get("key_conclusion"),
                model_used=get_claude_client().haiku_model,
            )
        )
    await db.commit()

    # Broadcast to any connected websocket clients
    try:
        from app.services.realtime_inbox import broadcast_new_email

        await broadcast_new_email(user_email, email_obj)
    except Exception as exc:  # noqa: BLE001
        logger.debug("realtime broadcast skipped: {}", exc)

    # Auto-archive to OneDrive (non-blocking on failure).
    try:
        from app.services.onedrive_service import OneDriveService, safe_archive

        onedrive = OneDriveService(access_token)
        await safe_archive(
            onedrive.archive_email(
                {
                    "id": email_obj.graph_message_id,
                    "subject": email_obj.subject,
                    "sender_email": email_obj.sender_email,
                    "sender_name": email_obj.sender_name,
                    "body_preview": email_obj.body_preview,
                    "received_at": email_obj.received_at.isoformat() if email_obj.received_at else None,
                    "timestamp": email_obj.received_at.isoformat() if email_obj.received_at else None,
                    "tag": email_obj.tag,
                    "relevance_score": email_obj.relevance_score,
                    "is_from_ceo": email_obj.is_from_ceo,
                }
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("OneDrive auto-archive skipped: {}", exc)

    return email_obj


async def _classify(
    sender_name: str, sender_email: str, subject: str, body_preview: str
) -> dict[str, Any]:
    from app.core.claude_client import get_claude_client
    from app.modules.email_intelligence.prompts import (
        EMAIL_SCORING_PROMPT,
        EMAIL_SCORING_SYSTEM,
        VALID_TAGS,
    )

    claude = get_claude_client()
    prompt = EMAIL_SCORING_PROMPT.format(
        sender_name=sender_name or "",
        sender_email=sender_email or "",
        subject=subject or "",
        body_text=(body_preview or "")[:2000],
        attachment_list="[]",
        timestamp=datetime.now(timezone.utc).isoformat(),
        thread_count=1,
    )
    try:
        result = await claude.complete_json(
            prompt=prompt, system=EMAIL_SCORING_SYSTEM, use_sonnet=False
        )
        result = normalize_email_classification_for_storage(result)
        tag = result.get("tag", "SKIP")
        if tag not in VALID_TAGS:
            tag = "SKIP"
        result["tag"] = tag
        score = result.get("relevance_score", 50)
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 50
        result["relevance_score"] = max(0, min(100, score))
        for f in ("action_required", "key_conclusion"):
            v = result.get(f)
            if v in (None, "null", "NULL", "", "none", "None"):
                result[f] = None
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("classification failed: {}", exc)
        return {
            "tag": "SKIP",
            "relevance_score": 0,
            "ai_summary": None,
            "action_required": None,
            "key_conclusion": None,
        }
