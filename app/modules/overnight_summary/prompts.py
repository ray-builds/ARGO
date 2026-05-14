"""Claude prompts for the Overnight Summary module (Section 0 + JSON pipeline)."""

from app.prompts.architecture import SYSTEM_BASE

OVERNIGHT_SUMMARY_SYSTEM = (
    SYSTEM_BASE
    + """

You must return valid JSON only (no markdown fences) with exactly these keys:
executive_summary (string), important_emails (array), top_market_moves (array),
key_news (array), macro_watch (string). Every claim must be grounded in the inputs;
use "[DATA MISSING]" where inputs lack figures."""
)

OVERNIGHT_SUMMARY_PROMPT = """
Analyze the following overnight data and produce a structured briefing.

EMAILS (received since 10pm yesterday):
{emails_json}

MARKET DATA (overnight moves):
{market_data_json}

NEWS HEADLINES:
{news_json}

Return a JSON object with exactly these keys:
{{
  "executive_summary": "3 sentences: what changed overnight, biggest risks/opportunities",
  "important_emails": [
    {{"sender": "...", "subject": "...", "action_required": "...", "priority": "HIGH|MEDIUM"}}
  ],
  "top_market_moves": [
    {{"asset": "...", "move": "...", "magnitude": "...", "why_it_matters": "..."}}
  ],
  "key_news": [
    {{"headline": "...", "significance": "one sentence"}}
  ],
  "macro_watch": "paragraph specifically on rates/credit/FX implications"
}}

Rules:
- important_emails: only include if relevance_score >= 50 or from CEO
- top_market_moves: exactly 3, sorted by magnitude
- key_news: exactly 3 most market-relevant
- macro_watch: focus on what matters for a macro discretionary book
"""
