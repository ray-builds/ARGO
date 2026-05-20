"""Overnight Summary service — full pipeline: fetch, synthesise, deliver, store."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.claude_client import get_claude_client
from app.core.database import get_db_session
from app.core.serper_client import get_serper_client
from app.core.twilio_client import get_twilio_client
from app.models.summary import OvernightSummary
from app.modules.overnight_summary.market_data import get_market_data_fetcher
from app.modules.overnight_summary.prompts import (
    OVERNIGHT_SUMMARY_SYSTEM,
    OVERNIGHT_SUMMARY_PROMPT,
)


class OvernightSummaryService:
    """Orchestrates the daily ARP morning briefing pipeline.

    Pipeline:
    1. Fetch overnight emails from DB (emails stored by Email Intelligence)
    2. Fetch market data snapshot (MarketDataFetcher)
    3. Fetch financial news headlines (Serper)
    4. Synthesise via Claude (Haiku by default for cost; Sonnet optional)
    5. Persist OvernightSummary to DB
    6. Deliver via WhatsApp; fall back to email on failure
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.claude = get_claude_client()
        self.serper = get_serper_client()
        self.settings = get_settings()

    # ── Main pipeline ─────────────────────────────────────────────────────────

    async def generate_summary(
        self, target_date: date | None = None
    ) -> OvernightSummary:
        """Run the full generation pipeline and return the persisted summary.

        Args:
            target_date: Date for the briefing (defaults to today UTC).

        Returns:
            OvernightSummary ORM object.

        Notes:
            If a summary already exists for `target_date` it is returned
            immediately without re-running the pipeline.
        """
        if target_date is None:
            target_date = datetime.now(timezone.utc).date()

        # Return existing summary if already generated today
        existing = await self._get_by_date(target_date)
        if existing is not None:
            logger.info(
                "Overnight summary already exists for {} (id={})", target_date, existing.id
            )
            return existing

        # Coverage window: 22:00 previous day → now
        now_utc = datetime.now(timezone.utc)
        coverage_end = now_utc
        coverage_start = (
            datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
            - timedelta(hours=2)  # 22:00 prior day
        )

        logger.info(
            "Generating overnight summary for {} (window {} → {})",
            target_date,
            coverage_start.isoformat(),
            coverage_end.isoformat(),
        )

        # 1. Emails
        emails = await self._fetch_overnight_emails(coverage_start, coverage_end)

        # 2. Market data
        market_data = get_market_data_fetcher().get_overnight_moves()

        # 3. News
        news = await self._fetch_news()

        # 4. Synthesise
        ai_result = await self._synthesise(emails, market_data, news)

        # 5. Build full WhatsApp text
        full_text = self._format_whatsapp_message(target_date, ai_result)

        # 6. Persist
        summary = OvernightSummary(
            summary_date=target_date,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            executive_summary=ai_result.get("executive_summary", ""),
            email_section=json.dumps(ai_result.get("important_emails", []), ensure_ascii=False),
            market_moves_section=json.dumps(
                ai_result.get("top_market_moves", []), ensure_ascii=False
            ),
            news_section=json.dumps(ai_result.get("key_news", []), ensure_ascii=False),
            macro_section=ai_result.get("macro_watch"),
            full_briefing_text=full_text,
            model_used=self.claude.haiku_model,
            raw_inputs=json.dumps(
                {
                    "emails_count": len(emails),
                    "market_data_source": market_data.get("data_source"),
                    "news_count": len(news),
                },
                ensure_ascii=False,
            ),
        )
        self.db.add(summary)
        await self.db.flush()
        logger.info("Overnight summary persisted: id={} date={}", summary.id, target_date)
        return summary

    async def deliver_summary(self, summary_id: str) -> bool:
        """Deliver a stored summary via WhatsApp (email fallback on failure).

        Args:
            summary_id: UUID of the OvernightSummary record.

        Returns:
            True if at least one delivery channel succeeded.
        """
        summary = await self.get_summary(summary_id)
        if summary is None:
            logger.error("deliver_summary: summary {} not found", summary_id)
            return False

        message = summary.full_briefing_text

        # ── WhatsApp ──────────────────────────────────────────────────────────
        whatsapp_ok = False
        whatsapp_err: str | None = None

        pm_number = self.settings.pm_whatsapp_number
        if self.settings.enable_whatsapp and pm_number:
            try:
                twilio = get_twilio_client()
                result = twilio.send_whatsapp(to_number=pm_number, message=message)
                whatsapp_ok = result.get("success", False)
                if not whatsapp_ok:
                    whatsapp_err = result.get("error", "Unknown Twilio error")
                    logger.warning("WhatsApp delivery failed: {}", whatsapp_err)
                else:
                    logger.info("WhatsApp delivered for summary {}", summary_id)
            except Exception as exc:
                whatsapp_err = str(exc)
                logger.exception("WhatsApp delivery exception for {}: {}", summary_id, exc)
        else:
            logger.info(
                "WhatsApp delivery skipped (enable_whatsapp={}, pm_number set={})",
                self.settings.enable_whatsapp,
                bool(pm_number),
            )

        # ── Email fallback ────────────────────────────────────────────────────
        email_ok = False
        email_err: str | None = None

        if not whatsapp_ok:
            try:
                email_ok = await self._send_email_fallback(summary)
            except Exception as exc:
                email_err = str(exc)
                logger.exception("Email fallback failed for {}: {}", summary_id, exc)

        # ── Persist delivery status ───────────────────────────────────────────
        now = datetime.now(timezone.utc)
        summary.whatsapp_delivered = whatsapp_ok
        summary.whatsapp_delivered_at = now if whatsapp_ok else None
        summary.whatsapp_error = whatsapp_err
        summary.email_delivered = email_ok
        summary.email_delivered_at = now if email_ok else None
        summary.email_error = email_err
        self.db.add(summary)
        await self.db.flush()

        return whatsapp_ok or email_ok

    # ── Query helpers ─────────────────────────────────────────────────────────

    async def get_summaries(
        self, limit: int = 30, offset: int = 0
    ) -> list[OvernightSummary]:
        """Return paginated list ordered by summary_date desc."""
        result = await self.db.execute(
            select(OvernightSummary)
            .order_by(desc(OvernightSummary.summary_date))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_summary(self, summary_id: str) -> OvernightSummary | None:
        """Return a single summary by UUID or None."""
        result = await self.db.execute(
            select(OvernightSummary).where(OvernightSummary.id == summary_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_summary(self) -> OvernightSummary | None:
        """Return the most recent summary or None."""
        result = await self.db.execute(
            select(OvernightSummary)
            .order_by(desc(OvernightSummary.summary_date))
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _get_by_date(self, target_date: date) -> OvernightSummary | None:
        result = await self.db.execute(
            select(OvernightSummary).where(OvernightSummary.summary_date == target_date)
        )
        return result.scalar_one_or_none()

    async def _fetch_overnight_emails(
        self, since: datetime, until: datetime
    ) -> list[dict[str, Any]]:
        """Query DB for relevant emails in the overnight window.

        Falls back to Graph API if access token is available in settings.
        Uses DB-only approach as the primary path (emails already synced by
        Email Intelligence module).
        """
        from app.models.email import Email
        from sqlalchemy import and_

        try:
            result = await self.db.execute(
                select(Email)
                .where(
                    and_(
                        Email.received_at >= since,
                        Email.received_at <= until,
                        Email.is_archived == False,
                    )
                )
                .order_by(desc(Email.relevance_score))
                .limit(30)
            )
            emails = result.scalars().all()
            logger.info("Overnight emails fetched from DB: {}", len(emails))
            return [
                {
                    "sender": f"{e.sender_name} <{e.sender_email}>",
                    "subject": e.subject,
                    "preview": e.body_preview or "",
                    "relevance_score": e.relevance_score or 0,
                    "tag": e.tag or "SKIP",
                    "is_from_ceo": e.is_from_ceo,
                }
                for e in emails
            ]
        except Exception as exc:
            logger.warning("DB email fetch failed: {}. Using empty list.", exc)
            return []

    async def _fetch_news(self) -> list[dict[str, Any]]:
        """Fetch macro financial headlines via Serper."""
        try:
            results = await self.serper.search_news(
                query="macro markets overnight rates FX equities",
                num_results=10,
                # date_range="d",
            )
            return [
                {
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "source": item.get("source", ""),
                    "link": item.get("link", ""),
                    "date": item.get("date", ""),
                }
                for item in results
            ]
        except Exception as exc:
            logger.warning("News fetch failed: {}. Using empty list.", exc)
            return []

    async def _synthesise(
        self,
        emails: list[dict[str, Any]],
        market_data: dict[str, Any],
        news: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Call Claude to produce structured JSON briefing.

        Returns a dict with keys: executive_summary, important_emails,
        top_market_moves, key_news, macro_watch.
        Falls back to a safe default dict on any Claude error.
        """
        prompt = OVERNIGHT_SUMMARY_PROMPT.format(
            emails_json=json.dumps(emails, ensure_ascii=False, indent=2),
            market_data_json=json.dumps(market_data, ensure_ascii=False, indent=2),
            news_json=json.dumps(news, ensure_ascii=False, indent=2),
        )

        try:
            result = await self.claude.complete_json(
                prompt=prompt,
                system=OVERNIGHT_SUMMARY_SYSTEM,
                use_sonnet=False,  # Haiku for cost efficiency; set True for richer output
            )
            return result
        except Exception as exc:
            logger.exception("Claude synthesis failed: {}", exc)
            return {
                "executive_summary": (
                    "Overnight briefing synthesis failed — please review logs. "
                    "Market data was collected but AI analysis is unavailable."
                ),
                "important_emails": [],
                "top_market_moves": [],
                "key_news": [],
                "macro_watch": "AI analysis unavailable. Check logs for details.",
            }

    @staticmethod
    def _format_whatsapp_message(
        briefing_date: date, ai_result: dict[str, Any]
    ) -> str:
        """Compose the WhatsApp plain-text message from AI result."""
        date_str = briefing_date.strftime("%a %d %b %Y") if hasattr(briefing_date, "strftime") else str(briefing_date)

        lines: list[str] = [
            f"🌅 *ARP Global Capital — Morning Briefing {date_str}*",
            "",
            "📊 *EXECUTIVE SUMMARY*",
            ai_result.get("executive_summary", ""),
            "",
        ]

        important_emails: list[dict[str, Any]] = ai_result.get("important_emails", [])
        if important_emails:
            lines.append("📧 *KEY EMAILS*")
            for em in important_emails:
                priority = em.get("priority", "")
                sender = em.get("sender", "")
                subject = em.get("subject", "")
                action = em.get("action_required", "")
                lines.append(f"  [{priority}] {sender}: {subject}")
                if action:
                    lines.append(f"  → {action}")
            lines.append("")

        top_moves: list[dict[str, Any]] = ai_result.get("top_market_moves", [])
        if top_moves:
            lines.append("📈 *MARKET MOVES*")
            for mv in top_moves:
                asset = mv.get("asset", "")
                move = mv.get("move", "")
                magnitude = mv.get("magnitude", "")
                matters = mv.get("why_it_matters", "")
                lines.append(f"  {asset}: {move} ({magnitude})")
                if matters:
                    lines.append(f"  → {matters}")
            lines.append("")

        key_news: list[dict[str, Any]] = ai_result.get("key_news", [])
        if key_news:
            lines.append("📰 *NEWS*")
            for n in key_news:
                headline = n.get("headline", "")
                sig = n.get("significance", "")
                lines.append(f"  • {headline}")
                if sig:
                    lines.append(f"    {sig}")
            lines.append("")

        macro_watch = ai_result.get("macro_watch", "")
        if macro_watch:
            lines.append("🔭 *MACRO WATCH*")
            lines.append(macro_watch)

        return "\n".join(lines)

    async def _send_email_fallback(self, summary: OvernightSummary) -> bool:
        """Attempt to send summary as email via Microsoft Graph.

        Requires the CEO to be authenticated and have a stored access token.
        This is best-effort; failures are logged but not raised.
        """
        from app.models.user import User

        # Look for any active user with a Graph token (prefer ceo_email)
        result = await self.db.execute(
            select(User)
            .where(User.graph_access_token.isnot(None))
            .order_by(
                (User.email == self.settings.ceo_email).desc()
            )
            .limit(1)
        )
        sender_user = result.scalar_one_or_none()

        if sender_user is None or not sender_user.graph_access_token:
            logger.warning("No Graph-authenticated user available for email fallback")
            return False

        from app.core.graph_client import GraphClient

        graph = GraphClient(sender_user.graph_access_token)
        date_str = summary.summary_date.strftime("%d %b %Y")
        subject = f"ARGO Morning Briefing — {date_str}"
        body_html = f"""
<html><body style="font-family: monospace; font-size: 13px; white-space: pre-wrap;">
{summary.full_briefing_text}
</body></html>
"""
        success = await graph.send_email(
            from_email=sender_user.email,
            to_email=self.settings.ceo_email,
            subject=subject,
            body_html=body_html,
        )
        if success:
            logger.info("Email fallback delivered for summary {}", summary.id)
        else:
            logger.error("Email fallback failed for summary {}", summary.id)
        return success
