"""Section 9 authenticated API tests for run/status endpoints."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_morning_briefing_endpoints_require_auth(async_client) -> None:
    run_resp = await async_client.post("/api/v1/morning-briefing/run")
    status_resp = await async_client.get("/api/v1/morning-briefing/status")
    assert run_resp.status_code == 401
    assert status_resp.status_code == 401


@pytest.mark.asyncio
async def test_morning_briefing_run_authenticated(async_client) -> None:
    from app.dependencies import get_current_user
    from app.main import app

    user = SimpleNamespace(email="tester@arp.local", graph_access_token="token")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch(
            "app.routes.morning_briefing.generate_morning_briefing",
            new_callable=AsyncMock,
            return_value="## OVERNIGHT P&L DRIVERS\n...",
        ) as mock_run:
            response = await async_client.post("/api/v1/morning-briefing/run")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert "OVERNIGHT P&L DRIVERS" in payload["brief"]
        mock_run.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_morning_briefing_status_authenticated(async_client) -> None:
    from app.dependencies import get_current_user
    from app.main import app

    user = SimpleNamespace(email="tester@arp.local", graph_access_token="token")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch(
            "app.routes.morning_briefing.get_scheduler_status",
            return_value={
                "running": True,
                "jobs": [{"id": "section9_morning_brief", "name": "Section 9 Morning Brief", "next_run_time": None}],
            },
        ):
            response = await async_client.get("/api/v1/morning-briefing/status")
        assert response.status_code == 200
        payload = response.json()
        assert payload["scheduler_running"] is True
        assert payload["job"]["id"] == "section9_morning_brief"
    finally:
        app.dependency_overrides.clear()

