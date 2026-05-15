"""Section 6 Research Lake ingestion + contradiction utilities."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio_research_conflict import PortfolioResearchConflict
from app.models.research import ResearchItem
from app.models.research_source import ResearchSourceRecord

BROKER_DOMAINS = [
    "gs.com",
    "jpmorgan.com",
    "ubs.com",
    "ms.com",
    "citi.com",
    "barclays.com",
    "deutsche-bank.com",
    "morganstanley.com",
    "bofa.com",
    "nomura.com",
    "macquarie.com",
    "hsbc.com",
]

RSS_FEEDS = {
    "BIS Research": "https://www.bis.org/rss/index.htm",
    "IMF Blog": "https://www.imf.org/en/Blogs/rss",
    "Fed Research": "https://www.federalreserve.gov/feeds/research.xml",
    "ECB Research": "https://www.ecb.europa.eu/pub/research/rss.html",
    "NBER Working Papers": "https://www.nber.org/rss/new_working_papers.rss",
}


async def ingest_article(article: dict[str, Any], db: AsyncSession) -> bool:
    """Store one article URL once; return True when inserted, False if duplicate."""
    source_url = str(article.get("url") or "").strip()
    if not source_url:
        return False

    existing = await db.execute(
        select(ResearchSourceRecord).where(ResearchSourceRecord.source_url == source_url)
    )
    if existing.scalar_one_or_none():
        return False

    record = ResearchSourceRecord(
        source_url=source_url,
        title=article.get("title"),
        source_name=article.get("source"),
        content_excerpt=(article.get("content") or "")[:4000],
    )
    db.add(record)
    await db.flush()

    # Lightweight research item creation for downstream Section 6 flows.
    item = ResearchItem(
        title=article.get("title") or source_url,
        supplier_name=article.get("source"),
        source_type="REPORT",
        asset_class=None,
        thesis_summary=(article.get("content") or article.get("description") or "")[:1200],
        key_data_points="[]",
        conviction_level="MEDIUM",
        ingested_by_email="auto-ingestion@argo.local",
        topics="[]",
    )
    db.add(item)
    await db.commit()
    return True


async def count_ingested_by_url(source_url: str, db: AsyncSession) -> int:
    """Return count of source records for one URL (used by tests)."""
    result = await db.execute(
        select(func.count()).select_from(ResearchSourceRecord).where(
            ResearchSourceRecord.source_url == source_url
        )
    )
    return int(result.scalar_one() or 0)


async def ingest_rss_feeds(db: AsyncSession, max_entries_per_feed: int = 10) -> int:
    """Ingest latest entries from configured RSS feeds with URL de-duplication."""
    import feedparser

    inserted = 0
    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        for entry in (feed.entries or [])[:max_entries_per_feed]:
            article = {
                "source": source,
                "title": getattr(entry, "title", ""),
                "url": getattr(entry, "link", ""),
                "content": getattr(entry, "summary", ""),
                "date": getattr(entry, "published", datetime.now(UTC).isoformat()),
            }
            if await ingest_article(article, db):
                inserted += 1
    return inserted


async def ingest_financial_news(db: AsyncSession) -> int:
    """Ingest mandate-relevant financial news from NewsAPI with de-duplication."""
    from newsapi import NewsApiClient

    news_key = os.getenv("NEWSAPI_KEY", "")
    if not news_key:
        return 0

    keywords = [
        "macro hedge fund",
        "Federal Reserve",
        "ECB",
        "PBOC",
        "emerging markets",
        "FX volatility",
        "rates",
        "inflation",
        "geopolitical risk",
        "commodity prices",
    ]

    newsapi = NewsApiClient(api_key=news_key)
    inserted = 0
    for keyword in keywords:
        articles = newsapi.get_everything(
            q=keyword,
            language="en",
            sort_by="publishedAt",
            from_param=(datetime.now(UTC) - timedelta(hours=24)).isoformat(),
            page_size=5,
        )
        for article in articles.get("articles", []):
            payload = {
                "source": (article.get("source") or {}).get("name", "NewsAPI"),
                "title": article.get("title"),
                "url": article.get("url"),
                "content": article.get("content") or article.get("description") or "",
                "date": article.get("publishedAt"),
            }
            if await ingest_article(payload, db):
                inserted += 1
    return inserted


async def get_instrument_data(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Return lightweight Yahoo Finance fields for supplied tickers."""
    import yfinance as yf

    data: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        t = yf.Ticker(ticker)
        info = getattr(t, "info", {}) or {}
        hist = t.history(period="5d")
        closes = {}
        if hist is not None and not getattr(hist, "empty", True):
            close_series = hist.get("Close")
            if close_series is not None and hasattr(close_series, "to_dict"):
                closes = close_series.to_dict()
        data[ticker] = {
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "day_change_pct": info.get("regularMarketChangePercent"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "last_5d": closes,
        }
    return data


async def get_fred_series(
    series_ids: list[str],
    http_get: Callable[..., Any] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Fetch latest observations from FRED API for each series id."""
    getter = http_get or httpx.get
    fred_key = os.getenv("FRED_API_KEY", "")
    results: dict[str, list[dict[str, str]]] = {}

    for series_id in series_ids:
        response = getter(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": fred_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 10,
            },
            timeout=30.0,
        )
        payload = response.json() if hasattr(response, "json") else {}
        obs = payload.get("observations", [])
        results[series_id] = [{"date": o["date"], "value": o["value"]} for o in obs]
    return results


async def store_conflicts(conflicts: list[dict[str, Any]], db: AsyncSession | None = None) -> None:
    """Persist conflicts when DB session is provided."""
    if db is None:
        return
    for conflict in conflicts:
        position = conflict.get("position", {}) or {}
        research = conflict.get("research", {}) or {}
        row = PortfolioResearchConflict(
            research_instrument=(research.get("instruments_mentioned") or [None])[0],
            position_instrument=str(position.get("instrument") or "UNKNOWN"),
            conflict_type=str(conflict.get("conflict_type") or "UNKNOWN"),
            severity=str(conflict.get("severity") or "MED"),
            conflict_json=json.dumps(conflict, default=str),
        )
        db.add(row)
    await db.commit()


async def send_teams_alert(message: str) -> None:
    """Teams alert hook placeholder for Section 6."""
    _ = message


def format_conflict_alert(conflicts: list[dict[str, Any]]) -> str:
    """Build a concise Teams alert from conflicts."""
    lines = ["Section 6 Conflict Alert"]
    for c in conflicts:
        pos = c.get("position", {})
        lines.append(
            f"- {pos.get('instrument', 'UNKNOWN')} | {c.get('conflict_type')} | {c.get('severity')}"
        )
    return "\n".join(lines)


async def check_research_against_portfolio(
    research_summary: dict[str, Any],
    portfolio: dict[str, Any],
    db: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """Detect directional contradictions between research and active positions."""
    conflicts: list[dict[str, Any]] = []
    mentioned = set(research_summary.get("instruments_mentioned") or [])
    macro_themes = set(research_summary.get("macro_themes") or [])
    stance = (
        (research_summary.get("positioning_implication") or {}).get("stance")
        or "NEUTRAL"
    )

    for position in portfolio.get("positions", []):
        instrument = position.get("instrument")
        related_themes = set(position.get("related_themes", []))
        relevant = instrument in mentioned or bool(related_themes & macro_themes)
        if not relevant:
            continue

        direction = position.get("direction")
        contradiction = (direction == "LONG" and stance == "BEARISH") or (
            direction == "SHORT" and stance == "BULLISH"
        )
        if not contradiction:
            continue

        notional = abs(float(position.get("notional_usd", 0) or 0))
        conflicts.append(
            {
                "position": position,
                "research": research_summary,
                "conflict_type": "DIRECTIONAL_CONTRADICTION",
                "severity": "HIGH" if notional > 5_000_000 else "MED",
                "action": "FLAG_TO_PM",
            }
        )

    if conflicts:
        await store_conflicts(conflicts, db=db)
        if any(c["severity"] == "HIGH" for c in conflicts):
            await send_teams_alert(format_conflict_alert(conflicts))

    return conflicts

