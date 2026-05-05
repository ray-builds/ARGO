"""Meeting and MeetingActionItem models for the Meeting Intelligence module."""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

# Valid meeting types
MEETING_TYPES = ("INTERNAL", "STRATEGIST", "CLIENT", "EARNINGS")

# Valid meeting status values
MEETING_STATUSES = ("pending", "transcribing", "summarizing", "complete", "error")


class Meeting(Base, TimestampMixin):
    """A recorded meeting processed by ARGO for transcription and summarisation.

    Audio is uploaded by a team member. The processing pipeline transcribes
    via Whisper, cleans the transcript, and generates a structured summary
    with decisions and action items via Claude.
    """
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    meeting_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # meeting_type values: 'INTERNAL', 'STRATEGIST', 'CLIENT', 'EARNINGS'
    meeting_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    attendees: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list of names
    uploaded_by_email: Mapped[str] = mapped_column(String(255), nullable=False)
    audio_file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    transcript_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript_clean: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decisions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    key_quotes: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transcription_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    summary_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    # status values: 'pending', 'transcribing', 'summarizing', 'complete', 'error'
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship to action items
    action_items: Mapped[list["MeetingActionItem"]] = relationship(
        "MeetingActionItem", back_populates="meeting", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_meetings_date_type", "meeting_date", "meeting_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<Meeting id={self.id!r} title={self.title!r} "
            f"type={self.meeting_type!r} status={self.status!r}>"
        )


class MeetingActionItem(Base):
    """A single action item extracted from a meeting by ARGO's AI pipeline.

    Action items have an owner, optional due date, and completion tracking.
    """
    __tablename__ = "meeting_action_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship back to meeting
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="action_items")

    def __repr__(self) -> str:
        return (
            f"<MeetingActionItem meeting_id={self.meeting_id!r} "
            f"owner={self.owner_name!r} complete={self.is_complete}>"
        )
