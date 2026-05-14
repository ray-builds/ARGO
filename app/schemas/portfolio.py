"""Pydantic schemas for the Portfolio Intelligence module."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InstrumentType(str, Enum):
    """Financial instrument types tracked in the portfolio."""
    BOND = "BOND"
    EQUITY = "EQUITY"
    OPTION = "OPTION"
    FX = "FX"
    FUTURES = "FUTURES"
    OTHER = "OTHER"


class Direction(str, Enum):
    """Position direction."""
    LONG = "LONG"
    SHORT = "SHORT"


class PositionCreate(BaseModel):
    """Request to create a new portfolio position."""
    portfolio_name: str = "main"
    instrument: str
    instrument_type: InstrumentType
    asset_class: str
    geography: Optional[str] = None
    notional: float
    currency: str = "USD"
    direction: Direction
    entry_price: Optional[float] = None
    notes: Optional[str] = None
    as_of_date: date


class PositionResponse(PositionCreate):
    """Portfolio position with current market data."""
    id: str
    current_price: Optional[float] = None
    pnl: Optional[float] = None
    weight_pct: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompositionResponse(BaseModel):
    """Portfolio composition breakdown by multiple dimensions."""
    as_of_date: date
    total_positions: int
    by_asset_class: dict[str, float]
    by_geography: dict[str, float]
    by_direction: dict[str, int]
    by_instrument_type: dict[str, int]


class ScenarioRequest(BaseModel):
    """Request to run a macro scenario analysis."""
    macro_view: str
    constraints: Optional[str] = None


class TradeIdea(BaseModel):
    """Single AI-generated trade idea from scenario analysis."""
    name: str
    instruments: str
    structure: str
    rationale: str
    convexity_note: str
    key_risks: str


class ScenarioResponse(BaseModel):
    """Full scenario analysis with trade ideas."""
    id: str
    title: str
    macro_view_input: str
    analysis_output: str
    trade_ideas: list[TradeIdea] = []
    model_used: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
