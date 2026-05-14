"""Normalize Section 0 model outputs to legacy ARGO storage / API shapes."""
from __future__ import annotations

import json
from typing import Any

from app.modules.email_intelligence.prompts import VALID_TAGS

# Section 0 category → inbox tag (DB + UI)
CATEGORY_TO_TAG: dict[str, str] = {
    "CEO_DIRECTIVE": "URGENT",
    "CLIENT_COMMUNICATION": "CLIENT",
    "COUNTERPARTY": "TRADE",
    "TRADE_RELATED": "TRADE",
    "RESEARCH": "RESEARCH",
    "REGULATORY": "REGULATORY",
    "OPERATIONS": "OPERATIONS",
    "INTERNAL": "SKIP",
    "CALENDAR": "SKIP",
    "VENDOR": "SKIP",
    "NOISE": "SKIP",
}

PRIORITY_TO_SCORE: dict[str, int] = {
    "P1_URGENT": 95,
    "P2_TODAY": 75,
    "P3_THIS_WEEK": 50,
    "P4_FYI": 25,
}


def normalize_email_classification_for_storage(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Section 0 email JSON (and legacy keys) to EmailIntelligenceService fields."""
    out = dict(raw)

    # Legacy path: model returned old shape
    if raw.get("tag") and raw["tag"] in VALID_TAGS and raw.get("relevance_score") is not None:
        return out

    cat = str(raw.get("category", "NOISE")).strip()
    tag = CATEGORY_TO_TAG.get(cat, "SKIP")
    if tag not in VALID_TAGS:
        tag = "SKIP"
    out["tag"] = tag

    prio = str(raw.get("priority", "P4_FYI")).strip()
    score = raw.get("relevance_score")
    if score is None:
        out["relevance_score"] = PRIORITY_TO_SCORE.get(prio, 30)
    elif not isinstance(score, int):
        try:
            out["relevance_score"] = max(0, min(100, int(score)))
        except (TypeError, ValueError):
            out["relevance_score"] = PRIORITY_TO_SCORE.get(prio, 30)
    else:
        out["relevance_score"] = max(0, min(100, score))

    one_line = raw.get("one_line_summary")
    if one_line and not raw.get("ai_summary"):
        out["ai_summary"] = str(one_line).strip()

    action_req = raw.get("action_required")
    summary = raw.get("action_summary")
    if isinstance(action_req, bool):
        if action_req and summary:
            out["action_required"] = str(summary).strip()
        else:
            out["action_required"] = None
    elif summary and not raw.get("action_required"):
        out["action_required"] = str(summary).strip()

    if not raw.get("key_conclusion"):
        entities = raw.get("key_entities")
        if isinstance(entities, list) and entities:
            out["key_conclusion"] = "; ".join(str(x) for x in entities[:5])
        elif raw.get("priority_rationale"):
            out["key_conclusion"] = str(raw["priority_rationale"])[:500]

    return out


def normalize_meeting_intelligence_json(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Section 0 meeting JSON to MeetingIntelligenceService summarize() shape."""
    if "executive_summary" in raw and "summary" not in raw:
        decisions: list[str] = []
        for d in raw.get("decisions_made") or []:
            if isinstance(d, dict):
                txt = d.get("decision", "")
                if txt:
                    decisions.append(str(txt))
            elif isinstance(d, str):
                decisions.append(d)

        action_items: list[dict[str, Any]] = []
        for a in raw.get("action_items") or []:
            if not isinstance(a, dict):
                continue
            action_items.append(
                {
                    "description": a.get("task") or a.get("description") or "",
                    "owner": a.get("owner"),
                    "due_date": a.get("deadline") or a.get("due_date"),
                }
            )

        quotes: list[dict[str, str]] = []
        for q in raw.get("open_questions") or []:
            if isinstance(q, str) and q.strip():
                quotes.append({"speaker": "OpenQuestion", "quote": q.strip()})

        return {
            "summary": raw.get("executive_summary", ""),
            "decisions": decisions,
            "key_quotes": quotes,
            "action_items": action_items,
        }

    # Legacy mock / old schema
    items = raw.get("action_items") or []
    fixed_items: list[dict[str, Any]] = []
    for a in items:
        if not isinstance(a, dict):
            continue
        desc = a.get("description") or a.get("text") or ""
        fixed_items.append(
            {
                "description": desc,
                "owner": a.get("owner"),
                "due_date": a.get("due_date"),
            }
        )
    out = dict(raw)
    out["action_items"] = fixed_items
    return out


def normalize_research_analysis_json(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Section 0 research JSON to ResearchIntelligenceService summarize_research shape."""
    if "core_thesis" not in raw:
        return raw

    ar = raw.get("arp_relevance") or {}
    score = ar.get("score", 5)
    try:
        s = int(score)
    except (TypeError, ValueError):
        s = 5
    if s >= 7:
        conviction = "HIGH"
    elif s <= 3:
        conviction = "LOW"
    else:
        conviction = "MEDIUM"

    themes = list(raw.get("macro_themes") or [])
    themes.extend(raw.get("asset_classes_covered") or [])
    instruments = raw.get("instruments_mentioned") or []
    if instruments:
        themes.extend([f"instrument:{i}" for i in instruments[:5]])

    thesis = raw.get("core_thesis") or raw.get("one_line_digest") or ""

    return {
        "thesis_summary": thesis,
        "key_data_points": raw.get("key_data_points") or [],
        "conviction_level": conviction,
        "topics": themes[:20] if themes else ["macro"],
    }


def economic_surprise_direction_for_prompt(surprise_db: str | None) -> str:
    """Map DB surprise token to wording expected by ECONOMIC_RELEASE_PROMPT."""
    if not surprise_db:
        return "IN_LINE"
    u = surprise_db.upper()
    if u == "BEAT":
        return "UPSIDE"
    if u == "MISS":
        return "DOWNSIDE"
    return u
