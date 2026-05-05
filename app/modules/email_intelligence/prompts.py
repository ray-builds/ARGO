"""Claude prompts for the Email Intelligence module."""

EMAIL_SCORING_SYSTEM = """You are an email classifier for ARP Global Capital, a macro hedge fund.
Classify emails accurately. Output valid JSON only."""

EMAIL_SCORING_PROMPT = """
Classify this email for a macro hedge fund:

From: {sender_name} <{sender_email}>
Subject: {subject}
Preview: {body_preview}

Tags available (choose exactly one):
- URGENT: requires immediate action today
- CLIENT: from/about an investor, LP, or client relationship
- TRADE: trade confirmation, execution, prime broker, counterparty
- RESEARCH: research reports, market analysis, broker notes
- OPERATIONS: fund ops, settlements, reconciliation, compliance
- HR: people, payroll, benefits, recruitment
- REGULATORY: regulatory filings, compliance, legal
- SKIP: newsletters, marketing, spam, automated notifications

Return JSON only:
{{
  "tag": "ONE_OF_THE_TAGS_ABOVE",
  "relevance_score": <integer 0-100, how important for the PM>,
  "ai_summary": "<1-2 sentence extract of what this email is about and why it matters>",
  "action_required": "<null or specific action needed>",
  "key_conclusion": "<null or key fact/number from this email>"
}}
"""

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
