"""Section 7 market data helpers."""
from __future__ import annotations

from typing import Any

TICKER_MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Gold": "GC=F",
    "WTI": "CL=F",
    "US 10Y": "^TNX",
    "US 2Y": "^IRX",
}


def map_instrument_to_ticker(instrument: str, yahoo_ticker: str | None = None) -> str | None:
    """Map internal instrument labels to Yahoo tickers."""
    if yahoo_ticker:
        return yahoo_ticker
    return TICKER_MAP.get(instrument)


async def get_portfolio_prices(positions: list[dict[str, Any]]) -> dict[str, Any]:
    """Fetch 2-day Yahoo price data for all mapped position tickers."""
    import yfinance as yf

    tickers = []
    for p in positions:
        mapped = map_instrument_to_ticker(
            instrument=str(p.get("instrument") or ""),
            yahoo_ticker=p.get("yahoo_ticker"),
        )
        if mapped:
            tickers.append(mapped)

    if not tickers:
        return {"tickers": [], "prices": {}}

    data = yf.download(tickers, period="2d", auto_adjust=True, group_by="ticker")
    prices: dict[str, Any] = {}
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                close_series = data["Close"]
            else:
                close_series = data[ticker]["Close"]
            prices[ticker] = close_series.dropna().to_dict()
        except Exception:
            prices[ticker] = {}
    return {"tickers": tickers, "prices": prices}

