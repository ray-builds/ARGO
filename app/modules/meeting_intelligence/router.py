"""Meeting Intelligence API router — /api/v1/meetings/* endpoints and HTML view routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.dependencies import get_current_user, get_current_user_optional
from app.models.user import User
from app.schemas.meeting import (
    MeetingCreate,
    MeetingListItem,
    MeetingDetailResponse,
    ActionItemResponse,
    ActionItemUpdate,
    MeetingSearchResult,
    MeetingChatResponse,
    MeetingType,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ── API routes ────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[MeetingListItem])
async def list_meetings(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
) -> list[MeetingListItem]:
    """Return a paginated list of meetings sorted by date descending."""
    from app.modules.meeting_intelligence.service import MeetingIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = MeetingIntelligenceService(db)
        return await service.list_meetings(limit, offset)


@router.post("/", response_model=MeetingDetailResponse)
async def create_meeting(
    body: MeetingCreate,
    current_user: User = Depends(get_current_user),
) -> MeetingDetailResponse:
    """Create a new meeting record and trigger AI summarisation if transcript provided."""
    from app.modules.meeting_intelligence.service import MeetingIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = MeetingIntelligenceService(db)
        return await service.create_meeting(body, current_user.email)


@router.post("/upload", response_model=MeetingDetailResponse)
async def upload_meeting(
    title: str = Form(...),
    meeting_type: str = Form("INTERNAL"),
    meeting_date: str = Form(...),
    attendees: str = Form(""),
    duration_minutes: int | None = Form(None),
    transcript_text: str | None = Form(None),
    file: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
) -> MeetingDetailResponse:
    """Upload a meeting: audio file for Whisper transcription OR pasted transcript.

    Multipart form endpoint. Creates the meeting record immediately (status=pending)
    and triggers background processing.
    """
    from datetime import date
    from app.modules.meeting_intelligence.service import MeetingIntelligenceService
    from app.core.database import get_db_session

    # Parse attendees list
    attendees_list: list[str] = (
        [a.strip() for a in attendees.split(",") if a.strip()] if attendees else []
    )

    # Parse meeting date
    try:
        parsed_date = date.fromisoformat(meeting_date)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Invalid meeting_date: {meeting_date}")

    # Validate meeting type
    try:
        mt = MeetingType(meeting_type.upper())
    except ValueError:
        mt = MeetingType.INTERNAL

    body = MeetingCreate(
        title=title,
        meeting_type=mt,
        meeting_date=parsed_date,
        attendees=attendees_list,
        duration_minutes=duration_minutes,
        transcript_text=transcript_text or None,
    )

    async with get_db_session() as db:
        service = MeetingIntelligenceService(db)
        meeting_resp = await service.create_meeting(body, current_user.email)

    # If an audio file was provided, trigger transcription in the background
    if file and file.filename:
        import asyncio
        asyncio.create_task(_background_transcribe(meeting_resp.id, file, current_user.email))

    return meeting_resp


async def _background_transcribe(meeting_id: str, file: UploadFile, user_email: str) -> None:
    """Background task: read file bytes and run Whisper transcription."""
    from app.modules.meeting_intelligence.service import MeetingIntelligenceService
    from app.core.database import get_db_session
    from loguru import logger

    try:
        async with get_db_session() as db:
            service = MeetingIntelligenceService(db)
            await service.transcribe(meeting_id, file)
    except Exception as exc:
        logger.exception(f"Background transcription failed for meeting {meeting_id}: {exc}")


@router.get("/action-items", response_model=list[ActionItemResponse])
async def list_action_items(
    incomplete_only: bool = True,
    current_user: User = Depends(get_current_user),
) -> list[ActionItemResponse]:
    """List all action items, optionally filtered to incomplete only."""
    from app.modules.meeting_intelligence.service import MeetingIntelligenceService
    from app.core.database import get_db_session
    from sqlalchemy import select
    from app.models.meeting import MeetingActionItem

    async with get_db_session() as db:
        stmt = select(MeetingActionItem)
        if incomplete_only:
            stmt = stmt.where(MeetingActionItem.is_complete == False)  # noqa: E712
        stmt = stmt.order_by(MeetingActionItem.created_at.desc())
        result = await db.execute(stmt)
        items = result.scalars().all()
        return [ActionItemResponse.model_validate(i) for i in items]


@router.post("/action-items/{item_id}/complete", response_model=ActionItemResponse)
async def complete_action_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
) -> ActionItemResponse:
    """Mark an action item as complete."""
    from app.modules.meeting_intelligence.service import MeetingIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = MeetingIntelligenceService(db)
        return await service.update_action_item(item_id, is_complete=True)


@router.get("/search/query", response_model=list[MeetingSearchResult])
async def search_meetings(
    q: str,
    limit: int = 5,
    current_user: User = Depends(get_current_user),
) -> list[MeetingSearchResult]:
    """Semantic search across meeting transcripts and summaries."""
    from app.modules.meeting_intelligence.service import MeetingIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = MeetingIntelligenceService(db)
        return await service.search_meetings(q, limit)


@router.post("/chat", response_model=MeetingChatResponse)
async def chat_with_meetings(
    question: str,
    conversation_id: str | None = None,
    current_user: User = Depends(get_current_user),
) -> MeetingChatResponse:
    """Ask a question across all meeting knowledge and get a cited answer."""
    from app.modules.meeting_intelligence.service import MeetingIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = MeetingIntelligenceService(db)
        return await service.chat(question, conversation_id)


@router.get("/{meeting_id}", response_model=MeetingDetailResponse)
async def get_meeting(
    meeting_id: str,
    current_user: User = Depends(get_current_user),
) -> MeetingDetailResponse:
    """Return full meeting detail with transcript, summary, and action items."""
    from app.modules.meeting_intelligence.service import MeetingIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = MeetingIntelligenceService(db)
        return await service.get_meeting(meeting_id)


@router.post("/{meeting_id}/upload-audio")
async def upload_audio(
    meeting_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload an audio file for a meeting and trigger Whisper transcription."""
    from app.modules.meeting_intelligence.service import MeetingIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = MeetingIntelligenceService(db)
        result = await service.transcribe(meeting_id, file)
    return result


@router.patch("/{meeting_id}/action-items/{item_id}", response_model=ActionItemResponse)
async def update_action_item(
    meeting_id: str,
    item_id: str,
    body: ActionItemUpdate,
    current_user: User = Depends(get_current_user),
) -> ActionItemResponse:
    """Mark an action item as complete or incomplete."""
    from app.modules.meeting_intelligence.service import MeetingIntelligenceService
    from app.core.database import get_db_session

    async with get_db_session() as db:
        service = MeetingIntelligenceService(db)
        return await service.update_action_item(item_id, body.is_complete)


# ── HTML view routes ─────────────────────────────────────────────────────────

@router.get("/view/list", response_class=HTMLResponse)
async def view_meetings_list(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """HTML page: meeting list with upload form."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse(
        "meetings/list.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "meetings",
        },
    )


@router.get("/view/{meeting_id}", response_class=HTMLResponse)
async def view_meeting_detail(
    meeting_id: str,
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    """HTML page: meeting detail with summary, decisions, action items, and transcript."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    # Attempt to server-render the meeting; fall back to client-side load on error
    meeting = None
    try:
        from app.modules.meeting_intelligence.service import MeetingIntelligenceService
        from app.core.database import get_db_session

        async with get_db_session() as db:
            service = MeetingIntelligenceService(db)
            meeting = await service.get_meeting(meeting_id)
    except Exception:
        pass

    return templates.TemplateResponse(
        "meetings/detail.html",
        {
            "request": request,
            "user": current_user,
            "active_nav": "meetings",
            "meeting": meeting,
        },
    )
