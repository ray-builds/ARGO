"""Economic Intelligence service — calendar management, release analysis, and market alerts."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, update

from app.core.claude_client import get_claude_client
from app.models.economic import EconomicEvent
from app.modules.economic_intelligence.prompts import RELEASE_ANALYSIS_PROMPT
from app.schemas.economic import (
    EconEventResponse,
    ReleaseAnalysisResponse,
    Importance,
)


class EconomicIntelligenceService:
    """Service for economic calendar intelligence.

    Manages the economic event calendar, records actual release values,
    analyses surprises versus forecasts using Claude, and sends WhatsApp
    alerts for high-importance events via Twilio.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialise service with DB session.

        Args:
            db: Async SQLAlchemy session.
        """
        self._db = db
        self._claude = get_claude_client()
        self._pm_whatsapp = os.getenv("PM_WHATSAPP_NUMBER", "")

    async def get_today_events(self) -> list[EconEventResponse]:
        """Return today's economic calendar events sorted by importance.

        HIGH importance events are returned first, then MEDIUM, then LOW.

        Returns:
            List of EconEventResponse objects for today.
        """
        today = date.today()
        result = await self._db.execute(
            select(EconomicEvent)
            .where(EconomicEvent.release_date == today)
            .order_by(
                # Custom importance ordering: HIGH first
                EconomicEvent.importance.desc(),
                EconomicEvent.release_time_utc.asc().nullslast(),
            )
        )
        events = result.scalars().all()
        return [EconEventResponse.model_validate(e) for e in events]

    async def get_calendar(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
        importance: str | None = None,
    ) -> list[EconEventResponse]:
        """Return economic calendar events for a date range.

        Args:
            from_date: Start date (inclusive). Defaults to today if not provided.
            to_date: End date (inclusive). Defaults to 7 days from from_date.
            importance: Optional filter: 'HIGH', 'MEDIUM', or 'LOW'.

        Returns:
            List of EconEventResponse objects.
        """
        from_dt = from_date or date.today()
        from datetime import timedelta
        to_dt = to_date or (from_dt + timedelta(days=7))

        stmt = select(EconomicEvent).where(
            and_(
                EconomicEvent.release_date >= from_dt,
                EconomicEvent.release_date <= to_dt,
            )
        ).order_by(EconomicEvent.release_date, EconomicEvent.release_time_utc.asc().nullslast())

        if importance:
            stmt = stmt.where(EconomicEvent.importance == importance.upper())

        result = await self._db.execute(stmt)
        events = result.scalars().all()
        return [EconEventResponse.model_validate(e) for e in events]

    async def refresh_calendar(
        self, from_date: date, to_date: date
    ) -> int:
        """Refresh the economic calendar from an external data source.

        Currently a stub — returns 0. Replace with ForexFactory, Investing.com,
        or Bloomberg calendar API integration when available.

        Args:
            from_date: Start date for calendar refresh.
            to_date: End date for calendar refresh.

        Returns:
            Count of events upserted into the database.
        """
        logger.info(
            f"Economic calendar refresh requested: {from_date} to {to_date}. "
            "External source not yet integrated."
        )
        # TODO: Integrate ForexFactory or Bloomberg calendar API
        return 0

    async def analyze_release(
        self, event_id: str, actual_value: str
    ) -> ReleaseAnalysisResponse:
        """Record the actual release value and generate a surprise analysis.

        Updates the EconomicEvent with the actual value and computes the
        surprise direction (BEAT/MISS/IN_LINE). Then asks Claude to provide
        a brief market impact analysis.

        Args:
            event_id: UUID of the economic event.
            actual_value: The released actual data value as a string.

        Returns:
            ReleaseAnalysisResponse with AI analysis and surprise direction.

        Raises:
            HTTPException: 404 if event not found.
        """
        result = await self._db.execute(
            select(EconomicEvent).where(EconomicEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Economic event not found")

        event.actual = actual_value

        # Determine surprise direction
        surprise_direction = self._compute_surprise(
            actual=actual_value,
            forecast=event.forecast,
            event_name=event.event_name,
        )
        event.surprise_direction = surprise_direction

        context = (
            f"Event: {event.event_name}\n"
            f"Country: {event.country} ({event.currency or ''})\n"
            f"Release Date: {event.release_date}\n"
            f"Forecast: {event.forecast or 'N/A'}\n"
            f"Previous: {event.previous or 'N/A'}\n"
            f"Actual: {actual_value}\n"
            f"Surprise: {surprise_direction or 'Unknown'}"
        )

        try:
            analysis = await self._claude.complete(
                prompt=context,
                system=RELEASE_ANALYSIS_PROMPT,
                use_sonnet=True,
                max_tokens=300,
            )
            event.ai_analysis = analysis
        except Exception as exc:
            logger.warning(f"Release analysis failed for {event_id}: {exc}")
            analysis = "Analysis unavailable."

        await self._db.flush()

        return ReleaseAnalysisResponse(
            event_id=event_id,
            event_name=event.event_name,
            analysis=analysis,
            surprise_direction=surprise_direction,
        )

    def _compute_surprise(
        self,
        actual: str,
        forecast: str | None,
        event_name: str,
    ) -> str | None:
        """Heuristically determine surprise direction by comparing actual vs forecast.

        Args:
            actual: Actual data value string.
            forecast: Forecast value string.
            event_name: Event name for context (used to determine direction).

        Returns:
            'BEAT', 'MISS', 'IN_LINE', or None if values can't be parsed.
        """
        if not forecast:
            return None

        try:
            actual_num = float(actual.replace("%", "").replace(",", "").strip())
            forecast_num = float(forecast.replace("%", "").replace(",", "").strip())
        except ValueError:
            return None

        diff_pct = abs(actual_num - forecast_num) / (abs(forecast_num) + 1e-9)
        if diff_pct < 0.01:  # Within 1%
            return "IN_LINE"

        # For most economic indicators, higher = better for the economy (BEAT)
        # For unemployment and inflation, lower is better — could refine with name heuristics
        name_lower = event_name.lower()
        is_inverted = any(k in name_lower for k in ("unemployment", "jobless", "cpi", "inflation", "ppi"))

        if is_inverted:
            return "BEAT" if actual_num < forecast_num else "MISS"
        else:
            return "BEAT" if actual_num > forecast_num else "MISS"

    async def send_morning_alerts(self) -> int:
        """Send WhatsApp alerts for today's high-importance economic events.

        Queries today's HIGH importance events that have not yet had an alert
        sent, formats a summary, and delivers via Twilio WhatsApp.

        Returns:
            Count of alerts sent.
        """
        if not self._pm_whatsapp:
            logger.warning("PM_WHATSAPP_NUMBER not configured — skipping morning alerts")
            return 0

        events = await self.get_today_events()
        high_events = [e for e in events if e.importance == Importance.HIGH and not e.alert_sent]

        if not high_events:
            logger.info("No high-importance events to alert today")
            return 0

        lines = [f"ARGO Economic Alerts — {date.today().strftime('%d %b %Y')}", ""]
        for ev in high_events:
            time_str = str(ev.release_time_utc) if ev.release_time_utc else "TBC"
            lines.append(
                f"HIGH: {ev.event_name} ({ev.country}) @ {time_str} UTC\n"
                f"  Forecast: {ev.forecast or 'N/A'}  |  Previous: {ev.previous or 'N/A'}"
            )

        message = "\n".join(lines)

        try:
            from app.core.twilio_client import TwilioClient
            client = TwilioClient()
            await client.send_whatsapp(to=self._pm_whatsapp, body=message[:1550])

            # Mark alerts as sent
            for ev in high_events:
                await self._db.execute(
                    update(EconomicEvent)
                    .where(EconomicEvent.id == ev.id)
                    .values(alert_sent=True)
                )

            logger.info(f"Morning alerts sent for {len(high_events)} events")
            return len(high_events)
        except Exception as exc:
            logger.exception(f"Morning alerts delivery failed: {exc}")
            return 0
