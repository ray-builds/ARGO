"""Section 11 economic releases table."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class EconomicRelease(Base):
    """Captured economic release values + generated commentary."""

    __tablename__ = "economic_releases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    indicator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    release_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_value: Mapped[Optional[float]] = mapped_column(Numeric(20, 6), nullable=True)
    consensus_value: Mapped[Optional[float]] = mapped_column(Numeric(20, 6), nullable=True)
    prior_value: Mapped[Optional[float]] = mapped_column(Numeric(20, 6), nullable=True)
    surprise_direction: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ai_commentary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

