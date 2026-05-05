"""Email Intelligence service — Graph sync, AI classification, and inbox management."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.claude_client import get_claude_client
from app.core.graph_client import GraphClient
from app.models.email import Email, EmailHighlight
from app.modules.email_intelligence.prompts import (
    EMAIL_SCORING_SYSTEM,
    EMAIL_SCORING_PROMPT,
    VALID_TAGS,
)


class EmailIntelligenceService:
    """AI-powered email intelligence: sync, classify, query, and archive."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.claude = get_claude_client()
        self.settings = get_settings()

    # ── Sync ──────────────────────────────────────────────────────────────────

    async def sync_mailbox(
        self,
        access_token: str,
        user_email: str,
        hours_back: int = 24,
    ) -> int:
        """Fetch new emails from Microsoft Graph and classify them with Claude.

        Args:
            access_token: Valid Microsoft Graph access token.
            user_email: Mailbox owner's UPN / email address.
            hours_back: How many hours back to fetch (default 24).

        Returns:
            Count of new emails processed.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        filter_query = f"receivedDateTime ge {since_str}"

        graph = GraphClient(access_token)
        try:
            messages = await graph.get_messages(
                user_email=user_email,
                top=50,
                filter_query=filter_query,
                select=(
                    "id,subject,sender,from,receivedDateTime,isRead,"
                    "bodyPreview,importance"
                ),
            )
        except PermissionError as exc:
            logger.error("Graph permission error for {}: {}", user_email, exc)
            return 0
        except Exception as exc:
            logger.exception("Graph fetch failed for {}: {}", user_email, exc)
            return 0

        new_count = 0
        for msg in messages:
            graph_id = msg.get("id", "")
            if not graph_id:
                continue

            # Skip already-stored emails
            existing = await self._get_email_by_graph_id(graph_id)
            if existing is not None:
                continue

            # Parse message fields
            sender_obj = msg.get("from", msg.get("sender", {})).get("emailAddress", {})
            sender_email: str = sender_obj.get("address", "")
            sender_name: str = sender_obj.get("name", "")
            subject: str = msg.get("subject", "(no subject)")
            body_preview: str = msg.get("bodyPreview", "")
            is_read: bool = msg.get("isRead", False)

            received_raw: str = msg.get("receivedDateTime", "")
            try:
                received_at = datetime.fromisoformat(
                    received_raw.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                received_at = datetime.now(timezone.utc)

            # AI classification
            classification = await self._classify_email(
                sender_name=sender_name,
                sender_email=sender_email,
                subject=subject,
                body_preview=body_preview,
            )

            email_obj = Email(
                graph_message_id=graph_id,
                mailbox_user_email=user_email,
                sender_email=sender_email,
                sender_name=sender_name or None,
                subject=subject,
                body_preview=body_preview or None,
                received_at=received_at,
                is_read=is_read,
                relevance_score=classification.get("relevance_score"),
                tag=classification.get("tag"),
                is_from_ceo=(
                    sender_email.lower() == self.settings.ceo_email.lower()
                ),
                processed_at=datetime.now(timezone.utc),
            )
            self.db.add(email_obj)
            await self.db.flush()

            # Persist highlight if Claude returned one
            ai_summary = classification.get("ai_summary")
            action_required = classification.get("action_required")
            key_conclusion = classification.get("key_conclusion")
            if ai_summary:
                highlight = EmailHighlight(
                    email_id=email_obj.id,
                    highlight_text=ai_summary,
                    action_required=action_required if action_required else None,
                    key_conclusion=key_conclusion if key_conclusion else None,
                    model_used=self.claude.haiku_model,
                )
                self.db.add(highlight)

            new_count += 1

        logger.info(
            "sync_mailbox {}: {} messages fetched, {} new processed",
            user_email,
            len(messages),
            new_count,
        )
        return new_count

    # ── Classification ────────────────────────────────────────────────────────

    async def _classify_email(
        self,
        sender_name: str,
        sender_email: str,
        subject: str,
        body_preview: str,
    ) -> dict[str, Any]:
        """Call Claude Haiku with EMAIL_SCORING_PROMPT and return parsed JSON.

        Returns a safe default dict on any failure.
        """
        prompt = EMAIL_SCORING_PROMPT.format(
            sender_name=sender_name or "",
            sender_email=sender_email or "",
            subject=subject or "",
            body_preview=(body_preview or "")[:500],
        )

        try:
            result = await self.claude.complete_json(
                prompt=prompt,
                system=EMAIL_SCORING_SYSTEM,
                use_sonnet=False,
            )
            # Sanitise tag
            tag = result.get("tag", "SKIP")
            if tag not in VALID_TAGS:
                tag = "SKIP"
            result["tag"] = tag

            # Clamp score
            score = result.get("relevance_score", 50)
            if not isinstance(score, int):
                try:
                    score = int(score)
                except (TypeError, ValueError):
                    score = 50
            result["relevance_score"] = max(0, min(100, score))

            # Null-safe fields
            for field in ("action_required", "key_conclusion"):
                val = result.get(field)
                if val in (None, "null", "NULL", "", "none", "None"):
                    result[field] = None

            return result

        except Exception as exc:
            logger.warning("Email classification failed: {}. Using defaults.", exc)
            return {
                "tag": "SKIP",
                "relevance_score": 0,
                "ai_summary": None,
                "action_required": None,
                "key_conclusion": None,
            }

    # ── Inbox queries ─────────────────────────────────────────────────────────

    async def get_inbox(
        self,
        user_email: str,
        tag_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Email]:
        """Return emails for a mailbox, optionally filtered by tag.

        Args:
            user_email: Mailbox owner's email.
            tag_filter: Optional tag to filter by (e.g. "URGENT").
            limit: Max results.
            offset: Pagination offset.

        Returns:
            List of Email ORM objects, ordered by relevance_score desc, received_at desc.
        """
        conditions = [
            Email.mailbox_user_email == user_email,
            Email.is_archived == False,
        ]
        if tag_filter and tag_filter in VALID_TAGS:
            conditions.append(Email.tag == tag_filter)

        result = await self.db.execute(
            select(Email)
            .where(and_(*conditions))
            .order_by(desc(Email.relevance_score), desc(Email.received_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_ceo_emails(self, user_email: str) -> dict[str, list[Email]]:
        """Return all non-archived CEO emails grouped by tag.

        Args:
            user_email: Mailbox to query.

        Returns:
            Dict mapping tag → list of Email ORM objects.
        """
        result = await self.db.execute(
            select(Email)
            .where(
                and_(
                    Email.mailbox_user_email == user_email,
                    Email.is_from_ceo == True,
                    Email.is_archived == False,
                )
            )
            .order_by(desc(Email.received_at))
        )
        emails = result.scalars().all()

        grouped: dict[str, list[Email]] = {}
        for email in emails:
            tag = email.tag or "SKIP"
            grouped.setdefault(tag, []).append(email)
        return grouped

    async def get_email_stats(self, user_email: str) -> dict[str, Any]:
        """Return aggregate email statistics for a mailbox.

        Returns:
            Dict with keys: total_today, by_tag, avg_relevance_score,
            ceo_emails_today, last_sync.
        """
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # All non-archived emails today
        result = await self.db.execute(
            select(Email).where(
                and_(
                    Email.mailbox_user_email == user_email,
                    Email.received_at >= today_start,
                    Email.is_archived == False,
                )
            )
        )
        today_emails = result.scalars().all()

        by_tag: dict[str, int] = {}
        scores: list[int] = []
        ceo_count = 0

        for e in today_emails:
            tag = e.tag or "SKIP"
            by_tag[tag] = by_tag.get(tag, 0) + 1
            if e.relevance_score is not None:
                scores.append(e.relevance_score)
            if e.is_from_ceo:
                ceo_count += 1

        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

        # Last sync = most recent processed_at across all emails for this user
        last_sync_result = await self.db.execute(
            select(func.max(Email.processed_at)).where(
                Email.mailbox_user_email == user_email
            )
        )
        last_sync: datetime | None = last_sync_result.scalar_one_or_none()

        return {
            "total_today": len(today_emails),
            "by_tag": by_tag,
            "avg_relevance_score": avg_score,
            "ceo_emails_today": ceo_count,
            "last_sync": last_sync.isoformat() if last_sync else None,
        }

    # ── Archive ───────────────────────────────────────────────────────────────

    async def archive_emails(self, email_ids: list[str]) -> int:
        """Mark a list of emails as archived.

        Args:
            email_ids: List of email UUID strings.

        Returns:
            Count of emails actually updated.
        """
        if not email_ids:
            return 0

        now = datetime.now(timezone.utc)
        await self.db.execute(
            update(Email)
            .where(Email.id.in_(email_ids))
            .values(is_archived=True, archived_at=now)
        )
        logger.info("Archived {} emails", len(email_ids))
        return len(email_ids)

    async def archive_skip_emails(self, user_email: str) -> int:
        """Bulk-archive all SKIP-tagged emails for a mailbox.

        Args:
            user_email: Mailbox owner's email.

        Returns:
            Count of emails archived.
        """
        now = datetime.now(timezone.utc)

        # Fetch IDs first to return count
        result = await self.db.execute(
            select(Email.id).where(
                and_(
                    Email.mailbox_user_email == user_email,
                    Email.tag == "SKIP",
                    Email.is_archived == False,
                )
            )
        )
        ids = [row[0] for row in result.fetchall()]

        if not ids:
            return 0

        await self.db.execute(
            update(Email)
            .where(Email.id.in_(ids))
            .values(is_archived=True, archived_at=now)
        )
        logger.info("Bulk-archived {} SKIP emails for {}", len(ids), user_email)
        return len(ids)

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _get_email_by_graph_id(self, graph_id: str) -> Email | None:
        result = await self.db.execute(
            select(Email).where(Email.graph_message_id == graph_id)
        )
        return result.scalar_one_or_none()
