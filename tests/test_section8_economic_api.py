"""Section 8 authenticated API integration tests for realtime endpoints."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_realtime_endpoints_require_auth(async_client) -> None:
    endpoints = [
        "/api/v1/econ-realtime/calendar/trading-economics",
        "/api/v1/econ-realtime/calendar/fred",
        "/api/v1/econ-realtime/central-banks/rss?url=https://example.com/rss.xml",
    ]
    for ep in endpoints:
        response = await async_client.get(ep)
        assert response.status_code == 401

    release_response = await async_client.post(
        "/api/v1/econ-realtime/release",
        json={"indicator": "US CPI", "actual": 3.4, "consensus": 3.2, "prior": 3.1},
    )
    assert release_response.status_code == 401


@pytest.mark.asyncio
async def test_realtime_calendar_te_authenticated(async_client) -> None:
    from app.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(email="tester@arp.local")
    try:
        with patch(
            "app.routes.economic_realtime.get_economic_calendar_trading_economics",
            new_callable=AsyncMock,
            return_value=[{"event": "US CPI"}],
        ) as mock_te:
            response = await async_client.get("/api/v1/econ-realtime/calendar/trading-economics?days_ahead=5")
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        assert payload["events"][0]["event"] == "US CPI"
        mock_te.assert_awaited_once_with(days_ahead=5)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_realtime_calendar_fred_authenticated(async_client) -> None:
    from app.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(email="tester@arp.local")
    try:
        with patch(
            "app.routes.economic_realtime.get_fred_release_calendar",
            new_callable=AsyncMock,
            return_value={"release_dates": [{"date": "2026-05-20"}]},
        ) as mock_fred:
            response = await async_client.get("/api/v1/econ-realtime/calendar/fred")
        assert response.status_code == 200
        payload = response.json()
        assert "data" in payload
        assert payload["data"]["release_dates"][0]["date"] == "2026-05-20"
        mock_fred.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_realtime_release_commentary_authenticated(async_client) -> None:
    from app.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(email="tester@arp.local")
    try:
        with patch(
            "app.routes.economic_realtime.on_data_release",
            new_callable=AsyncMock,
            return_value="## US CPI - 3.4 vs 3.2 consensus [UPSIDE SURPRISE]",
        ) as mock_release:
            response = await async_client.post(
                "/api/v1/econ-realtime/release",
                json={"indicator": "US CPI", "actual": 3.4, "consensus": 3.2, "prior": 3.1},
            )
        assert response.status_code == 200
        payload = response.json()
        assert "UPSIDE SURPRISE" in payload["commentary"]
        mock_release.assert_awaited_once_with(
            indicator="US CPI",
            actual=3.4,
            consensus=3.2,
            prior=3.1,
        )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_realtime_central_bank_endpoints_authenticated(async_client) -> None:
    from app.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(email="tester@arp.local")
    try:
        with patch(
            "app.routes.economic_realtime.fetch_cb_rss",
            new_callable=AsyncMock,
            return_value=[{"title": "Fed Statement"}],
        ) as mock_rss, patch(
            "app.routes.economic_realtime.track_central_bank_language",
            new_callable=AsyncMock,
            return_value={"Fed": {"shift_vs_last": "MORE_HAWKISH"}},
        ) as mock_track:
            rss_response = await async_client.get(
                "/api/v1/econ-realtime/central-banks/rss?url=https://fed.example/rss.xml"
            )
            track_response = await async_client.post("/api/v1/econ-realtime/central-banks/track")

        assert rss_response.status_code == 200
        rss_payload = rss_response.json()
        assert rss_payload["count"] == 1
        assert rss_payload["items"][0]["title"] == "Fed Statement"

        assert track_response.status_code == 200
        track_payload = track_response.json()
        assert track_payload["result"]["Fed"]["shift_vs_last"] == "MORE_HAWKISH"

        mock_rss.assert_awaited_once_with("https://fed.example/rss.xml")
        mock_track.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()

