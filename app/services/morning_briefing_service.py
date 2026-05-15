"""Section 9 morning briefing aggregation + distribution service."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.prompts.architecture import MORNING_BRIEFING_PROMPT
from app.core.claude_client import get_claude_client
from app.services.onedrive_service import OneDriveService, safe_archive
from app.services.research_ingestion_service import get_fred_series

dubai_tz = ZoneInfo("Asia/Dubai")


async def get_classified_emails_since(_since: datetime) -> list[dict]:
    """Section 9 input placeholder: classified emails in lookback window."""
    return []


async def get_overnight_moves(tickers: list[str]) -> dict:
    """Section 9 input placeholder: overnight market moves."""
    return {t: {"move": "[DATA MISSING]"} for t in tickers}


async def get_todays_economic_events() -> list[dict]:
    """Section 9 input placeholder: economic events for today."""
    return []


async def search_overnight_news(_keywords: list[str]) -> list[dict]:
    """Section 9 input placeholder: overnight mandate-relevant headlines."""
    return []


async def get_portfolio_summary_for_briefing() -> dict:
    """Section 9 input placeholder: portfolio summary."""
    return {"note": "[DATA MISSING]"}


async def get_overdue_action_items() -> list[dict]:
    """Section 9 input placeholder: overdue action items."""
    return []


async def get_new_research_digest(hours: int = 24) -> list[dict]:
    """Section 9 input placeholder: new research digest."""
    _ = hours
    return []


def format_email_digest(emails: list[dict]) -> str:
    """Render compact digest string for prompt input."""
    if not emails:
        return "No P1/P2 emails in window."
    rows = []
    for e in emails:
        rows.append(f"{e.get('from','[DATA MISSING]')} | {e.get('subject','[DATA MISSING]')} | {e.get('priority')}")
    return "\n".join(rows)


async def email_morning_brief(_brief: str, _to: list[str]) -> None:
    """Section 9 output placeholder: email distribution hook."""
    return None


async def post_to_teams_channel(_brief: str, _channel: str) -> None:
    """Section 9 output placeholder: Teams distribution hook."""
    return None


def _default_brief() -> str:
    now = datetime.now(dubai_tz).strftime("%H:%M GST")
    return "\n".join(
        [
            "## OVERNIGHT P&L DRIVERS",
            "[DATA MISSING]",
            "",
            "## REQUIRES YOUR DECISION TODAY",
            "No CEO decisions required today.",
            "",
            "## MARKET OPEN WATCH LIST",
            "[DATA MISSING]",
            "",
            "## ECONOMIC EVENTS - IMPACT TO BOOK",
            "[DATA MISSING]",
            "",
            "## EMAILS REQUIRING RESPONSE",
            "None.",
            "",
            "## RESEARCH INTEL",
            "[DATA MISSING]",
            "",
            "## OPEN ITEMS OVERDUE",
            "None.",
            "",
            "---",
            f"Briefing generated: {now}",
        ]
    )


async def generate_morning_briefing(date: datetime, user_access_token: str) -> str:
    """Assemble Section 9 data sources, generate brief, archive and distribute."""
    emails = await get_classified_emails_since(date - timedelta(hours=12))
    p1_p2 = [e for e in emails if e.get("priority") in ["P1_URGENT", "P2_TODAY"]]
    email_digest = format_email_digest(p1_p2)

    overnight_tickers = [
        "^GSPC", "^IXIC", "^FTSE", "^N225", "^HSI", "^GDAXI",
        "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCNH=X",
        "GC=F", "CL=F", "^TNX", "^IRX",
    ]
    market_data = await get_overnight_moves(overnight_tickers)
    calendar = await get_todays_economic_events()
    news = await search_overnight_news(
        [
            "macro hedge fund", "Federal Reserve", "global markets",
            "central bank", "geopolitical", "OPEC", "inflation",
        ]
    )
    portfolio = await get_portfolio_summary_for_briefing()
    pending = await get_overdue_action_items()
    new_research = await get_new_research_digest(hours=24)
    try:
        fred_data = await get_fred_series(["FEDFUNDS", "DGS10", "T10Y2Y"])
    except Exception:
        fred_data = {"FEDFUNDS": [], "DGS10": [], "T10Y2Y": []}

    claude = get_claude_client()
    prompt = MORNING_BRIEFING_PROMPT.format(
        email_digest=email_digest,
        market_data=json.dumps(market_data),
        economic_calendar=json.dumps(calendar),
        news_headlines=json.dumps(news),
        portfolio_summary=json.dumps(portfolio),
        pending_actions=json.dumps(pending),
        new_research=json.dumps(new_research),
        timestamp=datetime.now(dubai_tz).strftime("%H:%M"),
        email_cutoff=(date - timedelta(hours=12)).astimezone(dubai_tz).strftime("%H:%M"),
        market_data_timestamp=datetime.now(dubai_tz).strftime("%H:%M"),
    )
    prompt += f"\n\nFRED_KEY_RATES: {json.dumps(fred_data)}"

    try:
        brief = await claude.complete(
            prompt=prompt,
            system="You are ARGO morning briefing model. Follow exact section headers.",
            use_sonnet=True,
            max_tokens=2200,
        )
    except Exception:
        brief = _default_brief()

    if not isinstance(brief, str) or not brief.strip():
        brief = _default_brief()

    required_sections = [
        "OVERNIGHT P&L DRIVERS",
        "REQUIRES YOUR DECISION TODAY",
        "MARKET OPEN WATCH LIST",
        "ECONOMIC EVENTS",
        "EMAILS REQUIRING RESPONSE",
        "RESEARCH INTEL",
    ]
    if any(section not in brief for section in required_sections):
        brief = _default_brief()

    onedrive = OneDriveService(user_access_token)
    await safe_archive(onedrive.archive_morning_brief(brief, date.strftime("%Y-%m-%d")))
    await email_morning_brief(brief, ["yusuf@arpglobal.com"])
    await post_to_teams_channel(brief, "morning-briefing")
    return brief


async def morning_brief_job() -> str:
    """Scheduler entrypoint for Section 9 briefing."""
    service_token = "service-token-placeholder"
    return await generate_morning_briefing(datetime.now(UTC), service_token)


async def timed_morning_brief_job() -> tuple[str, float]:
    """Helper used in tests to assert runtime against SLO."""
    start = time.time()
    brief = await morning_brief_job()
    return brief, time.time() - start
