"""ResearchItem model for the Research Intelligence module."""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Index, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid

# Valid source types
RESEARCH_SOURCE_TYPES = ("NOTE", "PODCAST", "CALL", "REPORT")

# Valid conviction levels
CONVICTION_LEVELS = ("HIGH", "MEDIUM", "LOW")

# Valid asset classes (shared across modules)
RESEARCH_ASSET_CLASSES = ("RATES", "CREDIT", "EQUITY", "FX", "MACRO", "COMMODITIES")


class ResearchItem(Base, TimestampMixin):
    """A structured research item derived from an external or internal source.

    Research items capture the investment thesis, key data points, and
    conviction level from strategist calls, research reports, podcasts, or
    internal notes. Linked optionally to a Document record for the raw source.
    """
    __tablename__ = "research_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    supplier_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    supplier_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # source_type values: 'NOTE', 'PODCAST', 'CALL', 'REPORT'
    asset_class: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    # asset_class values: 'RATES', 'CREDIT', 'EQUITY', 'FX', 'MACRO', 'COMMODITIES'
    thesis_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_data_points: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    conviction_level: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    # conviction_level values: 'HIGH', 'MEDIUM', 'LOW'
    quality_rating: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    # quality_rating: 1–5 scale
    document_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    # FK to documents.id (soft reference, not enforced as hard FK for flexibility)
    published_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    ingested_by_email: Mapped[str] = mapped_column(String(255), nullable=False)
    topics: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list of topic tags
    model_used: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("idx_research_items_asset_conviction", "asset_class", "conviction_level"),
    )

    def __repr__(self) -> str:
        return (
            f"<ResearchItem id={self.id!r} title={self.title!r} "
            f"source={self.source_type!r} conviction={self.conviction_level!r}>"
        )
