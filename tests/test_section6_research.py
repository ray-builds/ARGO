"""Section 6 tests: Research Lake upgrade."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.services.research_ingestion_service import (
    check_research_against_portfolio,
    count_ingested_by_url,
    get_fred_series,
    get_instrument_data,
    ingest_article,
)


@pytest.mark.asyncio
async def test_rss_ingestion_deduplication(test_db) -> None:
    """Same article URL ingested twice should only create one record."""
    article = {"url": "https://test.com/article1", "title": "Test"}
    await ingest_article(article, test_db)
    await ingest_article(article, test_db)
    count = await count_ingested_by_url("https://test.com/article1", test_db)
    assert count == 1


@pytest.mark.asyncio
async def test_contradiction_detection() -> None:
    """Bearish broker note on a LONG position triggers conflict."""
    portfolio = {
        "positions": [
            {"instrument": "EURUSD", "direction": "LONG", "notional_usd": 10_000_000}
        ]
    }
    research = {
        "instruments_mentioned": ["EURUSD"],
        "positioning_implication": {"stance": "BEARISH"},
    }
    conflicts = await check_research_against_portfolio(research, portfolio)
    assert len(conflicts) == 1
    assert conflicts[0]["conflict_type"] == "DIRECTIONAL_CONTRADICTION"
    assert conflicts[0]["severity"] == "HIGH"


@pytest.mark.asyncio
async def test_yfinance_returns_prices(monkeypatch) -> None:
    class FakeClose:
        def to_dict(self):
            return {"2026-05-14": 1.08}

    class FakeHist(dict):
        empty = False

        def __init__(self):
            super().__init__({"Close": FakeClose()})

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker
            self.info = {
                "currentPrice": 1.08 if ticker == "EURUSD=X" else 2400.0,
                "regularMarketChangePercent": 0.1,
                "fiftyTwoWeekHigh": 1.2,
                "fiftyTwoWeekLow": 1.0,
            }

        def history(self, period="5d"):
            return FakeHist()

    fake_mod = SimpleNamespace(Ticker=FakeTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake_mod)

    data = await get_instrument_data(["EURUSD=X", "GC=F"])
    assert "EURUSD=X" in data
    assert data["EURUSD=X"]["current_price"] is not None


@pytest.mark.asyncio
async def test_fred_returns_series() -> None:
    class FakeResponse:
        def json(self):
            return {"observations": [{"date": "2026-05-01", "value": "4.25"}]}

    def fake_get(*_args, **_kwargs):
        return FakeResponse()

    data = await get_fred_series(["FEDFUNDS", "DGS10"], http_get=fake_get)
    assert len(data["FEDFUNDS"]) > 0
    assert "date" in data["FEDFUNDS"][0]

