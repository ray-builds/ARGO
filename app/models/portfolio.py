"""Position and Scenario models for the Portfolio Intelligence module."""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid

# Valid instrument types
INSTRUMENT_TYPES = ("BOND", "EQUITY", "OPTION", "FX", "FUTURES", "OTHER")

# Valid asset classes
ASSET_CLASSES = ("RATES", "CREDIT", "EQUITY", "FX", "MACRO")

# Valid directions
DIRECTIONS = ("LONG", "SHORT")

# Valid scenario types
SCENARIO_TYPES = ("MACRO_VIEW", "CONVEXITY", "TRADE_IDEA", "RISK")


class Position(Base, TimestampMixin):
    """A portfolio position held by ARP Global Capital.

    Positions are uploaded manually or via CSV import. The as_of_date
    field marks the snapshot date for the position data. PnL and price
    fields are optional and may be updated via market data feeds.
    """
    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    portfolio_name: Mapped[str] = mapped_column(String(128), nullable=False, default="main", index=True)
    instrument: Mapped[str] = mapped_column(String(255), nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # instrument_type values: 'BOND', 'EQUITY', 'OPTION', 'FX', 'FUTURES', 'OTHER'
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # asset_class values: 'RATES', 'CREDIT', 'EQUITY', 'FX', 'MACRO'
    geography: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notional: Mapped[Optional[object]] = mapped_column(Numeric(20, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    # direction values: 'LONG', 'SHORT'
    entry_price: Mapped[Optional[object]] = mapped_column(Numeric(20, 8), nullable=True)
    current_price: Mapped[Optional[object]] = mapped_column(Numeric(20, 8), nullable=True)
    pnl: Mapped[Optional[object]] = mapped_column(Numeric(20, 4), nullable=True)
    weight_pct: Mapped[Optional[object]] = mapped_column(Numeric(8, 4), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    uploaded_by_email: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        Index("idx_positions_portfolio_date", "portfolio_name", "as_of_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<Position instrument={self.instrument!r} type={self.instrument_type!r} "
            f"direction={self.direction!r} notional={self.notional}>"
        )


class Scenario(Base, TimestampMixin):
    """An AI-generated macro scenario, convexity analysis, trade idea, or risk study.

    Scenarios are created interactively via the Portfolio AI chat or triggered
    automatically. The analysis_output field contains the full Claude response.
    trade_ideas is a JSON list of structured trade recommendations.
    """
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    scenario_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # scenario_type values: 'MACRO_VIEW', 'CONVEXITY', 'TRADE_IDEA', 'RISK'
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    macro_view_input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis_output: Mapped[str] = mapped_column(Text, nullable=False)
    trade_ideas: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_email: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<Scenario id={self.id!r} type={self.scenario_type!r} "
            f"title={self.title!r}>"
        )
