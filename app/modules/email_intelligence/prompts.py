"""Claude prompts for the Email Intelligence module (Section 0 architecture)."""

from __future__ import annotations

from app.prompts.architecture import EMAIL_CLASSIFICATION_PROMPT

# User message includes SYSTEM_BASE + task; keep system minimal for JSON mode.
EMAIL_CLASSIFICATION_SYSTEM = (
    "You follow the rules and schema in the user message. "
    "Respond with JSON only — no markdown fences, no prose outside the JSON object."
)

# Backward-compatible names used by EmailIntelligenceService
EMAIL_SCORING_SYSTEM = EMAIL_CLASSIFICATION_SYSTEM
EMAIL_SCORING_PROMPT = EMAIL_CLASSIFICATION_PROMPT

# Tag color mapping (CSS classes)
TAG_COLORS: dict[str, str] = {
    "URGENT": "#dc2626",      # red
    "CLIENT": "#7c3aed",      # purple
    "TRADE": "#2563eb",       # blue
    "RESEARCH": "#059669",    # green
    "OPERATIONS": "#d97706",  # amber
    "HR": "#0891b2",          # cyan
    "REGULATORY": "#9333ea",  # violet
    "SKIP": "#6b7280",        # gray
}

# Valid tag set
VALID_TAGS: frozenset[str] = frozenset(TAG_COLORS.keys())
