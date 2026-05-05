"""Email tag classification logic — standalone utilities."""
from __future__ import annotations

EMAIL_TAG_COLORS = {
    "URGENT": "#dc2626",
    "CLIENT": "#2685B5",
    "TRADE": "#16a34a",
    "RESEARCH": "#7c3aed",
    "OPERATIONS": "#ea580c",
    "HR": "#db2777",
    "REGULATORY": "#991b1b",
    "SKIP": "#6b7280",
}

EMAIL_TAG_LABELS = {
    "URGENT": "Urgent",
    "CLIENT": "Client",
    "TRADE": "Trade",
    "RESEARCH": "Research",
    "OPERATIONS": "Operations",
    "HR": "HR",
    "REGULATORY": "Regulatory",
    "SKIP": "Skip",
}


def get_tag_color(tag: str) -> str:
    """Return the hex color for a given email tag.

    Args:
        tag: The email tag string (e.g. 'URGENT', 'CLIENT').

    Returns:
        Hex color string, defaulting to grey for unknown tags.
    """
    return EMAIL_TAG_COLORS.get(tag, "#6b7280")


def is_high_priority(relevance_score: int | None, tag: str | None) -> bool:
    """Return True if this email is considered high priority.

    An email is high priority if it is tagged URGENT or has a relevance
    score of 80 or above.

    Args:
        relevance_score: AI-assigned relevance score (0-100).
        tag: AI-assigned tag string.

    Returns:
        True if the email should be treated as high priority.
    """
    if tag == "URGENT":
        return True
    if relevance_score and relevance_score >= 80:
        return True
    return False
