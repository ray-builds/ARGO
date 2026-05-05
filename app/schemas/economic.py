"""Pydantic schemas for the Economic Data Intelligence module."""
from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Importance(str, Enum):
    """Importance level for economic events."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SurpriseDirection(str, Enum):
    """Whether an economic release beat, missed, or was in line with forecasts."""
    BEAT = "BEAT"
    MISS = "MISS"
    IN_LINE = "IN_LINE"


class EconEventResponse(BaseModel):
    """Economic calendar event with release data and AI analysis."""
    id: str
    event_name: str
    country: str
    currency: Optional[str] = None
    release_date: date
    release_time_utc: Optional[time] = None
    importance: Importance
    forecast: Optional[str] = None
    actual: Optional[str] = None
    previous: Optional[str] = None
    surprise_direction: Optional[SurpriseDirection] = None
    ai_analysis: Optional[str] = None
    alert_sent: bool

    model_config = {"from_attributes": True}


class ReleaseAnalysisRequest(BaseModel):
    """Request to analyse an economic data release."""
    actual_value: str


class ReleaseAnalysisResponse(BaseModel):
    """AI analysis of an economic data release."""
    event_id: str
    event_name: str
    analysis: str
    surprise_direction: Optional[str] = None


class CalendarRefreshRequest(BaseModel):
    """Request to refresh the economic calendar for a date range."""
    from_date: date
    to_date: date
