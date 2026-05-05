"""ChatConversation and ChatMessage models for the ARGO AI Chat module."""
from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User

# Valid message roles
CHAT_ROLES = ("user", "assistant", "system")


class ChatConversation(Base, TimestampMixin):
    """A multi-turn conversation session between a user and ARGO's AI assistant.

    Conversations are scoped to a module_context (e.g. 'email', 'portfolio',
    'research', 'general') to provide appropriate system prompts. Message count
    is a denormalised counter updated on each new message for quick display.
    """
    __tablename__ = "chat_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # user_email retained for fast display without join
    user_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    module_context: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # module_context values: 'email', 'portfolio', 'research', 'meeting', 'general', etc.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="chat_conversations", foreign_keys=[user_id]
    )
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="conversation", cascade="all, delete-orphan",
        order_by="ChatMessage.sequence_num",
    )

    def __repr__(self) -> str:
        return (
            f"<ChatConversation id={self.id!r} user={self.user_email!r} "
            f"context={self.module_context!r} messages={self.message_count}>"
        )


class ChatMessage(Base):
    """A single message within a ChatConversation.

    Stores both user and assistant turns, including tool call/result JSON
    for agentic interactions. Token counts are recorded for cost tracking.
    sequence_num enforces ordering within a conversation.
    """
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # role values: 'user', 'assistant', 'system'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # JSON
    tool_results: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    model_used: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    token_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sequence_num: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship back to conversation
    conversation: Mapped["ChatConversation"] = relationship(
        "ChatConversation", back_populates="messages"
    )

    __table_args__ = (
        Index("idx_chat_messages_conv_seq", "conversation_id", "sequence_num"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChatMessage conversation_id={self.conversation_id!r} "
            f"role={self.role!r} seq={self.sequence_num}>"
        )
