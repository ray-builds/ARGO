"""Tests for authentication routes and protected endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_page_returns_200(async_client: AsyncClient) -> None:
    """GET /login renders the login page with HTTP 200."""
    response = await async_client.get("/login")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient) -> None:
    """GET /health returns 200 with a JSON status field."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    # "ok" when DB is reachable; "degraded" when DB is not yet initialised in test env
    assert data.get("status") in ("ok", "degraded")


@pytest.mark.asyncio
async def test_protected_root_redirects_to_login(async_client: AsyncClient) -> None:
    """GET / without a session redirects to /login (302)."""
    response = await async_client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "/login" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_logout_redirects_to_login(async_client: AsyncClient) -> None:
    """GET /logout clears session and redirects to /login (302)."""
    response = await async_client.get("/logout", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "/login" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_login_page_contains_html(async_client: AsyncClient) -> None:
    """Login page response has Content-Type text/html."""
    response = await async_client.get("/login")
    assert "text/html" in response.headers.get("content-type", "")
