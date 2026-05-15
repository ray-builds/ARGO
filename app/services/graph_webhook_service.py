"""Microsoft Graph change-notification (webhook) service.

Handles subscription lifecycle (register / renew) and dispatches incoming
notifications to the appropriate processor.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import get_db_session
from app.models.graph_subscription import GraphSubscription
from app.services import email_processor

GRAPH_SUBSCRIPTION_ENDPOINT = "https://graph.microsoft.com/v1.0/subscriptions"

# Graph allows up to 4230 minutes (~70.5h) for mailbox subscriptions.
# Renew well before that — every ~3 days.
SUBSCRIPTION_LIFETIME = timedelta(minutes=4230)
RENEWAL_THRESHOLD = timedelta(hours=12)

# Static set of resources ARGO watches. Each clientState should come from env
# in production; we default to fixed strings for now.
RESOURCES_TO_WATCH: list[dict[str, Any]] = [
    {
        "key": "email",
        "resource": "me/mailFolders('Inbox')/messages",
        "change_types": ["created"],
        "client_state": "ARGO_EMAIL_WEBHOOK_SECRET",
    },
    {
        "key": "calendar",
        "resource": "me/events",
        "change_types": ["created", "updated"],
        "client_state": "ARGO_CALENDAR_WEBHOOK_SECRET",
    },
]


def valid_client_states() -> set[str]:
    return {r["client_state"] for r in RESOURCES_TO_WATCH}


# ── Subscription lifecycle ────────────────────────────────────────────────────


async def register_subscriptions(
    access_token: str,
    user_email: str,
    db: AsyncSession,
) -> list[GraphSubscription]:
    """Create Graph subscriptions for every resource in RESOURCES_TO_WATCH.

    Stores subscription IDs in the DB for renewal tracking. Skips resources
    that already have an unexpired subscription for this user.
    """
    settings = get_settings()
    base_url = settings.argo_base_url or settings.app_base_url
    notification_url = f"{base_url}/api/webhooks/graph"
    created: list[GraphSubscription] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for resource in RESOURCES_TO_WATCH:
            existing = await _get_active_subscription(
                db, user_email, resource["resource"]
            )
            if existing is not None:
                continue

            expires = datetime.now(timezone.utc) + SUBSCRIPTION_LIFETIME
            payload = {
                "changeType": ",".join(resource["change_types"]),
                "notificationUrl": notification_url,
                "resource": resource["resource"],
                "expirationDateTime": expires.isoformat().replace("+00:00", "Z"),
                "clientState": resource["client_state"],
            }
            try:
                response = await client.post(
                    GRAPH_SUBSCRIPTION_ENDPOINT,
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
                data = response.json()
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Failed to create Graph subscription for {}: {}",
                    resource["resource"], exc,
                )
                continue

            sub = GraphSubscription(
                subscription_id=data.get("id"),
                user_email=user_email,
                resource=resource["resource"],
                change_types=",".join(resource["change_types"]),
                client_state=resource["client_state"],
                notification_url=notification_url,
                expires_at=expires,
                last_renewed_at=datetime.now(timezone.utc),
            )
            db.add(sub)
            created.append(sub)
    await db.commit()
    logger.info("Registered {} Graph subscriptions for {}", len(created), user_email)
    return created


async def renew_due_subscriptions(access_token: str | None = None) -> int:
    """Renew any subscription whose expiry is within ``RENEWAL_THRESHOLD``.

    Returns the count of subscriptions renewed (or recreated).
    """
    renewed = 0
    cutoff = datetime.now(timezone.utc) + RENEWAL_THRESHOLD

    async with get_db_session() as db:
        result = await db.execute(
            select(GraphSubscription).where(GraphSubscription.expires_at <= cutoff)
        )
        subs = list(result.scalars().all())

        if not subs:
            return 0

        if access_token is None:
            access_token = await _first_available_token(db)
        if not access_token:
            logger.warning("renew_due_subscriptions: no Graph token available")
            return 0

        new_expiry = datetime.now(timezone.utc) + SUBSCRIPTION_LIFETIME
        async with httpx.AsyncClient(timeout=30.0) as client:
            for sub in subs:
                url = f"{GRAPH_SUBSCRIPTION_ENDPOINT}/{sub.subscription_id}"
                payload = {
                    "expirationDateTime": new_expiry.isoformat().replace("+00:00", "Z")
                }
                try:
                    response = await client.patch(
                        url,
                        json=payload,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    response.raise_for_status()
                    sub.expires_at = new_expiry
                    sub.last_renewed_at = datetime.now(timezone.utc)
                    renewed += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Renewal failed for {}: {}. Recreating.",
                        sub.subscription_id, exc,
                    )
                    # Fall back to creating a fresh subscription.
                    try:
                        create_payload = {
                            "changeType": sub.change_types,
                            "notificationUrl": sub.notification_url,
                            "resource": sub.resource,
                            "expirationDateTime": new_expiry.isoformat().replace(
                                "+00:00", "Z"
                            ),
                            "clientState": sub.client_state,
                        }
                        response = await client.post(
                            GRAPH_SUBSCRIPTION_ENDPOINT,
                            json=create_payload,
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        response.raise_for_status()
                        data = response.json()
                        sub.subscription_id = data.get("id") or sub.subscription_id
                        sub.expires_at = new_expiry
                        sub.last_renewed_at = datetime.now(timezone.utc)
                        renewed += 1
                    except Exception as exc2:  # noqa: BLE001
                        logger.exception("Recreate failed too: {}", exc2)
        await db.commit()
    logger.info("Renewed {} Graph subscriptions", renewed)
    return renewed


# ── Notification handling ────────────────────────────────────────────────────


async def handle_webhook_notification(
    notification: dict[str, Any], db: AsyncSession
) -> None:
    """Validate ``clientState`` and dispatch the notification.

    Raises ``ValueError`` on a spoofed / invalid ``clientState`` — the router
    catches this and returns 400 / 401.
    """
    client_state = notification.get("clientState")
    if client_state not in valid_client_states():
        raise ValueError("Invalid clientState — possible spoofed webhook")

    resource = notification.get("resource", "") or ""
    resource_data = notification.get("resourceData") or {}

    if "messages" in resource:
        email_id = resource_data.get("id")
        if not email_id:
            # Fall back to parsing the trailing id from the resource path
            email_id = resource.rstrip("/").split("/")[-1]
        # Reference through the module so tests can patch
        # `app.services.email_processor.process_incoming_email`.
        await email_processor.process_incoming_email(email_id, db)
        return

    if "events" in resource:
        await _process_calendar_event(resource_data, db)
        return

    logger.debug("Unhandled Graph notification resource: {}", resource)


async def _process_calendar_event(resource_data: dict[str, Any], db: AsyncSession) -> None:
    """Calendar event stub — wired up in a later section."""
    logger.debug("Calendar event notification received: {}", resource_data.get("id"))


# ── Fallback polling ─────────────────────────────────────────────────────────


async def fallback_email_sync() -> int:
    """Catch emails that slipped past webhooks. Safe to call without auth.

    Returns the number of emails freshly processed across all users.
    """
    total = 0
    try:
        async with get_db_session() as db:
            from app.models.user import User
            from app.modules.email_intelligence.service import EmailIntelligenceService

            result = await db.execute(
                select(User).where(User.graph_access_token.is_not(None))
            )
            users = list(result.scalars().all())
            if not users:
                return 0

            service = EmailIntelligenceService(db)
            for user in users:
                try:
                    total += await service.sync_mailbox(
                        access_token=user.graph_access_token,
                        user_email=user.email,
                        hours_back=1,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("fallback_email_sync for {} failed: {}", user.email, exc)
            await db.commit()
    except RuntimeError as exc:
        logger.debug("fallback_email_sync: DB unavailable ({}). Skipping.", exc)
        return 0
    return total


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_active_subscription(
    db: AsyncSession, user_email: str, resource: str
) -> GraphSubscription | None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(GraphSubscription).where(
            GraphSubscription.user_email == user_email,
            GraphSubscription.resource == resource,
            GraphSubscription.expires_at > now,
        )
    )
    return result.scalar_one_or_none()


async def _first_available_token(db: AsyncSession) -> str | None:
    from app.models.user import User

    result = await db.execute(
        select(User).where(User.graph_access_token.is_not(None)).limit(1)
    )
    user = result.scalar_one_or_none()
    return user.graph_access_token if user else None


def iter_notifications(body: dict[str, Any]) -> Iterable[dict[str, Any]]:
    return body.get("value", []) or []
