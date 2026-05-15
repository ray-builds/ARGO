"""Section 2 — OneDrive auto-archiving service tests.

Graph API responses are stubbed so tests run without live credentials.
We exercise the request URLs / payloads the service issues, plus the
folder/path conventions defined in the upgrade plan.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.onedrive_service import OneDriveService, slugify


# ── In-memory Graph stand-in ──────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, payload: Any = None, *, content: bytes = b"", status: int = 200):
        self._payload = payload if payload is not None else {}
        self.content = content
        self.status_code = status

    def raise_for_status(self) -> None:  # pragma: no cover - trivial
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._payload


class _FakeDrive:
    """Minimal stand-in for the OneDrive REST surface used by the service."""

    def __init__(self) -> None:
        # folder_id -> {"name": str, "children": {name: id}, "parent": id|None}
        self.folders: dict[str, dict[str, Any]] = {
            "root": {"name": "root", "children": {}, "parent": None}
        }
        self.files: dict[str, dict[str, Any]] = {}  # path -> {"content": bytes}
        self._counter = 0

    def _new_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter}"

    # Used by ensure_folder GET /items/{parent_id}/children?$filter=name eq '...'
    async def list_children(self, parent_id: str, name: str) -> _FakeResponse:
        parent = self.folders.get(parent_id)
        if parent is None:
            return _FakeResponse({"value": []})
        if name in parent["children"]:
            child_id = parent["children"][name]
            return _FakeResponse({"value": [{"id": child_id, "name": name, "folder": {}}]})
        return _FakeResponse({"value": []})

    async def create_folder(self, parent_id: str, name: str) -> _FakeResponse:
        new_id = self._new_id("folder")
        self.folders[new_id] = {"name": name, "children": {}, "parent": parent_id}
        self.folders[parent_id]["children"][name] = new_id
        return _FakeResponse({"id": new_id, "name": name, "folder": {}})

    async def put_file(self, path: str, content: bytes) -> _FakeResponse:
        self.files[path] = {"content": content}
        return _FakeResponse({"id": self._new_id("file"), "name": path.split("/")[-1]})

    async def get_file(self, path: str) -> _FakeResponse:
        entry = self.files.get(path)
        if entry is None:
            return _FakeResponse(content=b"", status=404)
        return _FakeResponse(content=entry["content"])


@pytest.fixture
def fake_drive() -> _FakeDrive:
    return _FakeDrive()


@pytest.fixture
def patched_httpx(fake_drive: _FakeDrive):
    """Patch httpx.AsyncClient so OneDriveService talks to the fake drive."""

    async def _get(url: str, headers=None, params=None, **_):
        if "/items/" in url and url.endswith("/children"):
            parent_id = url.split("/items/")[1].split("/children")[0]
            filt = (params or {}).get("$filter", "")
            # Parse "name eq 'X'"
            name = ""
            if "name eq '" in filt:
                name = filt.split("name eq '", 1)[1].split("'", 1)[0]
            return await fake_drive.list_children(parent_id, name)
        if "/root:/" in url and url.endswith(":/content"):
            path = url.split("/root:/", 1)[1].rsplit(":/content", 1)[0]
            return await fake_drive.get_file(path)
        return _FakeResponse({"value": []})

    async def _post(url: str, headers=None, json=None, **_):
        if "/items/" in url and url.endswith("/children"):
            parent_id = url.split("/items/")[1].split("/children")[0]
            name = (json or {}).get("name", "untitled")
            return await fake_drive.create_folder(parent_id, name)
        return _FakeResponse({})

    async def _put(url: str, headers=None, content=None, **_):
        if "/root:/" in url and url.endswith(":/content"):
            path = url.split("/root:/", 1)[1].rsplit(":/content", 1)[0]
            return await fake_drive.put_file(path, content or b"")
        return _FakeResponse({})

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        get = staticmethod(_get)
        post = staticmethod(_post)
        put = staticmethod(_put)

    with patch("app.services.onedrive_service.httpx.AsyncClient", _FakeClient):
        yield


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_slugify_handles_unicode_and_punctuation() -> None:
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("") == "untitled"
    assert slugify("UST 10Y > 4.5%") == "ust-10y-4-5"


@pytest.mark.asyncio
async def test_ensure_folder_creates_hierarchy(fake_drive, patched_httpx) -> None:
    """Nested folders that don't exist are created top-down; final id is returned."""
    svc = OneDriveService("test-token")
    folder_id = await svc.ensure_folder("ARGO/Test/Nested")
    assert folder_id is not None
    # ARGO under root, Test under ARGO, Nested under Test
    argo_id = fake_drive.folders["root"]["children"]["ARGO"]
    test_id = fake_drive.folders[argo_id]["children"]["Test"]
    nested_id = fake_drive.folders[test_id]["children"]["Nested"]
    assert folder_id == nested_id


@pytest.mark.asyncio
async def test_ensure_folder_idempotent(fake_drive, patched_httpx) -> None:
    """Calling ensure_folder twice does not create duplicate folders."""
    svc = OneDriveService("test-token")
    first = await svc.ensure_folder("ARGO/Test/Nested")
    second = await svc.ensure_folder("ARGO/Test/Nested")
    assert first == second
    # Only one ARGO child exists.
    assert list(fake_drive.folders["root"]["children"].keys()) == ["ARGO"]


@pytest.mark.asyncio
async def test_upload_and_retrieve_file(fake_drive, patched_httpx) -> None:
    """Uploaded file content matches what was uploaded."""
    svc = OneDriveService("test-token")
    content = '{"test": "value", "timestamp": "2026-05-14"}'
    await svc.upload_file("ARGO/Test/test_upload.json", content)
    fetched = await svc.get_file_content("ARGO/Test/test_upload.json")
    assert json.loads(fetched) == json.loads(content)


@pytest.mark.asyncio
async def test_email_archive_path_correct(fake_drive, patched_httpx) -> None:
    """Archived email lands in ARGO/Emails/{YYYY}/{MM}/{id}_{slug}.json."""
    svc = OneDriveService("test-token")
    email = {
        "id": "AAA",
        "timestamp": "2026-05-14T08:00:00+00:00",
        "subject": "Test Email",
    }
    await svc.archive_email(email)
    expected_path = "ARGO/Emails/2026/05/AAA_test-email.json"
    assert expected_path in fake_drive.files
    stored = json.loads(fake_drive.files[expected_path]["content"].decode())
    assert stored["id"] == "AAA"


@pytest.mark.asyncio
async def test_morning_brief_archived(fake_drive, patched_httpx) -> None:
    """Morning brief markdown is written under ARGO/MorningBriefings."""
    svc = OneDriveService("test-token")
    await svc.archive_morning_brief("# Test Brief", "2026-05-14")
    path = "ARGO/MorningBriefings/2026-05-14_morning_brief.md"
    assert path in fake_drive.files
    assert fake_drive.files[path]["content"] == b"# Test Brief"


@pytest.mark.asyncio
async def test_archive_meeting_paths(fake_drive, patched_httpx) -> None:
    """Meeting transcripts and summaries follow the documented layout."""
    svc = OneDriveService("test-token")
    await svc.archive_meeting_transcript("hello", "2026-05-14", "Risk Review")
    await svc.archive_meeting_summary({"k": "v"}, "2026-05-14", "Risk Review")
    assert "ARGO/Meetings/Transcripts/2026-05-14_risk-review.txt" in fake_drive.files
    assert (
        "ARGO/Meetings/Summaries/2026-05-14_risk-review_summary.json"
        in fake_drive.files
    )


@pytest.mark.asyncio
async def test_safe_archive_swallows_errors() -> None:
    """safe_archive must never propagate exceptions to the caller."""
    from app.services.onedrive_service import safe_archive

    async def _boom() -> None:
        raise RuntimeError("graph 503")

    await safe_archive(_boom())  # Must not raise.
