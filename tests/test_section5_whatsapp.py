"""Section 5 tests: WhatsApp ingestion + weekly reports."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest

from app.services.whatsapp_service import (
    detect_trade_related,
    generate_weekly_whatsapp_report,
    process_whatsapp_message,
)


@pytest.mark.asyncio
async def test_trade_pattern_detection() -> None:
    trade_messages = [
        "buy 10M EURUSD at 1.0850",
        "short 5Y UST at 4.32",
        "close the S&P puts",
        "long 2M GBPUSD from here",
    ]
    non_trade_messages = [
        "see you at the meeting",
        "ok got it",
        "what time is dinner?",
    ]
    for msg in trade_messages:
        assert detect_trade_related(msg) is True, f"Should be trade: {msg}"
    for msg in non_trade_messages:
        assert detect_trade_related(msg) is False, f"Should NOT be trade: {msg}"


@pytest.mark.asyncio
async def test_trade_messages_archived_to_s3(test_db) -> None:
    with mock.patch("app.services.whatsapp_service.archive_to_compliance_s3") as mock_s3:
        await process_whatsapp_message(
            {
                "id": "1",
                "body": "buy 10M EURUSD at 1.0850",
                "author": "Yusuf",
                "timestamp": 1715680000,
                "groupName": "Trading",
            },
            test_db,
        )
        mock_s3.assert_called_once()


@pytest.mark.asyncio
async def test_weekly_report_includes_all_days(test_db) -> None:
    week_start = datetime(2026, 5, 4, tzinfo=UTC)
    week_end = week_start + timedelta(days=6, hours=23, minutes=59)
    report = await generate_weekly_whatsapp_report(week_start, week_end, test_db)
    assert week_start.strftime("%Y-%m-%d") in report
    assert week_end.strftime("%Y-%m-%d") in report


@pytest.mark.asyncio
async def test_compliance_flag_in_report(test_db) -> None:
    week_start = datetime(2026, 5, 4, tzinfo=UTC)
    week_end = week_start + timedelta(days=6, hours=23, minutes=59)
    await process_whatsapp_message(
        {
            "id": "2",
            "body": "yeah do that thing we discussed",
            "author": "Ops",
            "timestamp": int((week_start + timedelta(days=2)).timestamp()),
            "groupName": "Trading",
        },
        test_db,
    )
    report = await generate_weekly_whatsapp_report(week_start, week_end, test_db)
    assert "COMPLIANCE FLAGS" in report
    assert "do that thing we discussed" in report

