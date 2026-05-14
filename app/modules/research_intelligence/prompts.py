"""Claude prompts for the Research Intelligence module (Section 0)."""

from app.prompts.architecture import RESEARCH_ANALYSIS_PROMPT, SYSTEM_BASE

RESEARCH_SUMMARY_SYSTEM = (
    "You follow the rules in the user message. "
    "Respond with JSON only — no markdown fences, no prose outside the JSON object."
)

# Backward-compatible name (was full prompt; now system string only)
RESEARCH_SUMMARY_PROMPT = RESEARCH_SUMMARY_SYSTEM

DIGEST_SYNTHESIS_PROMPT = (
    SYSTEM_BASE
    + """

You are synthesising a weekly research digest for a macro hedge fund.
Select and rank the most actionable research items. Focus on items with specific catalysts,
trade-able ideas, or high-conviction views that are differentiated from consensus."""
)
