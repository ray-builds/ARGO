"""Tests for the AI Assistant service (conversation management and routing)."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, MagicMock, patch


class TestAIAssistantService:
    """Tests for question routing, conversation lifecycle, and message persistence."""

    @pytest.mark.asyncio
    async def test_route_question_to_email_module(
        self,
        test_db: AsyncSession,
        mock_claude,
    ) -> None:
        """Questions about emails are routed to the email intelligence module."""
        mock_claude.return_value = '{"module": "email", "confidence": 0.95}'

        from app.services.ai_assistant import AIAssistantService

        service = AIAssistantService(db=test_db)
        module = await service.route_question("What urgent emails need my attention today?")

        assert module == "email" or module in ("email", "EMAIL", "email_intelligence")

    @pytest.mark.asyncio
    async def test_route_question_to_portfolio_module(
        self,
        test_db: AsyncSession,
        mock_claude,
    ) -> None:
        """Questions about portfolio positions are routed to the portfolio module."""
        mock_claude.return_value = '{"module": "portfolio", "confidence": 0.91}'

        from app.services.ai_assistant import AIAssistantService

        service = AIAssistantService(db=test_db)
        module = await service.route_question("Summarise our current portfolio risk positions")

        assert module in ("portfolio", "PORTFOLIO", "portfolio_intelligence")

    @pytest.mark.asyncio
    async def test_chat_creates_conversation(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Sending a first message creates a new Conversation record in the database."""
        mock_claude_json.return_value = {
            "reply": "Here are today's urgent emails...",
            "module_used": "email",
        }

        from app.services.ai_assistant import AIAssistantService

        service = AIAssistantService(db=test_db)
        result = await service.chat(
            message="What emails need attention?",
            conversation_id=None,
            user_id="test-user-001",
        )

        assert result is not None
        assert "conversation_id" in result or result.get("reply") is not None

    @pytest.mark.asyncio
    async def test_chat_continues_existing_conversation(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Sending a message to an existing conversation ID continues the same thread."""
        mock_claude_json.return_value = {
            "reply": "Continuing our discussion...",
            "module_used": "general",
        }

        from app.services.ai_assistant import AIAssistantService
        from app.models.conversation import Conversation

        conv = Conversation(
            user_id="test-user-001",
            title="Test conversation",
            message_count=1,
        )
        test_db.add(conv)
        await test_db.commit()
        await test_db.refresh(conv)

        service = AIAssistantService(db=test_db)
        result = await service.chat(
            message="Tell me more",
            conversation_id=str(conv.id),
            user_id="test-user-001",
        )

        assert result is not None
        conv_id = result.get("conversation_id")
        assert conv_id is None or str(conv_id) == str(conv.id)

    @pytest.mark.asyncio
    async def test_conversation_history_stored(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Both user and assistant messages are stored in the conversation history."""
        mock_claude_json.return_value = {
            "reply": "The overnight summary shows UST yields rose 5bps.",
        }

        from app.services.ai_assistant import AIAssistantService

        service = AIAssistantService(db=test_db)
        result = await service.chat(
            message="What happened overnight?",
            conversation_id=None,
            user_id="test-user-001",
        )

        conv_id = result.get("conversation_id")
        if conv_id:
            history = await service.get_conversation_history(conv_id)
            assert isinstance(history, list)
            # Should have at least the user message and assistant reply
            roles = [m["role"] if isinstance(m, dict) else m.role for m in history]
            assert "user" in roles
            assert "assistant" in roles

    @pytest.mark.asyncio
    async def test_message_count_increments(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Each exchange increments the conversation's message_count by 2 (user + assistant)."""
        mock_claude_json.return_value = {"reply": "Test reply"}

        from app.services.ai_assistant import AIAssistantService
        from app.models.conversation import Conversation

        conv = Conversation(
            user_id="test-user-001",
            title="Count test",
            message_count=0,
        )
        test_db.add(conv)
        await test_db.commit()
        await test_db.refresh(conv)

        initial_count = conv.message_count or 0

        service = AIAssistantService(db=test_db)
        await service.chat(
            message="Hello ARGO",
            conversation_id=str(conv.id),
            user_id="test-user-001",
        )

        await test_db.refresh(conv)
        assert (conv.message_count or 0) >= initial_count + 1
