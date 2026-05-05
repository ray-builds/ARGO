"""Research Intelligence API router — /api/v1/research/* endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.research import (
    ResearchIngestRequest,
    ResearchListItem,
    ResearchDetailResponse,
    SupplierStats,
    DigestResponse,
)
from app.schemas.document import RatingUpdate

router = APIRouter()


@router.get("/", response_model=list[ResearchListItem])
async def list_research(
    limit: int = 30,
    offset: int = 0,
    supplier: str | None = None,
    current_user: User = Depends(get_current_user),
) -> list[ResearchListItem]:
    """Return a paginated list of research items with optional supplier filter."""
    from app.modules.research_intelligence.service import ResearchIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchIntelligenceService(db)
        return await service.list_research(limit, offset, supplier)


@router.post("/ingest", response_model=ResearchDetailResponse)
async def ingest_research(
    body: ResearchIngestRequest,
    current_user: User = Depends(get_current_user),
) -> ResearchDetailResponse:
    """Ingest new research content and run AI summarisation."""
    from app.modules.research_intelligence.service import ResearchIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchIntelligenceService(db)
        return await service.ingest_research(body, current_user.email)


@router.get("/digest", response_model=DigestResponse)
async def get_weekly_digest(
    days: int = 7,
    current_user: User = Depends(get_current_user),
) -> DigestResponse:
    """Return the research digest for the past N days."""
    from app.modules.research_intelligence.service import ResearchIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchIntelligenceService(db)
        return await service.build_weekly_digest(days)


@router.get("/suppliers", response_model=list[SupplierStats])
async def get_supplier_stats(
    current_user: User = Depends(get_current_user),
) -> list[SupplierStats]:
    """Return aggregated stats for all research suppliers."""
    from app.modules.research_intelligence.service import ResearchIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchIntelligenceService(db)
        return await service.get_supplier_stats()


@router.get("/{item_id}", response_model=ResearchDetailResponse)
async def get_research_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
) -> ResearchDetailResponse:
    """Return a single research item with full AI summary."""
    from app.modules.research_intelligence.service import ResearchIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchIntelligenceService(db)
        return await service.get_research_item(item_id)


@router.patch("/{item_id}/rate")
async def rate_research(
    item_id: str,
    body: RatingUpdate,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Rate a research item 1-5 stars."""
    from app.modules.research_intelligence.service import ResearchIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = ResearchIntelligenceService(db)
        await service.rate_research(item_id, body.rating)
    return {"rated": True, "rating": body.rating}
