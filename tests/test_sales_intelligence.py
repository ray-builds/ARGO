"""Tests for the Sales Intelligence (CRM) service."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch


class TestSalesIntelligenceService:
    """Tests for client management, interaction logging, and follow-up recommendations."""

    @pytest.mark.asyncio
    async def test_create_client_stores_in_db(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Creating a client record persists it with the correct fields."""
        from app.services.sales_intelligence import SalesIntelligenceService

        service = SalesIntelligenceService(db=test_db)
        client = await service.create_client(
            first_name="John",
            last_name="Smith",
            firm="BlackRock",
            email="jsmith@blackrock.com",
            tier=1,
            country="US",
        )

        assert client is not None
        assert client.id is not None
        assert client.first_name == "John"
        assert client.last_name == "Smith"
        assert client.firm == "BlackRock"
        assert client.tier == 1

    @pytest.mark.asyncio
    async def test_log_interaction_updates_last_contact(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Logging an interaction updates the client's last_contact_date field."""
        from app.services.sales_intelligence import SalesIntelligenceService
        from app.models.client import Client

        client = Client(
            first_name="Jane",
            last_name="Doe",
            firm="Citadel",
            email="jdoe@citadel.com",
            tier=2,
            last_contact_date=None,
        )
        test_db.add(client)
        await test_db.commit()
        await test_db.refresh(client)

        service = SalesIntelligenceService(db=test_db)
        await service.log_interaction(
            client_id=str(client.id),
            interaction_date="2026-05-05",
            interaction_type="call",
            summary="Reviewed Q2 performance.",
        )

        await test_db.refresh(client)
        assert client.last_contact_date is not None

    @pytest.mark.asyncio
    async def test_follow_up_recommendations_respects_days_threshold(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Follow-up recommendations only include clients not contacted within the threshold."""
        from app.services.sales_intelligence import SalesIntelligenceService
        from app.models.client import Client
        import datetime

        overdue_client = Client(
            first_name="Overdue",
            last_name="Client",
            firm="Old Fund",
            tier=1,
            last_contact_date=(datetime.date.today() - datetime.timedelta(days=45)).isoformat(),
        )
        recent_client = Client(
            first_name="Recent",
            last_name="Client",
            firm="New Fund",
            tier=1,
            last_contact_date=datetime.date.today().isoformat(),
        )
        test_db.add_all([overdue_client, recent_client])
        await test_db.commit()

        service = SalesIntelligenceService(db=test_db)
        overdue = await service.get_follow_up_recommendations(days_threshold=30)

        names = [c.first_name for c in overdue]
        assert "Overdue" in names
        assert "Recent" not in names

    @pytest.mark.asyncio
    async def test_search_clients_natural_language(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Searching clients by name or firm returns matching results."""
        from app.services.sales_intelligence import SalesIntelligenceService
        from app.models.client import Client

        clients = [
            Client(first_name="Alice", last_name="Wong",   firm="PIMCO",    tier=1),
            Client(first_name="Bob",   last_name="Chen",   firm="Vanguard", tier=2),
            Client(first_name="Carol", last_name="Garcia", firm="PIMCO",    tier=1),
        ]
        test_db.add_all(clients)
        await test_db.commit()

        service = SalesIntelligenceService(db=test_db)
        results = await service.search_clients(query="PIMCO")

        assert len(results) == 2
        firms = [c.firm for c in results]
        assert all(f == "PIMCO" for f in firms)

    @pytest.mark.asyncio
    async def test_soft_delete_client(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Soft-deleting a client sets is_active=False without removing the record."""
        from app.services.sales_intelligence import SalesIntelligenceService
        from app.models.client import Client

        client = Client(
            first_name="Delete",
            last_name="Me",
            firm="Test Firm",
            tier=3,
            is_active=True,
        )
        test_db.add(client)
        await test_db.commit()
        await test_db.refresh(client)

        service = SalesIntelligenceService(db=test_db)
        await service.soft_delete_client(str(client.id))

        await test_db.refresh(client)
        assert client.is_active is False

        # Record still exists in DB
        from sqlalchemy import select
        from app.models.client import Client as ClientModel
        stmt = select(ClientModel).where(ClientModel.id == client.id)
        record = (await test_db.execute(stmt)).scalar_one_or_none()
        assert record is not None
