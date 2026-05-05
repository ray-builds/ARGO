"""Tests for the Economic Intelligence (calendar) service."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch


class TestEconomicIntelligenceService:
    """Tests for economic event filtering, release analysis, and alerting."""

    @pytest.mark.asyncio
    async def test_get_today_events_filters_correctly(
        self,
        test_db: AsyncSession,
    ) -> None:
        """get_today_events returns only HIGH and MEDIUM importance events for today."""
        from app.services.economic_intelligence import EconomicIntelligenceService
        from app.models.economic_event import EconomicEvent
        import datetime

        today = datetime.date.today().isoformat()
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

        events = [
            EconomicEvent(event_name="NFP",         country="US", importance="HIGH",   event_date=today),
            EconomicEvent(event_name="CPI",          country="US", importance="MEDIUM", event_date=today),
            EconomicEvent(event_name="Old NFP",      country="US", importance="HIGH",   event_date=yesterday),
            EconomicEvent(event_name="Low Imp Event",country="EU", importance="LOW",    event_date=today),
        ]
        test_db.add_all(events)
        await test_db.commit()

        service = EconomicIntelligenceService(db=test_db)
        today_events = await service.get_today_events(importance_filter=["HIGH", "MEDIUM"])

        names = [e.event_name for e in today_events]
        assert "NFP" in names
        assert "CPI" in names
        assert "Old NFP" not in names
        assert "Low Imp Event" not in names

    @pytest.mark.asyncio
    async def test_analyze_release_stores_analysis(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Analysing an economic release creates a ReleaseAnalysis record."""
        mock_claude_json.return_value = {
            "beat_miss": "BEAT",
            "market_impact": "USD strengthened, yields rose 5bps.",
            "positioning_implication": "Reduce duration; market pricing more hikes.",
        }

        from app.services.economic_intelligence import EconomicIntelligenceService
        from app.models.economic_event import EconomicEvent
        import datetime

        event = EconomicEvent(
            event_name="NFP",
            country="US",
            importance="HIGH",
            event_date=datetime.date.today().isoformat(),
            forecast=200.0,
            actual=256.0,
        )
        test_db.add(event)
        await test_db.commit()
        await test_db.refresh(event)

        service = EconomicIntelligenceService(db=test_db)
        analysis = await service.analyze_release(event_id=str(event.id))

        assert analysis is not None
        mock_claude_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_beat_miss_determination(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Beat/miss determination works correctly for various actual vs forecast pairs."""
        from app.services.economic_intelligence import EconomicIntelligenceService

        service = EconomicIntelligenceService(db=test_db)

        assert service.determine_beat_miss(actual=256.0, forecast=200.0) == "BEAT"
        assert service.determine_beat_miss(actual=150.0, forecast=200.0) == "MISS"
        assert service.determine_beat_miss(actual=200.0, forecast=200.0) == "IN_LINE"

    @pytest.mark.asyncio
    async def test_alert_sent_flag_updated(
        self,
        test_db: AsyncSession,
    ) -> None:
        """After sending a release alert, alert_sent is set to True on the event record."""
        from app.services.economic_intelligence import EconomicIntelligenceService
        from app.models.economic_event import EconomicEvent
        import datetime
        from unittest.mock import AsyncMock, patch

        event = EconomicEvent(
            event_name="CPI",
            country="US",
            importance="HIGH",
            event_date=datetime.date.today().isoformat(),
            forecast=3.2,
            actual=3.5,
            alert_sent=False,
        )
        test_db.add(event)
        await test_db.commit()
        await test_db.refresh(event)

        service = EconomicIntelligenceService(db=test_db)

        with patch.object(
            service,
            "_send_alert",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await service.send_release_alert(event_id=str(event.id))

        await test_db.refresh(event)
        assert event.alert_sent is True
