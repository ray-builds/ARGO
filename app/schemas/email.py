"""Pydantic schemas for the Email Intelligence module."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmailTag(str, Enum):
    """Valid email classification tags."""
    URGENT = "URGENT"
    CLIENT = "CLIENT"
    TRADE = "TRADE"
    RESEARCH = "RESEARCH"
    OPERATIONS = "OPERATIONS"
    HR = "HR"
    REGULATORY = "REGULATORY"
    SKIP = "SKIP"


class EmailHighlightResponse(BaseModel):
    """AI-extracted highlight for an email."""
    id: str
    highlight_text: str
    action_required: Optional[str] = None
    key_conclusion: Optional[str] = None
    model_used: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class EmailResponse(BaseModel):
    """Email record with AI scoring and classification."""
    id: str
    graph_message_id: str
    mailbox_user_email: str
    sender_email: str
    sender_name: Optional[str] = None
    subject: str
    body_preview: Optional[str] = None
    received_at: datetime
    is_read: bool
    relevance_score: Optional[int] = Field(None, ge=0, le=100)
    tag: Optional[EmailTag] = None
    is_from_ceo: bool
    is_archived: bool
    processed_at: Optional[datetime] = None
    highlights: list[EmailHighlightResponse] = []

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class EmailDetailResponse(EmailResponse):
    """Email with full body included."""
    body_full: Optional[str] = None


class FetchEmailsRequest(BaseModel):
    """Request to fetch emails from Graph API."""
    user_email: str
    force_refresh: bool = False


class FetchEmailsResponse(BaseModel):
    """Response after fetching emails."""
    fetched: int
    new: int
    processed: int


class ArchiveEmailsRequest(BaseModel):
    """Request to archive multiple emails."""
    email_ids: list[str]


class DigestResponse(BaseModel):
    """Email digest for a given user and date."""
    user_email: str
    total_emails: int
    urgent_count: int
    ceo_email_count: int
    emails: list[EmailResponse]


class TagCountResponse(BaseModel):
    """Count of emails per tag."""
    tag: str
    count: int
