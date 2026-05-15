"""Section 4 — Teams recording auto-transcription pipeline tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services import teams_recording_service as trs
from app.services.teams_recording_service import (
    extract_meeting_date,
    extract_meeting_name,
    parse_vtt_to_plain_text,
    process_new_recording,
    run_meeting_intelligence,
)


# ── VTT parser ───────────────────────────────────────────────────────────────


def test_vtt_parsing_preserves_speakers() -> None:
    vtt = (
        "WEBVTT\n\n1\n00:00:00.000 --> 00:00:05.000\n"
        "<v Yusuf>Good morning everyone.\n\n"
        "2\n00:00:05.000 --> 00:00:09.000\n"
        "<v Rhys>Pulling up the book now.\n"
    )
    result = parse_vtt_to_plain_text(vtt)
    assert "Yusuf: Good morning everyone." in result
    assert "Rhys: Pulling up the book now." in result


def test_vtt_parser_ignores_timecodes_and_cues() -> None:
    vtt = (
        "WEBVTT\n\n1\n00:00:00.000 --> 00:00:05.000\n"
        "Welcome to the call.\n"
    )
    result = parse_vtt_to_plain_text(vtt)
    assert "00:00" not in result
    assert "WEBVTT" not in result
    assert "Welcome to the call." in result


# ── Filename parsing ─────────────────────────────────────────────────────────


def test_extract_meeting_name_strips_date_and_extension() -> None:
    assert extract_meeting_name("Risk Review_2026-05-14.mp4") == "Risk Review"
    assert extract_meeting_name("Daily Standup-2026-05-14.vtt") == "Daily Standup"


def test_extract_meeting_date_parses_iso() -> None:
    assert extract_meeting_date("Risk Review_2026-05-14.mp4") == "2026-05-14"
    assert extract_meeting_date("Risk Review_20260514.mp4") == "2026-05-14"


# ── Recording dispatch ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recording_watcher_ignores_non_meeting_files(test_db) -> None:
    """Files outside the .mp4 / .vtt set are skipped."""
    non_meeting = {"name": "report.docx", "id": "XYZ"}
    result = await process_new_recording(non_meeting, "token", test_db)
    assert result is None


@pytest.mark.asyncio
async def test_meeting_summary_saved_to_onedrive(test_db) -> None:
    """A .mp4 with a companion .vtt produces transcript + summary archives."""
    file_info = {"name": "Risk Review_2026-05-14.mp4", "id": "FILE-1"}

    fake_summary = {
        "summary": "Reviewed UST positioning. Decision to trim 10Y duration.",
        "decisions": ["Trim 10Y duration by 15% before market close"],
        "action_items": [
            {"task": "Reconcile Broadridge positions", "owner": "Rhys", "due_date": None}
        ],
        "key_quotes": ["Yusuf: we need to trim before close"],
    }

    with patch.object(
        trs, "find_companion_vtt", new_callable=AsyncMock, return_value=(
            "WEBVTT\n\n1\n00:00:00.000 --> 00:00:05.000\n<v Yusuf>Trim by close."
        ),
    ), patch.object(
        trs, "run_meeting_intelligence", new_callable=AsyncMock, return_value=fake_summary,
    ), patch(
        "app.services.teams_recording_service.OneDriveService.upload_file",
        new_callable=AsyncMock,
        return_value={"id": "uploaded"},
    ) as mock_upload:
        result = await process_new_recording(file_info, "token", test_db)

    assert result == fake_summary
    upload_paths = [call.args[0] for call in mock_upload.await_args_list]
    assert any("ARGO/Meetings/Summaries" in p for p in upload_paths)
    assert any("ARGO/Meetings/Transcripts" in p for p in upload_paths)


@pytest.mark.asyncio
async def test_action_items_extracted(test_db) -> None:
    """A transcript with a clear directive produces an action item with owner+task."""
    transcript = (
        "Yusuf: Rhys please reconcile the Broadridge positions by Friday.\n"
        "Rhys: Will do."
    )
    fake_json = {
        "summary": "Reconciliation request.",
        "decisions": [],
        "action_items": [
            {"task": "Reconcile the Broadridge positions by Friday", "owner": "Rhys"}
        ],
        "key_quotes": [],
    }
    with patch(
        "app.core.claude_client.ClaudeClient.complete_json",
        new_callable=AsyncMock,
        return_value=fake_json,
    ):
        summary = await run_meeting_intelligence(
            transcript_text=transcript,
            meeting_title="Test Meeting",
            meeting_date="2026-05-14",
            participants=["Yusuf", "Rhys"],
        )

    items = summary["action_items"]
    assert any("Rhys" in (item.get("owner") or "") for item in items)
    assert any("Broadridge" in (item.get("task") or "") for item in items)


@pytest.mark.asyncio
async def test_whisper_fallback_when_no_vtt(test_db) -> None:
    """No companion .vtt → service downloads the .mp4 and calls Whisper."""
    file_info = {"name": "Standup_2026-05-14.mp4", "id": "FILE-MP4"}

    fake_summary = {
        "summary": "Sprint check-in.",
        "decisions": [],
        "action_items": [],
        "key_quotes": [],
    }

    with patch.object(
        trs, "find_companion_vtt", new_callable=AsyncMock, return_value=None,
    ), patch.object(
        trs, "download_recording", new_callable=AsyncMock, return_value=b"FAKE_AUDIO",
    ) as mock_download, patch.object(
        trs, "transcribe_with_whisper", new_callable=AsyncMock, return_value="Standup transcript text.",
    ) as mock_whisper, patch.object(
        trs, "run_meeting_intelligence", new_callable=AsyncMock, return_value=fake_summary,
    ), patch(
        "app.services.teams_recording_service.OneDriveService.upload_file",
        new_callable=AsyncMock,
        return_value={"id": "x"},
    ):
        result = await process_new_recording(file_info, "token", test_db)

    assert result == fake_summary
    mock_whisper.assert_awaited_once()
    mock_download.assert_awaited_once()


@pytest.mark.asyncio
async def test_meeting_persisted_to_db(test_db) -> None:
    """After processing, a Meeting row + action items exist in the DB."""
    from sqlalchemy import select

    from app.models.meeting import Meeting, MeetingActionItem

    file_info = {"name": "All Hands_2026-05-14.mp4", "id": "FILE-AH"}
    fake_summary = {
        "summary": "All-hands recap.",
        "decisions": ["Adopt new compliance workflow"],
        "action_items": [{"task": "Draft new SOP", "owner": "Rayhan"}],
        "key_quotes": [],
    }

    with patch.object(
        trs, "find_companion_vtt", new_callable=AsyncMock,
        return_value="WEBVTT\n\n1\n00:00:00.000 --> 00:00:05.000\n<v Yusuf>Welcome.",
    ), patch.object(
        trs, "run_meeting_intelligence", new_callable=AsyncMock, return_value=fake_summary,
    ), patch(
        "app.services.teams_recording_service.OneDriveService.upload_file",
        new_callable=AsyncMock, return_value={"id": "x"},
    ):
        await process_new_recording(file_info, "token", test_db)

    meetings = (await test_db.execute(select(Meeting))).scalars().all()
    assert len(meetings) == 1
    assert meetings[0].title == "All Hands"
    items = (await test_db.execute(select(MeetingActionItem))).scalars().all()
    assert any("Rayhan" in (i.owner_name or "") for i in items)
