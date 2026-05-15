"""WhatsApp ingestion model for Section 5."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WhatsAppMessage(Base):
    """Single WhatsApp message captured by ARGO."""

    __tablename__ = "whatsapp_messages"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    group_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_trade_related: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    classification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    compliance_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("idx_wa_timestamp", "timestamp"),
        Index("idx_wa_trade", "is_trade_related"),
    )
