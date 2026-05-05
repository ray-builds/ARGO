"""Client and ClientInteraction models for the CRM module."""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

# Valid client tiers
CLIENT_TIERS = ("investor", "prospect", "counterparty", "standard")

# Valid interaction types
INTERACTION_TYPES = ("CALL", "EMAIL", "MEETING", "NOTE", "WHATSAPP")

# Valid interaction directions
INTERACTION_DIRECTIONS = ("inbound", "outbound")


class Client(Base, TimestampMixin):
    """A client, investor, prospect, or counterparty tracked in ARGO's CRM.

    Clients are linked to their interactions (calls, emails, meetings, notes).
    The tier field drives priority sorting in the CRM dashboard. Soft deletion
    is used (deleted_at) so interaction history is preserved.
    """
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    firm: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="standard", index=True)
    # tier values: 'investor', 'prospect', 'counterparty', 'standard'
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_contact_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by_email: Mapped[str] = mapped_column(String(255), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship to interactions
    interactions: Mapped[list["ClientInteraction"]] = relationship(
        "ClientInteraction", back_populates="client", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_clients_tier_contact", "tier", "last_contact_date"),
    )

    def __repr__(self) -> str:
        return f"<Client name={self.name!r} firm={self.firm!r} tier={self.tier!r}>"


class ClientInteraction(Base):
    """A logged interaction with a client — call, email, meeting, note, or WhatsApp.

    All interactions are timestamped and attributed to the team member who
    logged them. The summary field contains either a manual note or an
    AI-generated summary from a meeting or call transcript.
    """
    __tablename__ = "client_interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interaction_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # interaction_type values: 'CALL', 'EMAIL', 'MEETING', 'NOTE', 'WHATSAPP'
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="outbound")
    # direction values: 'inbound', 'outbound'
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logged_by_email: Mapped[str] = mapped_column(String(255), nullable=False)
    interaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship back to client
    client: Mapped["Client"] = relationship("Client", back_populates="interactions")

    def __repr__(self) -> str:
        return (
            f"<ClientInteraction client_id={self.client_id!r} "
            f"type={self.interaction_type!r} direction={self.direction!r}>"
        )
