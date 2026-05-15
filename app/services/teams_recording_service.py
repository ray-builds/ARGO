"""Teams meeting recording auto-transcription pipeline.

Watches the user's OneDrive ``/Recordings`` folder via Graph change
notifications. When a new ``.mp4`` (recording) or ``.vtt`` (transcript) lands
we:

1. Prefer the companion ``.vtt`` transcript (free, instant).
2. Otherwise download the ``.mp4`` and transcribe with OpenAI Whisper.
3. Parse the transcript, run Meeting Intelligence via Claude Sonnet.
4. Archive both transcript + summary to ``/ARGO/Meetings/...``.
5. Persist a ``Meeting`` row with extracted action items.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.claude_client import get_claude_client
from app.models.meeting import Meeting, MeetingActionItem
from app.prompts.adapters import normalize_meeting_intelligence_json
from app.prompts.architecture import MEETING_INTELLIGENCE_PROMPT
from app.services.onedrive_service import OneDriveService, safe_archive, slugify

RECORDINGS_FOLDER_PATH = "Recordings"
RECORDINGS_CLIENT_STATE = "ARGO_RECORDINGS_SECRET"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


# ── Filename parsing ────────────────────────────────────────────────────────


_DATE_PATTERNS = [
    r"(\d{4}-\d{2}-\d{2})",
    r"(\d{4}_\d{2}_\d{2})",
    r"(\d{8})",  # YYYYMMDD
]


def extract_meeting_name(filename: str) -> str:
    """Strip extension + trailing date stamp, return a clean meeting title."""
    base = os.path.splitext(filename or "")[0]
    for pat in _DATE_PATTERNS:
        base = re.sub(r"[\s_-]*" + pat + r"$", "", base)
    base = base.strip(" _-")
    return base or "Untitled Meeting"


def extract_meeting_date(filename: str) -> str:
    """Extract a ``YYYY-MM-DD`` date string from the filename, else today."""
    base = os.path.splitext(filename or "")[0]
    for pat in _DATE_PATTERNS:
        match = re.search(pat, base)
        if match:
            raw = match.group(1)
            if "_" in raw:
                return raw.replace("_", "-")
            if len(raw) == 8 and raw.isdigit():
                return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
            return raw
    return date.today().isoformat()


# ── VTT → plain text ────────────────────────────────────────────────────────


def parse_vtt_to_plain_text(vtt_content: str) -> str:
    """Convert WebVTT into a readable ``Speaker: line`` transcript.

    Recognises Teams ``<v Speaker>`` voice tags. Lines without a tag are
    appended verbatim (after stripping any other inline tags).
    """
    if not vtt_content:
        return ""

    transcript_lines: list[str] = []
    current_speaker = "Unknown"

    for line in vtt_content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("WEBVTT"):
            continue
        if "-->" in stripped:
            continue
        if stripped.isdigit():
            continue
        if stripped.startswith("NOTE"):
            continue

        speaker_match = re.search(r"<v\s+([^>]+)>", stripped)
        if speaker_match:
            current_speaker = speaker_match.group(1).strip()
            text = re.sub(r"<[^>]+>", "", stripped).strip()
            if text:
                transcript_lines.append(f"{current_speaker}: {text}")
            continue

        clean = re.sub(r"<[^>]+>", "", stripped).strip()
        if clean:
            transcript_lines.append(clean)

    return "\n".join(transcript_lines)


# ── Graph helpers ───────────────────────────────────────────────────────────


async def find_companion_vtt(
    file_info: dict[str, Any], access_token: str
) -> Optional[str]:
    """Look for a sibling ``.vtt`` file next to ``file_info`` in /Recordings.

    Returns the VTT body as a string, or ``None`` when no companion exists.
    """
    filename: str = file_info.get("name", "") or ""
    if not filename:
        return None
    stem = os.path.splitext(filename)[0]
    vtt_name = f"{stem}.vtt"
    url = (
        f"{GRAPH_BASE}/me/drive/root:/"
        f"{RECORDINGS_FOLDER_PATH}/{vtt_name}:/content"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return response.text
            return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("find_companion_vtt failed for {}: {}", vtt_name, exc)
        return None


async def download_recording(file_id: str, access_token: str) -> bytes:
    """Download an item by Graph driveItem id and return raw bytes."""
    url = f"{GRAPH_BASE}/me/drive/items/{file_id}/content"
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        return response.content


async def transcribe_with_whisper(audio_bytes: bytes, suffix: str = ".mp4") -> str:
    """Transcribe raw audio bytes via OpenAI Whisper."""
    import openai

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not configured for Whisper transcription")

    client = openai.AsyncOpenAI(api_key=api_key)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as fh:
            response = await client.audio.transcriptions.create(
                model="whisper-1", file=fh, response_format="text"
            )
        return str(response)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Meeting Intelligence ────────────────────────────────────────────────────


async def run_meeting_intelligence(
    transcript_text: str,
    meeting_title: str,
    meeting_date: str,
    participants: list[str],
) -> dict[str, Any]:
    """Run the Meeting Intelligence prompt over a transcript and return JSON.

    The returned dict always contains ``summary``, ``decisions``,
    ``action_items``, ``key_quotes``. Falsy / missing fields are normalised.
    """
    claude = get_claude_client()
    prompt = MEETING_INTELLIGENCE_PROMPT.format(
        meeting_date=meeting_date,
        meeting_title=meeting_title,
        participants=", ".join(participants) if participants else "Unknown",
        duration_minutes=0,
        meeting_type="INTERNAL",
        transcript_text=(transcript_text or "")[:12000],
    )

    try:
        result = await claude.complete_json(
            prompt=prompt,
            system="You are ARGO Meeting Intelligence. Return strict JSON only.",
            use_sonnet=True,
            max_tokens=2000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_meeting_intelligence Claude call failed: {}", exc)
        return {"summary": "", "decisions": [], "action_items": [], "key_quotes": []}

    result = normalize_meeting_intelligence_json(result)

    # Normalise action item shape: ensure each has owner + task keys
    raw_items = result.get("action_items", []) or []
    normalised: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        task = item.get("task") or item.get("description") or ""
        owner = item.get("owner") or item.get("owner_name") or ""
        normalised.append(
            {
                "task": task,
                "description": task,  # keep both keys for back-compat
                "owner": owner,
                "owner_name": owner,
                "due_date": item.get("due_date"),
            }
        )
    result["action_items"] = normalised
    result.setdefault("summary", "")
    result.setdefault("decisions", [])
    result.setdefault("key_quotes", [])
    return result


# ── Top-level pipeline ──────────────────────────────────────────────────────


async def process_new_recording(
    file_info: dict[str, Any],
    access_token: str,
    db: AsyncSession,
) -> Optional[dict[str, Any]]:
    """Detect / transcribe / summarise / archive a Teams recording.

    Returns the structured summary on success, ``None`` when the file is not
    a recording or the .vtt event arrived first (we wait for the .mp4 / VTT
    that ultimately drives processing).
    """
    filename: str = (file_info.get("name") or "").strip()
    if not filename:
        return None

    lower = filename.lower()
    if not (lower.endswith(".mp4") or lower.endswith(".vtt")):
        logger.debug("Ignoring non-recording file: {}", filename)
        return None

    meeting_title = extract_meeting_name(filename)
    meeting_date = extract_meeting_date(filename)

    transcript_text = ""
    transcription_method = "unknown"

    vtt_content = await find_companion_vtt(file_info, access_token)
    if vtt_content:
        transcript_text = parse_vtt_to_plain_text(vtt_content)
        transcription_method = "teams_vtt"
    elif lower.endswith(".mp4"):
        try:
            audio_bytes = await download_recording(file_info.get("id", ""), access_token)
            transcript_text = await transcribe_with_whisper(audio_bytes, suffix=".mp4")
            transcription_method = "whisper"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Whisper fallback failed for {}: {}", filename, exc)
            return None
    else:
        # .vtt event landed before the .mp4 — process the VTT we just received
        try:
            audio_bytes = await download_recording(file_info.get("id", ""), access_token)
            transcript_text = parse_vtt_to_plain_text(audio_bytes.decode("utf-8", "ignore"))
            transcription_method = "teams_vtt"
        except Exception as exc:  # noqa: BLE001
            logger.warning("VTT-only handling failed for {}: {}", filename, exc)
            return None

    if not transcript_text.strip():
        logger.warning("Empty transcript for {} — skipping", filename)
        return None

    participants = await _extract_participants_from_transcript(transcript_text)

    summary = await run_meeting_intelligence(
        transcript_text=transcript_text,
        meeting_title=meeting_title,
        meeting_date=meeting_date,
        participants=participants,
    )

    # Archive both transcript and summary (best-effort).
    onedrive = OneDriveService(access_token)
    slug = slugify(meeting_title)
    await safe_archive(
        onedrive.upload_file(
            f"ARGO/Meetings/Transcripts/{meeting_date}_{slug}.txt",
            transcript_text,
            "text/plain",
        )
    )
    await safe_archive(
        onedrive.upload_file(
            f"ARGO/Meetings/Summaries/{meeting_date}_{slug}_summary.json",
            json.dumps(summary, indent=2, default=str),
            "application/json",
        )
    )

    # Persist to DB
    try:
        await _save_meeting(
            db=db,
            summary=summary,
            meeting_title=meeting_title,
            meeting_date=meeting_date,
            participants=participants,
            transcript_text=transcript_text,
            transcription_method=transcription_method,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Meeting persistence failed for {}: {}", filename, exc)

    return summary


async def _extract_participants_from_transcript(transcript: str) -> list[str]:
    """Scan ``Speaker:`` prefixes to discover participants from the VTT/text."""
    speakers: list[str] = []
    for line in transcript.splitlines():
        match = re.match(r"^([A-Z][A-Za-z .'-]{1,40}):\s", line)
        if match:
            name = match.group(1).strip()
            if name and name not in speakers and name.lower() != "unknown":
                speakers.append(name)
    return speakers


async def _save_meeting(
    db: AsyncSession,
    summary: dict[str, Any],
    meeting_title: str,
    meeting_date: str,
    participants: list[str],
    transcript_text: str,
    transcription_method: str,
) -> Meeting:
    try:
        meeting_date_obj = datetime.fromisoformat(meeting_date).date()
    except ValueError:
        meeting_date_obj = date.today()

    meeting = Meeting(
        title=meeting_title,
        meeting_type="INTERNAL",
        meeting_date=meeting_date_obj,
        attendees=json.dumps(participants),
        uploaded_by_email="auto-pipeline",
        transcript_clean=transcript_text,
        summary=summary.get("summary", ""),
        decisions=json.dumps(summary.get("decisions", [])),
        key_quotes=json.dumps(summary.get("key_quotes", [])),
        transcription_model=transcription_method,
        status="complete",
    )
    db.add(meeting)
    await db.flush()

    for item in summary.get("action_items", []) or []:
        if not isinstance(item, dict):
            continue
        db.add(
            MeetingActionItem(
                meeting_id=meeting.id,
                description=item.get("task") or item.get("description", ""),
                owner_name=item.get("owner") or item.get("owner_name"),
                due_date=None,  # parsing relative due dates is out of scope here
            )
        )
    await db.commit()
    return meeting


# ── Subscription registration ───────────────────────────────────────────────


async def register_recordings_watcher(
    access_token: str, user_email: str
) -> Optional[dict[str, Any]]:
    """Subscribe to /Recordings folder children for the current user."""
    from app.config import get_settings

    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=4230)
    payload = {
        "changeType": "created,updated",
        "notificationUrl": f"{settings.app_base_url}/api/webhooks/onedrive-recordings",
        "resource": f"/me/drive/root:/{RECORDINGS_FOLDER_PATH}:/children",
        "expirationDateTime": expires.isoformat().replace("+00:00", "Z"),
        "clientState": RECORDINGS_CLIENT_STATE,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GRAPH_BASE}/subscriptions",
                json=payload,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "Registered OneDrive Recordings subscription for {}: {}",
                user_email, data.get("id"),
            )
            return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("register_recordings_watcher failed for {}: {}", user_email, exc)
        return None
