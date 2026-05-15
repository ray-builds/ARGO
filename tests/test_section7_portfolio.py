"""Section 7 tests: portfolio prices + scenario templates."""
from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

import pytest

from app.services.market_data_service import get_portfolio_prices


@pytest.mark.asyncio
async def test_portfolio_prices_fetched(monkeypatch) -> None:
    class FakeSeries:
        def dropna(self):
            return self

        def to_dict(self):
            return {"2026-05-15": 1.085}

    class FakeDownloadFrame:
        def __getitem__(self, key):
            if key == "Close":
                return FakeSeries()
            return {"Close": FakeSeries()}

    def fake_download(*_args, **_kwargs):
        return FakeDownloadFrame()

    fake_mod = SimpleNamespace(download=fake_download)
    monkeypatch.setitem(sys.modules, "yfinance", fake_mod)

    positions = [
        {"instrument": "EURUSD", "yahoo_ticker": "EURUSD=X"},
        {"instrument": "Gold", "yahoo_ticker": "GC=F"},
    ]
    prices = await get_portfolio_prices(positions)
    assert prices is not None
    assert "EURUSD=X" in prices["tickers"]


@pytest.mark.asyncio
async def test_scenario_analysis_prompt_no_fabricated_figures(test_db) -> None:
    """Scenario output must contain [ESTIMATE] tags, not bare dollar figures."""
    from app.modules.portfolio_intelligence.service import PortfolioIntelligenceService
    from app.models.portfolio import Position

    positions = [
        Position(
            portfolio_name="main",
            instrument="EURUSD",
            instrument_type="FX",
            asset_class="FX",
            notional=2_000_000,
            currency="USD",
            direction="LONG",
            as_of_date=date.today(),
            uploaded_by_email="test@arp.local",
        ),
        Position(
            portfolio_name="main",
            instrument="US 10Y",
            instrument_type="BOND",
            asset_class="RATES",
            notional=5_000_000,
            currency="USD",
            direction="SHORT",
            as_of_date=date.today(),
            uploaded_by_email="test@arp.local",
        ),
    ]
    test_db.add_all(positions)
    await test_db.commit()

    service = PortfolioIntelligenceService(test_db)
    result = await service.run_prebuilt_scenario("Fed hikes 50bps surprise")
    output = result["analysis"]
    lines_with_numbers = [l for l in output.split("\n") if "$" in l or "M " in l]
    for line in lines_with_numbers:
        assert "[ESTIMATE]" in line or "⚠️" in line, f"Untagged figure in: {line}"


@pytest.mark.asyncio
async def test_positions_accessible(test_db) -> None:
    from app.modules.portfolio_intelligence.service import PortfolioIntelligenceService
    from app.models.portfolio import Position

    test_db.add(
        Position(
            portfolio_name="main",
            instrument="EURUSD",
            instrument_type="FX",
            asset_class="FX",
            notional=1_000_000,
            currency="USD",
            direction="LONG",
            as_of_date=date.today(),
            uploaded_by_email="test@arp.local",
        )
    )
    await test_db.commit()

    service = PortfolioIntelligenceService(test_db)
    positions = await service.list_positions("main")
    assert len(positions) > 0

