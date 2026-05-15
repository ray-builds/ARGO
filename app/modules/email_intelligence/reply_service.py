"""AI-drafted email replies using Claude Sonnet + Microsoft Graph drafts."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.claude_client import get_claude_client
from app.core.graph_client import GraphClient
from app.models.email import Email
from app.prompts.architecture import EMAIL_REPLY_PROMPT, SYSTEM_BASE


VALID_TONES = (
    "FORMAL_CLIENT",
    "COLLEGIAL_PEER",
    "DIRECT_INTERNAL",
    "BRIEF_ACKNOWLEDGMENT",
)


def strip_html_and_signatures(html_or_text: str) -> str:
    """Strip HTML tags, common signature delimiters, and excess whitespace."""
    if not html_or_text:
        return ""
    text = re.sub(r"<[^>]+>", " ", html_or_text)
    # Drop everything after a "-- " or "Best," / "Regards," signature marker
    for marker in (
        "\n-- \n",
        "\n--\n",
        "\nBest regards",
        "\nBest,",
        "\nRegards,",
        "\nKind regards",
        "\nThanks,",
    ):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
            break
    text = re.sub(r"\s+", " ", text).strip()
    return text[:6000]


def infer_relationship(sender_obj: dict[str, Any], stored_email: Optional[Email]) -> str:
    """Best-effort: classify the relationship between ARP and the sender."""
    address = ""
    if isinstance(sender_obj, dict):
        address = (sender_obj.get("emailAddress") or {}).get("address", "") or ""
    address = (address or "").lower()
    if "arpglobalcapital.com" in address:
        return "Internal ARP team member"
    if stored_email is not None and getattr(stored_email, "is_from_ceo", False):
        return "Internal — CEO"
    if stored_email is not None and (stored_email.tag or "").upper() == "CLIENT":
        return "External client / LP"
    if any(t in address for t in ("research", "broker", "sales@")):
        return "External broker / sell-side counterparty"
    return "External counterparty (relationship unspecified)"


def _safe_json_loads(text: str) -> dict[str, Any]:
    """Parse Claude output that may be wrapped in markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n", "", cleaned)
        cleaned = re.sub(r"\n```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Find the first {...} block as a fallback.
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            return json.loads(match.group(0))
        raise


class EmailReplyService:
    """Generate, draft, and send replies for stored emails."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.claude = get_claude_client()

    async def generate_suggestion(
        self,
        email_id: str,
        user_email: str,
        access_token: str,
        reply_author_name: str,
        reply_author_title: str,
        tone: str,
        user_context: str | None,
    ) -> dict[str, Any]:
        """Return ``{"suggestion": {...}, "graph_draft_id": str | None}``.

        Raises:
            ValueError: if ``tone`` is invalid or the email is not found.
        """
        if tone not in VALID_TONES:
            raise ValueError(
                f"Invalid tone {tone!r}. Must be one of: {', '.join(VALID_TONES)}"
            )

        result = await self.db.execute(
            select(Email).where(Email.id == email_id, Email.mailbox_user_email == user_email)
        )
        stored = result.scalar_one_or_none()
        if stored is None:
            raise ValueError(f"Email {email_id} not found for {user_email}")

        graph = GraphClient(access_token)
        try:
            graph_msg = await graph.get_message(user_email, stored.graph_message_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Graph get_message failed for reply ({}): {}. Falling back to stored body.",
                stored.graph_message_id, exc,
            )
            graph_msg = {
                "subject": stored.subject,
                "from": {"emailAddress": {"address": stored.sender_email, "name": stored.sender_name or ""}},
                "body": {"contentType": "Text", "content": stored.body_full or stored.body_preview or ""},
            }

        sender = graph_msg.get("from") or graph_msg.get("sender") or {}
        body_content = (graph_msg.get("body") or {}).get("content", "")
        body_text = strip_html_and_signatures(body_content)

        prompt = EMAIL_REPLY_PROMPT.format(
            reply_author_name=reply_author_name or "ARP team member",
            reply_author_title=reply_author_title or "ARP Global Capital",
            relationship_context=infer_relationship(sender, stored),
            tone=tone,
            original_sender=(sender.get("emailAddress") or {}).get("address", stored.sender_email or ""),
            subject=graph_msg.get("subject") or stored.subject or "(no subject)",
            body_text=body_text or stored.body_preview or "",
            user_context=(user_context or "None provided"),
        )

        raw = await self.claude.complete(
            prompt=prompt, system=SYSTEM_BASE, use_sonnet=True
        )
        try:
            suggestion = _safe_json_loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reply suggestion JSON parse failed: {}", exc)
            raise ValueError("AI returned malformed JSON")

        # Defensive defaults
        suggestion.setdefault("subject", f"Re: {stored.subject or ''}")
        suggestion.setdefault("body", "")
        suggestion.setdefault("flags", [])
        suggestion.setdefault("tone_used", tone)

        # Create a Graph draft so the user can edit in Outlook if preferred.
        draft_id: Optional[str] = None
        try:
            body_html = suggestion.get("body", "").replace("\n", "<br/>")
            draft = await graph.create_reply_draft(
                user_email=user_email,
                message_id=stored.graph_message_id,
                body_html=body_html,
            )
            draft_id = draft.get("id")
        except Exception as exc:  # noqa: BLE001
            logger.info("Graph draft creation skipped: {}", exc)

        return {"suggestion": suggestion, "graph_draft_id": draft_id}

    async def send_reply(
        self,
        email_id: str,
        user_email: str,
        access_token: str,
        body: str,
        subject: str | None = None,
    ) -> dict[str, Any]:
        """Send a reply through Graph's ``/reply`` endpoint."""
        result = await self.db.execute(
            select(Email).where(Email.id == email_id, Email.mailbox_user_email == user_email)
        )
        stored = result.scalar_one_or_none()
        if stored is None:
            raise ValueError(f"Email {email_id} not found for {user_email}")

        body_html = (body or "").replace("\n", "<br/>")
        graph = GraphClient(access_token)
        await graph.send_reply(
            user_email=user_email,
            message_id=stored.graph_message_id,
            body_html=body_html,
        )
        return {"status": "sent", "email_id": email_id, "subject": subject}
