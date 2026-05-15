"""Section 12.2 AI output quality tests."""
from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, patch

import pytest

from app.services.economic_calendar_service import on_data_release
from app.services.morning_briefing_service import generate_morning_briefing

QUALITY_RULES = {
    "no_filler_phrases": [
        "I'll analyze this",
        "Here is a summary",
        "It's important to note",
        "Please note that",
        "As an AI",
        "In conclusion",
        "To summarize",
    ],
    "no_vague_verbs": [
        "might increase",
        "could go up",
        "may fall",
        "possibly decline",
        "seems to be",
        "appears to be",
        "looks like",
    ],
}


def assert_output_quality(output: str, context: str) -> None:
    for phrase in QUALITY_RULES["no_filler_phrases"]:
        assert phrase.lower() not in output.lower(), f"[{context}] filler phrase: {phrase}"
    for phrase in QUALITY_RULES["no_vague_verbs"]:
        assert phrase.lower() not in output.lower(), f"[{context}] vague phrase: {phrase}"


@pytest.mark.asyncio
async def test_email_classification_output_quality(test_db) -> None:
    from app.modules.email_intelligence.service import EmailIntelligenceService

    fake = {
        "category": "RESEARCH",
        "priority": "P2_TODAY",
        "one_line_summary": "GS rates note on 2Y UST repricing risk",
        "tag": "RESEARCH",
        "relevance_score": 75,
    }
    service = EmailIntelligenceService(test_db)
    with patch("app.core.claude_client.ClaudeClient.complete_json", new_callable=AsyncMock, return_value=fake):
        result = await service._classify_email(
            sender_name="John Smith",
            sender_email="john@gsgroup.com",
            subject="GS Rates View: Repricing risk into H2",
            body_preview="We are moving to an overweight on 2Y UST given...",
        )
    assert result["tag"] == "RESEARCH"
    assert result["relevance_score"] in range(0, 101)


@pytest.mark.asyncio
async def test_morning_brief_output_quality() -> None:
    with patch("app.services.morning_briefing_service.get_fred_series", new_callable=AsyncMock, return_value={"FEDFUNDS": []}), patch(
        "app.services.onedrive_service.OneDriveService.upload_file", new_callable=AsyncMock
    ):
        brief = await generate_morning_briefing(__import__("datetime").datetime.now(__import__("datetime").UTC), "test-token")
    assert_output_quality(brief, "morning_brief")
    assert "##" in brief
    assert "[DATA MISSING]" in brief or "ESTIMATE" in brief


@pytest.mark.asyncio
async def test_research_analysis_no_hallucinated_figures() -> None:
    from app.prompts.adapters import normalize_research_analysis_json

    raw = {
        "core_thesis": "Goldman expects EUR/USD to reach 1.15 in 12 months.",
        "key_data_points": ["EUR/USD target 1.15 in 12 months"],
        "arp_relevance": {"score": 7},
    }
    parsed = normalize_research_analysis_json(raw)
    key_data = parsed["key_data_points"]
    assert any("1.15" in str(d) for d in key_data)
    assert not any("1.20" in str(d) for d in key_data)


@pytest.mark.asyncio
async def test_meeting_summary_action_items_have_owners() -> None:
    from app.services.teams_recording_service import run_meeting_intelligence

    fake_summary = {
        "summary": "Ops call.",
        "decisions": [],
        "action_items": [
            {"task": "Send NAV report to client by Thursday", "owner": "Rhys"},
            {"task": "Check Broadridge reconciliation", "owner": "Amin"},
        ],
        "key_quotes": [],
    }
    with patch("app.core.claude_client.ClaudeClient.complete_json", new_callable=AsyncMock, return_value=fake_summary):
        summary = await run_meeting_intelligence(
            transcript_text="Yusuf: Rhys send NAV. Yusuf: Amin check Broadridge.",
            meeting_title="Weekly Ops",
            meeting_date="2026-05-14",
            participants=["Yusuf", "Rhys", "Amin"],
        )
    owners = [item["owner"] for item in summary["action_items"]]
    assert "Rhys" in owners
    assert "Amin" in owners
    for item in summary["action_items"]:
        assert item["owner"] not in ("", "UNASSIGNED", None)


@pytest.mark.asyncio
async def test_scenario_analysis_uses_estimate_tags(test_db) -> None:
    from app.modules.portfolio_intelligence.service import PortfolioIntelligenceService
    from app.models.portfolio import Position
    from datetime import date

    test_db.add(
        Position(
            portfolio_name="main",
            instrument="EURUSD",
            instrument_type="FX",
            asset_class="FX",
            notional=2_000_000,
            currency="USD",
            direction="LONG",
            as_of_date=date.today(),
            uploaded_by_email="test@arp.local",
        )
    )
    await test_db.commit()
    service = PortfolioIntelligenceService(test_db)
    result = await service.run_prebuilt_scenario("Fed hikes 50bps surprise")
    monetary_figures = re.findall(r"\$[\d,\-\+]+[KMB]?", result["analysis"])
    for figure in monetary_figures:
        line = [l for l in result["analysis"].split("\n") if figure in l][0]
        assert "[ESTIMATE]" in line


@pytest.mark.asyncio
async def test_economic_release_directional_confidence() -> None:
    result = await on_data_release("US CPI", actual=3.9, consensus=3.2, prior=3.1)
    assert "Confidence in this assessment" in result
    assert "HIGH" in result

