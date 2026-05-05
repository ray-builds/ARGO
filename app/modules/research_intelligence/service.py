"""Research Intelligence service — supplier tracking, AI summarisation, and weekly digest generation."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from typing import Any, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, update

from app.core.claude_client import get_claude_client
from app.models.research import ResearchItem
from app.modules.research_intelligence.prompts import (
    RESEARCH_SUMMARY_PROMPT,
    DIGEST_SYNTHESIS_PROMPT,
)
from app.schemas.research import (
    ResearchIngestRequest,
    ResearchListItem,
    ResearchDetailResponse,
    SupplierStats,
    DigestItem,
    DigestResponse,
    ConvictionLevel,
)


class ResearchIntelligenceService:
    """Service for ARP Global Capital Research Intelligence.

    Manages the research pipeline: ingesting notes/podcasts/calls/reports from
    external suppliers, running Claude Haiku summarisation and conviction scoring,
    tracking supplier quality over time, and generating weekly research digests.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialise service with DB session.

        Args:
            db: Async SQLAlchemy session.
        """
        self._db = db
        self._claude = get_claude_client()

    async def ingest_research(
        self, data: ResearchIngestRequest, submitted_by: str
    ) -> ResearchDetailResponse:
        """Ingest research content and run Claude AI analysis.

        Creates a ResearchItem record and runs Haiku summarisation to extract
        the thesis, key data points, conviction level, and topics.

        Args:
            data: ResearchIngestRequest with content and metadata.
            submitted_by: Email of the user submitting the research.

        Returns:
            ResearchDetailResponse with AI-generated summary fields populated.
        """
        item = ResearchItem(
            title=data.title,
            supplier_name=data.supplier_name,
            supplier_email=data.supplier_email,
            source_type=data.source_type.value,
            asset_class=data.asset_class,
            published_date=data.published_date,
            text_content=data.text_content,
            topics=json.dumps(data.topics),
            submitted_by_email=submitted_by,
        )
        self._db.add(item)
        await self._db.flush()

        if data.text_content:
            await self.summarize_research(item)

        logger.info(f"Research ingested: {item.id} — {item.title} from {item.supplier_name}")
        return ResearchDetailResponse.model_validate(item)

    async def summarize_research(self, item: ResearchItem) -> None:
        """Run Claude Haiku analysis on a research item.

        Extracts thesis summary, key data points, conviction level, and topics.
        Updates the ResearchItem record in-place.

        Args:
            item: The ResearchItem ORM object to analyse.
        """
        if not item.text_content:
            return

        context = (
            f"Title: {item.title}\n"
            f"Supplier: {item.supplier_name}\n"
            f"Asset Class: {item.asset_class or 'Not specified'}\n\n"
            f"CONTENT:\n{item.text_content[:6000]}"
        )

        try:
            result = await self._claude.complete_json(
                prompt=context,
                system=RESEARCH_SUMMARY_PROMPT,
                use_sonnet=False,
                max_tokens=600,
            )
            item.thesis_summary = result.get("thesis_summary", "")
            item.key_data_points = json.dumps(result.get("key_data_points", []))
            conviction_raw = result.get("conviction_level", "MEDIUM")
            item.conviction_level = conviction_raw if conviction_raw in ("HIGH", "MEDIUM", "LOW") else "MEDIUM"
            topics_raw = result.get("topics", [])
            item.topics = json.dumps(topics_raw)
            logger.debug(f"Research {item.id} summarised: conviction={item.conviction_level}")
        except Exception as exc:
            logger.exception(f"Research summarisation failed for {item.id}: {exc}")

    async def rate_research(self, item_id: str, rating: int) -> None:
        """Update the quality rating for a research item.

        Args:
            item_id: UUID of the research item.
            rating: Quality rating from 1 to 5.
        """
        await self._db.execute(
            update(ResearchItem)
            .where(ResearchItem.id == item_id)
            .values(quality_rating=rating)
        )
        logger.info(f"Research {item_id} rated {rating}/5")

    async def list_research(
        self,
        limit: int = 30,
        offset: int = 0,
        supplier: str | None = None,
    ) -> list[ResearchListItem]:
        """Return paginated list of research items with optional supplier filter.

        Args:
            limit: Maximum records to return.
            offset: Pagination offset.
            supplier: Optional supplier name to filter by.

        Returns:
            List of ResearchListItem objects.
        """
        stmt = (
            select(ResearchItem)
            .order_by(desc(ResearchItem.created_at))
            .limit(limit)
            .offset(offset)
        )
        if supplier:
            stmt = stmt.where(ResearchItem.supplier_name.ilike(f"%{supplier}%"))

        result = await self._db.execute(stmt)
        items = result.scalars().all()
        return [ResearchListItem.model_validate(i) for i in items]

    async def get_research_item(self, item_id: str) -> ResearchDetailResponse:
        """Return a single research item by ID.

        Args:
            item_id: UUID of the research item.

        Returns:
            ResearchDetailResponse.

        Raises:
            HTTPException: 404 if item not found.
        """
        result = await self._db.execute(
            select(ResearchItem).where(ResearchItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Research item not found")
        return ResearchDetailResponse.model_validate(item)

    async def get_supplier_stats(self) -> list[SupplierStats]:
        """Return aggregated quality statistics per research supplier.

        Computes total items, average rating, and high-conviction count per supplier.

        Returns:
            List of SupplierStats objects sorted by total items descending.
        """
        result = await self._db.execute(
            select(
                ResearchItem.supplier_name,
                func.count(ResearchItem.id).label("total"),
                func.avg(ResearchItem.quality_rating).label("avg_rating"),
            ).group_by(ResearchItem.supplier_name)
            .order_by(desc("total"))
        )
        rows = result.all()

        stats: list[SupplierStats] = []
        for row in rows:
            # Count high conviction separately
            hc_result = await self._db.execute(
                select(func.count(ResearchItem.id)).where(
                    ResearchItem.supplier_name == row.supplier_name,
                    ResearchItem.conviction_level == "HIGH",
                )
            )
            hc_count = hc_result.scalar() or 0
            stats.append(
                SupplierStats(
                    supplier_name=row.supplier_name,
                    total_items=row.total,
                    avg_rating=round(float(row.avg_rating), 2) if row.avg_rating else None,
                    high_conviction_count=hc_count,
                )
            )
        return stats

    async def build_weekly_digest(self, period_days: int = 7) -> DigestResponse:
        """Build a research digest covering the past N days.

        Retrieves recent high-conviction and highly-rated research items
        and returns them ranked for the team's review.

        Args:
            period_days: Number of days to look back.

        Returns:
            DigestResponse with ranked top research items.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)

        result = await self._db.execute(
            select(ResearchItem)
            .where(ResearchItem.created_at >= cutoff)
            .order_by(
                ResearchItem.conviction_level.desc(),
                desc(ResearchItem.quality_rating),
                desc(ResearchItem.created_at),
            )
            .limit(20)
        )
        items = result.scalars().all()

        total = len(items)
        top_items = [
            DigestItem(
                research_id=i.id,
                title=i.title,
                supplier_name=i.supplier_name,
                thesis_summary=i.thesis_summary,
                quality_rating=i.quality_rating,
            )
            for i in items[:10]
        ]

        return DigestResponse(
            period_days=period_days,
            total_items=total,
            top_items=top_items,
        )
