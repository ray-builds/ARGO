"""Centralized Anthropic Claude API client with retry logic, model selection, and token logging."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import anthropic
from loguru import logger


# ── Model constants ──────────────────────────────────────────────────────────

HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-4-5"


# ── Exceptions ───────────────────────────────────────────────────────────────

class ClaudeAPIError(Exception):
    """Raised when Claude API calls fail after all retry attempts."""


# ── Client ────────────────────────────────────────────────────────────────────

class ClaudeClient:
    """Wrapper around the Anthropic AsyncAnthropic API.

    All ARGO Claude calls MUST go through this client. It provides:
    - Automatic model selection (Haiku vs Sonnet) based on task complexity
    - Retry logic with exponential backoff (3 attempts: 1 s, 2 s, 4 s)
    - Structured token-usage logging via loguru
    - Consistent error handling with ClaudeAPIError

    Usage::

        client = get_claude_client()
        text = await client.complete("Summarise this email...", use_sonnet=False)
        data = await client.complete_json("Extract entities from...", use_sonnet=True)
    """

    def __init__(self) -> None:
        from app.config import get_settings
        settings = get_settings()

        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured")

        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.haiku_model: str = HAIKU
        self.sonnet_model: str = SONNET

    def _select_model(self, use_sonnet: bool) -> str:
        return self.sonnet_model if use_sonnet else self.haiku_model

    async def complete(
        self,
        prompt: str,
        system: str = "",
        use_sonnet: bool = False,
        max_tokens: int = 1024,
    ) -> str:
        """Send a completion request to Claude and return the text response.

        Retries up to 3 times with exponential backoff (1 s, 2 s, 4 s).

        Args:
            prompt: The user message to send.
            system: Optional system prompt.
            use_sonnet: If True, use Sonnet for complex reasoning; default is Haiku.
            max_tokens: Maximum tokens in the response.

        Returns:
            The assistant's text response as a plain string.

        Raises:
            ClaudeAPIError: After all retry attempts are exhausted.
        """
        model = self._select_model(use_sonnet)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        delays = [1, 2, 4]

        for attempt, delay in enumerate(delays, start=1):
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": messages,
                }
                if system:
                    kwargs["system"] = system

                response = await self._client.messages.create(**kwargs)

                text: str = response.content[0].text
                logger.info(
                    "Claude {} | input_tokens={} output_tokens={} | attempt={}",
                    model,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    attempt,
                )
                return text

            except anthropic.RateLimitError as e:
                logger.warning(
                    "Claude rate limit hit (attempt {}/{}), waiting {}s: {}",
                    attempt,
                    len(delays),
                    delay,
                    e,
                )
                if attempt < len(delays):
                    await asyncio.sleep(delay)
                else:
                    raise ClaudeAPIError(
                        f"Claude rate limit exceeded after {len(delays)} attempts"
                    ) from e

            except anthropic.APIError as e:
                logger.error(
                    "Claude API error (attempt {}/{}): {}", attempt, len(delays), e
                )
                if attempt < len(delays):
                    await asyncio.sleep(delay)
                else:
                    raise ClaudeAPIError(
                        f"Claude API failed after {len(delays)} attempts: {e}"
                    ) from e

        # Unreachable — satisfies type checker
        raise ClaudeAPIError("Claude complete() exited retry loop unexpectedly")

    async def complete_json(
        self,
        prompt: str,
        system: str = "",
        use_sonnet: bool = False,
    ) -> dict[str, Any]:
        """Request a JSON-structured response from Claude and parse it.

        Appends a strict JSON-only instruction to the prompt. Strips any
        markdown code-fence wrapper Claude may include despite the instruction.

        Args:
            prompt: The user message to send.
            system: Optional system prompt.
            use_sonnet: If True, use Sonnet.

        Returns:
            Parsed dict from Claude's JSON response.

        Raises:
            ClaudeAPIError: If the response is not valid JSON or the API fails.
        """
        json_prompt = (
            prompt
            + "\n\nRespond with valid JSON only. No markdown code blocks."
        )

        response_text = await self.complete(
            prompt=json_prompt,
            system=system,
            use_sonnet=use_sonnet,
            max_tokens=2048,
        )

        # Strip ```json ... ``` or ``` ... ``` fences if present
        text = response_text.strip()
        if text.startswith("```"):
            # Remove opening fence line
            text = text.split("\n", 1)[-1]
            # Remove closing fence
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("Claude returned invalid JSON: {!r}", text[:300])
            raise ClaudeAPIError(f"Claude response is not valid JSON: {exc}") from exc


# ── Module-level singleton ────────────────────────────────────────────────────

_client: ClaudeClient | None = None


def get_claude_client() -> ClaudeClient:
    """Return the module-level ClaudeClient singleton (created on first call)."""
    global _client
    if _client is None:
        _client = ClaudeClient()
    return _client
