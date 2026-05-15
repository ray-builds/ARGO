"""Section 6 scheduled ingestion jobs."""
from __future__ import annotations

from loguru import logger

from app.core.database import get_db_session
from app.services.research_ingestion_service import ingest_financial_news, ingest_rss_feeds


async def run_research_rss_ingestion() -> int:
    """Scheduled job: ingest RSS feeds into Research Lake."""
    async with get_db_session() as db:
        inserted = await ingest_rss_feeds(db)
    logger.info("Section 6 RSS ingestion inserted {} new records", inserted)
    return inserted


async def run_research_news_ingestion() -> int:
    """Scheduled job: ingest NewsAPI financial headlines into Research Lake."""
    async with get_db_session() as db:
        inserted = await ingest_financial_news(db)
    logger.info("Section 6 news ingestion inserted {} new records", inserted)
    return inserted

