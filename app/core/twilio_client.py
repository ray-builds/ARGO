"""Twilio WhatsApp client for sending overnight summaries and alerts."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    pass

_CHUNK_SIZE = 1500


class TwilioClient:
    """Async-friendly wrapper around the Twilio REST API for WhatsApp delivery.

    Uses ``asyncio.to_thread`` to run the synchronous Twilio SDK without
    blocking the event loop.

    Falls back gracefully when TWILIO credentials are absent — sends are
    simply skipped with a log message.
    """

    def __init__(self) -> None:
        from app.config import get_settings
        settings = get_settings()

        self._account_sid: str = settings.twilio_account_sid
        self._auth_token: str = settings.twilio_auth_token
        self._from_number: str = settings.twilio_whatsapp_from
        self._environment: str = settings.environment

        self._enabled: bool = bool(
            self._account_sid
            and self._auth_token
            and not self._account_sid.startswith("FILL")
        )

        if not self._enabled:
            logger.warning("Twilio not configured — WhatsApp delivery disabled")

    async def send_whatsapp(self, to_number: str, body: str) -> bool:
        """Send a WhatsApp message, splitting into ≤1500-char chunks if needed.

        Args:
            to_number: Recipient in E.164 format (with or without "whatsapp:" prefix).
            body: Message body text.

        Returns:
            True if all chunks sent successfully, False on any failure (never raises).
        """
        if not self._enabled:
            logger.info(
                "[SANDBOX] WhatsApp disabled — would send to {}: {!r}...",
                to_number,
                body[:80],
            )
            return False

        # Normalise number
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

        # Split into chunks
        chunks: list[str] = (
            [body[i : i + _CHUNK_SIZE] for i in range(0, len(body), _CHUNK_SIZE)]
            if len(body) > _CHUNK_SIZE
            else [body]
        )

        if self._environment != "production":
            logger.info(
                "SANDBOX: would send {} chunk(s) to {}",
                len(chunks),
                to_number,
            )
            # Still actually send — sandbox is configured in Twilio dashboard

        all_ok = True
        for idx, chunk in enumerate(chunks, start=1):
            try:
                sid = await asyncio.to_thread(
                    self._send_sync,
                    to_number,
                    chunk,
                )
                logger.info(
                    "WhatsApp chunk {}/{} sent to {} SID={}",
                    idx,
                    len(chunks),
                    to_number,
                    sid,
                )
            except Exception as exc:
                logger.error(
                    "Twilio send failed (chunk {}/{}) to {}: {}",
                    idx,
                    len(chunks),
                    to_number,
                    exc,
                )
                all_ok = False

        return all_ok

    def _send_sync(self, to_number: str, chunk: str) -> str:
        """Synchronous Twilio SDK call — executed in a thread pool.

        Returns:
            Message SID string.
        """
        from twilio.rest import Client as TwilioRestClient

        client = TwilioRestClient(self._account_sid, self._auth_token)
        message = client.messages.create(
            from_=self._from_number,
            body=chunk,
            to=to_number,
        )
        return message.sid  # type: ignore[return-value]


# ── Module-level singleton ────────────────────────────────────────────────────

_client: TwilioClient | None = None


def get_twilio_client() -> TwilioClient:
    """Return the module-level TwilioClient singleton."""
    global _client
    if _client is None:
        _client = TwilioClient()
    return _client
