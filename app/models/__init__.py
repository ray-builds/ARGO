"""SQLAlchemy ORM models — imported here so Alembic discovers them all."""
from app.models.base import Base, TimestampMixin
from app.models.user import User
from app.models.email import Email, EmailHighlight
from app.models.summary import OvernightSummary
from app.models.meeting import Meeting, MeetingActionItem
from app.models.document import Document, DocumentChunk
from app.models.portfolio import Position, Scenario
from app.models.client import Client, ClientInteraction
from app.models.research import ResearchItem
from app.models.economic import EconomicEvent
from app.models.chat import ChatConversation, ChatMessage

__all__ = [
    "Base", "TimestampMixin",
    "User", "Email", "EmailHighlight", "OvernightSummary",
    "Meeting", "MeetingActionItem", "Document", "DocumentChunk",
    "Position", "Scenario", "Client", "ClientInteraction",
    "ResearchItem", "EconomicEvent", "ChatConversation", "ChatMessage",
]
