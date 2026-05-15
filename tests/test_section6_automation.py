"""Section 6 automation wiring tests (scheduler + service jobs)."""
from __future__ import annotations

import pytest
from contextlib import asynccontextmanager


def test_section6_jobs_registered() -> None:
    from app.core.scheduler import (
        get_scheduler_status,
        register_research_ingestion_jobs,
    )

    register_research_ingestion_jobs()
    status = get_scheduler_status()
    ids = [j["id"] for j in status["jobs"]]
    assert "research_rss_ingestion" in ids
    assert "research_news_ingestion" in ids


@pytest.mark.asyncio
async def test_scheduler_job_runs_with_stubbed_ingestion(monkeypatch) -> None:
    from app.modules.research_lake import scheduler_job

    async def fake_ingest(_db):
        return 3

    @asynccontextmanager
    async def fake_db_session():
        yield object()

    monkeypatch.setattr(scheduler_job, "ingest_rss_feeds", fake_ingest)
    monkeypatch.setattr(scheduler_job, "get_db_session", fake_db_session)
    inserted = await scheduler_job.run_research_rss_ingestion()
    assert inserted == 3
