"""Meeting Intelligence service — transcription, AI summarisation, and knowledge search."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update

from app.core.claude_client import get_claude_client
from app.models.meeting import Meeting, MeetingActionItem
from app.prompts.adapters import normalize_meeting_intelligence_json
from app.prompts.architecture import MEETING_INTELLIGENCE_PROMPT

from app.modules.meeting_intelligence.prompts import (
    MEETING_SUMMARY_SYSTEM,
    MEETING_CHAT_PROMPT,
)
from app.schemas.meeting import (
    MeetingCreate,
    MeetingListItem,
    MeetingDetailResponse,
    ActionItemResponse,
    MeetingSearchResult,
    MeetingChatResponse,
    MeetingStatus,
)


class MeetingIntelligenceService:
    """Service for AI-powered meeting intelligence.

    Handles meeting creation, Whisper transcription, Claude summarisation,
    action item extraction, semantic search, and conversational Q&A over the
    meeting knowledge base.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialise service with DB session.

        Args:
            db: Async SQLAlchemy session.
        """
        self._db = db
        self._claude = get_claude_client()

    async def create_meeting(
        self, data: MeetingCreate, created_by_email: str
    ) -> MeetingDetailResponse:
        """Create a new meeting record and optionally trigger summarisation.

        If transcript_text is provided in the request, immediately runs AI
        summarisation and action item extraction.

        Args:
            data: MeetingCreate payload from the API request.
            created_by_email: Email of the user creating the record.

        Returns:
            MeetingDetailResponse with the newly created meeting.
        """
        meeting = Meeting(
            title=data.title,
            meeting_type=data.meeting_type.value,
            meeting_date=data.meeting_date,
            attendees=data.attendees,
            duration_minutes=data.duration_minutes,
            transcript_clean=data.transcript_text,
            status=MeetingStatus.PENDING.value,
            created_by_email=created_by_email,
        )
        self._db.add(meeting)
        await self._db.flush()
        logger.info(f"Meeting created: {meeting.id} — {meeting.title}")

        if data.transcript_text:
            await self.summarize(meeting)

        return MeetingDetailResponse.model_validate(meeting)

    async def transcribe(self, meeting_id: str, file: UploadFile) -> dict[str, Any]:
        """Upload audio, run Whisper transcription, then summarise.

        Args:
            meeting_id: UUID of the meeting to attach transcription to.
            file: Uploaded audio/video file.

        Returns:
            Dict with status and transcript character count.

        Raises:
            HTTPException: 404 if meeting not found, 500 on transcription failure.
        """
        from app.modules.meeting_intelligence.transcriber import transcribe_audio

        result = await self._db.execute(
            select(Meeting).where(Meeting.id == meeting_id)
        )
        meeting = result.scalar_one_or_none()
        if not meeting:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Meeting not found")

        # Write to temp file for Whisper
        suffix = os.path.splitext(file.filename or "audio.mp3")[1] or ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            meeting.status = MeetingStatus.TRANSCRIBING.value
            await self._db.flush()

            transcript = await transcribe_audio(tmp_path)
            meeting.transcript_clean = transcript
            logger.info(f"Transcription complete for meeting {meeting_id}: {len(transcript)} chars")

            await self.summarize(meeting)
            return {"status": "complete", "transcript_length": len(transcript)}
        except Exception as exc:
            meeting.status = MeetingStatus.ERROR.value
            logger.exception(f"Transcription failed for {meeting_id}: {exc}")
            raise
        finally:
            os.unlink(tmp_path)

    async def summarize(self, meeting: Meeting) -> None:
        """Run Claude Sonnet summarisation and action item extraction on a meeting.

        Updates the meeting record in-place with summary, decisions, key_quotes,
        and creates MeetingActionItem records.

        Args:
            meeting: The Meeting ORM object to summarise.
        """
        if not meeting.transcript_clean:
            logger.warning(f"No transcript for meeting {meeting.id} — skipping summarise")
            return

        meeting.status = MeetingStatus.SUMMARIZING.value
        await self._db.flush()

        raw_attendees = meeting.attendees or "[]"
        try:
            attendees_list = (
                json.loads(raw_attendees)
                if isinstance(raw_attendees, str)
                else list(raw_attendees or [])
            )
        except (json.JSONDecodeError, TypeError):
            attendees_list = []

        user_prompt = MEETING_INTELLIGENCE_PROMPT.format(
            meeting_date=str(meeting.meeting_date),
            meeting_title=meeting.title,
            participants=", ".join(str(a) for a in attendees_list),
            duration_minutes=meeting.duration_minutes or 0,
            meeting_type=meeting.meeting_type,
            transcript_text=(meeting.transcript_clean or "")[:12000],
        )

        try:
            result = await self._claude.complete_json(
                prompt=user_prompt,
                system=MEETING_SUMMARY_SYSTEM,
                use_sonnet=True,
                max_tokens=2000,
            )
            result = normalize_meeting_intelligence_json(result)
            meeting.summary = result.get("summary", "")
            meeting.decisions = json.dumps(result.get("decisions", []))
            meeting.key_quotes = json.dumps(result.get("key_quotes", []))
            meeting.summary_model = self._claude.sonnet_model
            meeting.status = MeetingStatus.COMPLETE.value

            # Create action items
            for item in result.get("action_items", []):
                action = MeetingActionItem(
                    meeting_id=meeting.id,
                    description=item.get("description", ""),
                    owner_name=item.get("owner"),
                    due_date=item.get("due_date"),
                )
                self._db.add(action)

            logger.info(f"Meeting {meeting.id} summarised successfully")

        except Exception as exc:
            meeting.status = MeetingStatus.ERROR.value
            logger.exception(f"Meeting summarisation failed for {meeting.id}: {exc}")

    async def list_meetings(self, limit: int = 20, offset: int = 0) -> list[MeetingListItem]:
        """Return paginated list of meetings sorted by date descending.

        Args:
            limit: Maximum records to return.
            offset: Pagination offset.

        Returns:
            List of MeetingListItem objects.
        """
        result = await self._db.execute(
            select(Meeting)
            .order_by(desc(Meeting.meeting_date))
            .limit(limit)
            .offset(offset)
        )
        meetings = result.scalars().all()
        return [MeetingListItem.model_validate(m) for m in meetings]

    async def get_meeting(self, meeting_id: str) -> MeetingDetailResponse:
        """Return a single meeting with full details.

        Args:
            meeting_id: UUID of the meeting.

        Returns:
            MeetingDetailResponse with all fields including action items.

        Raises:
            HTTPException: 404 if meeting not found.
        """
        result = await self._db.execute(
            select(Meeting).where(Meeting.id == meeting_id)
        )
        meeting = result.scalar_one_or_none()
        if not meeting:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Meeting not found")
        return MeetingDetailResponse.model_validate(meeting)

    async def update_action_item(
        self, item_id: str, is_complete: bool
    ) -> ActionItemResponse:
        """Toggle the completion state of a meeting action item.

        Args:
            item_id: UUID of the action item.
            is_complete: New completion state.

        Returns:
            Updated ActionItemResponse.

        Raises:
            HTTPException: 404 if action item not found.
        """
        result = await self._db.execute(
            select(MeetingActionItem).where(MeetingActionItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Action item not found")

        item.is_complete = is_complete
        item.completed_at = datetime.now(timezone.utc) if is_complete else None
        await self._db.flush()
        return ActionItemResponse.model_validate(item)

    async def search_meetings(
        self, query: str, limit: int = 5
    ) -> list[MeetingSearchResult]:
        """Semantic search across meeting transcripts and summaries.

        Currently performs simple text matching. Replace with vector similarity
        search when embeddings are available.

        Args:
            query: Natural language search query.
            limit: Maximum number of results to return.

        Returns:
            List of MeetingSearchResult objects with snippets.
        """
        from sqlalchemy import or_, func

        result = await self._db.execute(
            select(Meeting)
            .where(
                or_(
                    Meeting.summary.ilike(f"%{query}%"),
                    Meeting.transcript_clean.ilike(f"%{query}%"),
                    Meeting.title.ilike(f"%{query}%"),
                )
            )
            .order_by(desc(Meeting.meeting_date))
            .limit(limit)
        )
        meetings = result.scalars().all()

        results = []
        for m in meetings:
            # Extract snippet around the query term
            text = (m.summary or m.transcript_clean or m.title or "")
            idx = text.lower().find(query.lower())
            if idx >= 0:
                start = max(0, idx - 100)
                snippet = "..." + text[start: idx + 200] + "..."
            else:
                snippet = text[:200] + "..."

            results.append(
                MeetingSearchResult(
                    meeting_id=m.id,
                    meeting_title=m.title,
                    meeting_date=m.meeting_date,
                    snippet=snippet,
                    score=1.0,
                )
            )
        return results

    async def chat(
        self, question: str, conversation_id: str | None = None
    ) -> MeetingChatResponse:
        """Answer a question using the meeting knowledge base.

        Performs a search, then uses Claude to synthesise an answer with
        citations to specific meetings.

        Args:
            question: Natural language question from the user.
            conversation_id: Optional existing conversation UUID for context.

        Returns:
            MeetingChatResponse with answer and source meeting references.
        """
        # Search for relevant meetings
        search_results = await self.search_meetings(question, limit=5)

        context_parts = []
        source_ids = []
        for sr in search_results:
            context_parts.append(
                f"[{sr.meeting_title} — {sr.meeting_date}]\n{sr.snippet}"
            )
            source_ids.append(sr.meeting_id)

        context = "\n\n".join(context_parts) if context_parts else "No relevant meetings found."
        prompt = f"QUESTION: {question}\n\nRELEVANT MEETING EXCERPTS:\n{context}"

        try:
            answer = await self._claude.complete(
                prompt=prompt,
                system=MEETING_CHAT_PROMPT,
                use_sonnet=True,
                max_tokens=800,
            )
        except Exception as exc:
            logger.exception(f"Meeting chat failed: {exc}")
            answer = "Unable to generate an answer at this time."

        return MeetingChatResponse(
            answer=answer,
            source_meetings=source_ids,
            conversation_id=conversation_id,
        )
