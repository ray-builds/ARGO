"""Email and EmailHighlight models for the Email Intelligence module."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

# Valid email tags
EMAIL_TAGS = ("URGENT", "CLIENT", "TRADE", "RESEARCH", "OPERATIONS", "HR", "REGULATORY", "SKIP")


class Email(Base, TimestampMixin):
    """Processed email from Microsoft Graph API with AI scoring and classification.

    Each email fetched via Graph is stored here once. The mailbox_user_email
    field records whose inbox this came from. AI scoring runs asynchronously
    after fetch and populates relevance_score, tag, and is_from_ceo.
    """
    __tablename__ = "emails"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    graph_message_id: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    mailbox_user_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_full: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    relevance_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    tag: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    is_from_ceo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship to highlights
    highlights: Mapped[list["EmailHighlight"]] = relationship(
        "EmailHighlight", back_populates="email", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_emails_received_score", "received_at", "relevance_score"),
    )

    def __repr__(self) -> str:
        return f"<Email id={self.id!r} from={self.sender_email!r} tag={self.tag!r} score={self.relevance_score}>"


class EmailHighlight(Base):
    """AI-extracted key information from a processed email.

    Contains the most important sentence(s), any identified action items,
    and the key conclusion — used to render email cards without opening the full email.
    """
    __tablename__ = "email_highlights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    email_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    highlight_text: Mapped[str] = mapped_column(Text, nullable=False)
    action_required: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_conclusion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship back to email
    email: Mapped["Email"] = relationship("Email", back_populates="highlights")

    def __repr__(self) -> str:
        return f"<EmailHighlight email_id={self.email_id!r}>"
