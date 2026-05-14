"""WebSocket endpoints for realtime UI updates."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.services.realtime_inbox import register, unregister

router = APIRouter()


@router.websocket("/api/ws/inbox")
async def inbox_socket(websocket: WebSocket) -> None:
    """Push realtime inbox events (NEW_EMAIL, EMAIL_CLASSIFIED) to the client.

    Authentication piggybacks on the session cookie that the browser sends
    during the WebSocket handshake.
    """
    session = websocket.scope.get("session") or {}
    user_data = session.get("user") if isinstance(session, dict) else None
    user_email = (user_data or {}).get("email") if isinstance(user_data, dict) else None

    await websocket.accept()
    if not user_email:
        await websocket.send_json({"type": "AUTH_REQUIRED"})
        await websocket.close(code=4401)
        return

    register(user_email, websocket)
    try:
        while True:
            # We don't expect inbound messages; receive_text keeps the connection alive
            # and surfaces disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.debug("inbox WS disconnect for {}", user_email)
    finally:
        unregister(user_email, websocket)
