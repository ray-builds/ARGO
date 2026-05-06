"""Tests for core utilities: Settings, chunker, and ClaudeClient retry logic."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.modules.research_lake.chunker import chunk_text


# ── Settings ──────────────────────────────────────────────────────────────────


def test_settings_loads() -> None:
    """get_settings() returns a Settings instance with required fields populated."""
    from app.config import get_settings

    # Clear lru_cache so env vars from conftest take effect
    get_settings.cache_clear()
    settings = get_settings()

    assert settings is not None
    assert settings.anthropic_api_key  # non-empty string set by conftest
    assert "@" in settings.ceo_email


def test_settings_is_development() -> None:
    """Settings.is_production returns False in test environment."""
    import os
    from app.config import Settings

    s = Settings(
        environment="development",
        secret_key="x" * 32,
        anthropic_api_key="k",
        azure_tenant_id="t",
        azure_client_id="c",
        azure_client_secret="s",
        ceo_email="ceo@test.com",
    )
    assert s.is_development is True
    assert s.is_production is False


def test_settings_graph_scopes_list() -> None:
    """Settings.graph_scopes_list returns a non-empty list of scope strings."""
    from app.config import Settings

    s = Settings(
        environment="test",
        secret_key="x" * 32,
        anthropic_api_key="k",
        azure_tenant_id="t",
        azure_client_id="c",
        azure_client_secret="s",
        ceo_email="ceo@test.com",
        graph_scopes="Mail.Read Mail.Send User.Read",
    )
    scopes = s.graph_scopes_list
    assert isinstance(scopes, list)
    assert "Mail.Read" in scopes
    assert "User.Read" in scopes


# ── chunk_text overlap ────────────────────────────────────────────────────────


def test_chunk_text_overlap_content() -> None:
    """Consecutive chunks from chunk_text share words due to the overlap window."""
    words = [f"tok{i}" for i in range(60)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size=10, overlap=3)

    assert len(chunks) >= 2
    # First chunk ends with words that should appear at the start of the second
    last_words_of_first = set(chunks[0].split()[-3:])
    first_words_of_second = set(chunks[1].split()[:3])
    assert last_words_of_first & first_words_of_second, (
        "Expected overlap between consecutive chunks"
    )


def test_chunk_text_all_words_covered() -> None:
    """chunk_text covers all words in the input across all chunks."""
    words = [f"w{i}" for i in range(200)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size=40, overlap=5)

    # Every word from the original text should appear in at least one chunk
    all_chunk_words: set[str] = set()
    for chunk in chunks:
        all_chunk_words.update(chunk.split())

    for word in words:
        assert word in all_chunk_words, f"Word {word!r} missing from chunks"


# ── ClaudeClient retry logic ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claude_client_retry_on_rate_limit() -> None:
    """ClaudeClient.complete retries after RateLimitError and eventually succeeds."""
    import anthropic

    # Build a mock response that looks like an Anthropic message
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Final answer")]
    mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)

    call_count = 0

    async def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise anthropic.RateLimitError(
                message="rate limit",
                response=MagicMock(status_code=429, headers={}),
                body={"error": {"type": "rate_limit_error", "message": "rate limit"}},
            )
        return mock_response

    with patch("anthropic.AsyncAnthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=_side_effect)
        MockAnthropic.return_value = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            from app.core.claude_client import ClaudeClient

            client = ClaudeClient.__new__(ClaudeClient)
            client._client = mock_client
            client.haiku_model = "claude-haiku-4-5"
            client.sonnet_model = "claude-sonnet-4-5"

            result = await client.complete("What is 2+2?")

    assert result == "Final answer"
    assert call_count == 3


@pytest.mark.asyncio
async def test_claude_client_raises_after_max_retries() -> None:
    """ClaudeClient.complete raises ClaudeAPIError after exhausting all retries."""
    import anthropic
    from app.core.claude_client import ClaudeAPIError

    async def _always_rate_limit(*args, **kwargs):
        raise anthropic.RateLimitError(
            message="rate limit",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"type": "rate_limit_error", "message": "rate limit"}},
        )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        from app.core.claude_client import ClaudeClient

        mock_inner = MagicMock()
        mock_inner.messages.create = AsyncMock(side_effect=_always_rate_limit)

        client = ClaudeClient.__new__(ClaudeClient)
        client._client = mock_inner
        client.haiku_model = "claude-haiku-4-5"
        client.sonnet_model = "claude-sonnet-4-5"

        with pytest.raises(ClaudeAPIError):
            await client.complete("Hello?")


def test_classifier_high_priority_urgent() -> None:
    """is_high_priority returns True when tag is URGENT."""
    from app.modules.email_intelligence.classifier import is_high_priority

    assert is_high_priority(relevance_score=50, tag="URGENT") is True


def test_classifier_high_priority_score() -> None:
    """is_high_priority returns True when relevance_score >= 80."""
    from app.modules.email_intelligence.classifier import is_high_priority

    assert is_high_priority(relevance_score=80, tag="RESEARCH") is True
    assert is_high_priority(relevance_score=79, tag="RESEARCH") is False


def test_classifier_tag_color_unknown_returns_grey() -> None:
    """get_tag_color returns grey (#6b7280) for unknown tags."""
    from app.modules.email_intelligence.classifier import get_tag_color

    assert get_tag_color("UNKNOWN_TAG") == "#6b7280"
    assert get_tag_color("URGENT") != "#6b7280"
