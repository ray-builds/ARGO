"""Section 3 — Email reply suggestion + send tests.

These tests exercise the reply service directly so they are independent of
session-based auth wiring. Claude and Graph calls are mocked.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.email import Email
from app.modules.email_intelligence.reply_service import (
    EmailReplyService,
    VALID_TONES,
    strip_html_and_signatures,
)


TEST_USER_EMAIL = "trader@arpglobalcapital.com"


async def _seed_email(db, *, subject: str, body_preview: str, graph_id: str = "graph-1") -> Email:
    email = Email(
        graph_message_id=graph_id,
        mailbox_user_email=TEST_USER_EMAIL,
        sender_email="counterparty@example.com",
        sender_name="Counterparty",
        subject=subject,
        body_preview=body_preview,
        received_at=datetime.now(timezone.utc),
        is_read=False,
        tag="CLIENT",
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)
    return email


def _mock_graph_message(subject: str, body: str) -> dict:
    return {
        "id": "graph-1",
        "subject": subject,
        "from": {"emailAddress": {"address": "counterparty@example.com", "name": "Counterparty"}},
        "body": {"contentType": "Text", "content": body},
    }


def _claude_reply(subject: str, body: str, flags=None) -> str:
    return json.dumps(
        {
            "subject": subject,
            "body": body,
            "tone_used": "drafted",
            "flags": flags or [],
        }
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def test_strip_html_and_signatures_removes_tags_and_signature() -> None:
    text = "<p>Hello</p> world\n\n-- \nBest,\nAlice"
    assert "Best" not in strip_html_and_signatures(text)
    assert "Hello" in strip_html_and_signatures(text)


# ── /reply-suggestion ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reply_suggestion_returns_valid_draft(test_db) -> None:
    """AI suggestion is valid JSON with required fields and is non-trivial."""
    email = await _seed_email(
        test_db,
        subject="Q3 portfolio review",
        body_preview="Could you confirm the revised attribution numbers before close?",
    )

    drafted_body = (
        "Confirming — attribution for Q3 will be circulated by today's close. "
        "I'll loop in Rhys so we have a sanity check before it goes out."
    )

    with patch(
        "app.modules.email_intelligence.reply_service.GraphClient.get_message",
        new_callable=AsyncMock,
        return_value=_mock_graph_message(email.subject, "Could you confirm the numbers?"),
    ), patch(
        "app.modules.email_intelligence.reply_service.GraphClient.create_reply_draft",
        new_callable=AsyncMock,
        return_value={"id": "draft-99"},
    ), patch(
        "app.core.claude_client.ClaudeClient.complete",
        new_callable=AsyncMock,
        return_value=_claude_reply(f"Re: {email.subject}", drafted_body, flags=["confirm attribution"]),
    ):
        service = EmailReplyService(test_db)
        result = await service.generate_suggestion(
            email_id=email.id,
            user_email=TEST_USER_EMAIL,
            access_token="token",
            reply_author_name="Rayhan Shhadeh",
            reply_author_title="Dev Lead",
            tone="COLLEGIAL_PEER",
            user_context="",
        )

    assert "suggestion" in result
    sugg = result["suggestion"]
    assert "subject" in sugg and sugg["subject"].lower().startswith("re:")
    assert "body" in sugg and len(sugg["body"]) > 20
    assert result["graph_draft_id"] == "draft-99"


@pytest.mark.asyncio
async def test_reply_suggestion_rejects_invalid_tone(test_db) -> None:
    email = await _seed_email(test_db, subject="x", body_preview="y")
    service = EmailReplyService(test_db)
    with pytest.raises(ValueError):
        await service.generate_suggestion(
            email_id=email.id,
            user_email=TEST_USER_EMAIL,
            access_token="token",
            reply_author_name="X",
            reply_author_title="Y",
            tone="SHOUTY",
            user_context=None,
        )


@pytest.mark.asyncio
async def test_reply_does_not_invent_numbers(test_db) -> None:
    """When the original email has no figures, the drafted body must contain none either.

    This is a contract check on our service surface: the service trusts whatever
    Claude returns, so we assert the mocked Claude reply itself is clean. The
    point of the test is the wiring — service must not append fabricated figures.
    """
    email = await _seed_email(
        test_db,
        subject="Brief check-in",
        body_preview="Just touching base, let me know when you have a minute.",
    )
    drafted_body = "Happy to chat. Are you free Thursday afternoon?"

    with patch(
        "app.modules.email_intelligence.reply_service.GraphClient.get_message",
        new_callable=AsyncMock,
        return_value=_mock_graph_message(email.subject, "Just touching base."),
    ), patch(
        "app.modules.email_intelligence.reply_service.GraphClient.create_reply_draft",
        new_callable=AsyncMock,
        return_value={"id": "draft-1"},
    ), patch(
        "app.core.claude_client.ClaudeClient.complete",
        new_callable=AsyncMock,
        return_value=_claude_reply(f"Re: {email.subject}", drafted_body),
    ):
        service = EmailReplyService(test_db)
        result = await service.generate_suggestion(
            email_id=email.id,
            user_email=TEST_USER_EMAIL,
            access_token="token",
            reply_author_name="R",
            reply_author_title="Dev Lead",
            tone="FORMAL_CLIENT",
            user_context="",
        )

    body = result["suggestion"]["body"]
    fabricated = re.findall(r"\$[\d,]+|\d+%|\d+\s*bps", body)
    assert fabricated == []


@pytest.mark.asyncio
async def test_reply_tone_affects_output(test_db) -> None:
    """Different tones map to different prompts; brief acknowledgement should be shorter."""
    email = await _seed_email(test_db, subject="follow up", body_preview="please confirm timing")

    formal_body = (
        "Thank you for the note. I will confirm our preferred timing shortly and "
        "circle back with calendar holds for both teams before end of day tomorrow."
    )
    brief_body = "Will confirm timing shortly."

    captured: list[str] = []

    async def _fake_complete(prompt: str, system: str = "", use_sonnet: bool = False, **_):
        captured.append(prompt)
        # Tone register is interpolated as "Tone register: <TONE>" — match on that
        # exact substring so we don't pick up the prompt's literal tone enum list.
        body = brief_body if "Tone register: BRIEF_ACKNOWLEDGMENT" in prompt else formal_body
        return _claude_reply(f"Re: {email.subject}", body)

    with patch(
        "app.modules.email_intelligence.reply_service.GraphClient.get_message",
        new_callable=AsyncMock,
        return_value=_mock_graph_message(email.subject, "please confirm timing"),
    ), patch(
        "app.modules.email_intelligence.reply_service.GraphClient.create_reply_draft",
        new_callable=AsyncMock,
        return_value={"id": "d"},
    ), patch(
        "app.core.claude_client.ClaudeClient.complete",
        new_callable=AsyncMock,
        side_effect=_fake_complete,
    ):
        service = EmailReplyService(test_db)
        formal = await service.generate_suggestion(
            email_id=email.id, user_email=TEST_USER_EMAIL, access_token="t",
            reply_author_name="X", reply_author_title="Y",
            tone="FORMAL_CLIENT", user_context="",
        )
        brief = await service.generate_suggestion(
            email_id=email.id, user_email=TEST_USER_EMAIL, access_token="t",
            reply_author_name="X", reply_author_title="Y",
            tone="BRIEF_ACKNOWLEDGMENT", user_context="",
        )

    assert len(brief["suggestion"]["body"]) < len(formal["suggestion"]["body"])
    assert any("FORMAL_CLIENT" in p for p in captured)
    assert any("BRIEF_ACKNOWLEDGMENT" in p for p in captured)


# ── /send-reply ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_reply_calls_graph(test_db) -> None:
    email = await _seed_email(test_db, subject="ready?", body_preview="ready?")
    with patch(
        "app.modules.email_intelligence.reply_service.GraphClient.send_reply",
        new_callable=AsyncMock,
    ) as mock_send:
        service = EmailReplyService(test_db)
        result = await service.send_reply(
            email_id=email.id,
            user_email=TEST_USER_EMAIL,
            access_token="token",
            body="Yes — let's proceed.",
            subject="Re: ready?",
        )

    assert result["status"] == "sent"
    mock_send.assert_awaited_once()
    kwargs = mock_send.await_args.kwargs
    assert kwargs["user_email"] == TEST_USER_EMAIL
    assert kwargs["message_id"] == email.graph_message_id
    assert "Yes" in kwargs["body_html"]


@pytest.mark.asyncio
async def test_send_reply_missing_email_raises(test_db) -> None:
    service = EmailReplyService(test_db)
    with pytest.raises(ValueError):
        await service.send_reply(
            email_id="no-such-id",
            user_email=TEST_USER_EMAIL,
            access_token="token",
            body="hi",
        )


# ── Surface check ────────────────────────────────────────────────────────────


def test_valid_tones_match_router() -> None:
    """Sanity: the tone constants the router and JS reference exist here."""
    expected = {
        "FORMAL_CLIENT",
        "COLLEGIAL_PEER",
        "DIRECT_INTERNAL",
        "BRIEF_ACKNOWLEDGMENT",
    }
    assert set(VALID_TONES) == expected
