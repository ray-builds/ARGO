"""Pydantic schemas for the Meeting Intelligence module."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class MeetingType(str, Enum):
    """Types of meetings tracked in ARGO."""
    INTERNAL = "INTERNAL"
    STRATEGIST = "STRATEGIST"
    CLIENT = "CLIENT"
    EARNINGS = "EARNINGS"


class MeetingStatus(str, Enum):
    """Processing status of a meeting."""
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    COMPLETE = "complete"
    ERROR = "error"


class ActionItemResponse(BaseModel):
    """Single action item extracted from a meeting."""
    id: str
    meeting_id: str
    description: str
    owner_name: Optional[str] = None
    due_date: Optional[date] = None
    is_complete: bool
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ActionItemUpdate(BaseModel):
    """Request to update an action item's completion state."""
    is_complete: bool


class MeetingCreate(BaseModel):
    """Request body to create a new meeting record."""
    title: str
    meeting_type: MeetingType
    meeting_date: date
    attendees: list[str] = []
    duration_minutes: Optional[int] = None
    transcript_text: Optional[str] = None  # If pasting transcript directly


class MeetingListItem(BaseModel):
    """Meeting summary for list views."""
    id: str
    title: str
    meeting_type: MeetingType
    meeting_date: date
    attendees: list[str] = []
    status: MeetingStatus
    summary: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MeetingDetailResponse(MeetingListItem):
    """Full meeting record with transcript, decisions, and action items."""
    transcript_clean: Optional[str] = None
    decisions: list[str] = []
    key_quotes: list[dict] = []
    action_items: list[ActionItemResponse] = []
    duration_minutes: Optional[int] = None
    summary_model: Optional[str] = None


class MeetingSearchResult(BaseModel):
    """Single result from semantic meeting search."""
    meeting_id: str
    meeting_title: str
    meeting_date: date
    snippet: str
    score: float = 0.0


class MeetingChatResponse(BaseModel):
    """Response from the meeting knowledge-base chat."""
    answer: str
    source_meetings: list[str] = []
    conversation_id: Optional[str] = None
