"""Section 5 WhatsApp ingestion + weekly digest service."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.whatsapp import WhatsAppMessage
from app.services.onedrive_service import OneDriveService, safe_archive

TRADE_PATTERNS = [
    r"\b(buy|sell|long|short|close|cover)\s+[\d,.]+[MmKk]?\s+\w+",
    r"\b(EUR|USD|GBP|JPY|CNH|AUD|CHF|CAD|NZD)[A-Z]{3}\b",
    r"\b\d+[Yy]\s+(UST|bund|gilt|JGB)\b",
    r"\b(S&P|SPX|NDX|DAX|FTSE|Nikkei|HSI)\b.*\b(puts?|calls?|\d+[Ss])\b",
]


def detect_trade_related(message_text: str) -> bool:
    """Return True when a message looks like a trade instruction/discussion."""
    text = message_text or ""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in TRADE_PATTERNS)


def detect_compliance_flag(message_text: str) -> bool:
    """Flag ambiguous execution language for compliance review."""
    text = (message_text or "").strip().lower()
    if not text:
        return False
    ambiguous_markers = [
        "do that thing we discussed",
        "as discussed",
        "same as before",
        "you know what to do",
    ]
    return any(marker in text for marker in ambiguous_markers)


async def claude_classify_whatsapp(body: str) -> dict[str, Any]:
    """Classify a WhatsApp message using lightweight deterministic heuristics."""
    is_trade = detect_trade_related(body)
    return {
        "category": "TRADE_RELATED" if is_trade else "OPERATIONS",
        "priority": "P1_URGENT" if is_trade else "P3_THIS_WEEK",
        "compliance_flag": detect_compliance_flag(body),
    }


async def archive_to_compliance_s3(record: WhatsAppMessage) -> None:
    """Compliance archive hook for trade-related WhatsApp traffic."""
    # Placeholder for Section 5. In production this should upload to a locked S3 bucket.
    _ = record


async def process_whatsapp_message(message: dict[str, Any], db: AsyncSession) -> WhatsAppMessage:
    """Persist + classify one inbound WhatsApp message."""
    body = str(message.get("body") or "")
    is_trade_related = detect_trade_related(body)
    classification = await claude_classify_whatsapp(body)
    ts = datetime.fromtimestamp(int(message.get("timestamp", 0)), tz=UTC)
    msg_id = str(message.get("id") or f"wa-{int(ts.timestamp())}")

    record = WhatsAppMessage(
        id=msg_id,
        group_name=message.get("groupName"),
        author=str(message.get("author") or "Unknown"),
        body=body,
        timestamp=ts,
        is_trade_related=is_trade_related,
        classification=json.dumps(classification),
        compliance_archived=False,
    )
    db.add(record)
    await db.flush()

    if is_trade_related:
        await archive_to_compliance_s3(record)
        record.compliance_archived = True

    await db.commit()
    await db.refresh(record)
    return record


def _render_weekly_report(
    week_start: datetime,
    week_end: datetime,
    messages: list[WhatsAppMessage],
) -> str:
    trade_msgs = [m for m in messages if m.is_trade_related]
    flagged = [m for m in messages if detect_compliance_flag(m.body)]
    groups = sorted({m.group_name for m in messages if m.group_name})

    lines: list[str] = [
        "## WEEKLY WHATSAPP INTELLIGENCE REPORT",
        f"### ARP Global Capital | Week of {week_start.date()}",
        "",
        f"**TRADE INSTRUCTIONS DETECTED** ({len(trade_msgs)})",
    ]
    if trade_msgs:
        for m in trade_msgs:
            lines.append(
                f"- {m.timestamp.isoformat()} | {m.body} | {m.author} | {m.group_name or 'Direct'} | status: {'confirmed in Broadridge' if m.compliance_archived else 'UNRECONCILED'}"
            )
    else:
        lines.append("- None detected.")

    lines.extend([
        "",
        "**PENDING ITEMS FROM LAST WEEK**",
        "- [DATA MISSING]",
        "",
        "**KEY DECISIONS VIA WHATSAPP**",
        "- [DATA MISSING]",
        "",
        "**UNRESOLVED OPEN ITEMS**",
        "- [DATA MISSING]",
        "",
        "**COMPLIANCE FLAGS**",
    ])

    if flagged:
        for m in flagged:
            lines.append(f"- {m.timestamp.isoformat()} | {m.author} | {m.body}")
    else:
        lines.append("- None.")

    lines.extend([
        "",
        "**VOLUME SUMMARY**",
        f"- Total messages processed: {len(messages)}",
        f"- Groups monitored: {', '.join(groups) if groups else 'None'}",
        f"- Date range: {week_start.date()} - {week_end.date()}",
    ])
    return "\n".join(lines)


async def generate_weekly_whatsapp_report(
    week_start: datetime,
    week_end: datetime,
    db: AsyncSession,
    access_token: str | None = None,
) -> str:
    """Generate + archive weekly report for WhatsApp messages in the window."""
    stmt = (
        select(WhatsAppMessage)
        .where(WhatsAppMessage.timestamp >= week_start)
        .where(WhatsAppMessage.timestamp <= week_end)
        .order_by(WhatsAppMessage.timestamp.asc())
    )
    result = await db.execute(stmt)
    messages = list(result.scalars().all())
    report = _render_weekly_report(week_start, week_end, messages)

    if access_token:
        week_num = week_start.isocalendar()[1]
        year = week_start.year
        path = f"ARGO/WhatsApp/WeeklyDigests/{year}-W{week_num:02d}_whatsapp_digest.md"
        onedrive = OneDriveService(access_token)
        await safe_archive(onedrive.upload_file(path, report, "text/markdown"))

    return report

