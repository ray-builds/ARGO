"""Section 8 realtime economic intelligence endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.user import User
from app.services.economic_calendar_service import (
    fetch_cb_rss,
    get_economic_calendar_trading_economics,
    get_fred_release_calendar,
    on_data_release,
    track_central_bank_language,
)

router = APIRouter(prefix="/api/v1/econ-realtime", tags=["econ-realtime"])


@router.get("/calendar/trading-economics")
async def te_calendar(
    days_ahead: int = 7,
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = await get_economic_calendar_trading_economics(days_ahead=days_ahead)
    return {"count": len(rows), "events": rows, "requested_by": current_user.email}


@router.get("/calendar/fred")
async def fred_calendar(
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = await get_fred_release_calendar()
    return {"data": rows, "requested_by": current_user.email}


@router.post("/release")
async def release_commentary(
    body: dict,
    current_user: User = Depends(get_current_user),
) -> dict:
    commentary = await on_data_release(
        indicator=str(body.get("indicator") or ""),
        actual=float(body.get("actual")),
        consensus=float(body.get("consensus")),
        prior=float(body.get("prior")),
    )
    return {"commentary": commentary, "requested_by": current_user.email}


@router.get("/central-banks/rss")
async def cb_rss(
    url: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    items = await fetch_cb_rss(url)
    return {"count": len(items), "items": items, "requested_by": current_user.email}


@router.post("/central-banks/track")
async def cb_track(
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await track_central_bank_language()
    return {"result": result, "requested_by": current_user.email}

