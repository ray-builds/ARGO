"""AI Assistant service — conversational interface with intelligent module routing."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.claude_client import get_claude_client
from app.models.chat import ChatConversation, ChatMessage
from app.modules.ai_assistant.prompts import (
    ARGO_ASSISTANT_SYSTEM_PROMPT,
    MODULE_ROUTER_PROMPT,
)
from app.schemas.chat import (
    ChatReplyResponse,
    ConversationListItem,
    ConversationDetailResponse,
    ChatMessageResponse,
)

# Module routing map — maps route name to module description
MODULE_DESCRIPTIONS = {
    "EMAIL": "Email inbox, email scoring, CEO emails, fetch emails from Graph",
    "OVERNIGHT": "Overnight market summary, morning briefing, past summaries",
    "MEETINGS": "Meeting transcripts, action items, decisions, meeting search",
    "DATALAKE": "Research data lake, document search, PDF library, Q&A on documents",
    "PORTFOLIO": "Portfolio positions, composition, scenario analysis, trade ideas",
    "CLIENTS": "Client CRM, investor relations, follow-ups, interaction history",
    "RESEARCH": "Research intelligence, supplier notes, weekly digest, conviction tracking",
    "ECON": "Economic calendar, data releases, surprise analysis, macro events",
    "GENERAL": "General ARGO questions, help, platform features",
}


class AIAssistantService:
    """Service for the ARGO AI Assistant — conversational interface across all modules.

    Routes user questions to the most relevant ARGO module, maintains conversation
    history, and provides a unified Claude-powered chat interface that can access
    context from any part of the platform.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialise service with DB session.

        Args:
            db: Async SQLAlchemy session.
        """
        self._db = db
        self._claude = get_claude_client()

    async def route_question(
        self, question: str, user_email: str
    ) -> ChatReplyResponse:
        """Route a question to the most relevant module and return an answer.

        Uses Claude Haiku to classify the question, then routes to the appropriate
        module service for context-aware responses. Falls back to general Claude
        response if routing fails.

        Args:
            question: The user's question.
            user_email: Email of the asking user.

        Returns:
            ChatReplyResponse with answer and routing metadata.
        """
        # Classify the question
        module = await self._classify_question(question)
        logger.debug(f"Question routed to module: {module}")

        # Get module-specific context and answer
        answer = await self._get_module_answer(question, module, user_email)

        return ChatReplyResponse(
            reply=answer,
            conversation_id="",
            module_routed_to=module,
        )

    async def start_conversation(
        self, first_message: str, user_email: str
    ) -> ChatReplyResponse:
        """Start a new persistent conversation.

        Creates a ChatConversation record, stores the user's first message,
        routes it to the appropriate module, stores the AI reply, and returns
        the response with the new conversation ID.

        Args:
            first_message: The user's first message.
            user_email: Email of the user starting the conversation.

        Returns:
            ChatReplyResponse with the AI reply and new conversation_id.
        """
        # Create conversation record
        title = first_message[:80] + "..." if len(first_message) > 80 else first_message
        conversation = ChatConversation(
            user_email=user_email,
            title=title,
            module_context=None,
        )
        self._db.add(conversation)
        await self._db.flush()

        # Route and answer
        module = await self._classify_question(first_message)
        conversation.module_context = module

        answer = await self._get_module_answer(first_message, module, user_email)

        # Store messages
        user_msg = ChatMessage(
            conversation_id=conversation.id,
            role="user",
            content=first_message,
        )
        ai_msg = ChatMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            model_used=self._claude.sonnet_model,
        )
        self._db.add(user_msg)
        self._db.add(ai_msg)
        conversation.updated_at = datetime.now(timezone.utc)

        await self._db.flush()

        return ChatReplyResponse(
            reply=answer,
            conversation_id=conversation.id,
            module_routed_to=module,
        )

    async def chat(
        self,
        conversation_id: str,
        message: str,
        user_email: str,
    ) -> ChatReplyResponse:
        """Continue an existing conversation with a new message.

        Loads conversation history (last 10 messages), appends the new user
        message, sends to Claude with full context, stores the reply, and
        returns the response.

        Args:
            conversation_id: UUID of the existing conversation.
            message: The user's new message.
            user_email: Email of the asking user.

        Returns:
            ChatReplyResponse with the AI reply.

        Raises:
            HTTPException: 404 if conversation not found.
        """
        result = await self._db.execute(
            select(ChatConversation).where(ChatConversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Load recent message history
        history_result = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(desc(ChatMessage.created_at))
            .limit(10)
        )
        history = list(reversed(history_result.scalars().all()))

        # Build messages list for Claude
        messages: list[dict[str, str]] = []
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": message})

        # Store user message
        user_msg = ChatMessage(
            conversation_id=conversation_id,
            role="user",
            content=message,
        )
        self._db.add(user_msg)

        try:
            answer = await self._claude.complete_with_history(
                messages=messages,
                system=ARGO_ASSISTANT_SYSTEM_PROMPT,
                use_sonnet=True,
                max_tokens=1000,
            )
        except Exception as exc:
            logger.exception(f"Chat completion failed: {exc}")
            answer = "I encountered an error processing your request. Please try again."

        # Store AI message
        ai_msg = ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            model_used=self._claude.sonnet_model,
        )
        self._db.add(ai_msg)
        conversation.updated_at = datetime.now(timezone.utc)
        await self._db.flush()

        return ChatReplyResponse(
            reply=answer,
            conversation_id=conversation_id,
            module_routed_to=conversation.module_context,
        )

    async def list_conversations(
        self, user_email: str, limit: int = 20
    ) -> list[ConversationListItem]:
        """Return recent conversations for a user.

        Args:
            user_email: Email of the user.
            limit: Maximum number of conversations to return.

        Returns:
            List of ConversationListItem objects.
        """
        result = await self._db.execute(
            select(ChatConversation)
            .where(ChatConversation.user_email == user_email)
            .order_by(desc(ChatConversation.updated_at))
            .limit(limit)
        )
        conversations = result.scalars().all()

        items = []
        for conv in conversations:
            # Count messages
            count_result = await self._db.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conv.id)
            )
            msg_count = len(count_result.scalars().all())
            items.append(
                ConversationListItem(
                    id=conv.id,
                    title=conv.title,
                    module_context=conv.module_context,
                    message_count=msg_count,
                    updated_at=conv.updated_at,
                )
            )
        return items

    async def get_conversation(self, conversation_id: str) -> ConversationDetailResponse:
        """Return a full conversation with all messages.

        Args:
            conversation_id: UUID of the conversation.

        Returns:
            ConversationDetailResponse with all message history.

        Raises:
            HTTPException: 404 if conversation not found.
        """
        result = await self._db.execute(
            select(ChatConversation).where(ChatConversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Conversation not found")

        msgs_result = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at)
        )
        messages = msgs_result.scalars().all()
        msg_responses = [ChatMessageResponse.model_validate(m) for m in messages]

        return ConversationDetailResponse(
            id=conversation.id,
            title=conversation.title,
            module_context=conversation.module_context,
            message_count=len(msg_responses),
            updated_at=conversation.updated_at,
            messages=msg_responses,
        )

    async def _classify_question(self, question: str) -> str:
        """Use Claude Haiku to classify which module should handle this question.

        Args:
            question: The user's question text.

        Returns:
            Module name string (one of the keys in MODULE_DESCRIPTIONS).
        """
        module_list = "\n".join(
            f"- {name}: {desc}" for name, desc in MODULE_DESCRIPTIONS.items()
        )
        prompt = f"Modules:\n{module_list}\n\nQuestion: {question}"

        try:
            response = await self._claude.complete(
                prompt=prompt,
                system=MODULE_ROUTER_PROMPT,
                use_sonnet=False,
                max_tokens=20,
            )
            module = response.strip().upper()
            if module in MODULE_DESCRIPTIONS:
                return module
            return "GENERAL"
        except Exception as exc:
            logger.warning(f"Module classification failed: {exc}")
            return "GENERAL"

    async def _get_module_answer(
        self, question: str, module: str, user_email: str
    ) -> str:
        """Generate an answer for the question using the routed module's context.

        For most modules, provides a Claude Sonnet response with module-specific
        system context. In future iterations, each module can contribute live data.

        Args:
            question: The user's question.
            module: The classified module name.
            user_email: Email of the asking user.

        Returns:
            AI-generated answer string.
        """
        module_context = MODULE_DESCRIPTIONS.get(module, "")
        system = (
            f"{ARGO_ASSISTANT_SYSTEM_PROMPT}\n\n"
            f"This question has been routed to the {module} module: {module_context}.\n"
            f"Answer with specific reference to ARP Global Capital's {module} data and context."
        )

        try:
            answer = await self._claude.complete(
                prompt=question,
                system=system,
                use_sonnet=True,
                max_tokens=800,
            )
            return answer
        except Exception as exc:
            logger.exception(f"Module answer generation failed: {exc}")
            return "I encountered an error processing your request. Please try again."

    async def get_history(
        self, conversation_id: str, limit: int = 20
    ) -> list[ChatMessageResponse]:
        """Return message history for a conversation.

        Args:
            conversation_id: UUID of the conversation.
            limit: Maximum number of messages to return.

        Returns:
            List of ChatMessageResponse objects in chronological order.
        """
        result = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at)
            .limit(limit)
        )
        messages = result.scalars().all()
        return [ChatMessageResponse.model_validate(m) for m in messages]
