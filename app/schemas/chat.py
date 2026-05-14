"""Pydantic schemas for the AI Assistant module."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, ConfigDict


class ChatMessageRequest(BaseModel):
    """Single message sent by the user to the AI assistant."""
    content: str


class NewConversationRequest(BaseModel):
    """Request to start a new conversation with the AI assistant."""
    first_message: str


class ChatMessageResponse(BaseModel):
    """Single chat message record."""
    id: str
    role: str
    content: str
    model_used: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ConversationListItem(BaseModel):
    """Conversation summary for list views."""
    id: str
    title: Optional[str] = None
    module_context: Optional[str] = None
    message_count: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailResponse(ConversationListItem):
    """Full conversation with all messages."""
    messages: list[ChatMessageResponse] = []


class ChatReplyResponse(BaseModel):
    """AI assistant reply with routing metadata."""
    reply: str
    conversation_id: str
    module_routed_to: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
