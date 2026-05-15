"""Section 11 meeting summaries table."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class MeetingSummary(Base):
    """Structured summary artifact for meeting transcript runs."""

    __tablename__ = "meeting_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    meeting_title: Mapped[str] = mapped_column(String(512), nullable=False)
    meeting_date: Mapped[date] = mapped_column(Date, nullable=False)
    participants: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript_onedrive_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    transcription_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

