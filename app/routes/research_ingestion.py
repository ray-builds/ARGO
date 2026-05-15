"""Section 6 research ingestion API endpoints."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.services.research_ingestion_service import (
    check_research_against_portfolio,
    get_fred_series,
    get_instrument_data,
    ingest_financial_news,
    ingest_rss_feeds,
)

router = APIRouter(prefix="/api/v1/research-ingestion", tags=["research-ingestion"])


@router.post("/run-rss")
async def run_rss_ingestion(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    inserted = await ingest_rss_feeds(db)
    return {"inserted": inserted, "triggered_by": current_user.email}


@router.post("/run-news")
async def run_news_ingestion(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    inserted = await ingest_financial_news(db)
    return {"inserted": inserted, "triggered_by": current_user.email}


@router.get("/instrument-data")
async def instrument_data(
    tickers: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    data = await get_instrument_data(ticker_list)
    return {"tickers": ticker_list, "data": data, "requested_by": current_user.email}


@router.get("/fred-series")
async def fred_series(
    series_ids: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    series_list = [s.strip() for s in series_ids.split(",") if s.strip()]
    data = await get_fred_series(series_list)
    return {"series_ids": series_list, "data": data, "requested_by": current_user.email}


@router.post("/check-conflicts")
async def check_conflicts(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    research_summary = payload.get("research_summary") or {}
    portfolio = payload.get("portfolio") or {"positions": []}
    conflicts = await check_research_against_portfolio(research_summary, portfolio, db=db)
    return {"conflicts": conflicts, "count": len(conflicts), "requested_by": current_user.email}


@router.get("/status")
async def ingestion_status(
    current_user: User = Depends(get_current_user),
) -> dict:
    now = datetime.now(UTC)
    return {
        "status": "ready",
        "section": "6",
        "window_last_24h_start": (now - timedelta(hours=24)).isoformat(),
        "requested_by": current_user.email,
    }

