"""Sales Intelligence service — client CRM, interaction logging, and AI follow-up recommendations."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from typing import Any, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_, update

from app.core.claude_client import get_claude_client
from app.models.client import Client, ClientInteraction
from app.modules.sales_intelligence.prompts import FOLLOW_UP_PROMPT
from app.schemas.client import (
    ClientCreate,
    ClientUpdate,
    ClientListItem,
    ClientDetailResponse,
    InteractionCreate,
    InteractionResponse,
    FollowUpRecommendation,
)


class SalesIntelligenceService:
    """Service for ARP Global Capital Sales & Client Intelligence.

    Manages the client CRM: creating and updating client records, logging
    interactions (calls, emails, meetings, WhatsApp), and using Claude to
    generate AI-powered follow-up recommendations based on engagement gaps
    and recent market context.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialise service with DB session.

        Args:
            db: Async SQLAlchemy session.
        """
        self._db = db
        self._claude = get_claude_client()

    async def create_client(self, data: ClientCreate) -> ClientDetailResponse:
        """Create a new client record.

        Args:
            data: ClientCreate payload with name, tier, and contact details.

        Returns:
            ClientDetailResponse for the newly created client.
        """
        client = Client(
            name=data.name,
            firm=data.firm,
            email=data.email,
            phone=data.phone,
            tier=data.tier.value,
            country=data.country,
            notes=data.notes,
            tags=json.dumps(data.tags),
            is_active=True,
        )
        self._db.add(client)
        await self._db.flush()
        logger.info(f"Client created: {client.id} — {client.name} ({client.tier})")
        return ClientDetailResponse.model_validate(client)

    async def update_client(self, client_id: str, data: ClientUpdate) -> ClientDetailResponse:
        """Update an existing client record.

        Args:
            client_id: UUID of the client to update.
            data: ClientUpdate payload with new values.

        Returns:
            Updated ClientDetailResponse.

        Raises:
            HTTPException: 404 if client not found.
        """
        result = await self._db.execute(
            select(Client).where(Client.id == client_id)
        )
        client = result.scalar_one_or_none()
        if not client:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Client not found")

        client.name = data.name
        client.firm = data.firm
        client.email = data.email
        client.phone = data.phone
        client.tier = data.tier.value
        client.country = data.country
        client.notes = data.notes
        client.tags = json.dumps(data.tags)
        await self._db.flush()
        return ClientDetailResponse.model_validate(client)

    async def get_client(self, client_id: str) -> ClientDetailResponse:
        """Return full client detail by ID.

        Args:
            client_id: UUID of the client.

        Returns:
            ClientDetailResponse.

        Raises:
            HTTPException: 404 if client not found.
        """
        result = await self._db.execute(
            select(Client).where(Client.id == client_id)
        )
        client = result.scalar_one_or_none()
        if not client:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Client not found")
        return ClientDetailResponse.model_validate(client)

    async def list_clients(
        self, tier: str | None = None, limit: int = 50
    ) -> list[ClientListItem]:
        """Return a list of clients with optional tier filter.

        Args:
            tier: Optional tier to filter by (investor, prospect, etc.).
            limit: Maximum records to return.

        Returns:
            List of ClientListItem objects.
        """
        stmt = select(Client).where(Client.is_active == True).order_by(Client.name).limit(limit)
        if tier:
            stmt = stmt.where(Client.tier == tier)

        result = await self._db.execute(stmt)
        clients = result.scalars().all()
        return [ClientListItem.model_validate(c) for c in clients]

    async def search_clients(self, query: str) -> list[ClientListItem]:
        """Search clients by name, firm, or email.

        Args:
            query: Search term to match against name, firm, or email fields.

        Returns:
            List of matching ClientListItem objects.
        """
        result = await self._db.execute(
            select(Client).where(
                Client.is_active == True,
                or_(
                    Client.name.ilike(f"%{query}%"),
                    Client.firm.ilike(f"%{query}%"),
                    Client.email.ilike(f"%{query}%"),
                ),
            ).limit(20)
        )
        clients = result.scalars().all()
        return [ClientListItem.model_validate(c) for c in clients]

    async def log_interaction(
        self,
        client_id: str,
        data: InteractionCreate,
        logged_by_email: str,
    ) -> InteractionResponse:
        """Log a new client interaction and update last_contact_date.

        Args:
            client_id: UUID of the client.
            data: InteractionCreate payload with type, direction, and summary.
            logged_by_email: Email of the user logging the interaction.

        Returns:
            InteractionResponse for the created interaction.

        Raises:
            HTTPException: 404 if client not found.
        """
        # Verify client exists
        result = await self._db.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if not client:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Client not found")

        interaction = ClientInteraction(
            client_id=client_id,
            interaction_type=data.interaction_type.value,
            direction=data.direction,
            summary=data.summary,
            interaction_date=data.interaction_date,
            logged_by_email=logged_by_email,
        )
        self._db.add(interaction)

        # Update client last contact date
        client.last_contact_date = data.interaction_date.date()
        await self._db.flush()

        logger.info(f"Interaction logged for client {client_id}: {data.interaction_type.value}")
        return InteractionResponse.model_validate(interaction)

    async def get_interactions(
        self, client_id: str, limit: int = 20
    ) -> list[InteractionResponse]:
        """Return interaction history for a client.

        Args:
            client_id: UUID of the client.
            limit: Maximum records to return.

        Returns:
            List of InteractionResponse objects ordered by date descending.
        """
        result = await self._db.execute(
            select(ClientInteraction)
            .where(ClientInteraction.client_id == client_id)
            .order_by(desc(ClientInteraction.interaction_date))
            .limit(limit)
        )
        interactions = result.scalars().all()
        return [InteractionResponse.model_validate(i) for i in interactions]

    async def get_follow_up_recommendations(
        self,
        stale_days: int = 21,
    ) -> list[FollowUpRecommendation]:
        """Generate AI-powered follow-up recommendations for neglected clients.

        Identifies investors and prospects not contacted in the past stale_days
        and uses Claude to generate personalised talking points.

        Args:
            stale_days: Days without contact before a client is flagged.

        Returns:
            List of FollowUpRecommendation objects sorted by days since contact.
        """
        cutoff = date.today() - timedelta(days=stale_days)

        result = await self._db.execute(
            select(Client).where(
                Client.is_active == True,
                Client.tier.in_(["investor", "prospect"]),
                or_(
                    Client.last_contact_date < cutoff,
                    Client.last_contact_date.is_(None),
                ),
            ).order_by(Client.last_contact_date.asc().nullsfirst())
        )
        clients = result.scalars().all()

        recommendations: list[FollowUpRecommendation] = []
        for client in clients[:10]:  # Cap at 10 to avoid large AI costs
            if client.last_contact_date:
                days_since = (date.today() - client.last_contact_date).days
            else:
                days_since = 999

            try:
                context = (
                    f"Client: {client.name}\n"
                    f"Firm: {client.firm or 'Unknown'}\n"
                    f"Tier: {client.tier}\n"
                    f"Country: {client.country or 'Unknown'}\n"
                    f"Notes: {client.notes or 'None'}\n"
                    f"Days since last contact: {days_since}"
                )
                talking_point = await self._claude.complete(
                    prompt=context,
                    system=FOLLOW_UP_PROMPT,
                    use_sonnet=False,
                    max_tokens=150,
                )
            except Exception as exc:
                logger.warning(f"Follow-up generation failed for {client.id}: {exc}")
                talking_point = f"Re-engage after {days_since} days. Review relationship and schedule a call."

            recommendations.append(
                FollowUpRecommendation(
                    client_id=client.id,
                    client_name=client.name,
                    firm=client.firm,
                    last_contact_date=client.last_contact_date,
                    days_since_contact=days_since,
                    suggested_talking_point=talking_point,
                )
            )

        return recommendations
