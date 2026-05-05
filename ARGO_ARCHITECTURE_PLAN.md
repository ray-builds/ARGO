# ARGO — AI Operations Platform
## Architectural Plan · ARP Global Capital · Dubai
### Version 1.0 · 2026-05-05 · Author: Rayhan Shhadeh

---

> **This document is the single source of truth for all ARGO implementation work.**
> No code is written until this plan is approved. Every implementation decision 
> must trace back to a section of this document.

---

# TABLE OF CONTENTS

1. [System Overview](#1-system-overview)
2. [Complete Folder Structure](#2-complete-folder-structure)
3. [Database Schema](#3-database-schema)
4. [API Endpoint Registry](#4-api-endpoint-registry)
5. [Module Specifications](#5-module-specifications)
6. [Authentication Flow](#6-authentication-flow)
7. [Frontend Pages](#7-frontend-pages)
8. [Environment Variables](#8-environment-variables)
9. [Deployment Architecture](#9-deployment-architecture)
10. [Phased Delivery Plan](#10-phased-delivery-plan)
11. [QA Strategy](#11-qa-strategy)

---

# 1. SYSTEM OVERVIEW

## 1.1 Mission Statement

ARGO is an internal AI operations platform that automates high-value recurring tasks
for ARP Global Capital — a macro hedge fund in Dubai. The platform eliminates
administrative drag so the investment team can focus entirely on capital allocation
and portfolio management.

## 1.2 High-Level Architecture

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                         ARGO PLATFORM ARCHITECTURE                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

  EXTERNAL WORLD                    ARGO CORE                      PERSISTENCE
  ─────────────                     ─────────                      ───────────

  ┌─────────────┐   OAuth2/MSAL    ┌──────────────────────────┐   ┌──────────┐
  │ Microsoft   │◄────────────────►│   FastAPI Application    │   │PostgreSQL│
  │ 365 / Graph │   Mail+Calendar  │   (Python 3.11)          │◄─►│  AWS RDS │
  └─────────────┘                  │                          │   │+pgvector │
                                   │  ┌────────────────────┐  │   └──────────┘
  ┌─────────────┐   REST API       │  │   /core layer      │  │
  │  Anthropic  │◄────────────────►│  │  claude_client.py  │  │   ┌──────────┐
  │  Claude API │   Haiku/Sonnet   │  │  graph_client.py   │  │   │  SQLite  │
  └─────────────┘                  │  │  database.py       │  │◄─►│  (dev)   │
                                   │  └────────────────────┘  │   └──────────┘
  ┌─────────────┐   REST API       │                          │
  │   Twilio    │◄────────────────►│  ┌────────────────────┐  │   ┌──────────┐
  │  WhatsApp   │   Send msgs      │  │   /modules layer   │  │   │  Alembic │
  └─────────────┘                  │  │  mod1_email        │  │   │migrations│
                                   │  │  mod2_overnight    │  │   └──────────┘
  ┌─────────────┐   REST API       │  │  mod3_meetings     │  │
  │   Serper    │◄────────────────►│  │  mod4_datalake     │  │
  │  News API   │   Headlines      │  │  mod5_portfolio    │  │
  └─────────────┘                  │  │  mod6_clients      │  │
                                   │  │  mod7_research     │  │
  ┌─────────────┐   HTTP/Web       │  │  mod8_econ         │  │
  │  FRED/Trad  │◄────────────────►│  │  mod9_assistant    │  │
  │  Economics  │   Econ data      │  └────────────────────┘  │
  └─────────────┘                  │                          │
                                   │  ┌────────────────────┐  │
  ┌─────────────┐                  │  │  APScheduler       │  │
  │  Browser    │◄────────────────►│  │  Cron Jobs         │  │
  │  (Team)     │   HTML/JS/CSS    │  │  (in-process)      │  │
  └─────────────┘                  │  └────────────────────┘  │
                                   └──────────────────────────┘

  ─────────────────────────────────────────────────────────────────────────────
  DEPLOYMENT: AWS ECS (Fargate) · ECR (image registry) · GitHub Actions CI/CD
  ─────────────────────────────────────────────────────────────────────────────
```

## 1.3 Data Flow — Morning Summary (Critical Path)

```
  03:30 AM London
       │
       ▼
  APScheduler fires overnight_summary job
       │
       ├──► Graph API: fetch emails 22:00–03:30 ──► DB: store raw emails
       │
       ├──► Market stub / OpenBB: fetch FX, rates, equities ──► DB: log data
       │
       ├──► Serper API: fetch top 10 financial headlines ──► DB: log headlines
       │
       ▼
  Claude (Sonnet): synthesize all inputs → structured briefing JSON
       │
       ├──► Twilio WhatsApp → PM's phone
       │
       └──► Graph API: send email (fallback) → CEO_EMAIL
             │
             └──► DB: store summary in overnight_summaries table
```

## 1.4 Data Flow — Email Intelligence (Daily)

```
  Team member opens dashboard
       │
       ▼
  ARGO fetches emails via Graph API (delta queries, token-cached)
       │
       ▼
  For each new email:
    Claude Haiku: score relevance (0–100) + assign tag
       │
       ▼
    Claude Haiku: extract highlight (1–2 key sentences)
       │
       ▼
  Store in DB: emails + email_highlights tables
       │
       ▼
  Frontend renders:
    - CEO email panel: cards grouped by tag, color-coded
    - Full digest: sorted by relevance score
```

## 1.5 Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `core/claude_client.py` | Single gateway for all Anthropic API calls. Model selection, retry logic, rate limiting, cost tracking |
| `core/graph_client.py` | Single gateway for all Microsoft Graph calls. Token refresh, delta query management, error handling |
| `core/database.py` | SQLAlchemy async engine, session factory, base model class |
| `core/scheduler.py` | APScheduler instance, job registration, timezone handling |
| `core/auth.py` | MSAL flow, session management, user identity middleware |
| `modules/mod*/router.py` | FastAPI APIRouter, HTTP endpoints for that module |
| `modules/mod*/service.py` | Business logic, orchestrates Claude + Graph + DB calls |
| `modules/mod*/models.py` | SQLAlchemy ORM models specific to that module |
| `modules/mod*/schemas.py` | Pydantic request/response schemas for that module |
| `templates/` | Jinja2 HTML templates, all UI rendering |
| `static/` | CSS, JS, images — served by FastAPI StaticFiles |

---

# 2. COMPLETE FOLDER STRUCTURE

```
ARGO/
│
├── .env                          # Local secrets (never committed)
├── .env.example                  # Template with all required vars, no values
├── .gitignore                    # Excludes .env, __pycache__, .pytest_cache, *.db
├── Dockerfile                    # Production container definition
├── docker-compose.yml            # Local dev: app + postgres + redis (future)
├── requirements.txt              # All Python dependencies, pinned versions
├── requirements-dev.txt          # Dev-only: pytest, ruff, black, httpx
├── alembic.ini                   # Alembic migration configuration
├── pyproject.toml                # ruff + black configuration
├── README.md                     # Project overview, quickstart
│
├── alembic/                      # Database migration files
│   ├── env.py                    # Alembic environment: loads async SQLAlchemy
│   ├── script.py.mako            # Migration file template
│   └── versions/                 # Auto-generated migration scripts
│       └── .gitkeep
│
├── app/                          # Application root package
│   ├── __init__.py
│   ├── main.py                   # FastAPI app factory, startup/shutdown, router registration
│   ├── config.py                 # Pydantic Settings class — loads from .env
│   ├── dependencies.py           # FastAPI Depends() factories: get_db, get_current_user
│   │
│   ├── core/                     # Shared infrastructure — no business logic
│   │   ├── __init__.py
│   │   ├── claude_client.py      # Anthropic SDK wrapper: model selection, retry, logging
│   │   ├── graph_client.py       # MSAL + Microsoft Graph HTTP client wrapper
│   │   ├── database.py           # SQLAlchemy async engine, session factory, Base model
│   │   ├── scheduler.py          # APScheduler instance + job registration helpers
│   │   ├── auth.py               # MSAL OAuth2 flow, session handling, user middleware
│   │   ├── exceptions.py         # Custom exception classes (ARGOError, AuthError, etc.)
│   │   └── logging.py            # loguru configuration: file rotation, format, levels
│   │
│   ├── modules/                  # Feature modules — each is self-contained
│   │   │
│   │   ├── mod1_email/           # MODULE 1 — Email Intelligence
│   │   │   ├── __init__.py
│   │   │   ├── router.py         # APIRouter: /api/v1/email/* endpoints
│   │   │   ├── service.py        # EmailService: fetch, score, tag, highlight, archive
│   │   │   ├── models.py         # ORM: Email, EmailHighlight tables
│   │   │   ├── schemas.py        # Pydantic: EmailResponse, TagEnum, ScoreResult
│   │   │   └── prompts.py        # Claude prompt templates for scoring + tagging + highlights
│   │   │
│   │   ├── mod2_overnight/       # MODULE 2 — Overnight Market Summary
│   │   │   ├── __init__.py
│   │   │   ├── router.py         # APIRouter: /api/v1/overnight/* endpoints
│   │   │   ├── service.py        # OvernightService: orchestrate fetch → synthesize → deliver
│   │   │   ├── models.py         # ORM: OvernightSummary table
│   │   │   ├── schemas.py        # Pydantic: SummaryResponse, DeliveryStatus
│   │   │   ├── prompts.py        # Claude synthesis prompt (structured briefing)
│   │   │   ├── market_stub.py    # Mock market data (FX/rates/equities) — OpenBB placeholder
│   │   │   └── jobs.py           # APScheduler job definition: run_overnight_summary()
│   │   │
│   │   ├── mod3_meetings/        # MODULE 3 — Meeting Intelligence
│   │   │   ├── __init__.py
│   │   │   ├── router.py         # APIRouter: /api/v1/meetings/* endpoints
│   │   │   ├── service.py        # MeetingService: upload, transcribe, summarize, search, chat
│   │   │   ├── models.py         # ORM: Meeting, MeetingActionItem tables
│   │   │   ├── schemas.py        # Pydantic: MeetingCreate, MeetingSummary, ActionItem
│   │   │   └── prompts.py        # Claude prompts for meeting summarization + Q&A
│   │   │
│   │   ├── mod4_datalake/        # MODULE 4 — Research Data Lake
│   │   │   ├── __init__.py
│   │   │   ├── router.py         # APIRouter: /api/v1/datalake/* endpoints
│   │   │   ├── service.py        # DataLakeService: ingest, chunk, embed, search, Q&A
│   │   │   ├── models.py         # ORM: Document, DocumentChunk (with pgvector) tables
│   │   │   ├── schemas.py        # Pydantic: DocumentIngest, SearchQuery, QAResponse
│   │   │   └── prompts.py        # Claude prompts for Q&A with citations
│   │   │
│   │   ├── mod5_portfolio/       # MODULE 5 — Portfolio Intelligence
│   │   │   ├── __init__.py
│   │   │   ├── router.py         # APIRouter: /api/v1/portfolio/* endpoints
│   │   │   ├── service.py        # PortfolioService: ingest, analyze, scenario, convexity
│   │   │   ├── models.py         # ORM: Position, Scenario tables
│   │   │   ├── schemas.py        # Pydantic: PositionUpload, ScenarioRequest, TradeIdea
│   │   │   └── prompts.py        # Claude prompts for scenario analysis + trade ideas
│   │   │
│   │   ├── mod6_clients/         # MODULE 6 — Sales & Client Intelligence
│   │   │   ├── __init__.py
│   │   │   ├── router.py         # APIRouter: /api/v1/clients/* endpoints
│   │   │   ├── service.py        # ClientService: CRUD, interaction log, follow-ups, search
│   │   │   ├── models.py         # ORM: Client, ClientInteraction tables
│   │   │   ├── schemas.py        # Pydantic: ClientCreate, InteractionLog, FollowUpList
│   │   │   └── prompts.py        # Claude prompts for follow-up recommendations + report drafts
│   │   │
│   │   ├── mod7_research/        # MODULE 7 — Research Intelligence
│   │   │   ├── __init__.py
│   │   │   ├── router.py         # APIRouter: /api/v1/research/* endpoints
│   │   │   ├── service.py        # ResearchService: ingest, summarize, rate, digest, search
│   │   │   ├── models.py         # ORM: ResearchItem table
│   │   │   ├── schemas.py        # Pydantic: ResearchIngest, ResearchSummary, DigestResponse
│   │   │   └── prompts.py        # Claude prompts for research summarization + weekly digest
│   │   │
│   │   ├── mod8_econ/            # MODULE 8 — Economic Data Intelligence
│   │   │   ├── __init__.py
│   │   │   ├── router.py         # APIRouter: /api/v1/econ/* endpoints
│   │   │   ├── service.py        # EconService: calendar fetch, alerts, on-release analysis
│   │   │   ├── models.py         # ORM: EconomicEvent table
│   │   │   ├── schemas.py        # Pydantic: EconEvent, ReleaseAnalysis, AlertConfig
│   │   │   └── prompts.py        # Claude prompts for release analysis vs consensus
│   │   │
│   │   └── mod9_assistant/       # MODULE 9 — AI Assistant (Chat)
│   │       ├── __init__.py
│   │       ├── router.py         # APIRouter: /api/v1/assistant/* endpoints + WebSocket
│   │       ├── service.py        # AssistantService: routing, context, tool use, history
│   │       ├── models.py         # ORM: ChatConversation, ChatMessage tables
│   │       ├── schemas.py        # Pydantic: ChatMessage, ConversationHistory, ToolCall
│   │       └── prompts.py        # System prompt for ARGO assistant persona + routing rules
│   │
│   └── templates/                # Jinja2 HTML templates
│       ├── base.html             # Base layout: nav, sidebar, brand colors, head
│       ├── dashboard.html        # Main dashboard: all module widgets, CEO email panel
│       ├── login.html            # Microsoft SSO login page
│       ├── email/
│       │   ├── inbox.html        # Full email digest view, sorted by relevance
│       │   ├── ceo_panel.html    # CEO email color-coded cards view (included in dashboard)
│       │   └── email_detail.html # Single email view with highlight + actions
│       ├── overnight/
│       │   ├── history.html      # List of all past overnight summaries, searchable
│       │   └── summary_detail.html # Single summary view with full content
│       ├── meetings/
│       │   ├── meetings_list.html # All meetings, filterable by type
│       │   ├── meeting_detail.html # Single meeting: transcript, summary, action items
│       │   ├── upload.html        # Upload audio/video or paste transcript
│       │   └── chat.html          # Cross-meeting Q&A chat interface
│       ├── datalake/
│       │   ├── datalake.html     # Document library view with search
│       │   ├── upload.html       # Document upload interface
│       │   └── qa.html           # Q&A interface with citations
│       ├── portfolio/
│       │   ├── dashboard.html    # Portfolio composition, risk metrics
│       │   ├── upload.html       # Position CSV upload / manual entry form
│       │   ├── scenario.html     # Scenario analysis interface
│       │   └── convexity.html    # Convexity analyzer + trade idea generator
│       ├── clients/
│       │   ├── clients_list.html # CRM table view, sortable
│       │   ├── client_detail.html # Single client profile + interaction history
│       │   └── followups.html    # Follow-up recommendations panel
│       ├── research/
│       │   ├── research_list.html # All research items, searchable
│       │   ├── research_detail.html # Single research item with AI summary
│       │   └── weekly_digest.html # Weekly best-of digest view
│       ├── econ/
│       │   ├── calendar.html     # Economic calendar view (week/month)
│       │   └── event_detail.html # Single event: data, analysis, history
│       └── assistant/
│           └── chat.html         # Full-screen chat interface
│
├── static/                       # Static assets
│   ├── css/
│   │   ├── main.css              # Global styles, brand colors, typography
│   │   ├── dashboard.css         # Dashboard layout + widget styles
│   │   ├── email_cards.css       # CEO email card styles, tag color badges
│   │   └── components.css        # Reusable: buttons, modals, toasts, tables
│   ├── js/
│   │   ├── main.js               # Global JS: HTMX-lite fetch helpers, toast notifications
│   │   ├── dashboard.js          # Dashboard live refresh, widget updates
│   │   ├── email.js              # Email inbox interactions, archive confirmation
│   │   ├── portfolio_charts.js   # Chart.js chart rendering for portfolio data
│   │   ├── chat.js               # Chat interface: streaming, history, input
│   │   └── calendar.js           # Economic calendar rendering
│   └── img/
│       ├── argo_logo.svg         # ARGO logo (navy/cyan brand colors)
│       └── arp_logo.svg          # ARP Global Capital logo
│
└── tests/                        # Test suite
    ├── __init__.py
    ├── conftest.py               # pytest fixtures: async client, test DB, mock Graph/Claude
    ├── test_health.py            # Health check endpoint tests
    ├── test_auth.py              # Auth flow, token refresh, session tests
    ├── test_mod1_email.py        # Email fetch, scoring, tagging, highlight, archive tests
    ├── test_mod2_overnight.py    # Summary generation, delivery, cron trigger tests
    ├── test_mod3_meetings.py     # Upload, transcription, summarization, search tests
    ├── test_mod4_datalake.py     # Ingest, chunking, embedding, semantic search tests
    ├── test_mod5_portfolio.py    # Position upload, scenario, convexity, trade idea tests
    ├── test_mod6_clients.py      # Client CRUD, interaction log, follow-up tests
    ├── test_mod7_research.py     # Research ingest, summary, rating, digest tests
    ├── test_mod8_econ.py         # Calendar fetch, alert, release analysis tests
    ├── test_mod9_assistant.py    # Chat routing, context, tool use, history tests
    ├── test_claude_client.py     # Claude wrapper: retry, model selection, error handling
    ├── test_graph_client.py      # Graph wrapper: token refresh, delta query tests
    └── fixtures/                 # Test data files
        ├── sample_email.json     # Mock Graph API email response
        ├── sample_positions.csv  # Test portfolio CSV
        ├── sample_research.pdf   # Test PDF for data lake
        └── sample_transcript.txt # Test meeting transcript
```

---

# 3. DATABASE SCHEMA

## 3.1 Design Principles

- All tables use UUID primary keys (not sequential integers — avoids enumeration attacks)
- `created_at` / `updated_at` on every table (auto-managed by SQLAlchemy events)
- Soft deletes via `deleted_at` nullable timestamp (never hard-delete business data)
- pgvector extension enabled on PostgreSQL for embedding columns
- All foreign keys have explicit `ON DELETE` behavior specified
- Indexes on all columns used in WHERE clauses or JOINs

## 3.2 Complete Schema

### Table: `users`
Stores M365-authenticated team members. Identity source of truth is Azure AD.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, default gen_random_uuid() | Internal ARGO user ID |
| `azure_oid` | VARCHAR(128) | UNIQUE, NOT NULL | Azure AD object ID (from JWT `oid` claim) |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | M365 email address |
| `display_name` | VARCHAR(255) | NOT NULL | Full name from Graph API |
| `role` | VARCHAR(64) | NOT NULL, default 'staff' | ENUM: 'ceo', 'dev_lead', 'staff' |
| `whatsapp_number` | VARCHAR(32) | NULLABLE | E.164 format for Twilio delivery |
| `preferences` | JSONB | default '{}' | User-specific settings (notification prefs, etc.) |
| `last_login_at` | TIMESTAMPTZ | NULLABLE | Last successful M365 login |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | Record creation time |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | Last modification (auto-updated) |
| `deleted_at` | TIMESTAMPTZ | NULLABLE | Soft delete timestamp |

**Indexes:** `idx_users_azure_oid`, `idx_users_email`

---

### Table: `emails`
Processed emails fetched via Graph API, with AI scoring and classification.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Internal email record ID |
| `graph_message_id` | VARCHAR(512) | UNIQUE, NOT NULL | Microsoft Graph message ID (immutable) |
| `mailbox_owner_id` | UUID | FK → users.id ON DELETE CASCADE | Which team member's mailbox |
| `sender_email` | VARCHAR(255) | NOT NULL | Sender email address |
| `sender_name` | VARCHAR(255) | NULLABLE | Sender display name |
| `subject` | TEXT | NOT NULL | Email subject line |
| `body_preview` | TEXT | NULLABLE | First ~500 chars (from Graph preview) |
| `body_full` | TEXT | NULLABLE | Full email body (fetched on demand) |
| `received_at` | TIMESTAMPTZ | NOT NULL | When email arrived in mailbox |
| `is_read` | BOOLEAN | NOT NULL, default false | Read status in M365 |
| `relevance_score` | SMALLINT | NULLABLE, CHECK (0–100) | AI relevance score 0–100 |
| `tag` | VARCHAR(32) | NULLABLE | ENUM: URGENT/CLIENT/TRADE/RESEARCH/OPERATIONS/HR/REGULATORY/SKIP |
| `is_from_ceo` | BOOLEAN | NOT NULL, default false | True if sender is CEO (yalireza@) |
| `is_archived` | BOOLEAN | NOT NULL, default false | User-initiated archive via ARGO |
| `archived_at` | TIMESTAMPTZ | NULLABLE | When archived |
| `archived_by_id` | UUID | FK → users.id ON DELETE SET NULL | Who archived it |
| `processed_at` | TIMESTAMPTZ | NULLABLE | When ARGO AI processed this email |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_emails_mailbox_owner`, `idx_emails_received_at`, `idx_emails_tag`,
`idx_emails_relevance_score`, `idx_emails_is_from_ceo`, `idx_emails_graph_id`

---

### Table: `email_highlights`
AI-extracted key sentences and action items per email.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `email_id` | UUID | FK → emails.id ON DELETE CASCADE | Parent email |
| `highlight_text` | TEXT | NOT NULL | 1–2 key sentences extracted by Claude |
| `action_required` | TEXT | NULLABLE | Specific action item identified (if any) |
| `key_conclusion` | TEXT | NULLABLE | Main conclusion/decision in email |
| `model_used` | VARCHAR(64) | NOT NULL | Which Claude model produced this |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_email_highlights_email_id`

---

### Table: `overnight_summaries`
Daily morning briefings generated and delivered.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `summary_date` | DATE | NOT NULL | The date this summary covers (night before) |
| `coverage_start` | TIMESTAMPTZ | NOT NULL | Window start (prev day 22:00 London) |
| `coverage_end` | TIMESTAMPTZ | NOT NULL | Window end (03:30 London) |
| `executive_summary` | TEXT | NOT NULL | 3-sentence AI-generated overview |
| `email_section` | JSONB | NOT NULL | Array of flagged emails with actions |
| `market_moves_section` | JSONB | NOT NULL | Top 3 moves with asset + magnitude + direction |
| `news_section` | JSONB | NOT NULL | Key headlines array |
| `macro_section` | TEXT | NULLABLE | Rates/credit/macro-specific commentary |
| `full_briefing_text` | TEXT | NOT NULL | Complete formatted briefing text |
| `whatsapp_delivered` | BOOLEAN | NOT NULL, default false | WhatsApp delivery status |
| `whatsapp_delivered_at` | TIMESTAMPTZ | NULLABLE | |
| `whatsapp_error` | TEXT | NULLABLE | Error message if WhatsApp failed |
| `email_delivered` | BOOLEAN | NOT NULL, default false | Email fallback delivery status |
| `email_delivered_at` | TIMESTAMPTZ | NULLABLE | |
| `email_error` | TEXT | NULLABLE | Error if email failed |
| `model_used` | VARCHAR(64) | NOT NULL | Claude model used for synthesis |
| `raw_inputs` | JSONB | NULLABLE | Raw data that fed into summary (for debugging) |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_overnight_summaries_date` (UNIQUE on summary_date)

---

### Table: `meetings`
Meeting metadata, transcripts, and AI summaries.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `title` | VARCHAR(512) | NOT NULL | Meeting title |
| `meeting_type` | VARCHAR(32) | NOT NULL | ENUM: INTERNAL/STRATEGIST/CLIENT/EARNINGS |
| `meeting_date` | DATE | NOT NULL | Date meeting occurred |
| `attendees` | JSONB | NOT NULL, default '[]' | Array of attendee names/emails |
| `uploaded_by_id` | UUID | FK → users.id ON DELETE SET NULL | Who uploaded |
| `audio_file_path` | VARCHAR(1024) | NULLABLE | S3 path or local path to audio file |
| `transcript_raw` | TEXT | NULLABLE | Raw Whisper transcript |
| `transcript_clean` | TEXT | NULLABLE | Cleaned/formatted transcript |
| `summary` | TEXT | NULLABLE | AI-generated meeting summary |
| `decisions` | JSONB | NULLABLE | Array of key decisions made |
| `key_quotes` | JSONB | NULLABLE | Notable quotes with attribution |
| `duration_minutes` | INTEGER | NULLABLE | Meeting duration |
| `transcription_model` | VARCHAR(64) | NULLABLE | Whisper model version used |
| `summary_model` | VARCHAR(64) | NULLABLE | Claude model used for summarization |
| `status` | VARCHAR(32) | NOT NULL, default 'pending' | ENUM: pending/transcribing/summarizing/complete/error |
| `error_message` | TEXT | NULLABLE | Error detail if status='error' |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_meetings_date`, `idx_meetings_type`, `idx_meetings_uploaded_by`
**Full-text:** `idx_meetings_transcript_fts` (GIN index on transcript_clean tsvector)

---

### Table: `meeting_action_items`
Action items extracted from meetings, with owner and status.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `meeting_id` | UUID | FK → meetings.id ON DELETE CASCADE | Parent meeting |
| `description` | TEXT | NOT NULL | What needs to be done |
| `owner_name` | VARCHAR(255) | NULLABLE | Who is responsible (from transcript) |
| `owner_id` | UUID | FK → users.id ON DELETE SET NULL | Matched ARGO user (if identifiable) |
| `due_date` | DATE | NULLABLE | When it should be done (if mentioned) |
| `is_complete` | BOOLEAN | NOT NULL, default false | Completion status |
| `completed_at` | TIMESTAMPTZ | NULLABLE | |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_action_items_meeting_id`, `idx_action_items_owner_id`

---

### Table: `documents`
Research data lake — all ingested documents.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `title` | VARCHAR(512) | NOT NULL | Document title (inferred or provided) |
| `source_type` | VARCHAR(32) | NOT NULL | ENUM: PDF/EMAIL/PASTE/PODCAST/NOTE |
| `source_name` | VARCHAR(255) | NULLABLE | Who sent it / which publication |
| `original_filename` | VARCHAR(512) | NULLABLE | Original upload filename |
| `file_path` | VARCHAR(1024) | NULLABLE | Storage path if file uploaded |
| `content_raw` | TEXT | NULLABLE | Raw extracted text |
| `asset_class` | VARCHAR(64) | NULLABLE | ENUM: RATES/CREDIT/EQUITY/FX/MACRO/COMMODITIES |
| `tag` | VARCHAR(64) | NULLABLE | Free-form classification tag |
| `uploaded_by_id` | UUID | FK → users.id ON DELETE SET NULL | |
| `email_id` | UUID | FK → emails.id ON DELETE SET NULL | If imported from email |
| `research_item_id` | UUID | FK → research_items.id ON DELETE SET NULL | If linked to research |
| `quality_rating` | SMALLINT | NULLABLE, CHECK (1–5) | Manual 1–5 star rating |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_documents_source_type`, `idx_documents_asset_class`, `idx_documents_uploaded_by`
**Full-text:** `idx_documents_content_fts` (GIN index on content_raw tsvector)

---

### Table: `document_chunks`
Chunked, embedded document segments for semantic search.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `document_id` | UUID | FK → documents.id ON DELETE CASCADE | Parent document |
| `chunk_index` | INTEGER | NOT NULL | Sequence within document (0-based) |
| `chunk_text` | TEXT | NOT NULL | Text content of this chunk |
| `embedding` | VECTOR(1536) | NULLABLE | pgvector embedding (text-embedding-3-small or Claude-compatible) |
| `token_count` | INTEGER | NULLABLE | Token count of chunk |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_chunks_document_id`
**Vector index:** `idx_chunks_embedding` using ivfflat (lists=100) WITH (lists=100)
**Constraint:** UNIQUE(document_id, chunk_index)

---

### Table: `positions`
Portfolio holdings — manually entered or CSV uploaded.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `portfolio_name` | VARCHAR(255) | NOT NULL, default 'main' | Portfolio identifier |
| `instrument` | VARCHAR(255) | NOT NULL | Instrument name or ticker |
| `instrument_type` | VARCHAR(64) | NOT NULL | ENUM: BOND/EQUITY/OPTION/FX/FUTURES/OTHER |
| `asset_class` | VARCHAR(64) | NOT NULL | ENUM: RATES/CREDIT/EQUITY/FX/MACRO |
| `geography` | VARCHAR(64) | NULLABLE | US/EU/EM/MENA/GLOBAL |
| `notional` | NUMERIC(20,4) | NOT NULL | Notional amount in base currency |
| `currency` | VARCHAR(8) | NOT NULL, default 'USD' | ISO 4217 currency code |
| `direction` | VARCHAR(8) | NOT NULL | LONG/SHORT |
| `entry_price` | NUMERIC(20,8) | NULLABLE | Average entry price |
| `current_price` | NUMERIC(20,8) | NULLABLE | Latest mark-to-market price |
| `pnl` | NUMERIC(20,4) | NULLABLE | Unrealized P&L |
| `weight_pct` | NUMERIC(8,4) | NULLABLE | % of NAV |
| `notes` | TEXT | NULLABLE | Free-text trade rationale |
| `as_of_date` | DATE | NOT NULL | Snapshot date for this position |
| `uploaded_by_id` | UUID | FK → users.id ON DELETE SET NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_positions_portfolio_date`, `idx_positions_instrument_type`, `idx_positions_asset_class`

---

### Table: `scenarios`
Portfolio scenario analyses and trade ideas.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `scenario_type` | VARCHAR(32) | NOT NULL | ENUM: MACRO_VIEW/CONVEXITY/TRADE_IDEA/RISK |
| `title` | VARCHAR(512) | NOT NULL | Scenario title |
| `macro_view_input` | TEXT | NULLABLE | User's macro thesis input |
| `analysis_output` | TEXT | NOT NULL | Claude-generated analysis |
| `trade_ideas` | JSONB | NULLABLE | Array of {instrument, rationale, structure} |
| `portfolio_snapshot_id` | UUID | NULLABLE | Links to positions as_of_date batch |
| `model_used` | VARCHAR(64) | NOT NULL | |
| `created_by_id` | UUID | FK → users.id ON DELETE SET NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_scenarios_type`, `idx_scenarios_created_by`

---

### Table: `clients`
CRM — investor and counterparty contact database.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `name` | VARCHAR(255) | NOT NULL | Full name |
| `firm` | VARCHAR(255) | NULLABLE | Institution/firm name |
| `email` | VARCHAR(255) | NULLABLE | Primary email |
| `phone` | VARCHAR(64) | NULLABLE | Phone / WhatsApp |
| `tier` | VARCHAR(32) | NOT NULL, default 'standard' | ENUM: investor/prospect/counterparty/standard |
| `country` | VARCHAR(64) | NULLABLE | Country of domicile |
| `last_contact_date` | DATE | NULLABLE | Date of most recent interaction |
| `notes` | TEXT | NULLABLE | Free-text notes about this client |
| `tags` | JSONB | NOT NULL, default '[]' | Array of custom tags |
| `is_active` | BOOLEAN | NOT NULL, default true | Active client flag |
| `created_by_id` | UUID | FK → users.id ON DELETE SET NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `deleted_at` | TIMESTAMPTZ | NULLABLE | |

**Indexes:** `idx_clients_tier`, `idx_clients_last_contact`, `idx_clients_firm`
**Full-text:** `idx_clients_name_fts` (GIN on name + firm tsvector)

---

### Table: `client_interactions`
Log of all interactions with clients.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `client_id` | UUID | FK → clients.id ON DELETE CASCADE | Client this relates to |
| `interaction_type` | VARCHAR(32) | NOT NULL | ENUM: CALL/EMAIL/MEETING/NOTE/WHATSAPP |
| `direction` | VARCHAR(16) | NOT NULL, default 'outbound' | ENUM: inbound/outbound |
| `summary` | TEXT | NOT NULL | What was discussed/decided |
| `logged_by_id` | UUID | FK → users.id ON DELETE SET NULL | ARGO user who logged this |
| `interaction_date` | TIMESTAMPTZ | NOT NULL | When it happened |
| `email_id` | UUID | FK → emails.id ON DELETE SET NULL | Linked email if type=EMAIL |
| `meeting_id` | UUID | FK → meetings.id ON DELETE SET NULL | Linked meeting if type=MEETING |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_client_interactions_client_id`, `idx_client_interactions_date`

---

### Table: `research_items`
External research: broker notes, strategist calls, podcast summaries.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `title` | VARCHAR(512) | NOT NULL | Research title |
| `supplier_name` | VARCHAR(255) | NOT NULL | Research provider (e.g. "Goldman Sachs Research") |
| `supplier_email` | VARCHAR(255) | NULLABLE | Contact email for provider |
| `source_type` | VARCHAR(32) | NOT NULL | ENUM: NOTE/PODCAST/CALL/REPORT |
| `asset_class` | VARCHAR(64) | NULLABLE | Primary asset class covered |
| `thesis_summary` | TEXT | NULLABLE | AI-extracted main thesis |
| `key_data_points` | JSONB | NULLABLE | Array of notable data/statistics |
| `conviction_level` | VARCHAR(16) | NULLABLE | HIGH/MEDIUM/LOW (AI assessment) |
| `quality_rating` | SMALLINT | NULLABLE, CHECK (1–5) | Manual team rating |
| `document_id` | UUID | FK → documents.id ON DELETE SET NULL | Linked data lake document |
| `email_id` | UUID | FK → emails.id ON DELETE SET NULL | Source email |
| `published_date` | DATE | NULLABLE | When research was published |
| `ingested_by_id` | UUID | FK → users.id ON DELETE SET NULL | |
| `topics` | JSONB | NOT NULL, default '[]' | Topic tags array |
| `model_used` | VARCHAR(64) | NULLABLE | Claude model for summarization |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_research_supplier`, `idx_research_asset_class`, `idx_research_published_date`

---

### Table: `economic_events`
Economic calendar entries with actual data and analysis.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `event_name` | VARCHAR(512) | NOT NULL | e.g. "US CPI YoY", "Fed Funds Rate Decision" |
| `country` | VARCHAR(8) | NOT NULL | ISO country code: US/EU/GB/JP/CN |
| `currency` | VARCHAR(8) | NULLABLE | Affected currency |
| `release_date` | DATE | NOT NULL | Scheduled release date |
| `release_time_utc` | TIME | NULLABLE | Scheduled release time (UTC) |
| `importance` | VARCHAR(16) | NOT NULL | ENUM: HIGH/MEDIUM/LOW |
| `forecast` | VARCHAR(64) | NULLABLE | Consensus forecast |
| `actual` | VARCHAR(64) | NULLABLE | Actual released value (set post-release) |
| `previous` | VARCHAR(64) | NULLABLE | Previous period value |
| `surprise_direction` | VARCHAR(16) | NULLABLE | BEAT/MISS/IN_LINE (set post-release) |
| `ai_analysis` | TEXT | NULLABLE | Claude analysis vs consensus + portfolio implications |
| `alert_sent` | BOOLEAN | NOT NULL, default false | Morning alert delivered flag |
| `data_source` | VARCHAR(64) | NOT NULL | ENUM: FRED/TRADING_ECONOMICS/MANUAL |
| `external_event_id` | VARCHAR(255) | NULLABLE | ID from source API |
| `model_used` | VARCHAR(64) | NULLABLE | Claude model used for analysis |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_econ_events_release_date`, `idx_econ_events_importance`, `idx_econ_events_country`
**Unique:** UNIQUE(external_event_id, data_source) when external_event_id IS NOT NULL

---

### Table: `chat_conversations`
Chat sessions in the AI Assistant module.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → users.id ON DELETE CASCADE | Which team member |
| `title` | VARCHAR(512) | NULLABLE | Auto-generated from first message |
| `module_context` | VARCHAR(64) | NULLABLE | Which module this conversation routed to |
| `is_active` | BOOLEAN | NOT NULL, default true | Current/archived |
| `message_count` | INTEGER | NOT NULL, default 0 | Denormalized count |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_chat_conversations_user_id`, `idx_chat_conversations_updated_at`

---

### Table: `chat_messages`
Individual messages within a chat conversation.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `conversation_id` | UUID | FK → chat_conversations.id ON DELETE CASCADE | Parent conversation |
| `role` | VARCHAR(16) | NOT NULL | ENUM: user/assistant/system |
| `content` | TEXT | NOT NULL | Message text |
| `tool_calls` | JSONB | NULLABLE | Any tool calls made by Claude |
| `tool_results` | JSONB | NULLABLE | Results of tool calls |
| `model_used` | VARCHAR(64) | NULLABLE | Claude model (for assistant messages) |
| `token_input` | INTEGER | NULLABLE | Input tokens used |
| `token_output` | INTEGER | NULLABLE | Output tokens used |
| `sequence_num` | INTEGER | NOT NULL | Message order within conversation |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes:** `idx_chat_messages_conversation_id`, `idx_chat_messages_sequence`

---

## 3.3 SQLAlchemy Base Model

All ORM models inherit from a `TimestampedBase` mixin providing:
- `created_at`: auto-set on insert via `server_default=func.now()`
- `updated_at`: auto-set on insert, auto-updated on every UPDATE via `onupdate=func.now()`

---

# 4. API ENDPOINT REGISTRY

All routes require authentication (M365 session cookie) unless marked **[PUBLIC]**.

## 4.1 System Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Required | Main dashboard — redirect to login if no session |
| GET | `/health` | **[PUBLIC]** | Health check: DB ping + version |
| GET | `/login` | **[PUBLIC]** | Microsoft SSO login redirect |
| GET | `/auth/callback` | **[PUBLIC]** | MSAL OAuth2 callback |
| GET | `/logout` | Required | Clear session, redirect to login |

## 4.2 Module 1 — Email Intelligence

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|---------|
| GET | `/api/v1/email/inbox` | Required | `?user_id=&limit=50&offset=0` | `[EmailResponse]` |
| POST | `/api/v1/email/fetch` | Required | `{user_id, force_refresh}` | `{fetched: int, new: int}` |
| GET | `/api/v1/email/{id}` | Required | — | `EmailDetailResponse` |
| POST | `/api/v1/email/{id}/process` | Required | — | `EmailProcessedResponse` |
| POST | `/api/v1/email/process-batch` | Required | `{email_ids: [uuid]}` | `{processed: int}` |
| POST | `/api/v1/email/{id}/archive` | Required | — | `{archived: true}` |
| GET | `/api/v1/email/ceo-inbox` | Required | `?limit=20` | `[EmailResponse]` (CEO only) |
| GET | `/api/v1/email/digest` | Required | `?user_id=&date=` | `DigestResponse` |
| GET | `/api/v1/email/tags` | Required | — | `[TagCount]` |

## 4.3 Module 2 — Overnight Summary

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|---------|
| GET | `/api/v1/overnight/summaries` | Required | `?limit=30&offset=0` | `[SummaryListItem]` |
| GET | `/api/v1/overnight/summaries/{id}` | Required | — | `SummaryDetailResponse` |
| GET | `/api/v1/overnight/latest` | Required | — | `SummaryDetailResponse` |
| POST | `/api/v1/overnight/trigger` | Required | `{target_date?}` | `{job_id, status}` |
| GET | `/api/v1/overnight/status/{job_id}` | Required | — | `{status, progress}` |

## 4.4 Module 3 — Meeting Intelligence

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|---------|
| GET | `/api/v1/meetings` | Required | `?type=&limit=20` | `[MeetingListItem]` |
| POST | `/api/v1/meetings` | Required | multipart: audio file OR JSON body with transcript | `MeetingResponse` |
| GET | `/api/v1/meetings/{id}` | Required | — | `MeetingDetailResponse` |
| POST | `/api/v1/meetings/{id}/transcribe` | Required | — | `{status, transcript_preview}` |
| POST | `/api/v1/meetings/{id}/summarize` | Required | — | `{summary, action_items}` |
| GET | `/api/v1/meetings/{id}/action-items` | Required | — | `[ActionItem]` |
| PATCH | `/api/v1/meetings/{id}/action-items/{ai_id}` | Required | `{is_complete}` | `ActionItem` |
| POST | `/api/v1/meetings/search` | Required | `{query}` | `[MeetingSearchResult]` |
| POST | `/api/v1/meetings/chat` | Required | `{question, conversation_id?}` | `ChatResponse` |

## 4.5 Module 4 — Research Data Lake

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|---------|
| GET | `/api/v1/datalake/documents` | Required | `?q=&asset_class=&limit=20` | `[DocumentListItem]` |
| POST | `/api/v1/datalake/documents` | Required | multipart: file OR JSON with text | `DocumentResponse` |
| GET | `/api/v1/datalake/documents/{id}` | Required | — | `DocumentDetailResponse` |
| DELETE | `/api/v1/datalake/documents/{id}` | Required | — | `{deleted: true}` |
| POST | `/api/v1/datalake/search` | Required | `{query, asset_class?, limit?}` | `[SearchResult]` (with scores) |
| POST | `/api/v1/datalake/qa` | Required | `{question, conversation_id?}` | `QAResponse` (with citations) |
| PATCH | `/api/v1/datalake/documents/{id}/rating` | Required | `{rating: 1-5}` | `DocumentResponse` |

## 4.6 Module 5 — Portfolio Intelligence

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|---------|
| GET | `/api/v1/portfolio/positions` | Required | `?as_of_date=` | `[PositionResponse]` |
| POST | `/api/v1/portfolio/positions/upload` | Required | multipart CSV | `{loaded: int, errors: []}` |
| POST | `/api/v1/portfolio/positions` | Required | JSON body `PositionCreate` | `PositionResponse` |
| DELETE | `/api/v1/portfolio/positions/{id}` | Required | — | `{deleted: true}` |
| GET | `/api/v1/portfolio/composition` | Required | `?as_of_date=` | `CompositionResponse` |
| POST | `/api/v1/portfolio/scenario` | Required | `{macro_view, constraints?}` | `ScenarioResponse` |
| POST | `/api/v1/portfolio/convexity` | Required | `{as_of_date?}` | `ConvexityResponse` |
| POST | `/api/v1/portfolio/trade-ideas` | Required | `{macro_view}` | `[TradeIdea]` (3 ideas) |
| GET | `/api/v1/portfolio/scenarios` | Required | `?limit=20` | `[ScenarioListItem]` |

## 4.7 Module 6 — Sales & Client Intelligence

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|---------|
| GET | `/api/v1/clients` | Required | `?q=&tier=&limit=20` | `[ClientListItem]` |
| POST | `/api/v1/clients` | Required | `ClientCreate` body | `ClientResponse` |
| GET | `/api/v1/clients/{id}` | Required | — | `ClientDetailResponse` |
| PUT | `/api/v1/clients/{id}` | Required | `ClientUpdate` body | `ClientResponse` |
| DELETE | `/api/v1/clients/{id}` | Required | — | `{deleted: true}` (soft) |
| GET | `/api/v1/clients/{id}/interactions` | Required | `?limit=20` | `[InteractionResponse]` |
| POST | `/api/v1/clients/{id}/interactions` | Required | `InteractionCreate` body | `InteractionResponse` |
| GET | `/api/v1/clients/follow-ups` | Required | `?days_silent=30` | `[FollowUpRecommendation]` |
| POST | `/api/v1/clients/search` | Required | `{query}` | `[ClientSearchResult]` |
| POST | `/api/v1/clients/monthly-report` | Required | `{month, year}` | `{draft_bullets: [string]}` |

## 4.8 Module 7 — Research Intelligence

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|---------|
| GET | `/api/v1/research` | Required | `?q=&supplier=&asset_class=&limit=20` | `[ResearchListItem]` |
| POST | `/api/v1/research` | Required | multipart/JSON | `ResearchItemResponse` |
| GET | `/api/v1/research/{id}` | Required | — | `ResearchDetailResponse` |
| PATCH | `/api/v1/research/{id}/rating` | Required | `{rating: 1-5}` | `ResearchItemResponse` |
| GET | `/api/v1/research/suppliers` | Required | — | `[SupplierStats]` |
| GET | `/api/v1/research/digest` | Required | `?days=7` | `DigestResponse` |

## 4.9 Module 8 — Economic Data Intelligence

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|---------|
| GET | `/api/v1/econ/calendar` | Required | `?from_date=&to_date=&importance=` | `[EconEvent]` |
| GET | `/api/v1/econ/events/{id}` | Required | — | `EconEventDetail` |
| POST | `/api/v1/econ/events/{id}/analyze` | Required | `{actual_value}` | `{analysis: text}` |
| POST | `/api/v1/econ/refresh-calendar` | Required | `{from_date, to_date}` | `{loaded: int}` |
| GET | `/api/v1/econ/today` | Required | — | `[EconEvent]` (today's releases) |

## 4.10 Module 9 — AI Assistant

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|---------|
| GET | `/api/v1/assistant/conversations` | Required | `?limit=20` | `[ConversationListItem]` |
| POST | `/api/v1/assistant/conversations` | Required | `{first_message}` | `{conversation_id, reply}` |
| GET | `/api/v1/assistant/conversations/{id}` | Required | — | `ConversationDetailResponse` |
| POST | `/api/v1/assistant/conversations/{id}/messages` | Required | `{content}` | `{reply, tool_calls?}` |
| DELETE | `/api/v1/assistant/conversations/{id}` | Required | — | `{archived: true}` |

---

# 5. MODULE SPECIFICATIONS

## 5.1 Module 1 — Email Intelligence

**Purpose:** Automate email triage. Every incoming email is scored, classified, and
surfaced to the right person with a one-sentence AI extract. The CEO's emails get
a special card-based view on the main dashboard.

**Service class:** `EmailService`

| Method | Description |
|--------|-------------|
| `fetch_emails(user_id, force_refresh)` | Delta-query Graph API, store new emails |
| `process_email(email_id)` | Run AI scoring + tagging + highlight extraction |
| `process_batch(email_ids)` | Batch process multiple emails |
| `get_digest(user_id, date)` | Return emails sorted by relevance_score DESC |
| `get_ceo_emails(limit)` | Return emails where is_from_ceo=True, grouped by tag |
| `archive_email(email_id, user_id)` | Set is_archived=True, call Graph archive |

**Claude Prompt Strategy:**

*Model: Haiku-4-5 for all email processing (cost-optimized)*

Prompt 1 — Scoring + Tagging (combined call for efficiency):
```
System: You are an AI assistant for ARP Global Capital, a macro hedge fund.
Given an email, you must:
1. Score its relevance to the investment team (0-100)
   - 90-100: Immediate action required (client trade, urgent news)
   - 70-89: Important, read today (research, regulatory)
   - 40-69: Useful background (general ops, updates)
   - 0-39: Low priority (newsletters, automated)
2. Assign exactly one tag: URGENT/CLIENT/TRADE/RESEARCH/OPERATIONS/HR/REGULATORY/SKIP

Return JSON: {"score": int, "tag": str, "reasoning": str (max 20 words)}
```

Prompt 2 — Highlight Extraction (for emails with score >= 40):
```
System: Extract the 1-2 most important sentences from this email for a busy 
fund manager. Also identify any specific action required and the key conclusion.
Return JSON: {"highlight": str, "action_required": str|null, "key_conclusion": str|null}
```

**External API calls:**
- Microsoft Graph: `GET /users/{id}/messages?$filter=...&$select=...` with delta link

**DB tables used:** `emails`, `email_highlights`

**Cron schedule:** None (event-driven; triggered by dashboard load or API call).
Optional: periodic background fetch every 15 minutes via APScheduler.

---

## 5.2 Module 2 — Overnight Market Summary

**Purpose:** Every morning at 3:30 AM London, the PM wakes up to a structured
briefing on their phone covering everything that happened overnight.

**Service class:** `OvernightService`

| Method | Description |
|--------|-------------|
| `run_daily_summary()` | Full orchestration: fetch → synthesize → deliver |
| `fetch_overnight_emails(start, end)` | Graph query: emails received in window |
| `fetch_market_data()` | market_stub.py → returns mock dict (OpenBB-ready interface) |
| `fetch_news_headlines()` | Serper API: query "financial markets overnight news" |
| `synthesize_briefing(emails, market, news)` | Claude Sonnet: produce structured JSON |
| `deliver_whatsapp(summary_text, phone)` | Twilio send; returns delivery status |
| `deliver_email(summary_text, recipient)` | Graph API send; fallback |
| `store_summary(summary_obj)` | Persist to overnight_summaries table |

**Claude Prompt Strategy:**

*Model: Sonnet-4-5 (complex synthesis task)*

```
System: You are ARGO, the AI operations assistant for ARP Global Capital,
a macro hedge fund based in Dubai. You are producing the daily overnight 
briefing for the portfolio manager.

Your briefing MUST follow this exact structure:
━━━ ARGO OVERNIGHT BRIEFING ━━━━━━━━
Date: {date} | Coverage: 22:00–03:30 London

EXECUTIVE SUMMARY
{3 sentences max. Only the most important things.}

IMPORTANT EMAILS ({N} flagged)
{For each: • [SENDER] Subject — Action: X}

OVERNIGHT MARKET MOVES
{Top 3 moves}
• {Asset}: {move magnitude} ({direction}) — {brief context}

KEY HEADLINES
{Top 3-4 headlines with one-line implication}

MACRO / RATES / CREDIT WATCH
{Anything specifically relevant to a macro fund: DM rates, 
EM spreads, central bank commentary}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Be factual and concise. Flag what requires action. Mark unknowns as unknown.
```

**External API calls:**
- Microsoft Graph: `GET /users/{ceo_id}/messages` with receivedDateTime filter
- Serper API: `POST https://google.serper.dev/news` with query
- Twilio: `POST https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json`

**DB tables used:** `emails`, `overnight_summaries`

**Cron schedule:** `0 3 30 * * *` → 03:30 daily, `Europe/London` timezone

**Market stub interface (future-proofed):**
```python
# market_stub.py returns this shape — OpenBB will replace the implementation
{
    "fx": [{"pair": "EURUSD", "change_pct": -0.23, "level": 1.0812}],
    "rates": [{"instrument": "UST 10Y", "change_bps": +8, "yield": 4.45}],
    "equities": [{"index": "SPX", "change_pct": +0.4, "level": 5250}],
    "credit": [{"instrument": "CDX IG", "change_bps": -2, "spread": 58}]
}
```

---

## 5.3 Module 3 — Meeting Intelligence

**Purpose:** Eliminate the manual effort of note-taking and action item tracking.
All meetings are captured, summarized by AI, and searchable across the full archive.

**Service class:** `MeetingService`

| Method | Description |
|--------|-------------|
| `create_meeting(data, file?)` | Create meeting record, save file if provided |
| `transcribe_meeting(meeting_id)` | Call Whisper API, store transcript |
| `summarize_meeting(meeting_id)` | Claude summarization → store results |
| `search_meetings(query)` | Full-text + semantic search |
| `chat_across_meetings(question, conv_id)` | Multi-doc Claude Q&A |

**Claude Prompt Strategy:**

*Model: Sonnet-4-5 for summarization (quality matters here), Haiku for search routing*

Summarization prompt:
```
You are summarizing a business meeting for ARP Global Capital.
Extract:
1. Attendees (name + role if mentioned)
2. Decisions made (clear and specific)  
3. Action items (what, who, by when — as explicit as possible)
4. Key quotes (max 3, direct speech with attribution)
5. Summary paragraph (3-5 sentences covering main discussion themes)

Format as JSON matching the MeetingSummary schema.
```

**External API calls:**
- OpenAI Whisper API: `POST https://api.openai.com/v1/audio/transcriptions`

**DB tables used:** `meetings`, `meeting_action_items`

---

## 5.4 Module 4 — Research Data Lake

**Purpose:** ARP's institutional memory. Every piece of research ever ingested is
searchable by meaning, not just keyword. AI can answer questions citing specific
documents.

**Service class:** `DataLakeService`

| Method | Description |
|--------|-------------|
| `ingest_document(file?, text?, metadata)` | Extract text, chunk, embed, store |
| `chunk_text(text, chunk_size=800, overlap=100)` | Sliding window chunker |
| `embed_chunks(chunks)` | Call embedding API, store vectors |
| `semantic_search(query, limit, asset_class?)` | pgvector cosine similarity |
| `qa_with_citations(question, conv_id?)` | RAG: retrieve chunks → Claude Q&A |
| `rate_document(doc_id, rating)` | Update quality_rating |

**Embedding Strategy:**
- Use OpenAI `text-embedding-3-small` (1536 dims, $0.02/1M tokens — cost-efficient)
- Store in `document_chunks.embedding` as pgvector VECTOR(1536)
- Similarity: cosine distance (pgvector `<=>` operator)
- Retrieval: top-8 chunks per query

**Claude Prompt Strategy:**

*Model: Haiku for retrieval routing, Sonnet for Q&A synthesis*

Q&A prompt:
```
You are ARGO's research assistant for ARP Global Capital.
Answer the question using ONLY the provided document excerpts.
For each fact, cite the source document with [SOURCE: title].
If the answer is not in the documents, say so clearly — do not fabricate.

Documents:
{chunk_1_text} [SOURCE: {doc_title}, {doc_date}]
{chunk_2_text} [SOURCE: ...]
...

Question: {user_question}
```

**External API calls:**
- OpenAI Embeddings API: `POST https://api.openai.com/v1/embeddings`

**DB tables used:** `documents`, `document_chunks`

---

## 5.5 Module 5 — Portfolio Intelligence

**Purpose:** AI-powered portfolio analysis and trade construction. The PM inputs a
macro view and ARGO generates concrete, structured trade ideas with rationale.

**Service class:** `PortfolioService`

| Method | Description |
|--------|-------------|
| `upload_positions_csv(file, uploaded_by)` | Parse CSV, validate, store positions |
| `get_composition(as_of_date)` | Aggregate by asset class, geography, direction |
| `run_scenario(macro_view, constraints)` | Claude analysis of view vs portfolio |
| `analyze_convexity(as_of_date)` | Identify convexity gaps, suggest structures |
| `generate_trade_ideas(macro_view)` | Claude: 3 specific trade expressions |

**Claude Prompt Strategy:**

*Model: Sonnet-4-5 for all portfolio analysis (highest quality needed)*

Trade idea prompt:
```
You are a macro fund portfolio strategist at ARP Global Capital in Dubai.
Given the PM's macro view, generate exactly 3 trade ideas with positive convexity.

Macro view: {user_input}

Current portfolio context: {portfolio_summary}

For each idea, provide:
1. Trade name (e.g., "Long UST 10Y vs Short Bunds via futures")
2. Instrument(s) and structure (be specific about maturity, strike if options)
3. Rationale (2-3 sentences connecting to the macro view)
4. Risk/reward: what makes this convex
5. Key risks to the thesis

Return as structured JSON with an array of 3 trade ideas.
```

**External API calls:** None (market data from stub/OpenBB)

**DB tables used:** `positions`, `scenarios`

---

## 5.6 Module 6 — Sales & Client Intelligence

**Purpose:** Never let a client relationship go cold. ARGO tracks all interactions
and proactively surfaces who needs attention.

**Service class:** `ClientService`

| Method | Description |
|--------|-------------|
| `create_client(data)` | Add new client to CRM |
| `log_interaction(client_id, data)` | Record call/email/meeting |
| `get_follow_up_recommendations(days)` | Clients silent for N+ days |
| `natural_language_search(query)` | Claude-powered search across client data |
| `draft_monthly_report(month, year)` | AI draft of investor update bullets |

**Claude Prompt Strategy:**

*Model: Haiku for follow-up lists, Sonnet for monthly report drafting*

Follow-up prompt: Simple Haiku completion identifying which clients haven't been
contacted, listing them with last contact date and suggested talking point.

Monthly report prompt:
```
Draft the bullet points for ARP Global Capital's monthly investor letter 
for {month} {year}. 

Recent portfolio events:
{portfolio_summary}

Client interaction themes:
{interaction_summary}

Format as 5-8 professional bullet points suitable for a hedge fund letter.
Focus on: performance attribution, key market themes, positioning changes, outlook.
```

**DB tables used:** `clients`, `client_interactions`

---

## 5.7 Module 7 — Research Intelligence

**Purpose:** Aggregate all external research from brokers, strategists, and podcasts.
Track who has the best calls over time. Surface the week's best ideas every Friday.

**Service class:** `ResearchService`

| Method | Description |
|--------|-------------|
| `ingest_research(data)` | Create ResearchItem, link to DataLake document |
| `summarize_research(item_id)` | Claude: thesis, data points, conviction |
| `rate_research(item_id, rating)` | Update quality_rating |
| `get_supplier_stats()` | Average ratings per supplier over time |
| `build_weekly_digest(days)` | Top-rated research from past N days |
| `search_research(query, filters)` | Full-text + filter search |

**Claude Prompt Strategy:**

*Model: Haiku for research summarization*

```
Summarize this research from {supplier_name} for a macro hedge fund PM.
Extract:
1. Main thesis (1 sentence)
2. Key supporting data points (3 max, specific numbers)
3. Asset class focus
4. Conviction level: HIGH (strong data, clear catalyst), MEDIUM, or LOW
5. Recommended action implication (if any)

Return JSON.
```

**DB tables used:** `research_items`, `documents`

---

## 5.8 Module 8 — Economic Data Intelligence

**Purpose:** Never miss a high-impact data release. When CPI or payrolls drops,
ARGO immediately provides analysis against consensus and portfolio implications.

**Service class:** `EconService`

| Method | Description |
|--------|-------------|
| `refresh_calendar(from_date, to_date)` | Pull events from FRED/Trading Economics |
| `get_today_events()` | Return today's high-importance releases |
| `send_morning_alerts()` | Notify team of today's important events |
| `analyze_release(event_id, actual_value)` | Claude: vs consensus + implications |
| `store_release_result(event_id, actual, analysis)` | Update event with actual + analysis |

**Claude Prompt Strategy:**

*Model: Sonnet-4-5 for release analysis (time-sensitive quality)*

```
You are analyzing an economic data release for ARP Global Capital.

Event: {event_name} ({country})
Date: {release_date}
Forecast (consensus): {forecast}
Actual: {actual}
Previous: {previous}

Analyze:
1. Beat/Miss/In-Line: {direction} by how much
2. Why this matters for financial markets (2 sentences)
3. Rates implications (DM, EM)
4. FX implications
5. Portfolio positioning implication for a macro long/short fund

Be specific and direct. Max 200 words total.
```

**External API calls:**
- FRED API: `https://fred.stlouisfed.org/graph/api/release?...`
- Trading Economics API (future): `https://api.tradingeconomics.com/calendar`

**DB tables used:** `economic_events`

**Cron schedule:** Daily 07:00 London — `send_morning_alerts()` for today's events

---

## 5.9 Module 9 — AI Assistant

**Purpose:** A unified conversational interface. Ask ARGO anything about emails,
research, portfolio, clients — and it knows which module to call.

**Service class:** `AssistantService`

| Method | Description |
|--------|-------------|
| `route_question(question, user_id)` | Classify intent → call right module service |
| `chat(conversation_id, message, user)` | Main chat turn: route → fetch context → Claude |
| `get_history(conversation_id)` | Return conversation messages |
| `trigger_action(tool_call, user)` | Execute module actions from within chat |

**Routing Logic (Claude Haiku as router):**
```
Classify this question into one of: EMAIL/OVERNIGHT/MEETINGS/DATALAKE/
PORTFOLIO/CLIENTS/RESEARCH/ECON/GENERAL

Question: {user_message}

Return only the category name.
```

**System prompt for ARGO assistant persona:**
```
You are ARGO, ARP Global Capital's AI operations assistant.
You have access to the team's emails, meetings, research library, 
portfolio data, client CRM, economic calendar, and research database.

Current user: {user_display_name} ({user_email})
Today's date: {date}
Time (Dubai): {time_dubai}

You are concise, professional, and numbers-oriented. You understand macro
finance, rates, credit, and EM. You surface what matters and skip what doesn't.

Available tools: [list of tool schemas]
```

**DB tables used:** `chat_conversations`, `chat_messages`

---

# 6. AUTHENTICATION FLOW

## 6.1 MSAL OAuth2 Authorization Code Flow

```
STEP 1: User visits ARGO (not logged in)
  └─► FastAPI middleware: no session cookie → redirect to /login

STEP 2: /login route
  └─► Build MSAL auth URL:
      - tenant: {AZURE_TENANT_ID}
      - client_id: {AZURE_CLIENT_ID}
      - redirect_uri: {APP_URL}/auth/callback
      - scopes: User.Read Mail.Read Mail.Send Mail.ReadWrite 
                Calendars.Read offline_access
      - response_type: code
      - state: random CSRF token (stored in session)
  └─► Redirect user to Microsoft login

STEP 3: Microsoft authenticates user
  └─► User logs in with @arpglobalcapital.com M365 credentials
  └─► Microsoft redirects to {APP_URL}/auth/callback?code=XXX&state=YYY

STEP 4: /auth/callback route
  └─► Validate state matches CSRF token (prevent CSRF attack)
  └─► Exchange code for tokens via MSAL:
      - access_token (Graph API calls, expires ~1 hour)
      - id_token (user identity claims: oid, email, name)
      - refresh_token (long-lived, 90 days, for offline_access)
  └─► Decode id_token: extract oid, email, display_name
  └─► Upsert user in DB: INSERT ... ON CONFLICT (azure_oid) DO UPDATE
  └─► Store in server-side session:
      {
        "user_id": "uuid",
        "azure_oid": "str",
        "email": "str",
        "display_name": "str",
        "access_token": "str",
        "refresh_token": "str",
        "token_expires_at": "unix_timestamp"
      }
  └─► Set signed session cookie (itsdangerous / Starlette SessionMiddleware)
  └─► Redirect to /

STEP 5: Subsequent requests
  └─► Middleware reads session cookie
  └─► Check token_expires_at: if within 5 minutes of expiry → refresh
  └─► Token refresh:
      POST to https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
      body: grant_type=refresh_token&refresh_token={token}&...
      → update session with new access_token + expiry
  └─► Inject current_user into request.state for Depends() injection

STEP 6: /logout
  └─► Clear server-side session
  └─► Redirect to Microsoft logout URL (optional: single logout)
  └─► Redirect to /login
```

## 6.2 Token Storage Strategy

- **Access token:** Stored in server-side session only (never sent to browser JS)
- **Refresh token:** Stored in server-side session only
- **Session store:** `itsdangerous`-signed cookies via Starlette `SessionMiddleware`
  with `SECRET_KEY` from env. **In production:** migrate to server-side Redis session
  store (cookie holds only session ID).
- **Session TTL:** 8 hours (one business day), re-auth required if idle
- **Token refresh:** Automatic, triggered transparently by middleware

## 6.3 Authorization Rules

| Resource | Who can access |
|----------|---------------|
| CEO email panel | All authenticated users (CEO emails are team-visible briefings) |
| Any user's email inbox | Only that user (or CEO/dev_lead role) |
| Portfolio data | All authenticated users |
| Client CRM | All authenticated users |
| Admin/settings | dev_lead role only |
| Trigger overnight job | dev_lead role only |

## 6.4 FastAPI Dependencies

```python
# dependencies.py
async def get_current_user(request: Request) -> User:
    # Reads from request.state (set by middleware)
    # Raises HTTPException(401) if no session

async def require_ceo_or_lead(user: User = Depends(get_current_user)) -> User:
    # Raises HTTPException(403) if role not in ['ceo', 'dev_lead']

async def get_db() -> AsyncSession:
    # Yields async SQLAlchemy session, commits/rolls back on exit
```

---

# 7. FRONTEND PAGES

## 7.1 Design System

**Brand Colors:**
```css
--navy:    #010042;   /* Primary background, nav */
--blue:    #1D3569;   /* Sidebar, card headers */
--mid-blue: #2685B5;  /* Interactive elements, links */
--cyan:    #0A8FB7;   /* Accents, highlights, CTAs */
--white:   #FFFFFF;
--light-gray: #F4F6F9; /* Page backgrounds */
--dark-text: #1A1A2E;
```

**Typography:** System font stack — no Google Fonts CDN dependency.
Headings: font-weight 600, navy color. Body: 14px, dark-text.

**Layout:** Fixed sidebar (220px) + main content area. Responsive down to 1024px.
Mobile-first is NOT required (this is a desktop operations tool).

## 7.2 Page Inventory

### `/` — Main Dashboard (`dashboard.html`)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  ARGO  [logo]                                     [User: Rayhan ▾] [logout]│
├─────────────┬──────────────────────────────────────────────────────────────┤
│ NAVIGATION  │                    MAIN CONTENT                               │
│             │                                                               │
│ ● Dashboard │  ┌─────────────────────────────────────────────────────────┐ │
│ ○ Email     │  │  TODAY AT A GLANCE                        [2026-05-05]  │ │
│ ○ Overnight │  │  📬 42 unread  |  ⚠ 3 urgent  |  📊 Markets open       │ │
│ ○ Meetings  │  └─────────────────────────────────────────────────────────┘ │
│ ○ Data Lake │                                                               │
│ ○ Portfolio │  ┌─────────────────────────────┐  ┌────────────────────────┐ │
│ ○ Clients   │  │  CEO EMAIL INBOX            │  │  OVERNIGHT SUMMARY     │ │
│ ○ Research  │  │  ─────────────────────────  │  │  ─────────────────────│ │
│ ○ Econ Data │  │  [URGENT]                   │  │  Last run: today 03:30 │ │
│ ○ Assistant │  │  ┌─────────────────────────┐│  │                        │ │
│             │  │  │ Re: Fund allocation Q3  ││  │  UST 10Y: +8bps        │ │
│             │  │  │ From: Y. Alireza        ││  │  EURUSD: -0.23%        │ │
│             │  │  │ Action: Review by EOD   ││  │  SPX: +0.4%            │ │
│             │  │  └─────────────────────────┘│  │                        │ │
│             │  │  [CLIENT]                   │  │  [View full summary →] │ │
│             │  │  ┌─────────────────────────┐│  └────────────────────────┘ │
│             │  │  │ Meeting follow-up       ││                              │
│             │  │  │ From: Y. Alireza        ││  ┌────────────────────────┐ │
│             │  │  └─────────────────────────┘│  │  TODAY'S ECON EVENTS   │ │
│             │  │                             │  │  ─────────────────────│ │
│             │  │  [View all CEO emails →]    │  │  15:30 US CPI YoY [H]  │ │
│             │  └─────────────────────────────┘  │  16:00 Fed Minutes [M] │ │
│             │                                   └────────────────────────┘ │
│             │  ┌─────────────────────────────────────────────────────────┐ │
│             │  │  RECENT MEETINGS         │  RESEARCH DIGEST             │ │
│             │  │  ─────────────────────── │  ─────────────────────────  │ │
│             │  │  2026-05-04 Strategist   │  Goldman: EM Rates thesis    │ │
│             │  │  call (summarized)       │  Rating: ★★★★☆              │ │
│             │  │  [View →]                │  [View digest →]             │ │
│             │  └─────────────────────────────────────────────────────────┘ │
└─────────────┴──────────────────────────────────────────────────────────────┘
```

### `/email` — Email Intelligence (`email/inbox.html`)

- Full-width table layout: sender | subject | preview | score badge | tag badge | time
- Sorted by relevance score descending by default
- Score badges: 90+ = red, 70-89 = orange, 40-69 = blue, <40 = gray
- Tag badges: color-coded pills (URGENT=red, CLIENT=navy, TRADE=cyan, etc.)
- Row click → email_detail.html
- "Archive SKIP emails" button with confirmation modal
- Filter bar: by tag, by date range, by mailbox owner (for CEO/lead)

### CEO Email Panel — `email/ceo_panel.html` (included in dashboard)

```
╔══ CEO EMAIL INBOX (from: Yusuf Alireza) ══════════════════════════════╗
║                                                                        ║
║  ┌─ [URGENT] ────────────────────────────────────────────────────┐    ║
║  │  Subject: Q3 allocation review — need input by COB             │    ║
║  │  Key action: Send portfolio summary to Yusuf by 17:00 today   │    ║
║  │  12:34 today                                          [View]   │    ║
║  └───────────────────────────────────────────────────────────────┘    ║
║                                                                        ║
║  ┌─ [TRADE] ─────────────────────────────────────────────────────┐    ║
║  │  Subject: UST position — reduce 20%                            │    ║
║  │  Key conclusion: Trim duration given CPI surprise              │    ║
║  │  Yesterday 23:14                                      [View]   │    ║
║  └───────────────────────────────────────────────────────────────┘    ║
╚════════════════════════════════════════════════════════════════════════╝
```

Each card is color-coded:
- URGENT: left border `#DC2626` (red)
- TRADE: left border `#0A8FB7` (cyan)
- CLIENT: left border `#1D3569` (navy)
- RESEARCH: left border `#2685B5` (mid-blue)
- OPERATIONS: left border `#6B7280` (gray)
- HR: left border `#7C3AED` (purple)
- REGULATORY: left border `#D97706` (amber)

### `/overnight` — Overnight Summaries (`overnight/history.html`)

- Table of all past summaries (date, delivery status, key market moves preview)
- Search box (full-text on full_briefing_text)
- Row click → summary_detail.html
- "Run now" button (dev_lead only) with confirmation

### `/overnight/{id}` — Summary Detail (`overnight/summary_detail.html`)

- Full formatted briefing text in a card
- Delivery status badges (WhatsApp ✓ / Email ✓)
- Email section: expandable list of flagged emails
- Market section: mini table of moves
- News section: bulleted headlines

### `/meetings` — Meeting List (`meetings/meetings_list.html`)

- Card grid layout: each card shows title, date, type badge, attendees, summary preview
- Filter: by type (INTERNAL/STRATEGIST/CLIENT/EARNINGS)
- Upload button → upload.html
- Search box: cross-meeting search

### `/meetings/{id}` — Meeting Detail (`meetings/meeting_detail.html`)

- Header: title, date, attendees, type badge
- Tabs: Summary | Transcript | Action Items
- Action items: checkbox list, owner, due date
- "Ask a question about this meeting" quick chat button

### `/meetings/chat` — Cross-Meeting Q&A (`meetings/chat.html`)

- Split view: chat on right, search results panel on left
- Chat interface matching assistant/chat.html style

### `/datalake` — Data Lake (`datalake/datalake.html`)

- Search bar (semantic search, prominent)
- Document list: title, source, date, rating stars, asset class badge
- Upload button
- Filter: by asset class, source type

### `/portfolio` — Portfolio Dashboard (`portfolio/dashboard.html`)

- Top stats strip: total positions, NAV estimate, asset class breakdown
- Two charts side-by-side: donut (asset class mix) + bar (geography)
- Positions table below: instrument, type, direction, notional, weight%
- Quick actions: "Upload positions", "Run scenario", "Analyze convexity"

### `/portfolio/scenario` — Scenario Analysis (`portfolio/scenario.html`)

- Left panel: text area for macro view input + Submit button
- Right panel: Claude-generated analysis (streamed or polled)
- Below: Trade ideas cards (3 cards, each with trade name, structure, rationale)

### `/clients` — Client List (`clients/clients_list.html`)

- Table: name, firm, tier badge, last contact date, follow-up indicator
- "⚠ 12 clients need follow-up" banner if any
- Add client button
- Search box

### `/econ/calendar` — Economic Calendar (`econ/calendar.html`)

- Week view calendar grid
- Events shown as colored blocks: HIGH=red, MEDIUM=amber, LOW=gray
- Click event → event_detail.html (shows forecast, actual if released, analysis)
- "Today" tab showing today's events prominently

### `/assistant` — AI Chat (`assistant/chat.html`)

- Full-height chat UI
- Left sidebar: conversation history list (titles, dates)
- Main area: message thread with user (right-aligned, navy) and ARGO (left-aligned, blue)
- Bottom: text input + Send button, "New conversation" button
- Suggested prompts for new users: "Show me this week's important emails",
  "What research came in this week?", "Analyze my portfolio for convexity"

### `/login` — Login Page (`login.html`)

- Centered card on navy background
- ARGO logo + "ARP Global Capital"
- "Sign in with Microsoft 365" button (mid-blue, Microsoft logo)
- Brief tagline: "Your AI operations platform"

---

# 8. ENVIRONMENT VARIABLES

Complete `.env` schema. Copy `.env.example`, fill in values.

```bash
# ═══════════════════════════════════════════════════════
# ARGO Configuration
# ═══════════════════════════════════════════════════════

# ── App Core ────────────────────────────────────────────
APP_ENV=development              # REQUIRED | development | production | test
APP_URL=http://localhost:8000    # REQUIRED | Full public URL (no trailing slash)
SECRET_KEY=                      # REQUIRED | 64-char random string for session signing
LOG_LEVEL=INFO                   # OPTIONAL | DEBUG | INFO | WARNING | ERROR

# ── Database ────────────────────────────────────────────
DATABASE_URL=sqlite+aiosqlite:///./argo_dev.db
# REQUIRED | Dev: sqlite+aiosqlite:///./argo_dev.db
# REQUIRED | Prod: postgresql+asyncpg://user:pass@host:5432/argo
PGVECTOR_ENABLED=false           # OPTIONAL | true in production (PostgreSQL only)

# ── Microsoft Azure AD ──────────────────────────────────
AZURE_TENANT_ID=                 # REQUIRED | ARP's M365 tenant GUID
AZURE_CLIENT_ID=                 # REQUIRED | ARGO app registration client ID
AZURE_CLIENT_SECRET=             # REQUIRED | App registration client secret
AZURE_REDIRECT_URI=http://localhost:8000/auth/callback
# REQUIRED | Must match registered redirect URI in Azure AD exactly

# ── Team Identities ─────────────────────────────────────
CEO_EMAIL=yalireza@arpglobalcapital.com
# REQUIRED | Used for CEO inbox filtering and overnight delivery
CEO_WHATSAPP=                    # REQUIRED | E.164 format: +971XXXXXXXX
PM_WHATSAPP=                     # OPTIONAL | PM's WhatsApp if different from CEO
DEV_LEAD_EMAIL=rshhadeh@arpglobalcapital.com
# OPTIONAL | For system alert emails

# ── Anthropic Claude API ────────────────────────────────
ANTHROPIC_API_KEY=               # REQUIRED | sk-ant-...
CLAUDE_HAIKU_MODEL=claude-haiku-4-5
# OPTIONAL | Default routine task model
CLAUDE_SONNET_MODEL=claude-sonnet-4-5
# OPTIONAL | Default complex reasoning model
CLAUDE_MAX_RETRIES=3             # OPTIONAL | Retry attempts on API errors
CLAUDE_RETRY_DELAY_SECONDS=2     # OPTIONAL | Base delay for exponential backoff

# ── Twilio WhatsApp ─────────────────────────────────────
TWILIO_ACCOUNT_SID=              # REQUIRED | Twilio account SID
TWILIO_AUTH_TOKEN=               # REQUIRED | Twilio auth token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
# REQUIRED | Twilio sandbox number (dev) or approved business number (prod)

# ── Serper API (News) ───────────────────────────────────
SERPER_API_KEY=                  # REQUIRED | From serper.dev account

# ── OpenAI (Whisper + Embeddings) ───────────────────────
OPENAI_API_KEY=                  # REQUIRED | For Whisper transcription + embeddings
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
# OPTIONAL | Default embedding model
WHISPER_MODEL=whisper-1          # OPTIONAL | Whisper model version

# ── Economic Data APIs ──────────────────────────────────
FRED_API_KEY=                    # OPTIONAL | FRED API key (free from stlouisfed.org)
TRADING_ECONOMICS_API_KEY=       # OPTIONAL | Trading Economics API (future)

# ── APScheduler ─────────────────────────────────────────
SCHEDULER_TIMEZONE=Europe/London # REQUIRED | Timezone for all cron jobs
OVERNIGHT_SUMMARY_HOUR=3         # OPTIONAL | Hour for overnight summary (default 3)
OVERNIGHT_SUMMARY_MINUTE=30      # OPTIONAL | Minute for overnight summary (default 30)
OVERNIGHT_WINDOW_START_HOUR=22   # OPTIONAL | Start of overnight email window (default 22)

# ── File Storage ────────────────────────────────────────
UPLOAD_DIR=./uploads             # REQUIRED | Local path for uploaded files
MAX_UPLOAD_SIZE_MB=50            # OPTIONAL | Max file upload size (default 50MB)
# Future: AWS S3 bucket config for production

# ── AWS (Production Only) ───────────────────────────────
AWS_REGION=eu-west-1             # OPTIONAL | AWS region for ECS/RDS
AWS_S3_BUCKET=                   # OPTIONAL | S3 bucket for file storage in prod

# ── Feature Flags ───────────────────────────────────────
ENABLE_WHATSAPP=true             # OPTIONAL | Disable for local dev without Twilio
ENABLE_EMAIL_FETCH=true          # OPTIONAL | Disable to avoid hitting Graph in tests
ENABLE_OVERNIGHT_CRON=true       # OPTIONAL | Disable in test/CI environments
```

---

# 9. DEPLOYMENT ARCHITECTURE

## 9.1 AWS ECS Fargate Architecture

```
  GitHub (main branch)
       │
       ▼
  GitHub Actions CI/CD
       │
       ├──► Run tests (pytest, 80% coverage gate)
       ├──► Run linting (ruff + black --check)
       ├──► Build Docker image
       ├──► Push to ECR (tag: commit SHA + latest)
       ├──► Run Alembic migrations (task in ECS)
       └──► Update ECS service (rolling deployment)
  
  ─────────────────────────────────────────────────────
  
  Internet
     │
     ▼
  AWS ALB (HTTPS, port 443)    ← SSL cert via ACM
  [argo.arpglobalcapital.com]
     │
     ▼
  ECS Service (Fargate)        ← Target Group
  ┌─────────────────────────┐
  │  ARGO Container         │
  │  Python 3.11 FastAPI    │
  │  uvicorn --workers 2    │
  │  Port: 8000             │
  │  CPU: 512               │
  │  Memory: 1024 MB        │
  └─────────────────────────┘
     │
     ├──► AWS RDS PostgreSQL (in private subnet)
     │    [argo-prod.xxxxx.rds.amazonaws.com]
     │    db.t3.micro initially, pgvector extension
     │
     └──► AWS Secrets Manager (production secrets)
          [not .env — ECS task definition env vars from Secrets Manager]
```

## 9.2 Dockerfile

```dockerfile
# Two-stage build: builder installs deps, runtime runs app

FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

# Non-root user for security
RUN adduser --disabled-password --gecos '' appuser
USER appuser

# Upload directory (will be overridden by ECS volume or S3 in prod)
RUN mkdir -p uploads

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

## 9.3 GitHub Actions CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml (two jobs)

# JOB 1: test — runs on every push/PR
test:
  runs-on: ubuntu-latest
  steps:
    - checkout
    - setup Python 3.11
    - pip install -r requirements.txt -r requirements-dev.txt
    - ruff check .
    - black --check .
    - pytest --cov=app --cov-report=xml --cov-fail-under=80
    - upload coverage report

# JOB 2: deploy — runs only on push to main, after test passes
deploy:
  needs: test
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
  steps:
    - checkout
    - configure AWS credentials (OIDC, no long-lived keys)
    - login to ECR
    - docker build + tag with commit SHA
    - docker push to ECR
    - run alembic upgrade head (via ECS run-task with migration command)
    - update ECS service (force new deployment)
    - wait for service stability
    - notify on failure (email to DEV_LEAD_EMAIL)
```

## 9.4 Health Check

`GET /health` returns:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "db": "ok",
  "timestamp": "2026-05-05T10:00:00Z"
}
```

Returns 200 if DB is reachable, 503 otherwise. Used by both ALB health check
and Dockerfile HEALTHCHECK.

## 9.5 Secrets Management

- **Development:** `.env` file (gitignored), loaded by python-dotenv
- **Production:** AWS Secrets Manager. ECS task definition references secrets
  as environment variables using `valueFrom` pointing to Secrets Manager ARNs.
  No secrets ever in container image or task definition plaintext.

## 9.6 Terraform Scope

Infrastructure as code covers:
- ECS cluster, service, task definition
- ECR repository
- RDS PostgreSQL instance (with pgvector extension via init script)
- ALB + target group + HTTPS listener
- VPC security groups (ECS ↔ RDS, ALB → ECS)
- IAM roles: ECS task execution role, task role (with Secrets Manager read)
- Route53 record for argo.arpglobalcapital.com

---

# 10. PHASED DELIVERY PLAN

## Phase 1 — Week 1: Core Infrastructure + Morning Briefing

**Goal:** Something real and valuable is delivered by end of week 1.

| # | Task | Description |
|---|------|-------------|
| 1.1 | Project scaffold | Folder structure, requirements, pyproject.toml, Dockerfile |
| 1.2 | Core infrastructure | `database.py`, `config.py`, `logging.py`, `main.py` app factory |
| 1.3 | Health check | `/health` endpoint, DB connectivity test |
| 1.4 | Auth flow | MSAL OAuth2 flow, session middleware, login/callback/logout |
| 1.5 | Base template | `base.html` with nav, brand colors, sidebar |
| 1.6 | Claude client | `claude_client.py` with retry, model selection, logging |
| 1.7 | Graph client | `graph_client.py` with token refresh, basic email fetch |
| 1.8 | Module 2 complete | Overnight summary: fetch emails + Serper news + synthesis + Twilio + DB |
| 1.9 | Module 2 UI | History list + detail view templates |
| 1.10 | APScheduler | Scheduler setup, overnight job registration |
| 1.11 | Basic dashboard | Dashboard with overnight summary widget |
| 1.12 | Tests: core | `test_health`, `test_auth`, `test_mod2_overnight`, `test_claude_client` |
| 1.13 | CI pipeline | GitHub Actions: lint + test gate |

**End of Week 1 deliverable:** ARGO is running, authenticated, and the PM receives
their first real overnight briefing via WhatsApp.

---

## Phase 2 — Week 2: Email Intelligence + Data Lake

**Goal:** Email triage is automated. Research is searchable.

| # | Task | Description |
|---|------|-------------|
| 2.1 | Module 1 — Email service | Fetch, score, tag, highlight all incoming emails |
| 2.2 | Module 1 — Email UI | Inbox view, CEO panel on dashboard, email detail |
| 2.3 | Module 1 — Archive | One-click archive for SKIP emails with confirmation |
| 2.4 | Dashboard refresh | CEO email boxes on main dashboard (live) |
| 2.5 | Module 4 — Ingest | PDF upload + text paste, chunking, embedding |
| 2.6 | Module 4 — Search | Semantic search UI (prominent search bar, results) |
| 2.7 | Module 4 — Q&A | RAG Q&A with source citations |
| 2.8 | Module 4 — UI | Data lake list, upload, Q&A templates |
| 2.9 | Alembic migrations | Migration for all tables created so far |
| 2.10 | Tests: modules 1+4 | Full test coverage for email and data lake |

**End of Week 2 deliverable:** The team's email inbox is fully triaged by AI.
Research PDFs are searchable with natural language.

---

## Phase 3 — Week 3+: Remaining Modules

**Priority order:**

| Week | Module | Rationale |
|------|--------|-----------|
| Week 3 | Module 3 — Meetings | High daily use; eliminates note-taking friction |
| Week 3 | Module 9 — Assistant (basic) | Unlocks natural language access to all data |
| Week 4 | Module 5 — Portfolio | Core investment tool; needs careful testing |
| Week 4 | Module 8 — Econ Data | Supports portfolio work, econ calendar feeds into overnight |
| Week 5 | Module 7 — Research | Builds on Module 4 (data lake) already built |
| Week 5 | Module 6 — Clients | Lower urgency; CRM is supporting infrastructure |

**Phase 3 completion criteria:**
- All 9 modules functional
- 80%+ test coverage across all modules
- Full Terraform IaC for AWS deployment
- Production deployment on ECS
- Overnight briefing running daily without manual intervention

---

## Prioritization Rationale

1. **Module 2 first** (overnight summary): immediate daily value, clear ROI, forces
   all core infrastructure to be built (Claude + Graph + Twilio + DB + scheduler)
2. **Module 1 second** (email intelligence): highest-volume daily task, eliminates
   significant cognitive load for the whole team
3. **Module 4 third** (data lake): foundational for research workflows; later modules
   (7, research) depend on it
4. **Modules 3, 9 in parallel**: meetings + assistant are both conversational; 
   share prompt patterns
5. **Module 5 carefully** (portfolio): touches real financial data; needs PM
   validation of AI outputs before trusting

---

# 11. QA STRATEGY

## 11.1 Test Architecture

```
tests/
  conftest.py    ← Shared fixtures
  unit/          ← Fast, isolated, no I/O
  integration/   ← DB (test SQLite), mocked external APIs
  e2e/           ← Full stack, against test DB (CI only)
```

## 11.2 Fixture Strategy (`conftest.py`)

```python
# Key fixtures:

@pytest.fixture
async def db_session():
    # In-memory SQLite via aiosqlite
    # Creates all tables fresh for each test
    # Rolls back after each test

@pytest.fixture
def mock_claude(monkeypatch):
    # Replaces ClaudeClient.call() with a deterministic mock
    # Returns pre-defined JSON responses per prompt pattern
    # Never hits Anthropic API in tests

@pytest.fixture  
def mock_graph(monkeypatch):
    # Replaces GraphClient.get_messages() with fixture JSON
    # Uses sample_email.json from tests/fixtures/
    # Never hits Microsoft Graph in tests

@pytest.fixture
def mock_twilio(monkeypatch):
    # Replaces Twilio send with a recording mock
    # Asserts correct payload was constructed

@pytest.fixture
async def authenticated_client(db_session):
    # httpx AsyncClient with pre-injected session cookie
    # User: rshhadeh@arpglobalcapital.com (dev_lead role)
    # Bypasses MSAL entirely in tests
```

## 11.3 Test Categories and Coverage

| Category | What is tested | What is mocked |
|----------|---------------|----------------|
| Unit: `claude_client` | Retry logic, model selection, backoff timing | Anthropic HTTP calls |
| Unit: `graph_client` | Token refresh logic, delta query building | MSAL HTTP calls |
| Integration: `mod1_email` | Full email processing flow: fetch → score → tag → store | Graph API responses |
| Integration: `mod2_overnight` | Full briefing generation and delivery flow | Graph, Serper, Twilio, Claude |
| Integration: `mod3_meetings` | Upload → transcribe → summarize → store | Whisper API, Claude |
| Integration: `mod4_datalake` | Ingest → chunk → embed → search → QA | OpenAI Embeddings, Claude |
| Integration: `mod5_portfolio` | Position upload → scenario → trade ideas | Claude |
| Integration: `mod6_clients` | CRUD, follow-up logic, report generation | Claude |
| Integration: `mod7_research` | Ingest → summarize → rate → digest | Claude, Serper |
| Integration: `mod8_econ` | Calendar fetch → alert → release analysis | FRED API, Claude |
| Integration: `mod9_assistant` | Routing, chat turn, tool call, history | Claude, all module services |
| Auth: `test_auth` | MSAL callback, token storage, refresh, session TTL | MSAL HTTP endpoints |
| API: all modules | Every endpoint: request validation, response schema, auth required | All external APIs |

## 11.4 Coverage Gate

- **Minimum:** 80% line coverage across `app/` directory
- **CI enforced:** `pytest --cov=app --cov-fail-under=80`
- **Excluded from coverage:** `alembic/`, `static/`, `templates/`, `tests/` themselves

## 11.5 What is NOT mocked (hits real services in integration testing)

- **SQLite test database:** All DB operations run against a real (in-memory) SQLite
  database. No DB mocking. Schema is verified to match SQLAlchemy models.
- **Pydantic validation:** All request/response schemas are validated with real data.
- **APScheduler job execution:** Jobs are triggered directly (not via scheduler) but
  execute real service code against the mocked external APIs.

## 11.6 CI Gate Requirements

Pull requests to `main` must pass:

| Check | Tool | Required |
|-------|------|---------|
| Linting | `ruff check .` | ✓ |
| Formatting | `black --check .` | ✓ |
| Type hints | `mypy app/` (warn only, not gate in Phase 1) | - |
| Unit + Integration tests | `pytest -x --cov=app --cov-fail-under=80` | ✓ |
| No hardcoded secrets | `git-secrets` or `truffleHog` scan | ✓ |
| Docker build | `docker build .` (smoke test) | ✓ |

## 11.7 Observability

- **Logging:** loguru to stdout (ECS picks up) + rotating file `./logs/argo.log`
- **Log format:** `{time:YYYY-MM-DD HH:mm:ss} | {level} | {module}:{function}:{line} | {message}`
- **Error policy:** All exceptions caught at the service layer, logged with full
  traceback via `logger.exception()`, then re-raised as typed `ARGOError` for
  the router to return a clean HTTP error response
- **Overnight job:** Logs each phase (fetch_emails, fetch_market, fetch_news,
  synthesize, deliver_whatsapp, deliver_email) with timing and success/failure

---

# APPENDIX A — Dependencies Reference

```
# requirements.txt (key packages, all pinned in final file)
fastapi==0.115.*
uvicorn[standard]==0.34.*
sqlalchemy[asyncio]==2.0.*
aiosqlite==0.20.*            # SQLite async driver (dev)
asyncpg==0.30.*              # PostgreSQL async driver (prod)
alembic==1.14.*
pydantic[email]==2.10.*
pydantic-settings==2.7.*
python-dotenv==1.0.*
msal==1.31.*
anthropic==0.49.*
httpx==0.28.*                # Async HTTP for Graph API, Serper
twilio==9.4.*
apscheduler==3.11.*
loguru==0.7.*
python-multipart==0.0.*      # File uploads
jinja2==3.1.*
itsdangerous==2.2.*          # Session signing
openai==1.65.*               # Whisper + embeddings
pgvector==0.3.*              # pgvector SQLAlchemy integration
pytz==2025.*                 # Timezone handling
python-jose[cryptography]    # JWT decoding for id_token

# requirements-dev.txt
pytest==8.3.*
pytest-asyncio==0.25.*
pytest-cov==6.0.*
httpx==0.28.*                # Test client
black==24.*
ruff==0.9.*
```

---

# APPENDIX B — Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Python files | snake_case | `claude_client.py` |
| Classes | PascalCase | `EmailService`, `OvernightSummary` |
| DB tables | snake_case plural | `email_highlights`, `overnight_summaries` |
| DB columns | snake_case | `relevance_score`, `is_from_ceo` |
| API routes | kebab-case resource nouns | `/api/v1/overnight/summaries` |
| Env vars | UPPER_SNAKE_CASE | `CEO_EMAIL`, `AZURE_TENANT_ID` |
| Pydantic schemas | PascalCase + suffix | `EmailResponse`, `SummaryCreate` |
| Template files | snake_case | `email_detail.html`, `ceo_panel.html` |
| CSS classes | kebab-case | `.email-card`, `.tag-badge-urgent` |
| JS variables | camelCase | `relevanceScore`, `fetchEmails` |

---

*End of ARGO Architecture Plan — v1.0*
*Next step: Begin Phase 1 implementation starting with project scaffold (Task 1.1)*
