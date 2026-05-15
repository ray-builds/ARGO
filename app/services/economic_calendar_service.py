"""Section 8 real-time economic intelligence services."""
from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from xml.etree import ElementTree

import httpx

from app.services.research_ingestion_service import get_fred_series
from app.services.teams_service import send_alert
from app.services.whatsapp_alert_service import send_whatsapp_alert

MONITORED_INDICATORS = {
    "US CPI": {"fred_series": "CPIAUCSL", "importance": "CRITICAL", "arp_sensitivity": "RATES + FX"},
    "US NFP": {"fred_series": "PAYEMS", "importance": "CRITICAL", "arp_sensitivity": "RATES + EQUITY"},
    "Fed Funds Rate": {"fred_series": "FEDFUNDS", "importance": "CRITICAL", "arp_sensitivity": "ALL"},
    "US 10Y Yield": {"fred_series": "DGS10", "importance": "HIGH", "arp_sensitivity": "RATES"},
    "EUR/USD": {"yahoo_ticker": "EURUSD=X", "importance": "HIGH", "arp_sensitivity": "FX"},
    "China PMI": {"importance": "HIGH", "arp_sensitivity": "ASIA BOOK + COMMODITIES"},
    "UK CPI": {"importance": "MEDIUM", "arp_sensitivity": "FX"},
    "ECB Rate Decision": {"importance": "CRITICAL", "arp_sensitivity": "RATES + FX"},
}

CB_SOURCES = {
    "Fed": "https://www.federalreserve.gov/feeds/press_monetary.xml",
    "ECB": "https://www.ecb.europa.eu/press/govcdec/mopo/rss.html",
    "BOE": "https://www.bankofengland.co.uk/rss/news",
    "BOJ": "https://www.boj.or.jp/en/about/release_2024/index.htm/rss.xml",
}


def get_surprise_direction(actual: float, consensus: float) -> str:
    """Return UPSIDE/DOWNSIDE/IN_LINE surprise direction."""
    diff = actual - consensus
    if abs(diff) < 1e-12:
        return "IN_LINE"
    return "UPSIDE" if diff > 0 else "DOWNSIDE"


async def get_economic_calendar_trading_economics(days_ahead: int = 7) -> list[dict[str, Any]]:
    """Fetch economic calendar from TradingEconomics."""
    key = os.getenv("TRADING_ECONOMICS_KEY", "")
    params = {
        "c": key,
        "country": "united states,euro area,united kingdom,china,japan",
        "importance": "2,3",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get("https://api.tradingeconomics.com/calendar", params=params)
        response.raise_for_status()
        rows = response.json()
    if not isinstance(rows, list):
        return []
    cutoff = datetime.now(UTC) + timedelta(days=days_ahead)
    out = []
    for row in rows:
        date_str = str(row.get("Date") or row.get("date") or "")
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            dt = None
        if dt is None or dt <= cutoff:
            out.append(row)
    return out


async def get_fred_release_calendar() -> dict[str, Any]:
    """Fetch FRED release calendar for the next 7 days."""
    key = os.getenv("FRED_API_KEY", "")
    params = {
        "api_key": key,
        "file_type": "json",
        "realtime_start": datetime.now(UTC).date().isoformat(),
        "realtime_end": (datetime.now(UTC) + timedelta(days=7)).date().isoformat(),
        "include_release_dates_with_no_data": "false",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get("https://api.stlouisfed.org/fred/releases/dates", params=params)
        response.raise_for_status()
        return response.json()


async def get_current_portfolio_summary() -> dict[str, Any]:
    """Placeholder portfolio summary for rapid impact commentary."""
    return {"positions": [], "note": "[DATA MISSING]"}


def _build_commentary(
    indicator: str,
    actual: float,
    consensus: float,
    prior: float,
    surprise_dir: str,
    portfolio: dict[str, Any],
) -> str:
    surprise = abs(actual - consensus)
    surprise_ratio = (surprise / abs(consensus)) if consensus else 0.0
    confidence = "HIGH" if surprise_ratio >= 0.15 else "MED"
    return "\n".join(
        [
            f"## {indicator} - {actual} vs {consensus} consensus [{surprise_dir} SURPRISE]",
            "",
            f"**Immediate read:** {'Growth/inflation upside pressure' if surprise_dir == 'UPSIDE' else 'Growth/inflation downside pressure' if surprise_dir == 'DOWNSIDE' else 'Inline release'}",
            "",
            "**Book impact estimate:**",
            f"| Exposure | Estimated Move | Estimated P&L Impact |",
            f"| Rates | +/- based on shock [ESTIMATE] | $[ESTIMATE] |",
            f"| FX | +/- based on USD sensitivity [ESTIMATE] | $[ESTIMATE] |",
            "",
            "**Rates:** sensitivity check required vs duration profile.",
            "**FX:** sensitivity check required vs core pairs.",
            "**Equity:** second-order impact via yields/real rates.",
            "",
            f"**Next catalyst:** follow-up prints and central bank guidance (prior={prior}, surprise={round(surprise, 3)}).",
            "",
            f"**Confidence in this assessment:** {confidence} - real-time directional read; verify against live position greeks.",
            "",
            f"Portfolio context: {json.dumps(portfolio)[:400]}",
        ]
    )


async def save_to_research_lake(indicator: str, actual: float, consensus: float, commentary: str) -> None:
    """Placeholder persistence hook for release commentary."""
    _ = (indicator, actual, consensus, commentary)


async def on_data_release(indicator: str, actual: float, consensus: float, prior: float) -> str:
    """Generate and distribute real-time release commentary."""
    start = time.time()
    portfolio = await get_current_portfolio_summary()
    surprise_dir = get_surprise_direction(actual, consensus)
    commentary = _build_commentary(indicator, actual, consensus, prior, surprise_dir, portfolio)

    await send_alert(commentary, channel="macro-alerts")
    await send_whatsapp_alert(commentary, group="ARP Trading")
    await save_to_research_lake(indicator, actual, consensus, commentary)

    elapsed = time.time() - start
    if elapsed > 90:
        commentary += f"\n\n[WARNING] runtime exceeded 90s ({elapsed:.2f}s)"
    return commentary


async def fetch_cb_rss(
    url: str,
    http_get: Callable[..., Any] | None = None,
) -> list[dict[str, str]]:
    """Fetch and parse an RSS/Atom feed into normalized items."""
    getter = http_get or httpx.get
    response = getter(url, timeout=30.0)
    text = response.text if hasattr(response, "text") else ""
    root = ElementTree.fromstring(text)
    items: list[dict[str, str]] = []

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if title:
            items.append({"title": title, "link": link, "description": desc, "published": pub})
    if items:
        return items

    # Atom fallback
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link_node = entry.find("a:link", ns)
        link = (link_node.attrib.get("href", "") if link_node is not None else "").strip()
        summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
        updated = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()
        if title:
            items.append({"title": title, "link": link, "description": summary, "published": updated})
    return items


def _simple_cb_shift(current_text: str, historical_texts: list[str]) -> dict[str, Any]:
    current = current_text.lower()
    history = " ".join(historical_texts).lower()
    hawkish_terms = ["higher for longer", "inflation risk", "tightening", "restrictive"]
    dovish_terms = ["accommodative", "downside risk", "easing", "support growth"]
    hawk_now = sum(t in current for t in hawkish_terms)
    dove_now = sum(t in current for t in dovish_terms)
    hawk_then = sum(t in history for t in hawkish_terms)
    dove_then = sum(t in history for t in dovish_terms)

    if hawk_now > dove_now:
        stance = "HAWKISH"
    elif dove_now > hawk_now:
        stance = "DOVISH"
    elif hawk_now == dove_now == 0:
        stance = "NEUTRAL"
    else:
        stance = "MIXED"

    net_now = hawk_now - dove_now
    net_then = hawk_then - dove_then
    delta = net_now - net_then
    if delta >= 2:
        shift = "MORE_HAWKISH"
        magnitude = "LARGE"
    elif delta == 1:
        shift = "MORE_HAWKISH"
        magnitude = "MODERATE"
    elif delta <= -2:
        shift = "MORE_DOVISH"
        magnitude = "LARGE"
    elif delta == -1:
        shift = "MORE_DOVISH"
        magnitude = "MODERATE"
    else:
        shift = "UNCHANGED"
        magnitude = "NONE"

    return {
        "stance": stance,
        "shift_vs_last": shift,
        "shift_magnitude": magnitude,
        "key_language_changes": [],
        "next_meeting_implication": "Monitor forward guidance language for rate-path confidence.",
        "arp_book_implication": "Rates/FX positioning should be reviewed versus communication shift.",
        "alert_worthy": magnitude in {"LARGE", "MODERATE"} and shift != "UNCHANGED",
    }


async def track_central_bank_language() -> dict[str, dict[str, Any]]:
    """Track weekly communication shift for major central banks."""
    output: dict[str, dict[str, Any]] = {}
    for bank, url in CB_SOURCES.items():
        items = await fetch_cb_rss(url)
        if not items:
            output[bank] = {
                "stance": "NEUTRAL",
                "shift_vs_last": "UNCHANGED",
                "shift_magnitude": "NONE",
                "key_language_changes": [],
                "next_meeting_implication": "[DATA MISSING]",
                "arp_book_implication": "[DATA MISSING]",
                "alert_worthy": False,
            }
            continue
        current = items[0].get("description") or items[0].get("title") or ""
        historical = [
            (x.get("description") or x.get("title") or "")
            for x in items[1:4]
        ]
        output[bank] = _simple_cb_shift(current, historical)
    return output
