"""EconomicEvent model for the Economic Calendar module."""
from __future__ import annotations
from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Index, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid

# Valid importance levels
IMPORTANCE_LEVELS = ("HIGH", "MEDIUM", "LOW")

# Valid surprise directions
SURPRISE_DIRECTIONS = ("BEAT", "MISS", "IN_LINE")

# Valid data sources
DATA_SOURCES = ("FRED", "TRADING_ECONOMICS", "MANUAL")


class EconomicEvent(Base, TimestampMixin):
    """A macro-economic data release or calendar event tracked by ARGO.

    Events are sourced from FRED, Trading Economics, or entered manually.
    When actual data is released, the AI analysis field is populated with
    Claude's interpretation of the surprise vs consensus and market implications.
    """
    __tablename__ = "economic_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    release_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    release_time_utc: Mapped[Optional[time]] = mapped_column(Time(timezone=False), nullable=True)
    importance: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM", index=True)
    # importance values: 'HIGH', 'MEDIUM', 'LOW'
    forecast: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    actual: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    previous: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    surprise_direction: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # surprise_direction values: 'BEAT', 'MISS', 'IN_LINE'
    ai_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alert_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_source: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    # data_source values: 'FRED', 'TRADING_ECONOMICS', 'MANUAL'
    external_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("idx_economic_events_date_importance", "release_date", "importance"),
    )

    def __repr__(self) -> str:
        return (
            f"<EconomicEvent name={self.event_name!r} country={self.country!r} "
            f"date={self.release_date!r} importance={self.importance!r}>"
        )
