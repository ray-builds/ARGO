"""Research source URL registry for Section 6 deduplication."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class ResearchSourceRecord(Base):
    """Tracks ingested research source URLs to avoid duplicates."""

    __tablename__ = "research_source_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

