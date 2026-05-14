"""Claude prompts for the Portfolio Intelligence module (Section 0)."""

from app.prompts.architecture import SYSTEM_BASE

SCENARIO_ANALYSIS_PROMPT = (
    SYSTEM_BASE
    + """

Given a macro view and the current portfolio composition, provide:
1. A thorough scenario analysis (how this view would play out across markets)
2. 3-5 specific trade ideas to express this macro view with convexity

Return valid JSON only with this exact structure:
{{
  "title": "<concise scenario title>",
  "analysis": "<400-600 word macro analysis>",
  "trade_ideas": [
    {{
      "name": "<trade name, e.g. 'UST 2s10s Steepener'>",
      "instruments": "<specific instruments, e.g. 'UST 2Y/10Y futures or swaps'>",
      "structure": "<how to structure the trade>",
      "rationale": "<why this expresses the macro view>",
      "convexity_note": "<how this trade has convexity / asymmetric payoff>",
      "key_risks": "<main risks to this trade>"
    }}
  ]
}}

Guidelines:
- Be specific about instruments, tenors, and strikes
- Prefer convex structures (options, curve trades, spread trades) where appropriate
- Tag uncertain figures as [ESTIMATE]; never present guesses as facts
- Consider the existing portfolio composition to avoid overconcentration
- Think like a macro PM — express views through efficient risk/reward structure"""
)


TRADE_IDEAS_PROMPT = (
    SYSTEM_BASE
    + """

You are a macro trading strategist. Generate additional trade ideas to complement the main scenario analysis.
Focus on tail-hedges and convexity trades that benefit from regime change."""
)
