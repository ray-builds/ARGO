"""Pydantic schemas for the Sales & Client Intelligence module."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr


class ClientTier(str, Enum):
    """Client relationship tier classification."""
    INVESTOR = "investor"
    PROSPECT = "prospect"
    COUNTERPARTY = "counterparty"
    STANDARD = "standard"


class InteractionType(str, Enum):
    """Types of client interaction."""
    CALL = "CALL"
    EMAIL = "EMAIL"
    MEETING = "MEETING"
    NOTE = "NOTE"
    WHATSAPP = "WHATSAPP"


class ClientCreate(BaseModel):
    """Request to create a new client record."""
    name: str
    firm: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    tier: ClientTier = ClientTier.STANDARD
    country: Optional[str] = None
    notes: Optional[str] = None
    tags: list[str] = []


class ClientUpdate(ClientCreate):
    """Request to update an existing client record."""
    pass


class ClientListItem(BaseModel):
    """Client summary for list views."""
    id: str
    name: str
    firm: Optional[str] = None
    tier: ClientTier
    last_contact_date: Optional[date] = None
    is_active: bool

    model_config = {"from_attributes": True}


class ClientDetailResponse(ClientListItem):
    """Full client record with contact details."""
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    tags: list[str] = []
    created_at: datetime


class InteractionCreate(BaseModel):
    """Request to log a new client interaction."""
    interaction_type: InteractionType
    direction: str = "outbound"
    summary: str
    interaction_date: datetime


class InteractionResponse(InteractionCreate):
    """Client interaction record with metadata."""
    id: str
    client_id: str
    logged_by_email: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FollowUpRecommendation(BaseModel):
    """AI-generated follow-up recommendation for a client."""
    client_id: str
    client_name: str
    firm: Optional[str] = None
    last_contact_date: Optional[date] = None
    days_since_contact: int
    suggested_talking_point: str
