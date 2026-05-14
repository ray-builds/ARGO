"""Claude prompts for the Economic Intelligence module (Section 0)."""

from app.prompts.architecture import ECONOMIC_RELEASE_PROMPT, SYSTEM_BASE

ECONOMIC_RELEASE_SYSTEM = (
    "Follow the rules and output structure in the user message. Markdown only — "
    "use the exact section headers requested."
)

# Backward-compatible alias (was used as system string)
RELEASE_ANALYSIS_PROMPT = ECONOMIC_RELEASE_SYSTEM

MORNING_ALERT_PROMPT = (
    SYSTEM_BASE
    + """

Format a concise morning economic event alert for a macro hedge fund PM.
Include: event name, country, release time UTC, consensus forecast, previous value.
Keep each alert to 2 lines maximum."""
)

__all__ = [
    "ECONOMIC_RELEASE_PROMPT",
    "ECONOMIC_RELEASE_SYSTEM",
    "RELEASE_ANALYSIS_PROMPT",
    "MORNING_ALERT_PROMPT",
]
