"""Section 0 — system prompt architecture (ARGO Upgrade Plan v2)."""
from __future__ import annotations

import pytest

from app.prompts import architecture
from app.prompts.adapters import (
    CATEGORY_TO_TAG,
    PRIORITY_TO_SCORE,
    economic_surprise_direction_for_prompt,
    normalize_email_classification_for_storage,
    normalize_meeting_intelligence_json,
    normalize_research_analysis_json,
)


class TestSection0SystemBase:
    def test_system_base_has_argo_identity(self) -> None:
        assert "ARGO" in architecture.SYSTEM_BASE
        assert "ARP Global Capital" in architecture.SYSTEM_BASE
        assert "[DATA MISSING]" in architecture.SYSTEM_BASE
        assert "→ REQUIRES DECISION:" in architecture.SYSTEM_BASE

    def test_system_base_bans_filler_tone(self) -> None:
        assert "zero tolerance" in architecture.SYSTEM_BASE.lower()


class TestSection0PromptTemplates:
    def test_email_classification_formats(self) -> None:
        s = architecture.EMAIL_CLASSIFICATION_PROMPT.format(
            sender_name="Test",
            sender_email="t@gs.com",
            subject="Rates",
            body_text="Body",
            attachment_list="[]",
            timestamp="2026-05-14T00:00:00Z",
            thread_count=1,
        )
        assert "CEO_DIRECTIVE" in s
        assert "Test" in s
        assert "Rates" in s

    def test_email_reply_formats(self) -> None:
        s = architecture.EMAIL_REPLY_PROMPT.format(
            reply_author_name="Rhys",
            reply_author_title="PM",
            relationship_context="broker",
            tone="COLLEGIAL_PEER",
            original_sender="a@b.com",
            subject="Hello",
            body_text="Hi",
            user_context="None",
        )
        assert "Rhys" in s
        assert '"subject"' in s

    def test_morning_briefing_has_required_sections(self) -> None:
        s = architecture.MORNING_BRIEFING_PROMPT.format(
            email_digest="[]",
            market_data="{}",
            economic_calendar="[]",
            news_headlines="[]",
            portfolio_summary="{}",
            pending_actions="[]",
            new_research="[]",
            timestamp="06:00",
            email_cutoff="22:00",
            market_data_timestamp="06:15",
        )
        assert "## OVERNIGHT P&L DRIVERS" in s
        assert "## REQUIRES YOUR DECISION TODAY" in s
        assert "## MARKET OPEN WATCH LIST" in s

    def test_research_analysis_formats(self) -> None:
        s = architecture.RESEARCH_ANALYSIS_PROMPT.format(
            source_firm="GS",
            author="Analyst",
            title="EUR",
            date="2026-05-14",
            doc_type="BROKER_NOTE",
            document_text="EUR/USD view",
            portfolio_context="{}",
        )
        assert "core_thesis" in s
        assert "EUR/USD view" in s

    def test_meeting_intelligence_formats(self) -> None:
        s = architecture.MEETING_INTELLIGENCE_PROMPT.format(
            meeting_date="2026-05-14",
            meeting_title="Ops",
            participants="A, B",
            duration_minutes=30,
            meeting_type="INTERNAL_PM",
            transcript_text="Hello",
        )
        assert "executive_summary" in s
        assert "Hello" in s

    def test_economic_release_formats(self) -> None:
        s = architecture.ECONOMIC_RELEASE_PROMPT.format(
            indicator_name="CPI",
            actual_value="3.4",
            consensus="3.2",
            prior_value="3.1",
            surprise="0.2",
            surprise_direction="UPSIDE",
            release_time="08:30",
            portfolio_exposures="{}",
            historical_reaction="RATES + FX",
        )
        assert "CPI" in s
        assert "[ESTIMATE]" in s

    def test_whatsapp_report_formats(self) -> None:
        s = architecture.WHATSAPP_REPORT_PROMPT.format(
            week_start="2026-05-10",
            week_end="2026-05-16",
            whatsapp_messages_json="[]",
            trade_count=0,
            total_messages=0,
            groups_list="none",
        )
        assert "WEEKLY WHATSAPP INTELLIGENCE REPORT" in s


class TestSection0Adapters:
    def test_map_v2_email_to_legacy(self) -> None:
        raw = {
            "category": "TRADE_RELATED",
            "priority": "P1_URGENT",
            "one_line_summary": "Margin call received",
            "action_required": True,
            "action_summary": "Post collateral by 10am",
            "key_entities": ["PB", "10M"],
        }
        out = normalize_email_classification_for_storage(raw)
        assert out["tag"] == "TRADE"
        assert out["relevance_score"] == 95
        assert out["ai_summary"] == "Margin call received"
        assert out["action_required"] == "Post collateral by 10am"

    def test_legacy_email_pass_through(self) -> None:
        raw = {
            "tag": "RESEARCH",
            "relevance_score": 55,
            "ai_summary": "x",
        }
        out = normalize_email_classification_for_storage(raw)
        assert out["tag"] == "RESEARCH"
        assert out["relevance_score"] == 55

    def test_category_to_tag_exhaustive_keys(self) -> None:
        expected = {
            "CEO_DIRECTIVE",
            "CLIENT_COMMUNICATION",
            "COUNTERPARTY",
            "TRADE_RELATED",
            "RESEARCH",
            "REGULATORY",
            "OPERATIONS",
            "INTERNAL",
            "CALENDAR",
            "VENDOR",
            "NOISE",
        }
        assert set(CATEGORY_TO_TAG.keys()) == expected

    def test_priority_scores_bounded(self) -> None:
        for _k, v in PRIORITY_TO_SCORE.items():
            assert 0 <= v <= 100

    def test_meeting_v2_to_legacy(self) -> None:
        raw = {
            "executive_summary": "Decided X.",
            "decisions_made": [{"decision": "Approve risk limit", "owner": "Yusuf"}],
            "action_items": [
                {"task": "Send file", "owner": "Rhys", "deadline": "2026-05-20", "priority": "P1"}
            ],
            "open_questions": ["Who owns Y?"],
        }
        out = normalize_meeting_intelligence_json(raw)
        assert out["summary"] == "Decided X."
        assert "Approve risk limit" in out["decisions"]
        assert out["action_items"][0]["description"] == "Send file"

    def test_meeting_legacy_action_text_key(self) -> None:
        raw = {
            "summary": "S",
            "action_items": [{"text": "Do thing", "owner": "A"}],
            "decisions": [],
            "key_quotes": [],
        }
        out = normalize_meeting_intelligence_json(raw)
        assert out["action_items"][0]["description"] == "Do thing"

    def test_research_v2_to_legacy(self) -> None:
        raw = {
            "core_thesis": "Rates higher.",
            "key_data_points": ["10Y at 4.5%"],
            "macro_themes": ["inflation"],
            "asset_classes_covered": ["RATES"],
            "arp_relevance": {"score": 8},
        }
        out = normalize_research_analysis_json(raw)
        assert out["thesis_summary"] == "Rates higher."
        assert out["conviction_level"] == "HIGH"
        assert "inflation" in out["topics"]

    def test_economic_surprise_mapping(self) -> None:
        assert economic_surprise_direction_for_prompt("BEAT") == "UPSIDE"
        assert economic_surprise_direction_for_prompt("MISS") == "DOWNSIDE"
        assert economic_surprise_direction_for_prompt("IN_LINE") == "IN_LINE"


class TestSection0ModuleImports:
    def test_app_imports_with_section0_prompts(self) -> None:
        from app.main import app  # noqa: F401 — registers routers

        assert app.title == "ARGO"
