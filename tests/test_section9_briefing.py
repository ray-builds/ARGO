"""Section 9 tests for morning briefing aggregation pipeline."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest import mock

import pytest

from app.services.morning_briefing_service import generate_morning_briefing, timed_morning_brief_job


@pytest.mark.asyncio
async def test_morning_briefing_contains_required_sections() -> None:
    brief = await generate_morning_briefing(datetime.now(UTC), "test-token")
    required_sections = [
        "OVERNIGHT P&L DRIVERS",
        "REQUIRES YOUR DECISION TODAY",
        "MARKET OPEN WATCH LIST",
        "ECONOMIC EVENTS",
        "EMAILS REQUIRING RESPONSE",
        "RESEARCH INTEL",
    ]
    for section in required_sections:
        assert section in brief, f"Missing section: {section}"


@pytest.mark.asyncio
async def test_briefing_archived_to_onedrive() -> None:
    with mock.patch("app.services.onedrive_service.OneDriveService.upload_file", new_callable=mock.AsyncMock) as mock_upload:
        await generate_morning_briefing(datetime.now(UTC), "test-token")
        paths = [c.args[0] for c in mock_upload.await_args_list]
        assert any("MorningBriefings" in p for p in paths)


@pytest.mark.asyncio
async def test_briefing_delivered_by_630() -> None:
    """Scheduler fires at 06:00 GST and completes before 06:30."""
    _brief, elapsed = await timed_morning_brief_job()
    assert elapsed < 1800, "Briefing generation took >30 minutes"

