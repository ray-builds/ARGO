"""Economic Intelligence API router — /api/v1/econ/* endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, require_dev_lead
from app.models.user import User
from app.schemas.economic import (
    EconEventResponse,
    ReleaseAnalysisRequest,
    ReleaseAnalysisResponse,
    CalendarRefreshRequest,
)

router = APIRouter()


@router.get("/today", response_model=list[EconEventResponse])
async def get_today_events(
    current_user: User = Depends(get_current_user),
) -> list[EconEventResponse]:
    """Return today's economic calendar events sorted by importance."""
    from app.modules.economic_intelligence.service import EconomicIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = EconomicIntelligenceService(db)
        return await service.get_today_events()


@router.get("/calendar", response_model=list[EconEventResponse])
async def get_calendar(
    from_date: date | None = None,
    to_date: date | None = None,
    importance: str | None = None,
    current_user: User = Depends(get_current_user),
) -> list[EconEventResponse]:
    """Return economic calendar events for a date range with optional importance filter."""
    from app.modules.economic_intelligence.service import EconomicIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = EconomicIntelligenceService(db)
        return await service.get_calendar(from_date, to_date, importance)


@router.post("/refresh-calendar")
async def refresh_calendar(
    body: CalendarRefreshRequest,
    current_user: User = Depends(require_dev_lead),
) -> dict:
    """Refresh the economic calendar from the data source for a given date range."""
    from app.modules.economic_intelligence.service import EconomicIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = EconomicIntelligenceService(db)
        count = await service.refresh_calendar(body.from_date, body.to_date)
    return {"refreshed": count}


@router.post("/{event_id}/analyse", response_model=ReleaseAnalysisResponse)
async def analyse_release(
    event_id: str,
    body: ReleaseAnalysisRequest,
    current_user: User = Depends(get_current_user),
) -> ReleaseAnalysisResponse:
    """Record the actual release value and run AI analysis of the economic surprise."""
    from app.modules.economic_intelligence.service import EconomicIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = EconomicIntelligenceService(db)
        return await service.analyze_release(event_id, body.actual_value)


@router.post("/morning-alerts")
async def send_morning_alerts(
    current_user: User = Depends(require_dev_lead),
) -> dict:
    """Send morning WhatsApp alerts for today's high-importance economic events."""
    from app.modules.economic_intelligence.service import EconomicIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = EconomicIntelligenceService(db)
        count = await service.send_morning_alerts()
    return {"alerts_sent": count}
