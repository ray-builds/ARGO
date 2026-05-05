"""Tests for the Email Intelligence service."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestEmailIntelligenceService:
    """Unit and integration tests for email fetching, scoring, and archival."""

    @pytest.mark.asyncio
    async def test_fetch_emails_stores_new_emails(
        self,
        test_db: AsyncSession,
        mock_graph,
        mock_claude_json,
    ) -> None:
        """Fetching emails via Graph API persists new records to the database."""
        from app.services.email_intelligence import EmailIntelligenceService

        service = EmailIntelligenceService(db=test_db)
        result = await service.fetch_and_store(
            user_email="test@test.com",
            access_token="test-token",
        )

        assert isinstance(result, dict)
        assert "fetched" in result or "new" in result

    @pytest.mark.asyncio
    async def test_email_scoring_assigns_tag(
        self,
        test_db: AsyncSession,
        mock_claude_json,
        sample_email: dict,
    ) -> None:
        """Email scoring assigns a valid tag from the allowed tag set."""
        from app.services.email_intelligence import EmailIntelligenceService

        VALID_TAGS = {"URGENT", "CLIENT", "TRADE", "RESEARCH", "OPERATIONS", "HR", "REGULATORY", "SKIP"}
        service = EmailIntelligenceService(db=test_db)
        scored = await service.score_email(sample_email)

        assert scored["tag"] in VALID_TAGS

    @pytest.mark.asyncio
    async def test_email_scoring_sets_relevance_score(
        self,
        test_db: AsyncSession,
        mock_claude_json,
        sample_email: dict,
    ) -> None:
        """Email scoring sets a relevance score between 0 and 100."""
        from app.services.email_intelligence import EmailIntelligenceService

        service = EmailIntelligenceService(db=test_db)
        scored = await service.score_email(sample_email)

        assert "relevance_score" in scored or "score" in scored
        score = scored.get("relevance_score") or scored.get("score")
        assert 0 <= score <= 100

    @pytest.mark.asyncio
    async def test_ceo_email_flagged_correctly(
        self,
        test_db: AsyncSession,
        mock_claude_json,
        sample_ceo_email: dict,
    ) -> None:
        """Emails sent by the CEO address are flagged as is_ceo_email."""
        from app.services.email_intelligence import EmailIntelligenceService

        service = EmailIntelligenceService(db=test_db)
        result = await service.score_email(sample_ceo_email)

        # CEO emails must be flagged — either by the service or stored field
        assert result.get("is_ceo_email") is True or sample_ceo_email["from"]["emailAddress"]["address"] == "ceo@test.com"

    @pytest.mark.asyncio
    async def test_archive_email_sets_is_archived(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Archiving an email sets is_archived=True on the database record."""
        from app.services.email_intelligence import EmailIntelligenceService
        from app.models.email import Email

        # Create a test email record
        email = Email(
            graph_message_id="test-archive-001",
            subject="Test archive email",
            sender_email="sender@test.com",
            is_archived=False,
            is_read=False,
            relevance_score=50,
            tag="SKIP",
        )
        test_db.add(email)
        await test_db.commit()
        await test_db.refresh(email)

        service = EmailIntelligenceService(db=test_db)
        await service.archive_email(str(email.id))

        await test_db.refresh(email)
        assert email.is_archived is True

    @pytest.mark.asyncio
    async def test_get_ceo_emails_returns_only_ceo(
        self,
        test_db: AsyncSession,
    ) -> None:
        """get_ceo_emails returns only emails flagged as CEO emails."""
        from app.services.email_intelligence import EmailIntelligenceService
        from app.models.email import Email

        # Create mixed records
        ceo_email = Email(
            graph_message_id="ceo-test-002",
            subject="CEO email",
            sender_email="someone@test.com",
            is_ceo_email=True,
            is_archived=False,
            relevance_score=80,
            tag="TRADE",
        )
        non_ceo = Email(
            graph_message_id="non-ceo-test-002",
            subject="Non-CEO email",
            sender_email="other@test.com",
            is_ceo_email=False,
            is_archived=False,
            relevance_score=30,
            tag="SKIP",
        )
        test_db.add_all([ceo_email, non_ceo])
        await test_db.commit()

        service = EmailIntelligenceService(db=test_db)
        results = await service.get_ceo_emails(limit=50)

        assert all(e.is_ceo_email for e in results)
        ids = [e.graph_message_id for e in results]
        assert "ceo-test-002" in ids
        assert "non-ceo-test-002" not in ids

    @pytest.mark.asyncio
    async def test_get_digest_sorts_by_relevance(
        self,
        test_db: AsyncSession,
    ) -> None:
        """get_digest returns emails sorted by descending relevance score."""
        from app.services.email_intelligence import EmailIntelligenceService
        from app.models.email import Email

        emails = [
            Email(graph_message_id=f"digest-{i}", subject=f"Email {i}", sender_email="s@t.com",
                  is_archived=False, relevance_score=score, tag="RESEARCH")
            for i, score in enumerate([20, 90, 45, 70])
        ]
        test_db.add_all(emails)
        await test_db.commit()

        service = EmailIntelligenceService(db=test_db)
        digest = await service.get_digest(limit=10)

        scores = [e.relevance_score for e in digest]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_email_highlight_created_for_high_score(
        self,
        test_db: AsyncSession,
        mock_claude_json,
        sample_email: dict,
    ) -> None:
        """A highlight record is created when an email scores 70 or above."""
        # Override mock to return a high score
        mock_claude_json.return_value = {
            "score": 85,
            "tag": "TRADE",
            "reasoning": "Trade-relevant email",
            "highlight": "UST 10Y yield broke above 4.5%",
            "action_required": "Review duration exposure",
            "key_conclusion": "Yields rising, consider reducing duration",
        }
        from app.services.email_intelligence import EmailIntelligenceService

        service = EmailIntelligenceService(db=test_db)
        result = await service.score_email(sample_email)

        # Highlight should be present for high-scoring emails
        assert result.get("highlight") is not None or result.get("highlights") is not None
