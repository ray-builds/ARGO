# ARGO — Full Upgrade Plan v2.0
### For ARP Global Capital · Internal AI Operations Platform
### Prepared for Claude Code — May 2026

---

## HOW TO USE THIS DOCUMENT

This is a complete, ordered implementation plan. Work through each section sequentially. Every section contains:
- **What to build** (feature spec)
- **How to build it** (implementation pattern with code structure)
- **System prompts** (exact Claude prompts, not placeholders)
- **External APIs/libraries** to use
- **Tests** (what must pass before moving on)

Do not skip ahead. Each section builds on the previous one. When a section is complete and all its tests pass, mark it `[DONE]` and proceed.

---

## CURRENT STACK BASELINE

```
Frontend:    React (Vite or CRA)
Backend:     FastAPI (Python)
Database:    PostgreSQL on AWS RDS
Auth:        Microsoft Azure AD (MSAL)
Email:       Microsoft Graph API
Storage:     AWS S3 + OneDrive (Microsoft Graph)
AI:          Anthropic Claude (Sonnet + Haiku)
Embeddings:  OpenAI text-embedding-3-small
Infra:       AWS ECS + ECR, Terraform (Pratik's repos)
Messaging:   Twilio WhatsApp (planned)
Search:      Serper
```

---

## SECTION 0 — SYSTEM PROMPT ARCHITECTURE UPGRADE

**Do this first. Everything downstream depends on it.**

Every current prompt in ARGO is to be replaced. The principle: every token must earn its place. No filler phrases like "I'll analyze this carefully" or "Here's a summary of...". No disclaimers unless factually necessary. No hedging on things that are not genuinely uncertain. Output structure must be machine-parseable AND human-readable. Every prompt operates as if the reader is a time-constrained investment professional who will fire you if you waste their time.

### 0.1 — Master System Persona (inject into ALL module prompts)

```
SYSTEM_BASE = """
You are ARGO, the intelligence engine for ARP Global Capital — a macro discretionary 
alternative asset manager based in DIFC, Dubai. ARP manages institutional capital 
across global macro strategies including rates, FX, equities, and commodities.

Your outputs are read by portfolio managers, the CEO, and operations staff before 
market open. They have zero tolerance for vague language, false confidence, or 
irrelevant information.

Hard rules that govern every response you produce:
1. Every claim must be traceable to data you were given. If you are inferring, 
   say "inference:" not "it appears that".
2. Never fabricate market data, prices, rates, or figures. If a number is missing, 
   say "[DATA MISSING]" and flag it.
3. Use hedge fund register: long/short, basis points, P&L, attribution, tenor, 
   convexity, carry, spread. Not "goes up/down" or "might increase".
4. Prioritize by decision-relevance, not by recency or volume.
5. Format output as structured sections with exact headers. Never prose walls.
6. If something requires human judgment, label it "→ REQUIRES DECISION:" explicitly.
7. Confidence levels when analyzing: [HIGH] = directly evidenced, [MED] = inferred 
   from pattern, [LOW] = speculative but flagged for awareness.
"""
```

### 0.2 — Email Classification Prompt (replaces current)

```python
EMAIL_CLASSIFICATION_PROMPT = """
{SYSTEM_BASE}

TASK: Classify and triage one email from ARP Global Capital's inbox.

INPUT FORMAT:
- From: {sender_name} <{sender_email}>
- Subject: {subject}
- Body: {body_text}
- Attachments: {attachment_list}
- Timestamp: {timestamp}
- Thread length: {thread_count} messages

OUTPUT — return JSON with this exact schema, no prose outside the JSON:
{
  "category": one of [
    "CEO_DIRECTIVE",        // Yusuf Alireza requires action or has given instruction
    "CLIENT_COMMUNICATION", // investor, LP, or prospective client
    "COUNTERPARTY",         // broker, prime broker, bank, exchange
    "TRADE_RELATED",        // trade confirmation, allocation, settlement, margin
    "RESEARCH",             // broker research, market commentary, economic analysis
    "REGULATORY",           // compliance, legal, regulatory filing, audit
    "OPERATIONS",           // Broadridge, reconciliation, fund admin, NAV
    "INTERNAL",             // ARP team communication
    "CALENDAR",             // meeting request, schedule change
    "VENDOR",               // non-financial service provider
    "NOISE"                 // newsletters, automated alerts with no action required
  ],
  "priority": one of ["P1_URGENT", "P2_TODAY", "P3_THIS_WEEK", "P4_FYI"],
  "priority_rationale": "One sentence: exactly why this priority, referencing specific content.",
  "action_required": true or false,
  "action_owner": one of ["YUSUF", "RHYS", "AHMED", "MASIRA", "AMIN", "HAMZA", "INNES", "NASSER", "UNASSIGNED"],
  "action_owner_rationale": "Why this person.",
  "action_summary": "Imperative sentence. Exactly what must be done. Null if action_required is false.",
  "deadline": "ISO date string if explicitly stated or strongly implied, else null",
  "one_line_summary": "≤15 words. What happened. No filler.",
  "key_entities": ["list of people, companies, instruments, or amounts mentioned"],
  "sentiment": one of ["POSITIVE", "NEUTRAL", "NEGATIVE", "URGENT_NEGATIVE"],
  "contains_attachment_requiring_processing": true or false,
  "suggested_reply_needed": true or false
}
"""
```

### 0.3 — AI Reply Suggestion Prompt

```python
EMAIL_REPLY_PROMPT = """
{SYSTEM_BASE}

TASK: Draft a reply to the email below on behalf of the ARP team member specified.

SENDER CONTEXT:
- Reply from: {reply_author_name}, {reply_author_title} at ARP Global Capital
- Relationship to recipient: {relationship_context}
- Tone register: {tone} — one of [FORMAL_CLIENT, COLLEGIAL_PEER, DIRECT_INTERNAL, BRIEF_ACKNOWLEDGMENT]

ORIGINAL EMAIL:
From: {original_sender}
Subject: {subject}
Body: {body_text}

ADDITIONAL CONTEXT PROVIDED BY USER: {user_context}

DRAFT RULES:
1. Do not invent commitments, numbers, or dates the original email did not contain.
2. If a question was asked, answer it directly or clearly state it will be followed up.
3. Match the register — if they wrote 3 sentences, don't write 8.
4. Never start with "I hope this email finds you well" or any equivalent.
5. Signature block is handled separately — do not add one.
6. If the reply requires a figure, position size, or specific data you were not given, 
   insert [FILL: description of what's needed] rather than guessing.
7. Offer exactly ONE draft. Not multiple options — one tight, professional draft.

OUTPUT FORMAT:
{
  "subject": "Re: original subject (or modified if appropriate)",
  "body": "full reply body text",
  "tone_used": "description of register chosen",
  "flags": ["array of strings: anything the sender should double-check before sending"]
}
"""
```

### 0.4 — Morning Briefing Prompt

```python
MORNING_BRIEFING_PROMPT = """
{SYSTEM_BASE}

TASK: Generate ARP Global Capital's morning intelligence briefing.
This will be read by Yusuf Alireza (CEO) at approximately 06:30 Gulf Standard Time.
Be ruthlessly concise. If something is not actionable or portfolio-relevant, cut it.

INPUTS PROVIDED:
- Overnight email digest: {email_digest}
- Market moves (previous close vs prior day): {market_data}
- Economic events today: {economic_calendar}
- News headlines filtered to ARP's mandate: {news_headlines}
- Current portfolio exposures summary: {portfolio_summary}
- Pending action items not yet completed: {pending_actions}
- New research received: {new_research}

OUTPUT FORMAT — use these exact section headers:

## OVERNIGHT P&L DRIVERS
[For each asset class with material move: instrument | move in bps/% | estimated book impact]
[If portfolio data unavailable, say so explicitly and flag for Rhys/Ahmed]

## REQUIRES YOUR DECISION TODAY
[Numbered list. Only items genuinely requiring CEO input. Each item: one sentence of context + exactly what the decision is]
[If none: state "No CEO decisions required today."]

## MARKET OPEN WATCH LIST
[Max 4 items. What to monitor in the next session and why it's relevant to ARP's book]

## ECONOMIC EVENTS — IMPACT TO BOOK
[Events today with: time GST | release name | consensus | prior | estimated book sensitivity]
[If sensitivity unknown, say "sensitivity unknown — assess vs [relevant positions]"]

## EMAILS REQUIRING RESPONSE
[Only P1 + P2 items. Format: From | Subject | Required action | Suggested owner]

## RESEARCH INTEL
[New broker research: firm | title | thesis in one sentence | agree/contradicts current positioning]

## OPEN ITEMS OVERDUE
[Items past deadline from previous briefings. Escalate if >48h overdue]

---
Briefing generated: {timestamp} GST
Data freshness: emails to {email_cutoff} | market data as of {market_data_timestamp}
```

### 0.5 — Research Ingestion & Analysis Prompt

```python
RESEARCH_ANALYSIS_PROMPT = """
{SYSTEM_BASE}

TASK: Ingest and analyze a research document. Extract signal, not summary.

DOCUMENT METADATA:
- Source: {source_firm}
- Author: {author}
- Title: {title}
- Date: {date}
- Document type: {doc_type} — one of [BROKER_NOTE, ECONOMIC_RELEASE, INTERNAL_MEMO, 
  REGULATORY_FILING, CONFERENCE_TRANSCRIPT, NEWS_ARTICLE]

DOCUMENT TEXT:
{document_text}

ARP CURRENT POSITIONING CONTEXT (for contradiction/confirmation analysis):
{portfolio_context}

OUTPUT — JSON, no prose outside:
{
  "core_thesis": "≤25 words. The single argument this document makes.",
  "asset_classes_covered": ["list"],
  "instruments_mentioned": ["specific tickers, pairs, or contracts"],
  "macro_themes": ["e.g. Fed pivot, China reopening, energy transition"],
  "time_horizon": "short-term <3M | medium-term 3-12M | long-term >12M | unspecified",
  "positioning_implication": {
    "stance": one of ["BULLISH", "BEARISH", "NEUTRAL", "MIXED"],
    "target_asset": "what the view is on",
    "confidence": "[HIGH|MED|LOW] with one-line rationale"
  },
  "arp_relevance": {
    "score": 1-10,
    "rationale": "Why it is or isn't relevant to ARP's current book",
    "conflicts_with_position": true or false,
    "conflict_detail": "If true: which ARP position and how"
  },
  "key_data_points": ["statistics, figures, dates, or rates explicitly stated in the doc"],
  "recommended_action": one of [
    "SHARE_WITH_PM",     // relevant to current positions
    "ARCHIVE_MONITOR",   // not immediately relevant but worth watching
    "FLAG_TO_CEO",       // material contradiction with large position
    "ROUTINE_ARCHIVE"    // standard research, no special action
  ],
  "one_line_digest": "≤20 words. For the morning briefing research section."
}
"""
```

### 0.6 — Meeting Intelligence Prompt

```python
MEETING_INTELLIGENCE_PROMPT = """
{SYSTEM_BASE}

TASK: Extract structured intelligence from a meeting transcript or notes.

MEETING METADATA:
- Date: {meeting_date}
- Title/Subject: {meeting_title}
- Participants: {participants}
- Duration: {duration_minutes} minutes
- Meeting type: {meeting_type} — [INTERNAL_PM | CLIENT_CALL | COUNTERPARTY | BOARD | VENDOR]

TRANSCRIPT:
{transcript_text}

OUTPUT — JSON:
{
  "executive_summary": "≤50 words. What this meeting was about and what was decided.",
  "decisions_made": [
    {
      "decision": "what was decided",
      "owner": "person responsible",
      "deadline": "date or null",
      "confidence": "was this clearly agreed or tentative?"
    }
  ],
  "action_items": [
    {
      "task": "imperative sentence",
      "owner": "name",
      "deadline": "ISO date or null",
      "priority": "P1|P2|P3"
    }
  ],
  "open_questions": ["things raised but not resolved"],
  "positions_or_trades_discussed": [
    {
      "instrument": "name/ticker",
      "direction": "LONG|SHORT|CLOSE|REDUCE|ADD|DISCUSSING",
      "context": "brief context",
      "size_mentioned": "if stated, else null"
    }
  ],
  "client_signals": ["sentiment or asks from any LP/investor on the call"],
  "follow_up_emails_needed": [
    {
      "to": "recipient",
      "re": "subject/purpose",
      "owner": "who sends it",
      "deadline": "by when"
    }
  ],
  "next_meeting": {
    "date": "if mentioned, else null",
    "purpose": "null if not mentioned"
  }
}
"""
```

### 0.7 — Economic Release Impact Prompt

```python
ECONOMIC_RELEASE_PROMPT = """
{SYSTEM_BASE}

TASK: Assess the impact of an economic data release on ARP Global Capital's book.
This must be generated within 90 seconds of the data release. Be precise. No hedging 
on direction if the data is clearly bullish or bearish.

RELEASE DATA:
- Indicator: {indicator_name}
- Actual: {actual_value}
- Consensus: {consensus}
- Prior: {prior_value}
- Surprise magnitude: {surprise} ({surprise_direction} surprise)
- Release time: {release_time}

ARP PORTFOLIO EXPOSURES:
{portfolio_exposures}

HISTORICAL CONTEXT: {historical_reaction} (avg market reaction to 1σ surprise in this indicator)

OUTPUT:
## {indicator_name} — {actual_value} vs {consensus} consensus [{surprise_direction} SURPRISE]

**Immediate read:** [One sentence. Hawkish/dovish/growth-positive/negative — be direct]

**Book impact estimate:**
| Exposure | Estimated Move | Estimated P&L Impact |
[Row for each relevant position. Use [ESTIMATE] tag — not presented as exact]

**Rates:** [specific impact on duration positions, if any]
**FX:** [specific impact on currency positions, if any]  
**Equity:** [if relevant]

**Next catalyst:** [what to watch next on this theme]

**Confidence in this assessment:** [HIGH/MED/LOW] — [one-line rationale]

⚠️ This is a real-time model estimate, not a confirmed P&L. Verify with Rhys/Ahmed.
"""
```

### 0.8 — WhatsApp Weekly Report Prompt

```python
WHATSAPP_REPORT_PROMPT = """
{SYSTEM_BASE}

TASK: Generate the weekly WhatsApp communication report for ARP Global Capital.
This covers the week {week_start} to {week_end}.

WHATSAPP DATA:
{whatsapp_messages_json}

COMPLIANCE NOTE: This report is for internal operational review. All trade-related 
communications are separately archived for compliance.

OUTPUT FORMAT:

## WEEKLY WHATSAPP INTELLIGENCE REPORT
### ARP Global Capital | Week of {week_start}

**TRADE INSTRUCTIONS DETECTED** ({trade_count})
[For each: timestamp | instruction text | parties | instrument if identifiable | status: confirmed in Broadridge / UNRECONCILED]

**PENDING ITEMS FROM LAST WEEK** 
[Items mentioned last week with no apparent resolution]

**KEY DECISIONS VIA WHATSAPP**
[Non-trade decisions or strategy discussions, max 5]

**UNRESOLVED OPEN ITEMS**
[Questions asked, tasks assigned, commitments made — that have no reply/completion]

**COMPLIANCE FLAGS** ⚠️
[Any communication that may need compliance review: unclear instructions, sensitive 
disclosures, external party discussions about portfolio positions]

**VOLUME SUMMARY**
- Total messages processed: {total_messages}
- Groups monitored: {groups_list}
- Date range: {week_start} – {week_end}
"""
```

---

## SECTION 1 — AUTO-SYNC: KILL THE MANUAL SYNC BUTTON

**Problem:** Users must click "Synchronize" to fetch new emails. Unacceptable.  
**Solution:** Microsoft Graph Change Notifications (webhooks) + fallback polling.

### 1.1 — Backend: Graph Webhook Service

**File:** `backend/services/graph_webhook_service.py`

```python
# PURPOSE: Register Microsoft Graph subscription and handle push notifications
# for new emails, calendar events, and OneDrive changes.

import httpx
from datetime import datetime, timedelta
from backend.db import get_db
from backend.services.email_processor import process_incoming_email

GRAPH_SUBSCRIPTION_ENDPOINT = "https://graph.microsoft.com/v1.0/subscriptions"

RESOURCES_TO_WATCH = [
    {
        "resource": "me/mailFolders('Inbox')/messages",
        "changeTypes": ["created"],
        "clientState": "ARGO_EMAIL_WEBHOOK_SECRET"  # store in env
    },
    {
        "resource": "me/events",
        "changeTypes": ["created", "updated"],
        "clientState": "ARGO_CALENDAR_WEBHOOK_SECRET"
    }
]

async def register_subscriptions(access_token: str):
    """
    Call on app startup and every 3 days (Graph subscriptions expire after 4320 minutes).
    Store subscription IDs in DB for renewal.
    """
    async with httpx.AsyncClient() as client:
        for resource in RESOURCES_TO_WATCH:
            payload = {
                "changeType": ",".join(resource["changeTypes"]),
                "notificationUrl": f"{ARGO_BASE_URL}/api/webhooks/graph",
                "resource": resource["resource"],
                "expirationDateTime": (datetime.utcnow() + timedelta(days=3)).isoformat() + "Z",
                "clientState": resource["clientState"]
            }
            response = await client.post(
                GRAPH_SUBSCRIPTION_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            # Store subscription.id in DB for renewal tracking


async def handle_webhook_notification(notification: dict, db):
    """
    Called by POST /api/webhooks/graph
    Validates clientState, then triggers appropriate processor.
    """
    # Validate
    if notification.get("clientState") not in [r["clientState"] for r in RESOURCES_TO_WATCH]:
        raise ValueError("Invalid clientState — possible spoofed webhook")
    
    resource_data = notification.get("resourceData", {})
    
    if "messages" in notification.get("resource", ""):
        email_id = resource_data.get("id")
        await process_incoming_email(email_id, db)
    elif "events" in notification.get("resource", ""):
        await process_calendar_event(resource_data, db)
```

**File:** `backend/api/webhooks.py`

```python
from fastapi import APIRouter, Request, Response, Depends
from backend.services.graph_webhook_service import handle_webhook_notification

router = APIRouter(prefix="/webhooks")

@router.post("/graph")
async def graph_webhook(request: Request, db=Depends(get_db)):
    """
    Microsoft Graph sends a validation request first (GET with validationToken).
    Then sends POST notifications.
    """
    # Handle Graph validation challenge
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return Response(content=validation_token, media_type="text/plain")
    
    body = await request.json()
    for notification in body.get("value", []):
        await handle_webhook_notification(notification, db)
    
    return Response(status_code=202)
```

**Fallback:** Add a background task that runs every 5 minutes via APScheduler for any missed notifications:

```python
# backend/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("interval", minutes=5, id="email_fallback_sync")
async def fallback_email_sync():
    """Catch any emails that slipped past webhooks."""
    await sync_emails_since_last_check()

@scheduler.scheduled_job("cron", hour=6, minute=0, timezone="Asia/Dubai", id="morning_brief")
async def morning_brief_job():
    await generate_and_deliver_morning_briefing()

@scheduler.scheduled_job("cron", day_of_week="sun", hour=20, minute=0, timezone="Asia/Dubai", id="weekly_report")
async def weekly_report_job():
    await generate_weekly_whatsapp_report()
    await generate_weekly_performance_report()
```

### 1.2 — Frontend: Remove the Sync Button

In your inbox component, replace the sync button with a real-time WebSocket connection to the backend that pushes new email notifications instantly:

```javascript
// frontend/src/hooks/useRealtimeInbox.js
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

export function useRealtimeInbox() {
  const queryClient = useQueryClient();
  
  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE_URL}/api/ws/inbox`);
    
    ws.onmessage = (event) => {
      const { type, data } = JSON.parse(event.data);
      
      if (type === "NEW_EMAIL") {
        // Optimistically prepend new email to inbox
        queryClient.setQueryData(["inbox"], (old) => ({
          ...old,
          emails: [data, ...(old?.emails || [])]
        }));
        // Show toast notification
        showNotification(`New email: ${data.one_line_summary}`);
      }
      
      if (type === "EMAIL_CLASSIFIED") {
        // Update the email classification badge in place
        queryClient.invalidateQueries(["inbox"]);
      }
    };
    
    return () => ws.close();
  }, []);
}
```

### 1.3 — Tests for Section 1

```python
# tests/test_auto_sync.py

async def test_graph_webhook_validation():
    """Graph sends GET with validationToken — must echo it back as text/plain."""
    response = await client.get("/api/webhooks/graph?validationToken=TEST123")
    assert response.status_code == 200
    assert response.text == "TEST123"
    assert response.headers["content-type"] == "text/plain"

async def test_webhook_processes_new_email():
    """Receiving a valid Graph notification triggers email processing."""
    payload = {
        "value": [{
            "resource": "me/mailFolders('Inbox')/messages/AAA111",
            "clientState": "ARGO_EMAIL_WEBHOOK_SECRET",
            "resourceData": {"id": "AAA111", "@odata.type": "#Microsoft.Graph.Message"}
        }]
    }
    with mock.patch("backend.services.email_processor.process_incoming_email") as mock_proc:
        response = await client.post("/api/webhooks/graph", json=payload)
        assert response.status_code == 202
        mock_proc.assert_called_once_with("AAA111", ANY)

async def test_invalid_client_state_rejected():
    """Webhook with wrong clientState must be rejected — security."""
    payload = {
        "value": [{"clientState": "WRONG_SECRET", "resource": "me/messages/X"}]
    }
    response = await client.post("/api/webhooks/graph", json=payload)
    assert response.status_code in [400, 401]

async def test_fallback_sync_runs():
    """Background job executes without exception."""
    await fallback_email_sync()  # Should not raise

async def test_subscription_renewal_before_expiry():
    """Subscriptions created >3 days ago should be renewed."""
    # Seed DB with an expired subscription
    # Run renewal check
    # Assert new subscription ID stored
```

---

## SECTION 2 — ONEDRIVE FULL INTEGRATION

**Every output ARGO generates must be archived to OneDrive automatically.**

### 2.1 — OneDrive Folder Structure

```
/ARGO/
├── Emails/
│   ├── {YYYY}/
│   │   └── {MM}/
│   │       └── {email_id}_{subject_slug}.json
├── MorningBriefings/
│   └── {YYYY-MM-DD}_morning_brief.md
├── Meetings/
│   ├── Transcripts/
│   │   └── {YYYY-MM-DD}_{meeting_title_slug}.txt
│   └── Summaries/
│       └── {YYYY-MM-DD}_{meeting_title_slug}_summary.json
├── Research/
│   ├── BrokerNotes/
│   ├── InternalMemos/
│   ├── EconomicReleases/
│   └── NewsClips/
├── WeeklyReports/
│   └── {YYYY-WNN}_weekly_report.md
└── WhatsApp/
    ├── Archive/
    │   └── {YYYY-MM-DD}_{group_name}.json
    └── WeeklyDigests/
        └── {YYYY-WNN}_whatsapp_digest.md
```

### 2.2 — OneDrive Service

**File:** `backend/services/onedrive_service.py`

```python
import httpx
import json
from pathlib import PurePosixPath

GRAPH_DRIVE_BASE = "https://graph.microsoft.com/v1.0/me/drive"

class OneDriveService:
    def __init__(self, access_token: str):
        self.token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}
    
    async def ensure_folder(self, path: str) -> str:
        """
        Create folder hierarchy if it doesn't exist.
        Returns the folder ID.
        path = "ARGO/Emails/2026/05"
        """
        parts = path.strip("/").split("/")
        parent_id = "root"
        
        async with httpx.AsyncClient() as client:
            for part in parts:
                url = f"{GRAPH_DRIVE_BASE}/items/{parent_id}/children"
                params = {"$filter": f"name eq '{part}' and folder ne null"}
                r = await client.get(url, headers=self.headers, params=params)
                items = r.json().get("value", [])
                
                if items:
                    parent_id = items[0]["id"]
                else:
                    # Create folder
                    payload = {"name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"}
                    r = await client.post(url, headers=self.headers, json=payload)
                    parent_id = r.json()["id"]
        
        return parent_id
    
    async def upload_file(self, path: str, content: str | bytes, content_type: str = "application/json"):
        """
        Upload file to OneDrive at the given path.
        path = "ARGO/MorningBriefings/2026-05-14_morning_brief.md"
        Creates parent folders if needed.
        """
        folder_path = str(PurePosixPath(path).parent)
        filename = PurePosixPath(path).name
        folder_id = await self.ensure_folder(folder_path)
        
        if isinstance(content, str):
            content = content.encode("utf-8")
        
        async with httpx.AsyncClient() as client:
            url = f"{GRAPH_DRIVE_BASE}/items/{folder_id}:/{filename}:/content"
            r = await client.put(
                url,
                headers={**self.headers, "Content-Type": content_type},
                content=content
            )
            return r.json()
    
    async def archive_email(self, email_data: dict):
        """Archive a processed email to OneDrive."""
        from datetime import datetime
        ts = datetime.fromisoformat(email_data["timestamp"])
        path = f"ARGO/Emails/{ts.year}/{ts.month:02d}/{email_data['id']}_{slugify(email_data['subject'][:40])}.json"
        await self.upload_file(path, json.dumps(email_data, indent=2))
    
    async def archive_morning_brief(self, brief_text: str, date: str):
        path = f"ARGO/MorningBriefings/{date}_morning_brief.md"
        await self.upload_file(path, brief_text, "text/markdown")
```

### 2.3 — Tests for Section 2

```python
async def test_ensure_folder_creates_hierarchy():
    """Creates nested folders that don't exist."""
    folder_id = await onedrive_service.ensure_folder("ARGO/Test/Nested")
    assert folder_id is not None

async def test_upload_and_retrieve_file():
    """Uploaded file content matches what was uploaded."""
    content = '{"test": "value", "timestamp": "2026-05-14"}'
    await onedrive_service.upload_file("ARGO/Test/test_upload.json", content)
    # Fetch back and compare
    fetched = await onedrive_service.get_file_content("ARGO/Test/test_upload.json")
    assert json.loads(fetched) == json.loads(content)

async def test_email_archive_path_correct():
    """Archived email lands in correct year/month folder."""
    email = {"id": "AAA", "timestamp": "2026-05-14T08:00:00Z", "subject": "Test Email"}
    await onedrive_service.archive_email(email)
    # Check file exists at ARGO/Emails/2026/05/AAA_test-email.json

async def test_morning_brief_archived():
    """Morning brief .md file appears in MorningBriefings folder."""
    await onedrive_service.archive_morning_brief("# Test Brief", "2026-05-14")
    # Assert file exists
```

---

## SECTION 3 — EMAIL REPLY BUTTON WITH AI SUGGESTIONS

### 3.1 — Backend Endpoint

**File:** `backend/api/emails.py` — add to existing email router:

```python
@router.post("/{email_id}/reply-suggestion")
async def get_reply_suggestion(
    email_id: str,
    request: ReplySuggestionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate an AI reply draft for an email.
    
    Body params:
    - reply_author: which ARP team member is replying
    - tone: FORMAL_CLIENT | COLLEGIAL_PEER | DIRECT_INTERNAL | BRIEF_ACKNOWLEDGMENT
    - user_context: optional additional context from the user
    """
    email = await get_email_by_id(email_id, current_user.access_token)
    classification = db.query(EmailClassification).filter_by(email_id=email_id).first()
    
    prompt = EMAIL_REPLY_PROMPT.format(
        reply_author_name=current_user.display_name,
        reply_author_title=current_user.job_title,
        relationship_context=infer_relationship(email["from"], classification),
        tone=request.tone,
        original_sender=email["from"]["emailAddress"]["address"],
        subject=email["subject"],
        body_text=strip_html_and_signatures(email["body"]["content"]),
        user_context=request.user_context or "None provided"
    )
    
    response = await claude_client.complete(
        model="claude-sonnet-4-20250514",
        system=SYSTEM_BASE,
        prompt=prompt
    )
    
    suggestion = json.loads(response.content[0].text)
    
    # Save draft to Graph as a draft email (not yet sent)
    draft_id = await create_email_draft(
        email_id=email_id,
        subject=suggestion["subject"],
        body=suggestion["body"],
        access_token=current_user.access_token
    )
    
    return {
        "suggestion": suggestion,
        "graph_draft_id": draft_id
    }


@router.post("/{email_id}/send-reply")
async def send_reply(
    email_id: str,
    request: SendReplyRequest,  # body: str, subject: str
    current_user: User = Depends(get_current_user)
):
    """Send a reply using the Graph API sendReply endpoint."""
    await graph_send_reply(
        email_id=email_id,
        body=request.body,
        access_token=current_user.access_token
    )
    return {"status": "sent"}
```

### 3.2 — Frontend: Inbox Reply UI

**File:** `frontend/src/components/InboxEmailRow.jsx`

Add to each email row. The reply panel slides in from the right or expands inline:

```jsx
// ReplyPanel.jsx
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

export function ReplyPanel({ email, onClose }) {
  const [tone, setTone] = useState("COLLEGIAL_PEER");
  const [userContext, setUserContext] = useState("");
  const [editedDraft, setEditedDraft] = useState("");
  const [step, setStep] = useState("config"); // config → generating → editing → sent

  const suggestionMutation = useMutation({
    mutationFn: () => api.post(`/emails/${email.id}/reply-suggestion`, { tone, user_context: userContext }),
    onSuccess: (data) => {
      setEditedDraft(data.suggestion.body);
      setStep("editing");
    }
  });

  const sendMutation = useMutation({
    mutationFn: () => api.post(`/emails/${email.id}/send-reply`, {
      body: editedDraft,
      subject: `Re: ${email.subject}`
    }),
    onSuccess: () => setStep("sent")
  });

  return (
    <div className="reply-panel">
      {step === "config" && (
        <>
          <div className="reply-panel__original">
            <strong>Replying to:</strong> {email.from} — {email.subject}
          </div>
          <label>Tone</label>
          <select value={tone} onChange={e => setTone(e.target.value)}>
            <option value="FORMAL_CLIENT">Formal (Client)</option>
            <option value="COLLEGIAL_PEER">Collegial (Peer)</option>
            <option value="DIRECT_INTERNAL">Direct (Internal)</option>
            <option value="BRIEF_ACKNOWLEDGMENT">Brief Acknowledgment</option>
          </select>
          <label>Additional context for AI (optional)</label>
          <textarea
            placeholder="e.g. 'we agreed on this in last Thursday's call'"
            value={userContext}
            onChange={e => setUserContext(e.target.value)}
          />
          <button onClick={() => { setStep("generating"); suggestionMutation.mutate(); }}>
            Generate AI Draft
          </button>
        </>
      )}

      {step === "generating" && <div className="spinner">Drafting reply...</div>}

      {step === "editing" && (
        <>
          <div className="reply-panel__flags">
            {suggestionMutation.data?.suggestion?.flags?.map(f => (
              <div key={f} className="flag-warning">⚠️ {f}</div>
            ))}
          </div>
          <textarea
            className="reply-panel__editor"
            value={editedDraft}
            onChange={e => setEditedDraft(e.target.value)}
            rows={12}
          />
          <div className="reply-panel__actions">
            <button onClick={() => suggestionMutation.mutate()}>Regenerate</button>
            <button className="btn-primary" onClick={() => sendMutation.mutate()}>
              Send Reply
            </button>
          </div>
        </>
      )}

      {step === "sent" && <div className="success-state">Reply sent ✓</div>}
    </div>
  );
}
```

**Add reply button to each email row:**

```jsx
// In InboxEmailRow.jsx, add:
const [showReply, setShowReply] = useState(false);

// In the row actions area:
<button 
  className="btn-icon reply-btn" 
  onClick={(e) => { e.stopPropagation(); setShowReply(true); }}
  title="Reply with AI assistance"
>
  ↩ Reply
</button>

{showReply && (
  <ReplyPanel email={email} onClose={() => setShowReply(false)} />
)}
```

### 3.3 — Tests for Section 3

```python
async def test_reply_suggestion_returns_valid_draft():
    """AI suggestion is valid JSON with required fields."""
    response = await client.post(f"/api/emails/{TEST_EMAIL_ID}/reply-suggestion", json={
        "tone": "COLLEGIAL_PEER",
        "user_context": ""
    })
    assert response.status_code == 200
    data = response.json()
    assert "suggestion" in data
    assert "body" in data["suggestion"]
    assert "subject" in data["suggestion"]
    assert len(data["suggestion"]["body"]) > 20

async def test_reply_does_not_invent_numbers():
    """AI reply to an email without figures should not contain fabricated figures."""
    # Use an email with no financial figures in body
    response = await client.post(f"/api/emails/{EMAIL_NO_FIGURES_ID}/reply-suggestion", json={
        "tone": "FORMAL_CLIENT", "user_context": ""
    })
    body = response.json()["suggestion"]["body"]
    # Should not contain dollar amounts or percentages not in original email
    import re
    figures = re.findall(r'\$[\d,]+|\d+%|\d+bps', body)
    assert len(figures) == 0  # Unless the test email contained figures

async def test_reply_tone_affects_output():
    """Different tones produce meaningfully different drafts."""
    formal = await get_suggestion(EMAIL_ID, "FORMAL_CLIENT")
    brief = await get_suggestion(EMAIL_ID, "BRIEF_ACKNOWLEDGMENT")
    assert len(brief["body"]) < len(formal["body"])

async def test_send_reply_calls_graph():
    """Send reply triggers Microsoft Graph sendReply API."""
    with mock.patch("backend.services.graph_service.send_reply") as mock_send:
        await client.post(f"/api/emails/{TEST_EMAIL_ID}/send-reply", json={
            "body": "Test reply body", "subject": "Re: Test"
        })
        mock_send.assert_called_once()
```

---

## SECTION 4 — TEAMS MEETING AUTO-TRANSCRIPTION FROM ONEDRIVE

**Goal:** Every Microsoft Teams meeting recording that appears in the user's OneDrive `Recordings` folder is automatically detected, transcribed (if no transcript available), processed through Meeting Intelligence, and saved to `/ARGO/Meetings/`.

### 4.1 — How Teams Stores Recordings

Teams recordings are saved to: `OneDrive/Recordings/{meeting_title}_{date}.mp4`
Teams transcripts (VTT format, when enabled): `OneDrive/Recordings/{meeting_title}_{date}.vtt`

We monitor the `/Recordings` folder via Graph change notifications.

### 4.2 — Recording Watcher Service

**File:** `backend/services/teams_recording_service.py`

```python
import httpx
import re
from datetime import datetime

RECORDINGS_FOLDER_PATH = "Recordings"

async def register_recordings_watcher(access_token: str):
    """
    Subscribe to OneDrive /Recordings folder changes.
    When a new .mp4 or .vtt appears, trigger processing.
    """
    async with httpx.AsyncClient() as client:
        payload = {
            "changeType": "created,updated",
            "notificationUrl": f"{ARGO_BASE_URL}/api/webhooks/onedrive-recordings",
            "resource": f"/me/drive/root:/{RECORDINGS_FOLDER_PATH}:/children",
            "expirationDateTime": get_expiry_3_days(),
            "clientState": "ARGO_RECORDINGS_SECRET"
        }
        r = await client.post(
            "https://graph.microsoft.com/v1.0/subscriptions",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        return r.json()


async def process_new_recording(file_info: dict, access_token: str, db):
    """
    Called when a new file appears in /Recordings.
    
    Strategy:
    1. Check if a .vtt transcript exists alongside the .mp4 → prefer it (free, instant)
    2. If no .vtt, download .mp4 and transcribe with Whisper
    3. Parse transcript into clean text
    4. Run Meeting Intelligence prompt
    5. Save results to DB + OneDrive
    6. Post summary to Teams channel
    """
    filename = file_info["name"]
    file_id = file_info["id"]
    
    if not (filename.endswith(".mp4") or filename.endswith(".vtt")):
        return  # Not a recording file
    
    meeting_slug = extract_meeting_name(filename)
    meeting_date = extract_meeting_date(filename)
    
    # Check for companion VTT file (Teams auto-generated transcript)
    vtt_content = await find_companion_vtt(meeting_slug, access_token)
    
    if vtt_content:
        transcript_text = parse_vtt_to_plain_text(vtt_content)
        transcription_method = "teams_vtt"
    elif filename.endswith(".mp4"):
        # Download and transcribe with Whisper
        audio_content = await download_recording(file_id, access_token)
        transcript_text = await transcribe_with_whisper(audio_content)
        transcription_method = "whisper"
    else:
        return  # It was the .vtt itself, wait for the .mp4 event or process directly
    
    # Extract participants from the transcript or calendar event
    participants = await extract_participants_from_calendar(meeting_slug, meeting_date, access_token)
    
    # Run Meeting Intelligence
    summary = await run_meeting_intelligence(
        transcript_text=transcript_text,
        meeting_title=meeting_slug,
        meeting_date=meeting_date,
        participants=participants
    )
    
    # Archive to OneDrive
    onedrive = OneDriveService(access_token)
    await onedrive.upload_file(
        f"ARGO/Meetings/Transcripts/{meeting_date}_{slugify(meeting_slug)}.txt",
        transcript_text
    )
    await onedrive.upload_file(
        f"ARGO/Meetings/Summaries/{meeting_date}_{slugify(meeting_slug)}_summary.json",
        json.dumps(summary, indent=2)
    )
    
    # Save to DB
    await save_meeting_summary(db, summary, meeting_date, meeting_slug, transcription_method)
    
    # Post to Teams channel (if configured)
    await post_meeting_summary_to_teams(summary, access_token)
    
    return summary


def parse_vtt_to_plain_text(vtt_content: str) -> str:
    """
    Convert WebVTT format to plain readable transcript with speaker labels.
    VTT format: timestamps → cue text with optional <v SpeakerName> tags
    """
    lines = vtt_content.split("\n")
    transcript_lines = []
    current_speaker = "Unknown"
    
    for line in lines:
        # Speaker tag: <v Yusuf Alireza>text here
        speaker_match = re.search(r'<v ([^>]+)>', line)
        if speaker_match:
            current_speaker = speaker_match.group(1)
            text = re.sub(r'<[^>]+>', '', line).strip()  # Remove all tags
            if text:
                transcript_lines.append(f"{current_speaker}: {text}")
        elif line and not line.startswith("WEBVTT") and not "-->" in line and not line.isdigit():
            clean = re.sub(r'<[^>]+>', '', line).strip()
            if clean:
                transcript_lines.append(clean)
    
    return "\n".join(transcript_lines)


async def transcribe_with_whisper(audio_bytes: bytes) -> str:
    """Transcribe audio via OpenAI Whisper API."""
    import openai
    client = openai.AsyncOpenAI()
    
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name
    
    with open(tmp_path, "rb") as audio_file:
        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"]
        )
    
    os.unlink(tmp_path)
    return response.text
```

### 4.3 — Webhook for Recordings

**File:** `backend/api/webhooks.py` — add:

```python
@router.post("/onedrive-recordings")
async def onedrive_recordings_webhook(request: Request, db=Depends(get_db)):
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return Response(content=validation_token, media_type="text/plain")
    
    body = await request.json()
    for notification in body.get("value", []):
        if notification.get("clientState") != "ARGO_RECORDINGS_SECRET":
            continue
        file_info = notification.get("resourceData", {})
        asyncio.create_task(process_new_recording(file_info, get_service_token(), db))
    
    return Response(status_code=202)
```

### 4.4 — Frontend: Meetings Tab

Add a `Meetings` tab to the ARGO navigation with:
- List of all processed meetings (date, title, participant count)
- Click to expand: full AI summary, action items, decisions
- Action item → assign to Planner button
- "View Transcript" drawer
- Manual upload fallback (drag-and-drop a .txt, .vtt, or .mp4)

### 4.5 — Tests for Section 4

```python
async def test_vtt_parsing_preserves_speakers():
    vtt = """WEBVTT\n\n1\n00:00:00.000 --> 00:00:05.000\n<v Yusuf>Good morning everyone."""
    result = parse_vtt_to_plain_text(vtt)
    assert "Yusuf: Good morning everyone." in result

async def test_recording_watcher_ignores_non_meeting_files():
    """Only .mp4 and .vtt files should trigger processing."""
    non_meeting = {"name": "report.docx", "id": "XYZ"}
    result = await process_new_recording(non_meeting, "token", db_mock)
    assert result is None

async def test_meeting_summary_saved_to_onedrive():
    """After processing, summary JSON appears in ARGO/Meetings/Summaries/"""
    # Use a short test transcript
    with mock.patch.object(OneDriveService, "upload_file") as mock_upload:
        await process_new_recording(test_vtt_file_info, token, db)
        upload_calls = [c.args[0] for c in mock_upload.call_args_list]
        assert any("ARGO/Meetings/Summaries" in p for p in upload_calls)

async def test_action_items_extracted():
    """Meeting with clear action items should have them in output."""
    transcript = "Yusuf: Rhys please reconcile the Broadridge positions by Friday."
    summary = await run_meeting_intelligence(transcript, "Test Meeting", "2026-05-14", ["Yusuf", "Rhys"])
    assert any("Rhys" in item["owner"] for item in summary["action_items"])
    assert any("Broadridge" in item["task"] for item in summary["action_items"])

async def test_whisper_fallback_when_no_vtt():
    """Falls back to Whisper when no VTT companion file exists."""
    with mock.patch("backend.services.teams_recording_service.find_companion_vtt", return_value=None):
        with mock.patch("backend.services.teams_recording_service.transcribe_with_whisper") as mock_whisper:
            mock_whisper.return_value = "Test transcript"
            await process_new_recording(mp4_file_info, token, db)
            mock_whisper.assert_called_once()
```

---

## SECTION 5 — WHATSAPP INGESTION + WEEKLY REPORTS

### 5.1 — WhatsApp Integration Options (choose based on ARP's setup)

**Option A — WhatsApp Business API (Meta Cloud API)**
Best for: ARP has a registered business phone number
- Use `requests` or `httpx` to call `https://graph.facebook.com/v18.0/{phone_number_id}/messages`
- Webhook receives incoming messages
- Requires Meta Business account + phone number verification

**Option B — whatsapp-web.js Bridge (personal accounts)**
Best for: Team uses personal WhatsApp accounts
- Node.js service that bridges WhatsApp Web via Puppeteer
- Deploy as a sidecar container on ECS
- Exposes REST API to FastAPI

**Implementation — Option B Bridge:**

```javascript
// whatsapp-bridge/index.js
const { Client, LocalAuth } = require('whatsapp-web.js');
const express = require('express');
const app = express();
app.use(express.json());

const client = new Client({ authStrategy: new LocalAuth() });

// Store messages in memory + POST to ARGO backend
client.on('message', async (msg) => {
  const payload = {
    id: msg.id._serialized,
    from: msg.from,
    to: msg.to,
    body: msg.body,
    timestamp: msg.timestamp,
    author: msg.author || msg.from,
    isGroup: msg.from.endsWith('@g.us'),
    groupName: msg.from.endsWith('@g.us') ? 
      (await msg.getChat()).name : null
  };
  
  await fetch(`${ARGO_BACKEND_URL}/api/whatsapp/incoming`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Bridge-Secret': BRIDGE_SECRET },
    body: JSON.stringify(payload)
  });
});

// Endpoint to fetch message history for a group
app.get('/messages/:groupId', async (req, res) => {
  const chat = await client.getChatById(req.params.groupId);
  const messages = await chat.fetchMessages({ limit: 500 });
  res.json(messages.map(m => ({
    id: m.id._serialized,
    body: m.body,
    timestamp: m.timestamp,
    author: m.author || m.from
  })));
});

client.initialize();
app.listen(3001);
```

### 5.2 — Backend WhatsApp Processor

**File:** `backend/services/whatsapp_service.py`

```python
import re
from datetime import datetime, timedelta

TRADE_PATTERNS = [
    r'\b(buy|sell|long|short|close|cover)\s+[\d,\.]+[MmKk]?\s+\w+',
    r'\b(EUR|USD|GBP|JPY|CNH|AUD|CHF|CAD|NZD)[A-Z]{3}\b',
    r'\b\d+[Yy]\s+(UST|bund|gilt|JGB)\b',
    r'\b(S&P|SPX|NDX|DAX|FTSE|Nikkei|HSI)\b.*\b(puts?|calls?|\d+[Ss])\b',
]

async def process_whatsapp_message(message: dict, db):
    """
    Classify each incoming WhatsApp message.
    Save to DB. Flag trade-related for compliance archive.
    """
    body = message["body"]
    
    is_trade_related = any(re.search(p, body, re.IGNORECASE) for p in TRADE_PATTERNS)
    
    classification = await claude_classify_whatsapp(body)
    
    record = WhatsAppMessage(
        id=message["id"],
        group_name=message.get("groupName"),
        author=message["author"],
        body=body,
        timestamp=datetime.fromtimestamp(message["timestamp"]),
        is_trade_related=is_trade_related,
        classification=classification,
        compliance_archived=False
    )
    
    db.add(record)
    
    if is_trade_related:
        await archive_to_compliance_s3(record)
        record.compliance_archived = True
    
    db.commit()


async def generate_weekly_whatsapp_report(week_start: datetime, week_end: datetime, db) -> str:
    """Generate the weekly WhatsApp digest. Called by scheduler every Sunday 8pm GST."""
    messages = db.query(WhatsAppMessage).filter(
        WhatsAppMessage.timestamp >= week_start,
        WhatsAppMessage.timestamp <= week_end
    ).order_by(WhatsAppMessage.timestamp).all()
    
    messages_json = [
        {
            "time": m.timestamp.isoformat(),
            "group": m.group_name,
            "author": m.author,
            "text": m.body,
            "is_trade_related": m.is_trade_related
        }
        for m in messages
    ]
    
    prompt = WHATSAPP_REPORT_PROMPT.format(
        week_start=week_start.date(),
        week_end=week_end.date(),
        whatsapp_messages_json=json.dumps(messages_json, indent=2),
        trade_count=sum(1 for m in messages if m.is_trade_related)
    )
    
    report = await claude_complete(SYSTEM_BASE + prompt)
    
    # Archive to OneDrive
    week_num = week_start.isocalendar()[1]
    year = week_start.year
    await onedrive.upload_file(
        f"ARGO/WhatsApp/WeeklyDigests/{year}-W{week_num:02d}_whatsapp_digest.md",
        report
    )
    
    # Email to Yusuf + Rhys
    await send_email_via_graph(
        to=["yusuf@arpglobal.com", "rhys@arpglobal.com"],
        subject=f"ARGO | WhatsApp Weekly Report — W{week_num} {year}",
        body=report
    )
    
    return report
```

### 5.3 — Tests for Section 5

```python
async def test_trade_pattern_detection():
    trade_messages = [
        "buy 10M EURUSD at 1.0850",
        "short 5Y UST at 4.32",
        "close the S&P puts",
        "long 2M GBPUSD from here"
    ]
    non_trade_messages = [
        "see you at the meeting",
        "ok got it",
        "what time is dinner?"
    ]
    for msg in trade_messages:
        assert detect_trade_related(msg) == True, f"Should be trade: {msg}"
    for msg in non_trade_messages:
        assert detect_trade_related(msg) == False, f"Should NOT be trade: {msg}"

async def test_trade_messages_archived_to_s3():
    with mock.patch("backend.services.whatsapp_service.archive_to_compliance_s3") as mock_s3:
        await process_whatsapp_message({
            "id": "1", "body": "buy 10M EURUSD at 1.0850",
            "author": "Yusuf", "timestamp": 1715680000, "groupName": "Trading"
        }, db)
        mock_s3.assert_called_once()

async def test_weekly_report_includes_all_days():
    """Report covers all 7 days of the week, not just days with messages."""
    report = await generate_weekly_whatsapp_report(week_start, week_end, db)
    assert week_start.strftime("%Y-%m-%d") in report
    assert week_end.strftime("%Y-%m-%d") in report

async def test_compliance_flag_in_report():
    """Ambiguous instructions appear in COMPLIANCE FLAGS section."""
    # Seed a message with unclear instruction
    await process_whatsapp_message({"body": "yeah do that thing we discussed", ...}, db)
    report = await generate_weekly_whatsapp_report(...)
    assert "COMPLIANCE FLAGS" in report
```

---

## SECTION 6 — RESEARCH LAKE UPGRADE

### 6.1 — Auto-Ingestion Sources

Install these libraries:

```
pip install feedparser yfinance newsapi-python sec-edgar-api python-docx
```

**File:** `backend/services/research_ingestion_service.py`

```python
# AUTO-INGESTION SOURCES

# 1. Broker research from email attachments
async def ingest_from_email_attachments(db, access_token):
    """
    Monitor inbox for emails from known broker domains.
    Extract PDF attachments and push to research pipeline.
    """
    BROKER_DOMAINS = [
        "gs.com", "jpmorgan.com", "ubs.com", "ms.com", "citi.com",
        "barclays.com", "deutsche-bank.com", "morganstanley.com",
        "bofa.com", "nomura.com", "macquarie.com", "hsbc.com"
    ]
    # Query emails from last 24h with attachments from broker domains
    # For each PDF attachment → extract text → run RESEARCH_ANALYSIS_PROMPT


# 2. Free macro data feeds
RSS_FEEDS = {
    "BIS Research": "https://www.bis.org/rss/index.htm",
    "IMF Blog": "https://www.imf.org/en/Blogs/rss",
    "Fed Research": "https://www.federalreserve.gov/feeds/research.xml",
    "ECB Research": "https://www.ecb.europa.eu/pub/research/rss.html",
    "NBER Working Papers": "https://www.nber.org/rss/new_working_papers.rss",
}

async def ingest_rss_feeds():
    import feedparser
    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:  # last 10 entries
            existing = db.query(ResearchDoc).filter_by(source_url=entry.link).first()
            if not existing:
                await process_research_document({
                    "source": source,
                    "title": entry.title,
                    "url": entry.link,
                    "content": entry.get("summary", ""),
                    "date": entry.get("published", datetime.now().isoformat())
                })


# 3. News API (financial news only)
async def ingest_financial_news():
    from newsapi import NewsApiClient
    newsapi = NewsApiClient(api_key=NEWSAPI_KEY)
    
    # ARP mandate-relevant keywords
    KEYWORDS = [
        "macro hedge fund", "Federal Reserve", "ECB", "PBOC",
        "emerging markets", "FX volatility", "rates", "inflation",
        "geopolitical risk", "commodity prices"
    ]
    
    for keyword in KEYWORDS:
        articles = newsapi.get_everything(
            q=keyword,
            language="en",
            sort_by="publishedAt",
            from_param=(datetime.now() - timedelta(hours=24)).isoformat(),
            page_size=5
        )
        for article in articles.get("articles", []):
            await process_research_document({
                "source": article["source"]["name"],
                "title": article["title"],
                "url": article["url"],
                "content": article.get("content", article.get("description", "")),
                "date": article["publishedAt"]
            })


# 4. Yahoo Finance for position context
async def get_instrument_data(tickers: list[str]) -> dict:
    import yfinance as yf
    data = {}
    for ticker in tickers:
        t = yf.Ticker(ticker)
        info = t.info
        hist = t.history(period="5d")
        data[ticker] = {
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "day_change_pct": info.get("regularMarketChangePercent"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "last_5d": hist["Close"].to_dict() if not hist.empty else {}
        }
    return data


# 5. FRED macro data
async def get_fred_series(series_ids: list[str]) -> dict:
    """
    Free Federal Reserve Economic Data API.
    series_ids: ["FEDFUNDS", "DGS10", "T10Y2Y", "DEXUSEU", "CPIAUCSL"]
    """
    import requests
    FRED_KEY = os.getenv("FRED_API_KEY")  # Free at fred.stlouisfed.org
    
    results = {}
    for series_id in series_ids:
        r = requests.get(
            f"https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": FRED_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 10
            }
        )
        obs = r.json().get("observations", [])
        results[series_id] = [{"date": o["date"], "value": o["value"]} for o in obs]
    
    return results
```

### 6.2 — Contradiction Detection Engine

```python
async def check_research_against_portfolio(research_summary: dict, portfolio: dict) -> list[dict]:
    """
    Core cross-reference feature. Called after every research ingestion.
    Returns list of conflicts between research conclusions and current positions.
    """
    conflicts = []
    
    for position in portfolio["positions"]:
        if position["instrument"] in research_summary["instruments_mentioned"] or \
           any(theme in research_summary["macro_themes"] for theme in position.get("related_themes", [])):
            
            if (position["direction"] == "LONG" and research_summary["positioning_implication"]["stance"] == "BEARISH") or \
               (position["direction"] == "SHORT" and research_summary["positioning_implication"]["stance"] == "BULLISH"):
                
                conflicts.append({
                    "position": position,
                    "research": research_summary,
                    "conflict_type": "DIRECTIONAL_CONTRADICTION",
                    "severity": "HIGH" if abs(position["notional_usd"]) > 5_000_000 else "MED",
                    "action": "FLAG_TO_PM"
                })
    
    if conflicts:
        await store_conflicts(conflicts)
        if any(c["severity"] == "HIGH" for c in conflicts):
            await send_teams_alert(format_conflict_alert(conflicts))
    
    return conflicts
```

### 6.3 — Tests for Section 6

```python
async def test_rss_ingestion_deduplication():
    """Same article URL ingested twice should only create one record."""
    await ingest_article({"url": "https://test.com/article1", "title": "Test"})
    await ingest_article({"url": "https://test.com/article1", "title": "Test"})
    count = db.query(ResearchDoc).filter_by(source_url="https://test.com/article1").count()
    assert count == 1

async def test_contradiction_detection():
    """Bearish broker note on a LONG position triggers conflict."""
    portfolio = {"positions": [{"instrument": "EURUSD", "direction": "LONG", "notional_usd": 10_000_000}]}
    research = {"instruments_mentioned": ["EURUSD"], "positioning_implication": {"stance": "BEARISH"}}
    conflicts = await check_research_against_portfolio(research, portfolio)
    assert len(conflicts) == 1
    assert conflicts[0]["conflict_type"] == "DIRECTIONAL_CONTRADICTION"
    assert conflicts[0]["severity"] == "HIGH"

async def test_yfinance_returns_prices():
    data = await get_instrument_data(["EURUSD=X", "GC=F"])
    assert "EURUSD=X" in data
    assert data["EURUSD=X"]["current_price"] is not None

async def test_fred_returns_series():
    data = await get_fred_series(["FEDFUNDS", "DGS10"])
    assert len(data["FEDFUNDS"]) > 0
    assert "date" in data["FEDFUNDS"][0]
```

---

## SECTION 7 — PORTFOLIO INTELLIGENCE

### 7.1 — Data Sources

**Primary (already have):** Broadridge SFTP pull → RDS

**Add these:**

```python
# backend/services/market_data_service.py

# Yahoo Finance (free, good enough for liquid instruments)
async def get_portfolio_prices(positions: list) -> dict:
    import yfinance as yf
    
    TICKER_MAP = {
        # Map internal instrument names to Yahoo Finance tickers
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "Gold": "GC=F",
        "WTI": "CL=F",
        "US 10Y": "^TNX",
        "US 2Y": "^IRX",
        # Add ARP's specific instruments
    }
    
    tickers = [TICKER_MAP.get(p["instrument"], p.get("yahoo_ticker")) for p in positions if p.get("yahoo_ticker") or p["instrument"] in TICKER_MAP]
    tickers = [t for t in tickers if t]
    
    data = yf.download(tickers, period="2d", auto_adjust=True)
    return data


# Alternative: Alpha Vantage for FX and rates
async def get_fx_rates(from_currency: str, to_currency: str) -> dict:
    """
    Free tier: 25 requests/day. Use sparingly.
    API key: https://www.alphavantage.co/support/#api-key
    """
    r = httpx.get(
        "https://www.alphavantage.co/query",
        params={
            "function": "FX_DAILY",
            "from_symbol": from_currency,
            "to_symbol": to_currency,
            "apikey": ALPHA_VANTAGE_KEY
        }
    )
    return r.json()
```

### 7.2 — Portfolio Intelligence Prompt

```python
PORTFOLIO_SCENARIO_PROMPT = """
{SYSTEM_BASE}

TASK: Generate scenario analysis for ARP Global Capital's current book.

CURRENT POSITIONS:
{positions_json}

CURRENT MARKET PRICES:
{market_prices}

SCENARIO: {scenario_name}
SCENARIO ASSUMPTIONS: {scenario_assumptions}
HISTORICAL PRECEDENT: {historical_precedent}

OUTPUT:
## SCENARIO: {scenario_name}

**Probability assessment (based on current market pricing):** [%] — [rationale]

**Position-by-position impact:**
| Position | Direction | Current Size | Estimated Move | Estimated P&L |
[One row per position. Use [ESTIMATE] for all figures. Base on described historical sensitivities.]

**Total estimated book P&L:** [ESTIMATE] [range]
**Biggest winner:** [position name, estimated gain]
**Biggest risk:** [position name, estimated loss]

**Recommended pre-emptive actions:**
[Numbered list of hedges or position adjustments to consider, with rationale]

**Confidence in this analysis:** [HIGH/MED/LOW]
Rationale: [why]

⚠️ All figures are model estimates for scenario planning only. Not investment advice.
Validate with actual position Greeks/sensitivities from Rhys/Ahmed before acting.
"""
```

### 7.3 — Portfolio Dashboard Frontend

The portfolio page must show:

1. **P&L ticker bar** at top: live updating, green/red by position
2. **Exposure matrix**: table of positions grouped by asset class with net exposure
3. **Scenario analysis panel**: run pre-built or custom scenarios
4. **Research linkage**: for each position, show last 3 research notes tagged to it
5. **Risk heatmap**: color-coded by concentration and correlation

Pre-built scenarios to ship (hardcode these as templates):
- "Fed hikes 50bps surprise"
- "China devalues CNY 3%"
- "Oil spikes to $120"
- "US recession declared"
- "EM contagion (1997 style)"
- "Risk-off flight to quality"

### 7.4 — Tests for Section 7

```python
async def test_portfolio_prices_fetched():
    """Prices returned for all positions in the book."""
    positions = [{"instrument": "EURUSD", "yahoo_ticker": "EURUSD=X"}, {"instrument": "Gold", "yahoo_ticker": "GC=F"}]
    prices = await get_portfolio_prices(positions)
    assert prices is not None

async def test_scenario_analysis_prompt_no_fabricated_figures():
    """Scenario output must contain [ESTIMATE] tags, not bare dollar figures."""
    result = await run_portfolio_scenario("Fed hikes 50bps", portfolio_mock)
    # All P&L figures must be tagged as estimates
    lines_with_numbers = [l for l in result.split("\n") if "$" in l or "M " in l]
    for line in lines_with_numbers:
        assert "[ESTIMATE]" in line or "⚠️" in line, f"Untagged figure in: {line}"

async def test_broadridge_positions_load():
    """Positions from Broadridge RDS sync are accessible via API."""
    response = await client.get("/api/portfolio/positions")
    assert response.status_code == 200
    assert len(response.json()["positions"]) > 0
```

---

## SECTION 8 — ECONOMIC INTELLIGENCE

### 8.1 — Economic Calendar Data Sources

```python
# backend/services/economic_calendar_service.py

# Option 1: Trading Economics API (free tier available)
async def get_economic_calendar_trading_economics(days_ahead: int = 7):
    r = httpx.get(
        "https://api.tradingeconomics.com/calendar",
        params={
            "c": TRADING_ECONOMICS_KEY,
            "country": "united states,euro area,united kingdom,china,japan",
            "importance": "2,3"  # Only medium and high importance
        }
    )
    return r.json()


# Option 2: Scrape investing.com (no key needed, use with care)
# Option 3: FRED release calendar (free, USA only)
async def get_fred_release_calendar():
    r = httpx.get(
        "https://api.stlouisfed.org/fred/releases/dates",
        params={
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "realtime_start": datetime.now().date().isoformat(),
            "realtime_end": (datetime.now() + timedelta(days=7)).date().isoformat(),
            "include_release_dates_with_no_data": "false"
        }
    )
    return r.json()


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


async def on_data_release(indicator: str, actual: float, consensus: float, prior: float):
    """
    Called when an economic release occurs (via polling FRED or webhook from data provider).
    Generate and distribute impact commentary within 90 seconds.
    """
    portfolio = await get_current_portfolio_summary()
    
    surprise = actual - consensus
    surprise_pct = (surprise / consensus * 100) if consensus else 0
    surprise_dir = "UPSIDE" if surprise > 0 else "DOWNSIDE"
    
    commentary = await claude_complete(ECONOMIC_RELEASE_PROMPT.format(
        indicator_name=indicator,
        actual_value=actual,
        consensus=consensus,
        prior_value=prior,
        surprise=round(abs(surprise), 3),
        surprise_direction=surprise_dir,
        release_time=datetime.now(tz=dubai_tz).strftime("%H:%M GST"),
        portfolio_exposures=json.dumps(portfolio, indent=2),
        historical_reaction=MONITORED_INDICATORS.get(indicator, {}).get("arp_sensitivity", "unknown")
    ))
    
    # Distribute immediately
    await send_teams_alert(commentary, channel="macro-alerts")
    await send_whatsapp_alert(commentary, group="ARP Trading")
    await save_to_research_lake(indicator, actual, consensus, commentary)
```

### 8.2 — Central Bank Language Tracker

```python
async def track_central_bank_language():
    """
    Weekly: Download latest central bank statements/minutes.
    Compare hawkishness/dovishness vs last 3 statements.
    Alert if material shift detected.
    """
    CB_SOURCES = {
        "Fed": "https://www.federalreserve.gov/feeds/press_monetary.xml",
        "ECB": "https://www.ecb.europa.eu/press/govcdec/mopo/rss.html",
        "BOE": "https://www.bankofengland.co.uk/rss/news",
        "BOJ": "https://www.boj.or.jp/en/about/release_2024/index.htm/rss.xml",
    }
    
    CB_ANALYSIS_PROMPT = """
    {SYSTEM_BASE}
    
    TASK: Analyze central bank communication for hawkish/dovish shift.
    
    CENTRAL BANK: {bank}
    CURRENT STATEMENT: {current_text}
    PREVIOUS 3 STATEMENTS (for comparison): {historical_texts}
    
    OUTPUT JSON:
    {
      "stance": "HAWKISH | DOVISH | NEUTRAL | MIXED",
      "shift_vs_last": "MORE_HAWKISH | MORE_DOVISH | UNCHANGED | MIXED",
      "shift_magnitude": "LARGE | MODERATE | SMALL | NONE",
      "key_language_changes": ["phrases added or removed that signal the shift"],
      "next_meeting_implication": "what this suggests about the next rate decision",
      "arp_book_implication": "one sentence: how this affects ARP's rates/FX positions",
      "alert_worthy": true or false
    }
    """
```

### 8.3 — Tests for Section 8

```python
async def test_economic_release_triggers_commentary():
    """Release detection generates commentary within 90s."""
    import time
    start = time.time()
    await on_data_release("US CPI", actual=3.4, consensus=3.2, prior=3.1)
    elapsed = time.time() - start
    assert elapsed < 90, f"Commentary took too long: {elapsed}s"

async def test_upside_surprise_detected():
    surprise_dir = get_surprise_direction(actual=3.4, consensus=3.2)
    assert surprise_dir == "UPSIDE"

async def test_central_bank_tracker_parses_rss():
    items = await fetch_cb_rss("https://www.federalreserve.gov/feeds/press_monetary.xml")
    assert len(items) > 0
    assert "title" in items[0]

async def test_alert_sent_on_major_release():
    with mock.patch("backend.services.teams_service.send_alert") as mock_teams:
        await on_data_release("US NFP", actual=280000, consensus=180000, prior=150000)
        mock_teams.assert_called_once()
```

---

## SECTION 9 — MORNING BRIEFING UPGRADE

### 9.1 — Data Aggregation Pipeline

**File:** `backend/services/morning_briefing_service.py`

```python
async def generate_morning_briefing(date: datetime, user_access_token: str) -> str:
    """
    Assembles all data sources, sends to Claude with the upgraded prompt,
    archives to OneDrive, emails to Yusuf, and posts to Teams.
    """
    
    # 1. Email digest (last 12 hours, P1+P2 only)
    emails = await get_classified_emails_since(date - timedelta(hours=12))
    p1_p2 = [e for e in emails if e["priority"] in ["P1_URGENT", "P2_TODAY"]]
    email_digest = format_email_digest(p1_p2)
    
    # 2. Overnight market data via Yahoo Finance
    OVERNIGHT_TICKERS = ["^GSPC", "^IXIC", "^FTSE", "^N225", "^HSI", "^GDAXI",
                          "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCNH=X",
                          "GC=F", "CL=F", "^TNX", "^IRX"]
    market_data = await get_overnight_moves(OVERNIGHT_TICKERS)
    
    # 3. Economic calendar for today
    calendar = await get_todays_economic_events()
    
    # 4. News (last 8 hours, Serper search)
    news = await search_overnight_news([
        "macro hedge fund", "Federal Reserve", "global markets", 
        "central bank", "geopolitical", "OPEC", "inflation"
    ])
    
    # 5. Portfolio summary from Broadridge
    portfolio = await get_portfolio_summary_for_briefing()
    
    # 6. Pending action items
    pending = await get_overdue_action_items()
    
    # 7. New research (last 24h)
    new_research = await get_new_research_digest(hours=24)
    
    # 8. FRED key rates
    fred_data = await get_fred_series(["FEDFUNDS", "DGS10", "T10Y2Y"])
    
    brief = await claude_complete(
        MORNING_BRIEFING_PROMPT.format(
            email_digest=email_digest,
            market_data=json.dumps(market_data),
            economic_calendar=json.dumps(calendar),
            news_headlines=json.dumps(news),
            portfolio_summary=json.dumps(portfolio),
            pending_actions=json.dumps(pending),
            new_research=json.dumps(new_research),
            timestamp=datetime.now(dubai_tz).strftime("%H:%M GST"),
            email_cutoff=(date - timedelta(hours=12)).strftime("%H:%M GST"),
            market_data_timestamp=datetime.now(dubai_tz).strftime("%H:%M GST")
        )
    )
    
    # Archive + distribute
    await onedrive.archive_morning_brief(brief, date.strftime("%Y-%m-%d"))
    await email_morning_brief(brief, to=["yusuf@arpglobal.com"])
    await post_to_teams_channel(brief, channel="morning-briefing")
    
    return brief
```

### 9.2 — Tests for Section 9

```python
async def test_morning_briefing_contains_required_sections():
    brief = await generate_morning_briefing(datetime.now(), test_token)
    required_sections = [
        "OVERNIGHT P&L DRIVERS",
        "REQUIRES YOUR DECISION TODAY",
        "MARKET OPEN WATCH LIST",
        "ECONOMIC EVENTS",
        "EMAILS REQUIRING RESPONSE",
        "RESEARCH INTEL"
    ]
    for section in required_sections:
        assert section in brief, f"Missing section: {section}"

async def test_briefing_archived_to_onedrive():
    with mock.patch.object(OneDriveService, "upload_file") as mock_upload:
        await generate_morning_briefing(datetime.now(), test_token)
        paths = [c.args[0] for c in mock_upload.call_args_list]
        assert any("MorningBriefings" in p for p in paths)

async def test_briefing_delivered_by_630():
    """Scheduler fires at 06:00 GST and completes before 06:30."""
    start = time.time()
    await morning_brief_job()
    elapsed = time.time() - start
    assert elapsed < 1800, "Briefing generation took >30 minutes"
```

---

## SECTION 10 — NEW ENVIRONMENT VARIABLES

Add all of the following to `.env`, `AWS Secrets Manager`, and `ECS task definition`:

```bash
# New in v2
NEWSAPI_KEY=                    # https://newsapi.org — free 100 req/day
FRED_API_KEY=                   # https://fred.stlouisfed.org/docs/api/api_key.html — free
ALPHA_VANTAGE_KEY=              # https://www.alphavantage.co — free 25 req/day
TRADING_ECONOMICS_KEY=          # https://tradingeconomics.com/api — has free tier
WHATSAPP_BRIDGE_SECRET=         # Internal bridge auth secret
WHATSAPP_BRIDGE_URL=            # URL of the whatsapp-web.js bridge container
ARGO_BASE_URL=                  # Public HTTPS URL of ARGO backend (for Graph webhooks)
GRAPH_EMAIL_WEBHOOK_SECRET=     # Random UUID, used to validate Graph push notifications
GRAPH_CALENDAR_WEBHOOK_SECRET=  # Random UUID
GRAPH_RECORDINGS_WEBHOOK_SECRET= # Random UUID
META_WHATSAPP_TOKEN=            # If using Meta Cloud API instead of bridge
META_PHONE_NUMBER_ID=           # Meta Cloud API phone number ID

# Already have (confirm)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
AZURE_CLIENT_ID=
AZURE_TENANT_ID=
AZURE_CLIENT_SECRET=
DATABASE_URL=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

---

## SECTION 11 — DATABASE SCHEMA ADDITIONS

Add these tables to the existing PostgreSQL schema (Alembic migration):

```sql
-- WhatsApp messages
CREATE TABLE whatsapp_messages (
    id VARCHAR PRIMARY KEY,
    group_name VARCHAR,
    author VARCHAR NOT NULL,
    body TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    is_trade_related BOOLEAN DEFAULT FALSE,
    classification JSONB,
    compliance_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_wa_timestamp ON whatsapp_messages(timestamp);
CREATE INDEX idx_wa_trade ON whatsapp_messages(is_trade_related);

-- Meeting summaries
CREATE TABLE meeting_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_title VARCHAR NOT NULL,
    meeting_date DATE NOT NULL,
    participants JSONB,
    transcript_onedrive_path VARCHAR,
    summary_json JSONB NOT NULL,
    transcription_method VARCHAR,  -- 'teams_vtt' or 'whisper'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Research documents
CREATE TABLE research_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_firm VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    source_url VARCHAR UNIQUE,
    doc_type VARCHAR NOT NULL,
    date DATE NOT NULL,
    content_text TEXT,
    embedding_vector vector(1536),  -- pgvector
    analysis_json JSONB,
    onedrive_path VARCHAR,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_research_date ON research_documents(date);

-- Portfolio conflicts (research vs positions)
CREATE TABLE portfolio_research_conflicts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_id UUID REFERENCES research_documents(id),
    position_instrument VARCHAR NOT NULL,
    conflict_type VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Economic releases
CREATE TABLE economic_releases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    indicator_name VARCHAR NOT NULL,
    release_datetime TIMESTAMPTZ NOT NULL,
    actual_value NUMERIC,
    consensus_value NUMERIC,
    prior_value NUMERIC,
    surprise_direction VARCHAR,
    ai_commentary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Graph webhook subscriptions (for renewal tracking)
CREATE TABLE graph_subscriptions (
    id VARCHAR PRIMARY KEY,
    resource VARCHAR NOT NULL,
    expiration_datetime TIMESTAMPTZ NOT NULL,
    client_state VARCHAR NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## SECTION 12 — FULL TESTING FRAMEWORK

### 12.1 — Test Setup

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx pytest-mock freezegun factory-boy

# Run all tests
pytest tests/ -v --tb=short

# Run section by section
pytest tests/test_section1_autosync.py -v
pytest tests/test_section2_onedrive.py -v
pytest tests/test_section3_reply.py -v
pytest tests/test_section4_meetings.py -v
pytest tests/test_section5_whatsapp.py -v
pytest tests/test_section6_research.py -v
pytest tests/test_section7_portfolio.py -v
pytest tests/test_section8_economic.py -v
pytest tests/test_section9_briefing.py -v

# Integration tests (requires live credentials)
pytest tests/integration/ -v -m integration --slow
```

### 12.2 — AI Output Quality Tests

These tests enforce that Claude's outputs are not weak, misleading, or generic:

```python
# tests/test_ai_output_quality.py

import anthropic
import json
import pytest

QUALITY_RULES = {
    "no_filler_phrases": [
        "I'll analyze this",
        "Here is a summary",
        "It's important to note",
        "Please note that",
        "As an AI",
        "I cannot provide",
        "As mentioned",
        "In conclusion",
        "To summarize"
    ],
    "no_vague_verbs": [
        "might increase", "could go up", "may fall", "possibly decline",
        "seems to be", "appears to be", "looks like"
    ],
    "must_have_structure": [
        "##"  # At least one section header
    ]
}

def assert_output_quality(output: str, context: str):
    """Assert AI output meets minimum quality standards."""
    for phrase in QUALITY_RULES["no_filler_phrases"]:
        assert phrase.lower() not in output.lower(), \
            f"[{context}] Filler phrase detected: '{phrase}'"
    
    for phrase in QUALITY_RULES["no_vague_verbs"]:
        assert phrase.lower() not in output.lower(), \
            f"[{context}] Vague verb detected: '{phrase}'"


async def test_email_classification_output_quality():
    test_email = {
        "sender_name": "John Smith",
        "sender_email": "john@gsgroup.com",
        "subject": "GS Rates View: Repricing risk into H2",
        "body_text": "We are moving to an overweight on 2Y UST given...",
        "attachment_list": ["GS_Rates_May2026.pdf"],
        "timestamp": "2026-05-14T06:30:00Z",
        "thread_count": 1
    }
    result = await classify_email(test_email)
    parsed = json.loads(result)
    
    assert parsed["category"] == "RESEARCH"
    assert parsed["priority"] in ["P1_URGENT", "P2_TODAY", "P3_THIS_WEEK", "P4_FYI"]
    assert len(parsed["one_line_summary"]) <= 15 * 6  # ~15 words
    assert parsed["one_line_summary"]  # Not empty


async def test_morning_brief_output_quality():
    brief = await generate_morning_briefing_with_mock_data()
    assert_output_quality(brief, "morning_brief")
    
    # Must not fabricate market figures
    assert "[DATA MISSING]" in brief or all(
        is_valid_market_data_reference(line) for line in brief.split("\n") if "$" in line or "bps" in line
    )


async def test_research_analysis_no_hallucinated_figures():
    doc_text = "Goldman Sachs expects EUR/USD to reach 1.15 in 12 months."
    result = await analyze_research_document(doc_text, "Goldman", "EUR/USD Outlook")
    parsed = json.loads(result)
    
    # The only figure should be 1.15, which was in the input
    key_data = parsed["key_data_points"]
    assert any("1.15" in str(d) for d in key_data)
    assert not any("1.20" in str(d) for d in key_data)  # Not fabricated


async def test_meeting_summary_action_items_have_owners():
    transcript = """
    Yusuf: Rhys, can you send the NAV report to the client by Thursday?
    Rhys: Yes I'll do that.
    Yusuf: Amin, check the Broadridge reconciliation from last week.
    """
    summary = await run_meeting_intelligence(transcript, "Weekly Ops", "2026-05-14", ["Yusuf", "Rhys", "Amin"])
    
    action_items = summary["action_items"]
    assert len(action_items) >= 2
    
    owners = [item["owner"] for item in action_items]
    assert "Rhys" in owners
    assert "Amin" in owners
    
    # All action items must have an owner
    for item in action_items:
        assert item["owner"] != "UNASSIGNED", f"Action item has no owner: {item['task']}"


async def test_scenario_analysis_uses_estimate_tags():
    """All monetary figures in scenario output must be tagged [ESTIMATE]."""
    result = await run_portfolio_scenario("Fed hikes 50bps", mock_portfolio)
    
    import re
    monetary_figures = re.findall(r'\$[\d,]+[MmKkBb]?', result)
    
    for figure in monetary_figures:
        # Find the line containing this figure
        line = [l for l in result.split("\n") if figure in l][0]
        assert "[ESTIMATE]" in line, f"Untagged figure '{figure}' in line: {line}"


async def test_economic_release_directional_confidence():
    """Large surprise (>2σ) should produce HIGH confidence directional call."""
    # CPI 0.5% above consensus = large surprise
    result = await on_data_release("US CPI", actual=3.9, consensus=3.2, prior=3.1)
    assert "[HIGH]" in result or "HIGH confidence" in result.lower()
```

### 12.3 — End-to-End Integration Tests

```python
# tests/integration/test_e2e_flows.py
# Run these with real credentials in staging environment

@pytest.mark.integration
async def test_email_to_onedrive_full_flow():
    """New email arrives → classified → archived to OneDrive."""
    # Send a test email to the monitored inbox
    # Wait up to 60s for webhook to fire
    # Assert email appears in DB with classification
    # Assert email appears in OneDrive /ARGO/Emails/


@pytest.mark.integration
async def test_meeting_recording_to_summary_full_flow():
    """Upload a test .vtt file to /Recordings → summary generated → saved."""
    # Upload test VTT to /Recordings in OneDrive
    # Wait up to 120s for webhook to fire
    # Assert meeting summary appears in DB
    # Assert summary JSON in /ARGO/Meetings/Summaries/


@pytest.mark.integration
async def test_morning_briefing_delivery():
    """Briefing generated and delivered — all sections present, email sent."""
    brief = await generate_morning_briefing(datetime.now(), service_token)
    assert brief and len(brief) > 500
    # Check Teams channel for the post (if Teams integration active)


@pytest.mark.integration  
async def test_research_ingestion_pipeline():
    """Ingest a real broker research PDF → analysis → cross-referenced vs portfolio."""
    with open("tests/fixtures/sample_broker_note.pdf", "rb") as f:
        pdf_bytes = f.read()
    result = await ingest_research_pdf(pdf_bytes, "Goldman Sachs", "2026-05-14")
    assert result["core_thesis"]
    assert result["arp_relevance"]["score"] is not None
```

### 12.4 — Performance Benchmarks

```python
# tests/test_performance.py

async def test_email_classification_under_3s():
    import time
    start = time.time()
    await classify_email(sample_email)
    assert time.time() - start < 3.0

async def test_reply_suggestion_under_8s():
    start = time.time()
    await get_reply_suggestion(sample_email, tone="COLLEGIAL_PEER")
    assert time.time() - start < 8.0

async def test_morning_briefing_under_45s():
    start = time.time()
    await generate_morning_briefing(datetime.now(), test_token)
    assert time.time() - start < 45.0

async def test_economic_release_commentary_under_10s():
    start = time.time()
    await on_data_release("US CPI", 3.4, 3.2, 3.1)
    assert time.time() - start < 10.0
```

---

## IMPLEMENTATION CHECKLIST

Work through these in order. Check each off before moving to the next.

### Phase 1 — Foundation (Week 1-2)
- [x] Section 0: Replace ALL system prompts with upgraded versions
- [x] Section 1.1: Implement Graph webhook subscription endpoint
- [ ] Section 1.2: Remove manual sync button; implement WebSocket inbox updates
- [x] Section 1.3: Subscription renewal background job
- [x] Section 2: OneDrive service + folder structure + auto-archiving
- [ ] Run all Section 1-2 tests → all pass

### Phase 2 — Reply & Meetings (Week 3-4)
- [ ] Section 3: Email reply button + AI suggestion endpoint + React UI
- [x] Section 4: Teams recording watcher + VTT parser + Whisper fallback
- [x] Section 4: Meeting intelligence prompt + summary storage
- [ ] Section 4: Meetings tab in frontend
- [ ] Run all Section 3-4 tests → all pass

### Phase 3 — WhatsApp & Research (Week 5-6)
- [x] Section 5: Choose WhatsApp integration method (Bridge vs Meta API)
- [x] Section 5: Trade pattern detection + compliance archiving
- [x] Section 5: Weekly WhatsApp report generation + delivery
- [x] Section 6: Research Lake auto-ingestion (RSS + email attachments + NewsAPI)
- [x] Section 6: Contradiction detection engine
- [x] Section 6: FRED + Yahoo Finance data helpers
- [x] Run all Section 5-6 tests → all pass

### Phase 4 — Intelligence Layer (Week 7-8)
- [x] Section 7: Portfolio intelligence with Yahoo Finance prices
- [x] Section 7: Pre-built scenario analysis templates
- [ ] Section 7: Portfolio dashboard frontend
- [x] Section 8: Economic calendar + impact assessment
- [x] Section 8: Central bank language tracker
- [x] Section 8: On-release commentary + Teams/WhatsApp alerts
- [x] Section 9: Morning briefing full aggregation pipeline
- [x] Run all Section 7-9 tests → all pass

### Phase 5 — Quality Gate
- [x] Section 12: All AI output quality tests pass
- [x] Section 12: All performance benchmarks pass
- [ ] Section 12: Integration tests pass against staging
- [ ] Security review: all webhook secrets validated, no env vars in code
- [ ] Database migration tested on staging RDS
- [ ] Load test: simulate 5 concurrent users + 50 simultaneous incoming emails

---

## EXTERNAL APIS — REGISTRATION CHECKLIST

| API | URL | Cost | Priority |
|-----|-----|------|----------|
| NewsAPI | newsapi.org | Free 100 req/day | HIGH |
| FRED | fred.stlouisfed.org/docs/api | Free | HIGH |
| Alpha Vantage | alphavantage.co | Free 25 req/day | MEDIUM |
| Trading Economics | tradingeconomics.com/api | Free tier | MEDIUM |
| Yahoo Finance | via `yfinance` Python lib | Free (unofficial) | HIGH |
| OpenAI Whisper | platform.openai.com | Already have key | HIGH |
| Serper | serper.dev | $50 for 50k | LOW (free tier first) |

Note: `yfinance` is an unofficial Yahoo Finance wrapper. Reliable for prices, historical data, and basic info. Do not use for tick data or compliance-grade pricing.

---

*ARGO v2.0 Upgrade Plan | ARP Global Capital | May 2026*
*Prepared by Rayhan Shhadeh, AI Automation Lead*
