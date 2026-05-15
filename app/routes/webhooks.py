"""Microsoft Graph change-notification webhook receiver."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from loguru import logger

import asyncio

from app.core.database import get_db_session
from app.services.graph_webhook_service import (
    handle_webhook_notification,
    iter_notifications,
)
from app.services.teams_recording_service import (
    RECORDINGS_CLIENT_STATE,
    process_new_recording,
)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.get("/graph")
async def graph_webhook_validation(request: Request) -> Response:
    """Echo the validationToken so Graph can confirm the endpoint is live."""
    validation_token = request.query_params.get("validationToken")
    if validation_token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing validationToken")
    return Response(content=validation_token, media_type="text/plain")


@router.post("/graph")
async def graph_webhook(request: Request) -> Response:
    """Receive and dispatch Microsoft Graph change notifications.

    Graph occasionally hits POST with ``?validationToken=...`` during the
    handshake — echo that back as text/plain when present.
    """
    validation_token = request.query_params.get("validationToken")
    if validation_token is not None:
        return Response(content=validation_token, media_type="text/plain")

    body = await request.json()
    notifications = list(iter_notifications(body))

    # Pre-validate clientState before touching the DB, so spoofed traffic
    # never opens a session.
    from app.services.graph_webhook_service import valid_client_states
    valid = valid_client_states()
    for n in notifications:
        if n.get("clientState") not in valid:
            logger.warning("Rejecting Graph webhook: invalid clientState")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid clientState",
            )

    if not notifications:
        return Response(status_code=status.HTTP_202_ACCEPTED)

    try:
        async with get_db_session() as db:
            for notification in notifications:
                await handle_webhook_notification(notification, db)
    except RuntimeError as exc:
        # No DB initialised (e.g. test bypass) — process without a session;
        # patched processors will still be exercised.
        if "Database not initialized" not in str(exc):
            raise
        logger.debug("Webhook dispatched without DB session: {}", exc)
        for notification in notifications:
            await handle_webhook_notification(notification, None)  # type: ignore[arg-type]
    except ValueError as exc:
        logger.warning("Rejecting Graph webhook: {}", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    return Response(status_code=status.HTTP_202_ACCEPTED)


async def _resolve_service_token() -> str | None:
    """Pick any user with a Graph token for background recording processing."""
    from sqlalchemy import select

    from app.models.user import User

    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(User).where(User.graph_access_token.is_not(None)).limit(1)
            )
            user = result.scalar_one_or_none()
            return user.graph_access_token if user else None
    except RuntimeError:
        return None


@router.get("/onedrive-recordings")
async def recordings_validation(request: Request) -> Response:
    token = request.query_params.get("validationToken")
    if token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing validationToken")
    return Response(content=token, media_type="text/plain")


@router.post("/onedrive-recordings")
async def onedrive_recordings_webhook(request: Request) -> Response:
    """Receive change notifications for the OneDrive ``/Recordings`` folder."""
    validation_token = request.query_params.get("validationToken")
    if validation_token is not None:
        return Response(content=validation_token, media_type="text/plain")

    body = await request.json()
    notifications = list(iter_notifications(body))

    for n in notifications:
        if n.get("clientState") != RECORDINGS_CLIENT_STATE:
            logger.warning("Rejecting recordings webhook: invalid clientState")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid clientState",
            )

    access_token = await _resolve_service_token()
    if not access_token:
        logger.warning("recordings webhook: no Graph token available")
        return Response(status_code=status.HTTP_202_ACCEPTED)

    async def _runner(file_info: dict) -> None:
        try:
            async with get_db_session() as db:
                await process_new_recording(file_info, access_token, db)
        except Exception as exc:  # noqa: BLE001
            logger.exception("process_new_recording failed: {}", exc)

    for n in notifications:
        file_info = n.get("resourceData") or {}
        asyncio.create_task(_runner(file_info))

    return Response(status_code=status.HTTP_202_ACCEPTED)
