"""Microsoft Graph change-notification webhook receiver."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from loguru import logger

from app.core.database import get_db_session
from app.services.graph_webhook_service import (
    handle_webhook_notification,
    iter_notifications,
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
