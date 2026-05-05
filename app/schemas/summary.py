"""Pydantic schemas for the Overnight Summary module."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Any

from pydantic import BaseModel


class MarketMove(BaseModel):
    """Single market instrument move."""
    asset: str
    change_pct: Optional[float] = None
    change_bps: Optional[float] = None
    level: Optional[float] = None
    direction: str = ""
    context: str = ""


class NewsItem(BaseModel):
    """Single news headline with metadata."""
    title: str
    snippet: str
    source: str = ""
    date: str = ""
    link: str = ""


class SummaryListItem(BaseModel):
    """Overnight summary list view item."""
    id: str
    summary_date: date
    executive_summary: str
    whatsapp_delivered: bool
    email_delivered: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SummaryDetailResponse(BaseModel):
    """Full overnight summary with all fields."""
    id: str
    summary_date: date
    coverage_start: datetime
    coverage_end: datetime
    executive_summary: str
    full_briefing_text: str
    whatsapp_delivered: bool
    whatsapp_delivered_at: Optional[datetime] = None
    whatsapp_error: Optional[str] = None
    email_delivered: bool
    email_delivered_at: Optional[datetime] = None
    model_used: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TriggerSummaryRequest(BaseModel):
    """Request to manually trigger an overnight summary."""
    target_date: Optional[date] = None
    force: bool = False


class TriggerSummaryResponse(BaseModel):
    """Response after triggering an overnight summary job."""
    job_id: str
    status: str
    message: str
