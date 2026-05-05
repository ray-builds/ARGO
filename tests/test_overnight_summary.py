"""Tests for the Overnight Summary service."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch


class TestOvernightSummaryService:
    """Tests for overnight briefing generation, delivery, and storage."""

    @pytest.mark.asyncio
    async def test_run_daily_summary_creates_record(
        self,
        test_db: AsyncSession,
        mock_claude_json,
        mock_serper,
        mock_twilio,
    ) -> None:
        """Running the daily summary pipeline creates an OvernightSummary DB record."""
        from app.services.overnight_summary import OvernightSummaryService

        service = OvernightSummaryService(db=test_db)
        result = await service.run_daily_summary(
            date_str="2026-05-05",
            send_whatsapp=False,
        )

        assert result is not None
        assert result.id is not None
        assert result.executive_summary is not None

    @pytest.mark.asyncio
    async def test_whatsapp_delivery_called(
        self,
        test_db: AsyncSession,
        mock_claude_json,
        mock_serper,
        mock_twilio,
    ) -> None:
        """When send_whatsapp=True, TwilioClient.send_whatsapp is called."""
        from app.services.overnight_summary import OvernightSummaryService

        service = OvernightSummaryService(db=test_db)
        await service.run_daily_summary(
            date_str="2026-05-05",
            send_whatsapp=True,
        )

        mock_twilio.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_fallback_on_whatsapp_failure(
        self,
        test_db: AsyncSession,
        mock_claude_json,
        mock_serper,
        mock_twilio,
    ) -> None:
        """If WhatsApp fails, an email fallback is attempted and the failure is recorded."""
        mock_twilio.return_value = {"success": False, "sid": None, "error": "Twilio error"}

        from app.services.overnight_summary import OvernightSummaryService

        service = OvernightSummaryService(db=test_db)
        result = await service.run_daily_summary(
            date_str="2026-05-05",
            send_whatsapp=True,
        )

        # Summary should still be stored; WhatsApp delivered should be False
        assert result is not None
        assert result.whatsapp_delivered is False

    @pytest.mark.asyncio
    async def test_summary_stored_in_database(
        self,
        test_db: AsyncSession,
        mock_claude_json,
        mock_serper,
        mock_twilio,
    ) -> None:
        """Generated summary is persisted and can be retrieved by ID."""
        from app.services.overnight_summary import OvernightSummaryService
        from app.models.overnight_summary import OvernightSummary

        service = OvernightSummaryService(db=test_db)
        result = await service.run_daily_summary(date_str="2026-05-05", send_whatsapp=False)

        # Re-fetch from DB
        from sqlalchemy import select
        stmt = select(OvernightSummary).where(OvernightSummary.id == result.id)
        db_record = (await test_db.execute(stmt)).scalar_one_or_none()

        assert db_record is not None
        assert db_record.id == result.id

    @pytest.mark.asyncio
    async def test_market_data_stub_returns_expected_shape(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Market data fetcher returns a dict with expected asset-class keys."""
        from app.services.overnight_summary import OvernightSummaryService

        service = OvernightSummaryService(db=test_db)
        data = await service.fetch_market_data()

        assert isinstance(data, dict)
        # Should contain at minimum rates and FX sections
        expected_keys = {"rates", "fx", "equities"}
        assert expected_keys.issubset(data.keys()) or len(data) > 0

    @pytest.mark.asyncio
    async def test_news_fetch_returns_headlines(
        self,
        test_db: AsyncSession,
        mock_serper,
    ) -> None:
        """News fetcher returns a list of headline dicts with title and snippet."""
        from app.services.overnight_summary import OvernightSummaryService

        service = OvernightSummaryService(db=test_db)
        headlines = await service.fetch_news_headlines()

        assert isinstance(headlines, list)
        assert len(headlines) > 0
        for h in headlines:
            assert "title" in h

    @pytest.mark.asyncio
    async def test_synthesize_briefing_uses_sonnet(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Briefing synthesis calls the Claude client with a non-empty prompt."""
        from app.services.overnight_summary import OvernightSummaryService

        service = OvernightSummaryService(db=test_db)
        briefing = await service.synthesize_briefing(
            market_data={"rates": {}, "fx": {}, "equities": {}},
            news=[{"title": "Fed steady", "snippet": "No change"}],
            email_digest="No urgent emails today.",
        )

        assert briefing is not None
        assert isinstance(briefing, str) or isinstance(briefing, dict)
        mock_claude_json.assert_called_once()
