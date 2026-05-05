"""Tests for the Research Intelligence service (broker research tracking)."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch


class TestResearchIntelligenceService:
    """Tests for broker research ingestion, summarisation, rating, and digest."""

    @pytest.mark.asyncio
    async def test_ingest_research_creates_record(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Ingesting a research item creates a ResearchItem record in the database."""
        from app.services.research_intelligence import ResearchIntelligenceService

        service = ResearchIntelligenceService(db=test_db)
        item = await service.ingest_research(
            title="Goldman Sachs Rates Outlook Q3 2026",
            supplier="Goldman Sachs",
            asset_class="Rates",
            conviction="HIGH",
            star_rating=4,
        )

        assert item is not None
        assert item.id is not None
        assert item.title == "Goldman Sachs Rates Outlook Q3 2026"
        assert item.supplier == "Goldman Sachs"
        assert item.conviction == "HIGH"

    @pytest.mark.asyncio
    async def test_summarize_research_extracts_thesis(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Summarising a research document extracts the key thesis."""
        mock_claude_json.return_value = {
            "key_thesis": "Rates to remain elevated; reduce duration.",
            "key_trades": ["Long 2s10s steepener"],
            "conviction": "HIGH",
            "summary": "Goldman expects Fed on hold through year-end.",
        }

        from app.services.research_intelligence import ResearchIntelligenceService

        service = ResearchIntelligenceService(db=test_db)
        result = await service.summarize_research(
            content="Goldman Sachs believes the Fed will hold rates through 2026...",
            research_id="test-research-001",
        )

        assert result is not None
        assert "key_thesis" in result or "summary" in result
        mock_claude_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_research_validates_range(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Rating a research item rejects ratings outside the 1-5 range."""
        from app.services.research_intelligence import ResearchIntelligenceService
        from app.models.research_item import ResearchItem

        item = ResearchItem(
            title="Ratable Research",
            supplier="JPMorgan",
            asset_class="FX",
            conviction="MEDIUM",
            star_rating=3,
        )
        test_db.add(item)
        await test_db.commit()
        await test_db.refresh(item)

        service = ResearchIntelligenceService(db=test_db)

        # Valid rating
        await service.rate_research(str(item.id), star_rating=5)
        await test_db.refresh(item)
        assert item.star_rating == 5

        # Invalid rating should raise
        with pytest.raises(ValueError):
            await service.rate_research(str(item.id), star_rating=6)

        with pytest.raises(ValueError):
            await service.rate_research(str(item.id), star_rating=0)

    @pytest.mark.asyncio
    async def test_supplier_stats_calculates_averages(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Supplier stats endpoint returns average rating and item count per supplier."""
        from app.services.research_intelligence import ResearchIntelligenceService
        from app.models.research_item import ResearchItem

        items = [
            ResearchItem(title="GS 1", supplier="Goldman Sachs", asset_class="Rates", conviction="HIGH", star_rating=5),
            ResearchItem(title="GS 2", supplier="Goldman Sachs", asset_class="FX",    conviction="MEDIUM", star_rating=3),
            ResearchItem(title="JPM 1", supplier="JPMorgan",     asset_class="Rates", conviction="LOW",  star_rating=2),
        ]
        test_db.add_all(items)
        await test_db.commit()

        service = ResearchIntelligenceService(db=test_db)
        stats = await service.get_supplier_stats()

        assert isinstance(stats, list)
        gs_stat = next((s for s in stats if (s["supplier"] if isinstance(s, dict) else s.supplier) == "Goldman Sachs"), None)
        assert gs_stat is not None
        avg = gs_stat["avg_rating"] if isinstance(gs_stat, dict) else gs_stat.avg_rating
        assert abs(avg - 4.0) < 0.01  # (5 + 3) / 2 = 4.0

    @pytest.mark.asyncio
    async def test_weekly_digest_filters_by_date(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Weekly digest includes only items published within the past 7 days."""
        from app.services.research_intelligence import ResearchIntelligenceService
        from app.models.research_item import ResearchItem
        import datetime

        today = datetime.date.today()
        recent = ResearchItem(
            title="Recent Note",
            supplier="Citi",
            asset_class="Equities",
            conviction="HIGH",
            star_rating=4,
            published_date=(today - datetime.timedelta(days=2)).isoformat(),
        )
        old = ResearchItem(
            title="Old Note",
            supplier="Citi",
            asset_class="Equities",
            conviction="MEDIUM",
            star_rating=3,
            published_date=(today - datetime.timedelta(days=14)).isoformat(),
        )
        test_db.add_all([recent, old])
        await test_db.commit()

        service = ResearchIntelligenceService(db=test_db)
        digest_items = await service.get_weekly_digest_items(days=7)

        titles = [i.title for i in digest_items]
        assert "Recent Note" in titles
        assert "Old Note" not in titles
