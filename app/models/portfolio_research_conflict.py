"""Portfolio vs research conflict records for Section 11."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class PortfolioResearchConflict(Base):
    """Stores directional conflicts detected between research and positions."""

    __tablename__ = "portfolio_research_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    research_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_documents.id"), nullable=True
    )
    position_instrument: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    conflict_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
