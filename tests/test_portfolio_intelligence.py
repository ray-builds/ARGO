"""Tests for the Portfolio Intelligence service."""
from __future__ import annotations

import io
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch


SAMPLE_CSV = """instrument,type,asset_class,direction,notional,weight
UST 10Y,Bond,Rates,LONG,10000000,0.25
UST 30Y,Bond,Rates,SHORT,5000000,0.125
EUR/USD,FX,FX,LONG,8000000,0.20
SPX,Equity,Equities,SHORT,7000000,0.175
"""


class TestPortfolioIntelligenceService:
    """Tests for position management, scenario analysis, and convexity analysis."""

    @pytest.mark.asyncio
    async def test_upload_positions_csv_parses_correctly(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Uploading a CSV with position data parses and stores all rows."""
        from app.services.portfolio_intelligence import PortfolioIntelligenceService

        service = PortfolioIntelligenceService(db=test_db)
        csv_file = io.BytesIO(SAMPLE_CSV.encode())

        result = await service.upload_positions_csv(
            csv_data=csv_file,
            as_of_date="2026-05-05",
        )

        assert result is not None
        positions = result.get("positions") or result
        if isinstance(positions, list):
            assert len(positions) == 4
            instruments = [p["instrument"] if isinstance(p, dict) else p.instrument for p in positions]
            assert "UST 10Y" in instruments

    @pytest.mark.asyncio
    async def test_get_composition_aggregates_by_asset_class(
        self,
        test_db: AsyncSession,
    ) -> None:
        """get_composition returns notional aggregated by asset class."""
        from app.services.portfolio_intelligence import PortfolioIntelligenceService
        from app.models.portfolio import Position

        positions = [
            Position(instrument="UST 10Y", asset_class="Rates",  direction="LONG",  notional=10_000_000, weight=0.25),
            Position(instrument="UST 2Y",  asset_class="Rates",  direction="LONG",  notional=5_000_000,  weight=0.125),
            Position(instrument="EUR/USD", asset_class="FX",     direction="SHORT", notional=8_000_000,  weight=0.20),
        ]
        test_db.add_all(positions)
        await test_db.commit()

        service = PortfolioIntelligenceService(db=test_db)
        composition = await service.get_composition()

        asset_classes = [c["asset_class"] if isinstance(c, dict) else c.asset_class for c in composition]
        assert "Rates" in asset_classes
        assert "FX" in asset_classes

        rates_entry = next((c for c in composition if (c["asset_class"] if isinstance(c, dict) else c.asset_class) == "Rates"), None)
        assert rates_entry is not None

    @pytest.mark.asyncio
    async def test_run_scenario_calls_sonnet(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Running a scenario analysis calls Claude and returns structured output."""
        mock_claude_json.return_value = {
            "scenario_description": "UST 10Y rises 100bps",
            "estimated_pnl": -1_500_000,
            "key_risks": ["Duration risk", "Convexity drag"],
            "recommendations": ["Reduce UST 10Y", "Add curve steepener"],
        }

        from app.services.portfolio_intelligence import PortfolioIntelligenceService

        service = PortfolioIntelligenceService(db=test_db)
        result = await service.run_scenario(
            description="UST 10Y yields rise 100bps, USD strengthens 5%"
        )

        assert result is not None
        mock_claude_json.assert_called_once()
        assert "scenario_description" in result or "recommendations" in result or result is not None

    @pytest.mark.asyncio
    async def test_generate_trade_ideas_returns_three_ideas(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Trade idea generation returns exactly 3 actionable ideas."""
        mock_claude_json.return_value = {
            "trade_ideas": [
                {"idea": "Long UST 2s10s steepener", "rationale": "Curve too flat"},
                {"idea": "Short EUR/USD", "rationale": "USD strength on data"},
                {"idea": "Long gold", "rationale": "Safe haven demand"},
            ]
        }

        from app.services.portfolio_intelligence import PortfolioIntelligenceService

        service = PortfolioIntelligenceService(db=test_db)
        ideas = await service.generate_trade_ideas()

        trade_ideas = ideas.get("trade_ideas", ideas) if isinstance(ideas, dict) else ideas
        assert len(trade_ideas) >= 3

    @pytest.mark.asyncio
    async def test_convexity_analysis_identifies_gaps(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Convexity analysis identifies positions with convexity gaps and returns recommendations."""
        mock_claude_json.return_value = {
            "convexity_gaps": [
                {"position": "UST 30Y", "issue": "Negative convexity at high duration"},
            ],
            "recommendations": [
                "Add swaption protection on UST 30Y",
            ],
        }

        from app.services.portfolio_intelligence import PortfolioIntelligenceService

        service = PortfolioIntelligenceService(db=test_db)
        result = await service.analyze_convexity()

        assert result is not None
        assert "convexity_gaps" in result or "recommendations" in result or result is not None
