"""Section 1 — auto-sync: Graph webhook + fallback sync + subscription renewal."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_graph_webhook_validation(async_client: AsyncClient) -> None:
    """Graph hits the endpoint with ?validationToken=... — must echo as text/plain."""
    response = await async_client.get("/api/webhooks/graph?validationToken=TEST123")
    assert response.status_code == 200
    assert response.text == "TEST123"
    assert response.headers["content-type"].startswith("text/plain")


@pytest.mark.asyncio
async def test_graph_webhook_validation_post(async_client: AsyncClient) -> None:
    """Graph also issues POST with the same query param during handshake."""
    response = await async_client.post(
        "/api/webhooks/graph?validationToken=POST123", json={}
    )
    assert response.status_code == 200
    assert response.text == "POST123"


@pytest.mark.asyncio
async def test_webhook_processes_new_email(async_client: AsyncClient) -> None:
    """A valid Graph notification triggers the email processor."""
    payload = {
        "value": [
            {
                "resource": "me/mailFolders('Inbox')/messages/AAA111",
                "clientState": "ARGO_EMAIL_WEBHOOK_SECRET",
                "resourceData": {
                    "id": "AAA111",
                    "@odata.type": "#Microsoft.Graph.Message",
                },
            }
        ]
    }
    with patch(
        "app.services.email_processor.process_incoming_email",
        new_callable=AsyncMock,
    ) as mock_proc:
        response = await async_client.post("/api/webhooks/graph", json=payload)
    assert response.status_code == 202
    mock_proc.assert_awaited_once_with("AAA111", ANY)


@pytest.mark.asyncio
async def test_invalid_client_state_rejected(async_client: AsyncClient) -> None:
    """clientState mismatch → reject with 4xx (no email processing)."""
    payload = {
        "value": [{"clientState": "WRONG_SECRET", "resource": "me/messages/X"}]
    }
    with patch(
        "app.services.email_processor.process_incoming_email",
        new_callable=AsyncMock,
    ) as mock_proc:
        response = await async_client.post("/api/webhooks/graph", json=payload)
    assert response.status_code in (400, 401)
    mock_proc.assert_not_awaited()


@pytest.mark.asyncio
async def test_fallback_sync_runs_without_users() -> None:
    """Background job must run cleanly even when no users have a Graph token."""
    from app.services.graph_webhook_service import fallback_email_sync

    count = await fallback_email_sync()
    assert count == 0


@pytest.mark.asyncio
async def test_subscription_renewal_before_expiry(test_db) -> None:
    """A subscription within the renewal threshold gets renewed; expires_at moves forward."""
    from app.core import database as db_mod
    from app.models.graph_subscription import GraphSubscription
    from app.models.user import User
    from app.services import graph_webhook_service as gws

    # Seed an about-to-expire subscription and a user with a token.
    user = User(
        azure_oid="oid-renew",
        email="renew@test.com",
        display_name="Renew Tester",
        role="staff",
        graph_access_token="renew-token",
    )
    near_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    sub = GraphSubscription(
        subscription_id="sub-id-1",
        user_email=user.email,
        resource="me/mailFolders('Inbox')/messages",
        change_types="created",
        client_state="ARGO_EMAIL_WEBHOOK_SECRET",
        notification_url="http://test/api/webhooks/graph",
        expires_at=near_expiry,
    )
    test_db.add_all([user, sub])
    await test_db.commit()

    # Route the service's get_db_session at the seeded session.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session():
        yield test_db

    fake_response = type(
        "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"id": "sub-id-1"}}
    )()

    with patch.object(gws, "get_db_session", _session):
        with patch("httpx.AsyncClient") as client_cls:
            instance = client_cls.return_value.__aenter__.return_value
            instance.patch = AsyncMock(return_value=fake_response)
            instance.post = AsyncMock(return_value=fake_response)
            renewed = await gws.renew_due_subscriptions(access_token="renew-token")

    assert renewed == 1

    await test_db.refresh(sub)
    # SQLite strips tz info; normalise both sides for comparison.
    def _naive(dt: datetime) -> datetime:
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    assert _naive(sub.expires_at) > _naive(near_expiry)
    assert sub.last_renewed_at is not None
