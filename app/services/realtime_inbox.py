"""In-process WebSocket broadcaster for realtime inbox updates."""
from __future__ import annotations

from typing import Any

from fastapi import WebSocket
from loguru import logger

# user_email -> set of connected WebSockets
_clients: dict[str, set[WebSocket]] = {}


def register(user_email: str, ws: WebSocket) -> None:
    _clients.setdefault(user_email, set()).add(ws)


def unregister(user_email: str, ws: WebSocket) -> None:
    bucket = _clients.get(user_email)
    if bucket and ws in bucket:
        bucket.remove(ws)
        if not bucket:
            _clients.pop(user_email, None)


def _email_payload(email: Any) -> dict[str, Any]:
    return {
        "id": getattr(email, "id", None),
        "graph_message_id": getattr(email, "graph_message_id", None),
        "sender_email": getattr(email, "sender_email", None),
        "sender_name": getattr(email, "sender_name", None),
        "subject": getattr(email, "subject", None),
        "body_preview": getattr(email, "body_preview", None),
        "received_at": (
            email.received_at.isoformat()
            if getattr(email, "received_at", None)
            else None
        ),
        "tag": getattr(email, "tag", None),
        "relevance_score": getattr(email, "relevance_score", None),
        "is_from_ceo": getattr(email, "is_from_ceo", False),
        "one_line_summary": getattr(email, "subject", None),
    }


async def broadcast_new_email(user_email: str, email: Any) -> None:
    """Push a NEW_EMAIL frame to every client subscribed to ``user_email``."""
    bucket = _clients.get(user_email)
    if not bucket:
        return
    message = {"type": "NEW_EMAIL", "data": _email_payload(email)}
    dead: list[WebSocket] = []
    for ws in bucket:
        try:
            await ws.send_json(message)
        except Exception as exc:  # noqa: BLE001
            logger.debug("ws send failed: {}", exc)
            dead.append(ws)
    for ws in dead:
        unregister(user_email, ws)
