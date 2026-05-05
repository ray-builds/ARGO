"""Pydantic schemas for the Research Intelligence module."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ResearchSourceType(str, Enum):
    """Source type for research content."""
    NOTE = "NOTE"
    PODCAST = "PODCAST"
    CALL = "CALL"
    REPORT = "REPORT"


class ConvictionLevel(str, Enum):
    """Conviction level assigned to a research item."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ResearchIngestRequest(BaseModel):
    """Request to ingest new research content."""
    title: str
    supplier_name: str
    supplier_email: Optional[str] = None
    source_type: ResearchSourceType
    asset_class: Optional[str] = None
    published_date: Optional[date] = None
    text_content: Optional[str] = None
    topics: list[str] = []


class ResearchListItem(BaseModel):
    """Research item summary for list views."""
    id: str
    title: str
    supplier_name: str
    source_type: ResearchSourceType
    asset_class: Optional[str] = None
    conviction_level: Optional[ConvictionLevel] = None
    quality_rating: Optional[int] = Field(None, ge=1, le=5)
    published_date: Optional[date] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ResearchDetailResponse(ResearchListItem):
    """Full research item with AI-extracted summary and data points."""
    thesis_summary: Optional[str] = None
    key_data_points: list[str] = []
    topics: list[str] = []
    supplier_email: Optional[str] = None


class SupplierStats(BaseModel):
    """Aggregated stats for a research supplier."""
    supplier_name: str
    total_items: int
    avg_rating: Optional[float] = None
    high_conviction_count: int


class DigestItem(BaseModel):
    """Single item in the research weekly digest."""
    research_id: str
    title: str
    supplier_name: str
    thesis_summary: Optional[str] = None
    quality_rating: Optional[int] = None


class DigestResponse(BaseModel):
    """Research digest covering a time period."""
    period_days: int
    total_items: int
    top_items: list[DigestItem]
