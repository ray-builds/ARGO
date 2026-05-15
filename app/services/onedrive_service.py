"""OneDrive archival service — every ARGO artefact lands in the user's drive.

Folder layout (under ``/ARGO``)::

    Emails/{YYYY}/{MM}/{email_id}_{subject_slug}.json
    MorningBriefings/{YYYY-MM-DD}_morning_brief.md
    Meetings/Transcripts/{YYYY-MM-DD}_{slug}.txt
    Meetings/Summaries/{YYYY-MM-DD}_{slug}_summary.json
    Research/{BrokerNotes|InternalMemos|EconomicReleases|NewsClips}/...
    WeeklyReports/{YYYY-WNN}_weekly_report.md
    WhatsApp/Archive/{YYYY-MM-DD}_{group_name}.json
    WhatsApp/WeeklyDigests/{YYYY-WNN}_whatsapp_digest.md
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

import httpx
from loguru import logger

GRAPH_DRIVE_BASE = "https://graph.microsoft.com/v1.0/me/drive"


def slugify(value: str, max_length: int = 60) -> str:
    """Return a filesystem-safe slug derived from ``value``."""
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value[:max_length] or "untitled"


class OneDriveService:
    """Async wrapper around the Microsoft Graph OneDrive endpoints."""

    def __init__(self, access_token: str) -> None:
        self.token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}

    # ── Folder management ───────────────────────────────────────────────────

    async def ensure_folder(self, path: str) -> str:
        """Create the folder hierarchy if missing; return the leaf folder ID.

        ``path`` is OneDrive-relative, e.g. ``"ARGO/Emails/2026/05"``.
        """
        parts = [p for p in path.strip("/").split("/") if p]
        parent_id = "root"

        async with httpx.AsyncClient(timeout=30.0) as client:
            for part in parts:
                url = f"{GRAPH_DRIVE_BASE}/items/{parent_id}/children"
                response = await client.get(
                    url,
                    headers=self.headers,
                    params={"$filter": f"name eq '{part}'"},
                )
                response.raise_for_status()
                items = [
                    item
                    for item in response.json().get("value", [])
                    if item.get("folder") is not None
                ]
                if items:
                    parent_id = items[0]["id"]
                    continue

                # Create folder
                payload = {
                    "name": part,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "rename",
                }
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                parent_id = response.json()["id"]

        return parent_id

    # ── Upload / download ───────────────────────────────────────────────────

    async def upload_file(
        self,
        path: str,
        content: str | bytes,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        """Upload ``content`` to ``path``, creating parent folders if needed."""
        pp = PurePosixPath(path)
        folder_path = str(pp.parent)
        filename = pp.name
        await self.ensure_folder(folder_path)

        if isinstance(content, str):
            content = content.encode("utf-8")

        # Use the /root:/{full-path}:/content endpoint — simpler than item-id paths.
        url = f"{GRAPH_DRIVE_BASE}/root:/{path.strip('/')}:/content"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.put(
                url,
                headers={**self.headers, "Content-Type": content_type},
                content=content,
            )
            response.raise_for_status()
            return response.json()

    async def get_file_content(self, path: str) -> bytes:
        """Return the raw bytes of the file at ``path``."""
        url = f"{GRAPH_DRIVE_BASE}/root:/{path.strip('/')}:/content"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.content

    # ── Archival helpers ────────────────────────────────────────────────────

    async def archive_email(self, email_data: dict[str, Any]) -> dict[str, Any]:
        """Archive a processed email to ``ARGO/Emails/{YYYY}/{MM}/...``."""
        ts_raw = email_data.get("timestamp") or email_data.get("received_at")
        if isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                ts = datetime.utcnow()
        subject_slug = slugify(email_data.get("subject", ""), max_length=40)
        email_id = email_data.get("id") or "unknown"
        path = (
            f"ARGO/Emails/{ts.year}/{ts.month:02d}/"
            f"{email_id}_{subject_slug}.json"
        )
        return await self.upload_file(
            path, json.dumps(email_data, indent=2, default=str)
        )

    async def archive_morning_brief(self, brief_text: str, date: str) -> dict[str, Any]:
        """Archive a morning briefing markdown file under ``ARGO/MorningBriefings``."""
        path = f"ARGO/MorningBriefings/{date}_morning_brief.md"
        return await self.upload_file(path, brief_text, "text/markdown")

    async def archive_meeting_transcript(
        self, transcript_text: str, date: str, title: str
    ) -> dict[str, Any]:
        path = f"ARGO/Meetings/Transcripts/{date}_{slugify(title)}.txt"
        return await self.upload_file(path, transcript_text, "text/plain")

    async def archive_meeting_summary(
        self, summary: dict[str, Any], date: str, title: str
    ) -> dict[str, Any]:
        path = (
            f"ARGO/Meetings/Summaries/{date}_{slugify(title)}_summary.json"
        )
        return await self.upload_file(path, json.dumps(summary, indent=2, default=str))

    async def archive_weekly_report(self, report_md: str, year_week: str) -> dict[str, Any]:
        path = f"ARGO/WeeklyReports/{year_week}_weekly_report.md"
        return await self.upload_file(path, report_md, "text/markdown")

    async def archive_research(
        self, category: str, filename: str, content: str | bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        category_clean = category.strip("/").replace("..", "")
        path = f"ARGO/Research/{category_clean}/{filename}"
        return await self.upload_file(path, content, content_type)


def get_onedrive_service(access_token: str) -> OneDriveService:
    return OneDriveService(access_token=access_token)


async def safe_archive(coro) -> None:
    """Await an archival coroutine, swallowing/logging any error.

    Auto-archive operations must never break the main pipeline.
    """
    try:
        await coro
    except Exception as exc:  # noqa: BLE001
        logger.warning("OneDrive archive skipped: {}", exc)
