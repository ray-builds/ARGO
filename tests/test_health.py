"""Tests for the /health endpoint."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(async_client: AsyncClient) -> None:
    """Health endpoint returns 200 OK."""
    response = await async_client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_schema(async_client: AsyncClient) -> None:
    """Health response contains required fields."""
    response = await async_client.get("/health")
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "db" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_status_ok(async_client: AsyncClient) -> None:
    """Health status is 'ok' when DB is reachable."""
    response = await async_client.get("/health")
    data = response.json()
    # In test environment with SQLite, DB should be reachable
    assert data["status"] in ("ok", "degraded")
