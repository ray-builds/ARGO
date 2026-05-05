"""AI Assistant API router — /api/v1/assistant/* endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.chat import (
    ChatMessageRequest,
    NewConversationRequest,
    ChatReplyResponse,
    ConversationListItem,
    ConversationDetailResponse,
)

router = APIRouter()


@router.get("/conversations", response_model=list[ConversationListItem])
async def list_conversations(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
) -> list[ConversationListItem]:
    """Return the user's recent conversations."""
    from app.modules.ai_assistant.service import AIAssistantService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = AIAssistantService(db)
        return await service.list_conversations(current_user.email, limit)


@router.post("/conversations", response_model=ChatReplyResponse)
async def new_conversation(
    body: NewConversationRequest,
    current_user: User = Depends(get_current_user),
) -> ChatReplyResponse:
    """Start a new conversation with the AI assistant."""
    from app.modules.ai_assistant.service import AIAssistantService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = AIAssistantService(db)
        return await service.start_conversation(body.first_message, current_user.email)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> ConversationDetailResponse:
    """Return a full conversation with all messages."""
    from app.modules.ai_assistant.service import AIAssistantService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = AIAssistantService(db)
        return await service.get_conversation(conversation_id)


@router.post("/conversations/{conversation_id}/messages", response_model=ChatReplyResponse)
async def send_message(
    conversation_id: str,
    body: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
) -> ChatReplyResponse:
    """Send a message to an existing conversation and get an AI reply."""
    from app.modules.ai_assistant.service import AIAssistantService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = AIAssistantService(db)
        return await service.chat(conversation_id, body.content, current_user.email)


@router.post("/quick-chat", response_model=ChatReplyResponse)
async def quick_chat(
    body: NewConversationRequest,
    current_user: User = Depends(get_current_user),
) -> ChatReplyResponse:
    """Single-shot question with no persistent conversation context."""
    from app.modules.ai_assistant.service import AIAssistantService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = AIAssistantService(db)
        return await service.route_question(body.first_message, current_user.email)
