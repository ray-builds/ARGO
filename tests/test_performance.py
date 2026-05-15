"""Section 12.4 performance benchmark tests."""
from __future__ import annotations

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_email_classification_under_3s(test_db) -> None:
    from app.modules.email_intelligence.service import EmailIntelligenceService

    service = EmailIntelligenceService(test_db)
    fake = {"tag": "RESEARCH", "relevance_score": 80}
    start = time.time()
    with patch("app.core.claude_client.ClaudeClient.complete_json", new_callable=AsyncMock, return_value=fake):
        await service._classify_email("A", "a@test.com", "subject", "body")
    assert time.time() - start < 3.0


@pytest.mark.asyncio
async def test_reply_suggestion_under_8s(test_db) -> None:
    from app.modules.email_intelligence.reply_service import EmailReplyService
    from app.models.email import Email

    email = Email(
        graph_message_id="msg-1",
        mailbox_user_email="user@test.com",
        sender_email="sender@test.com",
        sender_name="Sender",
        subject="Need update",
        body_preview="Please confirm timeline.",
        received_at=datetime.now(UTC),
        is_read=False,
        is_from_ceo=False,
    )
    test_db.add(email)
    await test_db.commit()
    await test_db.refresh(email)

    start = time.time()
    with patch("app.core.graph_client.GraphClient.get_message", new_callable=AsyncMock, return_value={
        "subject": "Need update",
        "from": {"emailAddress": {"address": "sender@test.com", "name": "Sender"}},
        "body": {"content": "Please confirm timeline."},
    }), patch("app.core.claude_client.ClaudeClient.complete", new_callable=AsyncMock, return_value='{"subject":"Re: Need update","body":"Will revert by EOD.","tone_used":"DIRECT_INTERNAL","flags":[]}'), patch(
        "app.core.graph_client.GraphClient.create_reply_draft", new_callable=AsyncMock, return_value={"id": "draft-1"}
    ):
        service = EmailReplyService(test_db)
        await service.generate_suggestion(
            email_id=email.id,
            user_email="user@test.com",
            access_token="token",
            reply_author_name="Tester",
            reply_author_title="Ops",
            tone="DIRECT_INTERNAL",
            user_context=None,
        )
    assert time.time() - start < 8.0


@pytest.mark.asyncio
async def test_morning_briefing_under_45s() -> None:
    from app.services.morning_briefing_service import generate_morning_briefing

    start = time.time()
    with patch("app.services.morning_briefing_service.get_fred_series", new_callable=AsyncMock, return_value={"FEDFUNDS": []}), patch(
        "app.services.onedrive_service.OneDriveService.upload_file", new_callable=AsyncMock
    ):
        await generate_morning_briefing(datetime.now(UTC), "test-token")
    assert time.time() - start < 45.0


@pytest.mark.asyncio
async def test_economic_release_commentary_under_10s() -> None:
    from app.services.economic_calendar_service import on_data_release

    start = time.time()
    await on_data_release("US CPI", 3.4, 3.2, 3.1)
    assert time.time() - start < 10.0

