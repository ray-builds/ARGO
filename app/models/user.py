"""User model — stores M365-authenticated ARP Global Capital team members."""
from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.meeting import Meeting
    from app.models.document import Document
    from app.models.client import Client, ClientInteraction
    from app.models.research import ResearchItem
    from app.models.chat import ChatConversation


class User(Base, TimestampMixin):
    """Represents an authenticated ARP Global Capital team member.

    Identity is sourced from Azure AD via MSAL OAuth2. Users are created
    or updated on every successful login.
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    azure_oid: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="staff")
    # role values: 'ceo', 'dev_lead', 'staff'
    whatsapp_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    preferences: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # JSON string: notification prefs, UI preferences
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    graph_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    graph_refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    graph_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships (back-populated from child models)
    chat_conversations: Mapped[list["ChatConversation"]] = relationship(
        "ChatConversation",
        back_populates="user",
        foreign_keys="ChatConversation.user_id",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User email={self.email!r} role={self.role!r}>"

    @property
    def is_ceo(self) -> bool:
        """Returns True if this user has the CEO role."""
        return self.role == "ceo"

    @property
    def is_dev_lead(self) -> bool:
        """Returns True if this user has the dev_lead role."""
        return self.role == "dev_lead"

    @property
    def is_active(self) -> bool:
        """Returns True if the user has not been soft-deleted."""
        return self.deleted_at is None
