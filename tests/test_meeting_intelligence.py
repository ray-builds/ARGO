"""Tests for the Meeting Intelligence service."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch


class TestMeetingIntelligenceService:
    """Tests for meeting creation, transcription, summarisation, and search."""

    @pytest.mark.asyncio
    async def test_create_meeting_stores_in_db(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Creating a meeting record persists it to the database with correct fields."""
        from app.services.meeting_intelligence import MeetingIntelligenceService

        service = MeetingIntelligenceService(db=test_db)
        meeting = await service.create_meeting(
            title="Goldman Sachs Rates Call",
            meeting_type="STRATEGIST",
            meeting_date="2026-05-05",
            attendees=["John Smith", "Jane Doe"],
        )

        assert meeting is not None
        assert meeting.id is not None
        assert meeting.title == "Goldman Sachs Rates Call"
        assert meeting.meeting_type == "STRATEGIST"
        assert meeting.status in ("pending", "PENDING")

    @pytest.mark.asyncio
    async def test_transcribe_requires_openai_key(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Transcription raises an error or returns a sensible result without a valid OpenAI key."""
        from app.services.meeting_intelligence import MeetingIntelligenceService

        service = MeetingIntelligenceService(db=test_db)

        # With a fake key, transcription should raise an exception or return an error state
        with pytest.raises(Exception):
            await service.transcribe_audio(
                audio_path="/tmp/nonexistent_audio.mp3",
                meeting_id="fake-meeting-id",
            )

    @pytest.mark.asyncio
    async def test_summarize_produces_action_items(
        self,
        test_db: AsyncSession,
        mock_claude_json,
    ) -> None:
        """Summarising a transcript produces action items."""
        mock_claude_json.return_value = {
            "summary": "Discussion of rate positioning for Q3.",
            "action_items": [
                {"text": "Reduce UST 10Y by 15%", "owner": "PM", "due_date": "2026-05-07"},
                {"text": "Update risk report", "owner": "Risk", "due_date": None},
            ],
            "key_themes": ["rates", "duration"],
        }

        from app.services.meeting_intelligence import MeetingIntelligenceService

        service = MeetingIntelligenceService(db=test_db)
        result = await service.summarize_transcript(
            transcript="We should reduce duration... PM agrees. Risk to update report.",
            meeting_id="fake-id-001",
        )

        assert result is not None
        action_items = result.get("action_items", [])
        assert len(action_items) > 0

    @pytest.mark.asyncio
    async def test_search_meetings_fulltext(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Full-text search over meetings returns relevant results."""
        from app.services.meeting_intelligence import MeetingIntelligenceService
        from app.models.meeting import Meeting

        # Create test meetings
        m1 = Meeting(title="Fed Policy Discussion", meeting_type="INTERNAL", status="complete",
                     summary="Discussion about Fed hiking cycle.")
        m2 = Meeting(title="Client CIO Call", meeting_type="CLIENT", status="complete",
                     summary="Portfolio review with client CIO.")
        test_db.add_all([m1, m2])
        await test_db.commit()

        service = MeetingIntelligenceService(db=test_db)
        results = await service.search_meetings(query="Fed policy")

        assert len(results) >= 1
        titles = [m.title for m in results]
        assert any("Fed" in t for t in titles)

    @pytest.mark.asyncio
    async def test_meeting_status_transitions(
        self,
        test_db: AsyncSession,
    ) -> None:
        """Meeting status transitions from pending → processing → complete correctly."""
        from app.services.meeting_intelligence import MeetingIntelligenceService
        from app.models.meeting import Meeting

        meeting = Meeting(
            title="Status Test Meeting",
            meeting_type="INTERNAL",
            status="pending",
        )
        test_db.add(meeting)
        await test_db.commit()
        await test_db.refresh(meeting)

        service = MeetingIntelligenceService(db=test_db)
        await service.update_meeting_status(str(meeting.id), "complete")

        await test_db.refresh(meeting)
        assert meeting.status in ("complete", "COMPLETE")
