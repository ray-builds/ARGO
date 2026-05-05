"""Portfolio Intelligence API router — /api/v1/portfolio/* endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.portfolio import (
    PositionCreate,
    PositionResponse,
    CompositionResponse,
    ScenarioRequest,
    ScenarioResponse,
)

router = APIRouter()


@router.get("/positions", response_model=list[PositionResponse])
async def list_positions(
    portfolio_name: str = "main",
    current_user: User = Depends(get_current_user),
) -> list[PositionResponse]:
    """Return all current positions for a portfolio."""
    from app.modules.portfolio_intelligence.service import PortfolioIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = PortfolioIntelligenceService(db)
        return await service.list_positions(portfolio_name)


@router.post("/positions", response_model=PositionResponse)
async def create_position(
    body: PositionCreate,
    current_user: User = Depends(get_current_user),
) -> PositionResponse:
    """Add a new position to the portfolio."""
    from app.modules.portfolio_intelligence.service import PortfolioIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = PortfolioIntelligenceService(db)
        return await service.create_position(body)


@router.post("/upload-csv")
async def upload_positions_csv(
    file: UploadFile = File(...),
    portfolio_name: str = "main",
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload a CSV of positions to bulk-import into the portfolio."""
    from app.modules.portfolio_intelligence.service import PortfolioIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = PortfolioIntelligenceService(db)
        count = await service.upload_positions_csv(file, portfolio_name)
    return {"imported": count}


@router.get("/composition", response_model=CompositionResponse)
async def get_composition(
    portfolio_name: str = "main",
    current_user: User = Depends(get_current_user),
) -> CompositionResponse:
    """Return portfolio composition breakdown by asset class, geography, and direction."""
    from app.modules.portfolio_intelligence.service import PortfolioIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = PortfolioIntelligenceService(db)
        return await service.get_composition(portfolio_name)


@router.post("/scenarios", response_model=ScenarioResponse)
async def run_scenario(
    body: ScenarioRequest,
    current_user: User = Depends(get_current_user),
) -> ScenarioResponse:
    """Run an AI scenario analysis and generate trade ideas for a given macro view."""
    from app.modules.portfolio_intelligence.service import PortfolioIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = PortfolioIntelligenceService(db)
        return await service.run_scenario(body)


@router.get("/scenarios", response_model=list[ScenarioResponse])
async def list_scenarios(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
) -> list[ScenarioResponse]:
    """Return past scenario analyses."""
    from app.modules.portfolio_intelligence.service import PortfolioIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = PortfolioIntelligenceService(db)
        return await service.list_scenarios(limit)
