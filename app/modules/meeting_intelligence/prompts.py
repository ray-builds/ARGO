"""Claude prompts for the Meeting Intelligence module (Section 0)."""

from app.prompts.architecture import MEETING_INTELLIGENCE_PROMPT, SYSTEM_BASE

MEETING_SUMMARY_SYSTEM = (
    "You follow the rules in the user message. "
    "Respond with JSON only — no markdown fences, no prose outside the JSON object."
)

MEETING_CHAT_PROMPT = (
    SYSTEM_BASE
    + """

You have access to meeting excerpts provided in the user message. Answer the user's question based solely on those excerpts.
If the excerpts do not contain sufficient information, say so clearly.

Format:
- Lead with the direct answer
- Cite meetings as [Meeting Title — Date]
- Keep the response concise (under 300 words)
- If multiple meetings are relevant, synthesise across them"""
)
