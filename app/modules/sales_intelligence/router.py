"""Sales Intelligence API router — /api/v1/clients/* endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.client import (
    ClientCreate,
    ClientUpdate,
    ClientListItem,
    ClientDetailResponse,
    InteractionCreate,
    InteractionResponse,
    FollowUpRecommendation,
)

router = APIRouter()


@router.get("/", response_model=list[ClientListItem])
async def list_clients(
    tier: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
) -> list[ClientListItem]:
    """Return all clients with optional tier filter."""
    from app.modules.sales_intelligence.service import SalesIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = SalesIntelligenceService(db)
        return await service.list_clients(tier, limit)


@router.post("/", response_model=ClientDetailResponse)
async def create_client(
    body: ClientCreate,
    current_user: User = Depends(get_current_user),
) -> ClientDetailResponse:
    """Create a new client record."""
    from app.modules.sales_intelligence.service import SalesIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = SalesIntelligenceService(db)
        return await service.create_client(body)


@router.get("/follow-ups", response_model=list[FollowUpRecommendation])
async def get_follow_up_recommendations(
    current_user: User = Depends(get_current_user),
) -> list[FollowUpRecommendation]:
    """Return AI-generated follow-up recommendations for clients needing attention."""
    from app.modules.sales_intelligence.service import SalesIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = SalesIntelligenceService(db)
        return await service.get_follow_up_recommendations()


@router.get("/search", response_model=list[ClientListItem])
async def search_clients(
    q: str,
    current_user: User = Depends(get_current_user),
) -> list[ClientListItem]:
    """Search clients by name, firm, or email."""
    from app.modules.sales_intelligence.service import SalesIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = SalesIntelligenceService(db)
        return await service.search_clients(q)


@router.get("/{client_id}", response_model=ClientDetailResponse)
async def get_client(
    client_id: str,
    current_user: User = Depends(get_current_user),
) -> ClientDetailResponse:
    """Return full client detail."""
    from app.modules.sales_intelligence.service import SalesIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = SalesIntelligenceService(db)
        return await service.get_client(client_id)


@router.put("/{client_id}", response_model=ClientDetailResponse)
async def update_client(
    client_id: str,
    body: ClientUpdate,
    current_user: User = Depends(get_current_user),
) -> ClientDetailResponse:
    """Update a client record."""
    from app.modules.sales_intelligence.service import SalesIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = SalesIntelligenceService(db)
        return await service.update_client(client_id, body)


@router.post("/{client_id}/interactions", response_model=InteractionResponse)
async def log_interaction(
    client_id: str,
    body: InteractionCreate,
    current_user: User = Depends(get_current_user),
) -> InteractionResponse:
    """Log a new interaction with a client."""
    from app.modules.sales_intelligence.service import SalesIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = SalesIntelligenceService(db)
        return await service.log_interaction(client_id, body, current_user.email)


@router.get("/{client_id}/interactions", response_model=list[InteractionResponse])
async def get_interactions(
    client_id: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
) -> list[InteractionResponse]:
    """Return interaction history for a client."""
    from app.modules.sales_intelligence.service import SalesIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = SalesIntelligenceService(db)
        return await service.get_interactions(client_id, limit)
