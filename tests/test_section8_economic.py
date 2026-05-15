"""Section 8 tests for realtime economic intelligence."""
from __future__ import annotations

import time
from unittest import mock

import pytest

from app.services.economic_calendar_service import (
    fetch_cb_rss,
    get_surprise_direction,
    on_data_release,
)


@pytest.mark.asyncio
async def test_economic_release_triggers_commentary() -> None:
    """Release detection generates commentary within 90s."""
    start = time.time()
    await on_data_release("US CPI", actual=3.4, consensus=3.2, prior=3.1)
    elapsed = time.time() - start
    assert elapsed < 90, f"Commentary took too long: {elapsed}s"


def test_upside_surprise_detected() -> None:
    surprise_dir = get_surprise_direction(actual=3.4, consensus=3.2)
    assert surprise_dir == "UPSIDE"


@pytest.mark.asyncio
async def test_central_bank_tracker_parses_rss() -> None:
    xml = """<?xml version='1.0'?>
<rss><channel><item><title>Fed Statement</title><link>https://x</link><description>Policy update</description></item></channel></rss>"""

    class FakeResponse:
        text = xml

    def fake_get(*_args, **_kwargs):
        return FakeResponse()

    items = await fetch_cb_rss("https://www.federalreserve.gov/feeds/press_monetary.xml", http_get=fake_get)
    assert len(items) > 0
    assert "title" in items[0]


@pytest.mark.asyncio
async def test_alert_sent_on_major_release() -> None:
    with mock.patch("app.services.economic_calendar_service.send_alert", new_callable=mock.AsyncMock) as mock_teams:
        await on_data_release("US NFP", actual=280000, consensus=180000, prior=150000)
        mock_teams.assert_awaited_once()

