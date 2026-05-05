"""Pytest configuration and shared fixtures for ARGO tests."""
from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Set test environment BEFORE importing app
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-argo-not-for-production")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("AZURE_TENANT_ID", "test-tenant-id")
os.environ.setdefault("AZURE_CLIENT_ID", "test-client-id")
os.environ.setdefault("AZURE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("AZURE_REDIRECT_URI", "http://localhost:8000/auth/callback")
os.environ.setdefault("CEO_EMAIL", "ceo@test.com")
os.environ.setdefault("ENABLE_OVERNIGHT_CRON", "false")
os.environ.setdefault("ENABLE_WHATSAPP", "false")
os.environ.setdefault("ENABLE_EMAIL_FETCH", "false")


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh in-memory SQLite database for each test function.

    Creates all tables, yields a session, then drops everything.
    """
    from app.models.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client for the ARGO FastAPI app."""
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
def mock_claude():
    """Mock the Claude API client to avoid hitting Anthropic in tests."""
    with patch("app.core.claude_client.ClaudeClient.complete") as mock:
        mock.return_value = '{"score": 75, "tag": "RESEARCH", "reasoning": "Market analysis"}'
        yield mock


@pytest.fixture
def mock_claude_json():
    """Mock Claude's complete_json method."""
    with patch("app.core.claude_client.ClaudeClient.complete_json") as mock:
        mock.return_value = {
            "score": 75,
            "tag": "RESEARCH",
            "reasoning": "Test email",
            "highlight": "Key point about the market",
            "action_required": None,
            "key_conclusion": "Markets moved higher",
        }
        yield mock


@pytest.fixture
def mock_graph():
    """Mock Microsoft Graph API calls."""
    sample_messages = [
        {
            "id": "graph-msg-001",
            "subject": "Q3 Portfolio Review",
            "from": {"emailAddress": {"address": "ceo@test.com", "name": "Test CEO"}},
            "receivedDateTime": "2026-05-05T08:00:00Z",
            "isRead": False,
            "bodyPreview": "Please review the Q3 portfolio allocation by EOD today.",
        }
    ]

    with patch(
        "app.core.graph_client.GraphClient.get_messages", new_callable=AsyncMock
    ) as mock:
        mock.return_value = sample_messages
        yield mock


@pytest.fixture
def mock_twilio():
    """Mock Twilio WhatsApp sending."""
    with patch("app.core.twilio_client.TwilioClient.send_whatsapp") as mock:
        mock.return_value = {"success": True, "sid": "SM_test_123", "error": None}
        yield mock


@pytest.fixture
def mock_serper():
    """Mock Serper news search."""
    with patch(
        "app.core.serper_client.SerperClient.search_news", new_callable=AsyncMock
    ) as mock:
        mock.return_value = [
            {
                "title": "Fed holds rates steady",
                "snippet": "The Federal Reserve kept rates unchanged...",
                "source": "Reuters",
                "date": "1 hour ago",
                "link": "https://example.com/fed-rates",
            }
        ]
        yield mock


@pytest.fixture
def sample_email() -> dict:
    """Sample Microsoft Graph API email message response."""
    return {
        "id": "graph-msg-test-001",
        "subject": "Market Update: UST 10Y breaks 4.5%",
        "from": {
            "emailAddress": {
                "address": "research@broker.com",
                "name": "Broker Research",
            }
        },
        "receivedDateTime": "2026-05-05T06:30:00Z",
        "isRead": False,
        "bodyPreview": (
            "The 10-year Treasury yield broke above 4.5% for the first time since November..."
        ),
        "importance": "high",
    }


@pytest.fixture
def sample_ceo_email() -> dict:
    """Sample email from the CEO with URGENT tag."""
    return {
        "id": "graph-msg-ceo-001",
        "subject": "URGENT: Reduce UST duration by EOD",
        "from": {
            "emailAddress": {"address": "ceo@test.com", "name": "Test CEO"}
        },
        "receivedDateTime": "2026-05-05T07:00:00Z",
        "isRead": False,
        "bodyPreview": (
            "Please reduce our UST 10Y duration by 20% before market close today."
        ),
        "importance": "high",
    }


@pytest.fixture
def authenticated_session() -> dict:
    """Session data for an authenticated test user."""
    return {
        "user_id": "test-user-uuid-001",
        "azure_oid": "test-azure-oid-001",
        "email": "rshhadeh@arpglobalcapital.com",
        "display_name": "Rayhan Shhadeh",
        "role": "dev_lead",
        "access_token": "test-graph-access-token",
        "refresh_token": "test-graph-refresh-token",
        "token_expires_at": 9999999999,
    }
