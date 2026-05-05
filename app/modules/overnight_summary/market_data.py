"""Market data fetcher — returns mock data with realistic variation.

TODO: Replace with OpenBB client when live data integration is available.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from loguru import logger


def _gauss(mu: float, sigma: float, decimals: int = 2) -> float:
    """Return a Gaussian-distributed float rounded to `decimals` places."""
    return round(random.gauss(mu, sigma), decimals)


class MarketDataFetcher:
    """Fetches overnight market data for the morning briefing.

    Currently returns mock data using Gaussian noise for realistic variation.
    The interface is stable; swap `get_overnight_moves()` internals with
    an OpenBB client when production data access is available.
    """

    def get_overnight_moves(self) -> dict[str, Any]:
        """Return a snapshot of overnight market moves across asset classes.

        Returns:
            Dict with keys: equities, rates, fx, credit, as_of, data_source.
            All numeric values are rounded to 2 decimal places.
        """
        logger.info("MarketDataFetcher: returning mock market data (OpenBB not yet integrated)")

        data: dict[str, Any] = {
            "equities": {
                "SPX": {
                    "price": round(5200.0 + _gauss(0, 40), 2),
                    "change_pct": _gauss(0, 0.8),
                },
                "FTSE": {
                    "price": round(7800.0 + _gauss(0, 60), 2),
                    "change_pct": _gauss(0, 0.7),
                },
                "DAX": {
                    "price": round(18000.0 + _gauss(0, 120), 2),
                    "change_pct": _gauss(0, 0.9),
                },
                "Nikkei": {
                    "price": round(38000.0 + _gauss(0, 300), 2),
                    "change_pct": _gauss(0, 1.0),
                },
            },
            "rates": {
                "US10Y": {
                    "level": round(4.35 + _gauss(0, 0.08), 2),
                    "change_bp": _gauss(0, 5),
                },
                "US2Y": {
                    "level": round(4.85 + _gauss(0, 0.06), 2),
                    "change_bp": _gauss(0, 4),
                },
                "Bund10Y": {
                    "level": round(2.55 + _gauss(0, 0.05), 2),
                    "change_bp": _gauss(0, 3),
                },
                "Gilt10Y": {
                    "level": round(4.10 + _gauss(0, 0.06), 2),
                    "change_bp": _gauss(0, 4),
                },
            },
            "fx": {
                "EURUSD": {
                    "price": round(1.085 + _gauss(0, 0.005), 4),
                    "change_pct": _gauss(0, 0.4),
                },
                "GBPUSD": {
                    "price": round(1.265 + _gauss(0, 0.006), 4),
                    "change_pct": _gauss(0, 0.35),
                },
                "USDJPY": {
                    "price": round(149.5 + _gauss(0, 0.8), 2),
                    "change_pct": _gauss(0, 0.4),
                },
                "DXY": {
                    "price": round(104.5 + _gauss(0, 0.4), 2),
                    "change_pct": _gauss(0, 0.3),
                },
            },
            "credit": {
                "CDX_IG": {
                    "level": round(52 + _gauss(0, 2), 2),
                    "change_bp": _gauss(0, 2),
                },
                "CDX_HY": {
                    "level": round(340 + _gauss(0, 8), 2),
                    "change_bp": _gauss(0, 5),
                },
                "ITRAXX_MAIN": {
                    "level": round(60 + _gauss(0, 2), 2),
                    "change_bp": _gauss(0, 2),
                },
            },
            "as_of": datetime.now(timezone.utc).isoformat(),
            "data_source": "MOCK_DATA",  # TODO: Replace with OpenBB client when live
        }

        return data


# ── Module-level singleton ────────────────────────────────────────────────────

_fetcher: MarketDataFetcher | None = None


def get_market_data_fetcher() -> MarketDataFetcher:
    """Return the module-level MarketDataFetcher singleton."""
    global _fetcher
    if _fetcher is None:
        _fetcher = MarketDataFetcher()
    return _fetcher
