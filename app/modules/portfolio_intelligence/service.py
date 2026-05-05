"""Portfolio Intelligence service — position management, scenario analysis, and trade idea generation."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from app.core.claude_client import get_claude_client
from app.models.portfolio import Position, Scenario
from app.modules.portfolio_intelligence.prompts import (
    SCENARIO_ANALYSIS_PROMPT,
    TRADE_IDEAS_PROMPT,
)
from app.schemas.portfolio import (
    PositionCreate,
    PositionResponse,
    CompositionResponse,
    ScenarioRequest,
    ScenarioResponse,
    TradeIdea,
)


class PortfolioIntelligenceService:
    """Service for AI-powered portfolio intelligence.

    Manages position storage, portfolio composition analysis, macro scenario
    analysis with Claude Sonnet, and convexity-aware trade idea generation.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialise service with DB session.

        Args:
            db: Async SQLAlchemy session.
        """
        self._db = db
        self._claude = get_claude_client()

    async def create_position(self, data: PositionCreate) -> PositionResponse:
        """Add a new position to the portfolio database.

        Args:
            data: PositionCreate payload with instrument and sizing details.

        Returns:
            PositionResponse for the created position.
        """
        position = Position(
            portfolio_name=data.portfolio_name,
            instrument=data.instrument,
            instrument_type=data.instrument_type.value,
            asset_class=data.asset_class,
            geography=data.geography,
            notional=data.notional,
            currency=data.currency,
            direction=data.direction.value,
            entry_price=data.entry_price,
            notes=data.notes,
            as_of_date=data.as_of_date,
        )
        self._db.add(position)
        await self._db.flush()
        logger.info(f"Position created: {position.id} — {position.instrument}")
        return PositionResponse.model_validate(position)

    async def upload_positions_csv(
        self, file: UploadFile, portfolio_name: str
    ) -> int:
        """Bulk import positions from a CSV file.

        Expected CSV columns: instrument, instrument_type, asset_class, geography,
        notional, currency, direction, entry_price, notes, as_of_date.

        Args:
            file: Uploaded CSV file.
            portfolio_name: Portfolio to assign positions to.

        Returns:
            Count of positions successfully imported.
        """
        content = await file.read()
        text = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))

        count = 0
        for row in reader:
            try:
                position = Position(
                    portfolio_name=portfolio_name,
                    instrument=row.get("instrument", ""),
                    instrument_type=row.get("instrument_type", "OTHER"),
                    asset_class=row.get("asset_class", "MACRO"),
                    geography=row.get("geography"),
                    notional=float(row.get("notional", 0)),
                    currency=row.get("currency", "USD"),
                    direction=row.get("direction", "LONG"),
                    entry_price=float(row["entry_price"]) if row.get("entry_price") else None,
                    notes=row.get("notes"),
                    as_of_date=date.fromisoformat(row["as_of_date"]) if row.get("as_of_date") else date.today(),
                )
                self._db.add(position)
                count += 1
            except Exception as exc:
                logger.warning(f"Skipping CSV row: {exc} — row={row}")
                continue

        await self._db.flush()
        logger.info(f"CSV import: {count} positions added to '{portfolio_name}'")
        return count

    async def list_positions(self, portfolio_name: str = "main") -> list[PositionResponse]:
        """Return all positions for a given portfolio.

        Args:
            portfolio_name: Name of the portfolio to query.

        Returns:
            List of PositionResponse objects.
        """
        result = await self._db.execute(
            select(Position)
            .where(Position.portfolio_name == portfolio_name)
            .order_by(desc(Position.as_of_date), Position.asset_class)
        )
        positions = result.scalars().all()
        return [PositionResponse.model_validate(p) for p in positions]

    async def get_composition(self, portfolio_name: str = "main") -> CompositionResponse:
        """Return portfolio composition breakdown by multiple dimensions.

        Computes notional weight percentages by asset class and geography,
        and count breakdowns by direction and instrument type.

        Args:
            portfolio_name: Name of the portfolio to analyse.

        Returns:
            CompositionResponse with all breakdown dimensions.
        """
        positions = await self.list_positions(portfolio_name)

        total_notional = sum(abs(p.notional) for p in positions)

        by_asset_class: dict[str, float] = {}
        by_geography: dict[str, float] = {}
        by_direction: dict[str, int] = {}
        by_instrument_type: dict[str, int] = {}

        for p in positions:
            weight = (abs(p.notional) / total_notional * 100) if total_notional > 0 else 0
            by_asset_class[p.asset_class] = by_asset_class.get(p.asset_class, 0) + weight
            if p.geography:
                by_geography[p.geography] = by_geography.get(p.geography, 0) + weight
            by_direction[p.direction] = by_direction.get(p.direction, 0) + 1
            by_instrument_type[p.instrument_type] = by_instrument_type.get(p.instrument_type, 0) + 1

        return CompositionResponse(
            as_of_date=date.today(),
            total_positions=len(positions),
            by_asset_class=by_asset_class,
            by_geography=by_geography,
            by_direction=by_direction,
            by_instrument_type=by_instrument_type,
        )

    async def run_scenario(self, request: ScenarioRequest) -> ScenarioResponse:
        """Run a macro scenario analysis and generate convexity-aware trade ideas.

        Uses Claude Sonnet to analyse the macro view against the current portfolio
        and generate structured trade ideas with risk commentary.

        Args:
            request: ScenarioRequest with macro_view string and optional constraints.

        Returns:
            ScenarioResponse with analysis and list of TradeIdea objects.
        """
        composition = await self.get_composition()
        portfolio_context = json.dumps(
            {
                "total_positions": composition.total_positions,
                "by_asset_class": composition.by_asset_class,
                "by_geography": composition.by_geography,
                "by_direction": composition.by_direction,
            },
            indent=2,
        )

        prompt = (
            f"MACRO VIEW:\n{request.macro_view}\n\n"
            f"CONSTRAINTS:\n{request.constraints or 'None specified'}\n\n"
            f"CURRENT PORTFOLIO COMPOSITION:\n{portfolio_context}"
        )

        try:
            result = await self._claude.complete_json(
                prompt=prompt,
                system=SCENARIO_ANALYSIS_PROMPT,
                use_sonnet=True,
                max_tokens=3000,
            )
            analysis_text = result.get("analysis", "")
            trade_ideas_raw = result.get("trade_ideas", [])
            title = result.get("title", f"Scenario: {request.macro_view[:60]}")
        except Exception as exc:
            logger.exception(f"Scenario analysis failed: {exc}")
            analysis_text = "Scenario analysis failed. Please try again."
            trade_ideas_raw = []
            title = f"Scenario: {request.macro_view[:60]}"

        trade_ideas = [
            TradeIdea(
                name=t.get("name", ""),
                instruments=t.get("instruments", ""),
                structure=t.get("structure", ""),
                rationale=t.get("rationale", ""),
                convexity_note=t.get("convexity_note", ""),
                key_risks=t.get("key_risks", ""),
            )
            for t in trade_ideas_raw
        ]

        scenario = Scenario(
            title=title,
            macro_view_input=request.macro_view,
            analysis_output=analysis_text,
            trade_ideas=json.dumps([t.model_dump() for t in trade_ideas]),
            model_used=self._claude.sonnet_model,
        )
        self._db.add(scenario)
        await self._db.flush()

        return ScenarioResponse(
            id=scenario.id,
            title=title,
            macro_view_input=request.macro_view,
            analysis_output=analysis_text,
            trade_ideas=trade_ideas,
            model_used=self._claude.sonnet_model,
            created_at=scenario.created_at,
        )

    async def list_scenarios(self, limit: int = 10) -> list[ScenarioResponse]:
        """Return past scenario analyses ordered by creation date descending.

        Args:
            limit: Maximum number of scenarios to return.

        Returns:
            List of ScenarioResponse objects.
        """
        result = await self._db.execute(
            select(Scenario).order_by(desc(Scenario.created_at)).limit(limit)
        )
        scenarios = result.scalars().all()
        responses = []
        for s in scenarios:
            trade_ideas_raw = json.loads(s.trade_ideas) if s.trade_ideas else []
            trade_ideas = [TradeIdea(**t) for t in trade_ideas_raw]
            responses.append(
                ScenarioResponse(
                    id=s.id,
                    title=s.title,
                    macro_view_input=s.macro_view_input,
                    analysis_output=s.analysis_output,
                    trade_ideas=trade_ideas,
                    model_used=s.model_used,
                    created_at=s.created_at,
                )
            )
        return responses
