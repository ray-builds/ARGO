# ARGO Project Information

## 1. Executive Summary

**ARGO** is a Python/FastAPI internal operations platform for **ARP Global Capital**, a macro hedge fund. It is designed to centralize AI-assisted workflows around:

- Microsoft 365 email triage
- overnight market briefings
- meeting transcription and summarization
- research document ingestion and search
- portfolio scenario analysis
- client/investor CRM workflows
- research supplier tracking
- economic calendar monitoring
- an AI chat assistant over the platform

The project is organized as a monolithic FastAPI web app with:

- server-rendered Jinja templates for browser pages
- JSON API endpoints under `/api/v1/*`
- SQLAlchemy async models against SQLite in development and PostgreSQL in production
- AI integrations through Anthropic Claude and OpenAI
- Microsoft Graph integration for auth/email
- Twilio and Serper integrations for delivery and news search
- APScheduler for in-process cron jobs

This repository contains both **the product code** and **local machine artifacts** like `.env`, `argo_dev.db`, `logs/argo.log`, `.venv`, `.pytest_cache`, and `.git`.

## 2. What Problem It Solves

ARGO exists to reduce operational overhead for an investment team. Instead of forcing PMs/analysts/IR staff to manually monitor inboxes, summarize meetings, search research PDFs, track client follow-ups, or compile morning macro notes, ARGO tries to make those workflows searchable, structured, and AI-assisted inside one internal platform.

### Intended users

- portfolio managers
- investment analysts
- investor relations / sales staff
- internal operations staff
- development/ops maintainers of the ARGO platform

## 3. Current State at a Glance

There is a meaningful gap between the **architecture docs / README / tests** and the **current implementation**:

- The app is real and bootable.
- The main pages, routers, models, schemas, and integrations exist.
- The database schema is substantial and mostly aligned with the model layer.
- A lot of tests are stale and no longer match the code layout.
- Several modules have runtime mismatches or incomplete plumbing.
- Some frontend code targets API routes that do not exist anymore.
- The checked-in `.env` contains real-looking secrets and credentials, which is a serious security issue.

## 4. Technology Stack

### Languages

| Layer | Language |
|---|---|
| Backend | Python |
| Templates | HTML + Jinja2 |
| Frontend behavior | JavaScript |
| Styling | CSS |
| CI/CD and container config | YAML, Dockerfile syntax, TOML, INI |

### Python/runtime versions found

| Source | Version |
|---|---|
| `README.md` | Python 3.11+ |
| `pyproject.toml` | Ruff/Black target `py311` |
| `Dockerfile` | `python:3.11-slim` |
| local `.venv` actually present | Python 3.12.2 |

This means the repo is **configured around Python 3.11**, but the current local virtualenv is **Python 3.12.2**.

### Main frameworks/libraries

From `requirements.txt`:

| Package | Version | Purpose |
|---|---:|---|
| `fastapi[standard]` | 0.115.0 | Web framework |
| `uvicorn[standard]` | 0.30.6 | ASGI server |
| `jinja2` | 3.1.4 | HTML templates |
| `python-multipart` | 0.0.9 | Form/file uploads |
| `httpx` | 0.27.2 | Async HTTP client |
| `pydantic` | 2.8.2 | Validation/schema layer |
| `pydantic-settings` | 2.4.0 | Environment-based settings |
| `python-dotenv` | 1.0.1 | `.env` loading |
| `sqlalchemy[asyncio]` | 2.0.35 | ORM and async DB layer |
| `aiosqlite` | 0.20.0 | Async SQLite driver |
| `asyncpg` | 0.29.0 | Async Postgres driver |
| `alembic` | 1.13.3 | Migrations |
| `anthropic` | 0.34.2 | Claude API client |
| `msal` | 1.30.0 | Microsoft auth |
| `twilio` | 9.3.2 | WhatsApp delivery |
| `apscheduler` | 3.10.4 | Scheduled jobs |
| `loguru` | 0.7.2 | Logging |
| `pgvector` | 0.3.2 | Vector column integration |
| `openai` | 1.45.0 | Whisper + embeddings |
| `pillow` | 10.4.0 | Image handling dependency |
| `itsdangerous` | 2.2.0 | Session signing helpers |
| `pytz` | 2024.1 | Timezone handling |

From `requirements-dev.txt`:

| Package | Version | Purpose |
|---|---:|---|
| `pytest` | 8.3.3 | Tests |
| `pytest-asyncio` | 0.24.0 | Async tests |
| `pytest-cov` | 5.0.0 | Coverage |
| `httpx` | 0.27.2 | Test client support |
| `ruff` | 0.6.4 | Linting |
| `black` | 24.8.0 | Formatting |
| `factory-boy` | 3.3.1 | Test factories |

## 5. High-Level Architecture

## 5.1 Runtime architecture

```text
Browser
  -> FastAPI app
     -> page routers render Jinja templates
     -> API routers return JSON
     -> services orchestrate workflows
     -> core clients talk to Claude / Graph / Twilio / Serper / OpenAI
     -> SQLAlchemy async session talks to SQLite or Postgres
     -> APScheduler runs in-process scheduled jobs
```

## 5.2 Code architecture

| Area | Responsibility |
|---|---|
| `app/main.py` | App factory, middleware, startup/shutdown, router registration |
| `app/config.py` | Environment-backed settings |
| `app/core/` | Shared integrations and infra helpers |
| `app/routes/` | Top-level auth/dashboard/page/system routes |
| `app/modules/` | Business features, each with router/service/prompts |
| `app/models/` | SQLAlchemy models |
| `app/schemas/` | Pydantic request/response models |
| `app/templates/` | Browser views |
| `static/` | CSS and JS |
| `alembic/` | DB migrations |
| `tests/` | Test suite |

## 5.3 Cross-component flow

### Authentication

1. User visits `/login`
2. App redirects to Azure AD via MSAL
3. Callback exchanges code for Graph token
4. User row is created/updated in DB
5. Session cookie stores `user_id`
6. Later requests load user from DB via `app/dependencies.py`

### Browser page flow

1. User opens a page route like `/dashboard` or `/email`
2. Jinja template is served
3. JavaScript in page/static files fetches `/api/v1/*` endpoints
4. API endpoints call module services
5. Services query DB and external APIs

### Scheduled overnight flow

1. App startup registers APScheduler job
2. Scheduler fires `run_overnight_summary`
3. Service fetches emails from DB, mock market data, Serper news
4. Claude synthesizes briefing
5. Summary is stored in `overnight_summaries`
6. Twilio/Graph delivery is attempted

## 6. Installation, Configuration, and Running

## 6.1 Local development

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Default local URL:

```text
http://localhost:8000
```

Docs in non-production mode:

```text
http://localhost:8000/api/docs
http://localhost:8000/api/redoc
```

## 6.2 Docker

```powershell
docker-compose up --build
docker-compose exec app alembic upgrade head
```

Services:

| Service | Port | Notes |
|---|---:|---|
| app | 8000 | FastAPI app |
| db | 5432 | Postgres 16 |
| adminer | 8080 | DB browser |

## 6.3 Production shape

- Docker image built by GitHub Actions
- pushed to AWS ECR
- ECS Fargate service updated
- migrations run through an ECS task

## 7. Environment Variables and Config

## 7.1 Variables actually used by code

| Variable | Used in code? | Purpose | Required for full functionality |
|---|---|---|---|
| `ENVIRONMENT` / `APP_ENV` | partially | env mode; code primarily uses `environment` field | yes |
| `APP_BASE_URL` | yes | auth redirect base URL | yes for auth |
| `APP_HOST` | yes | app host binding setting | no |
| `APP_PORT` | yes | app port setting | no |
| `SECRET_KEY` | yes | session signing | yes |
| `LOG_LEVEL` | yes | loguru level | no |
| `DATABASE_URL` | yes | DB connection string | yes |
| `ANTHROPIC_API_KEY` | yes | Claude access | yes for AI features |
| `CLAUDE_HAIKU_MODEL` | defined in config | intended model override | effectively ignored by client constants |
| `CLAUDE_SONNET_MODEL` | defined in config | intended model override | effectively ignored by client constants |
| `OPENAI_API_KEY` | yes | Whisper + embeddings | required for meeting transcription and real embeddings |
| `OPENAI_EMBEDDING_MODEL` | yes | embedding model | optional |
| `AZURE_TENANT_ID` | yes | MSAL | yes for auth |
| `AZURE_CLIENT_ID` | yes | MSAL | yes for auth |
| `AZURE_CLIENT_SECRET` | yes | MSAL | yes for auth |
| `GRAPH_SCOPES` | yes | delegated Graph scopes | yes for Graph features |
| `CEO_EMAIL` | yes | CEO identity and fallback email target | yes |
| `TEAM_EMAILS` | yes | comma-separated team mailboxes | partially used |
| `TWILIO_ACCOUNT_SID` | yes | Twilio auth | optional |
| `TWILIO_AUTH_TOKEN` | yes | Twilio auth | optional |
| `TWILIO_WHATSAPP_FROM` | yes | WhatsApp sender | optional |
| `PM_WHATSAPP_NUMBER` | yes | briefing recipient | optional |
| `SERPER_API_KEY` | yes | news search | optional |
| `OVERNIGHT_SUMMARY_TIMEZONE` | defined | intended scheduler timezone | currently not honored by scheduler |
| `OVERNIGHT_WINDOW_START_HOUR` | yes | overnight email window start | partially honored |
| `OVERNIGHT_WINDOW_END_HOUR` | in `.env` only | not in settings model | currently ignored |
| `ENABLE_WHATSAPP` | yes | feature flag | optional |
| `ENABLE_EMAIL_FETCH` | yes | feature flag | optional |
| `ENABLE_OVERNIGHT_CRON` | yes | scheduler toggle | optional |
| `AWS_REGION` | yes | deployment config | prod only |
| `ECR_REGISTRY` | yes | deployment config | prod only |
| `ECR_REPOSITORY` | yes | deployment config | prod only |

## 7.2 Hidden/config files

| File | Role |
|---|---|
| `.env` | local secrets and runtime config; **currently contains real-looking credentials** |
| `.env.example` | environment template |
| `.gitignore` | ignores secrets, DBs, logs, caches, uploads, envs |
| `pyproject.toml` | Ruff/Black/Pytest/Coverage config |
| `alembic.ini` | Alembic settings |
| `blackbox_mcp_settings.json` | local MCP/Notion connector settings |

## 8. External Services and APIs

| Service | Used for | Code location |
|---|---|---|
| Microsoft Graph API | mailbox reads, send mail, archive mail, calendar access | `app/core/graph_client.py` |
| Azure AD / MSAL | SSO login and token exchange | `app/core/graph_client.py`, `app/routes/auth.py` |
| Anthropic Claude | classification, summarization, routing, Q&A, scenario analysis | `app/core/claude_client.py` |
| OpenAI | Whisper transcription and embeddings | `app/modules/meeting_intelligence/transcriber.py`, `app/modules/research_lake/embeddings.py` |
| Twilio WhatsApp | morning briefings and econ alerts | `app/core/twilio_client.py` |
| Serper | financial/news search | `app/core/serper_client.py` |
| PostgreSQL + pgvector | intended production DB/vector search | settings, Docker, migration comments |
| SQLite | local development DB | settings/defaults |
| AWS ECS/ECR | deployment | `.github/workflows/deploy.yml` |

## 9. Data Model / Schema

## 9.1 Tables

### `users`

- Azure-authenticated users
- stores role, display identity, optional WhatsApp number
- stores Graph access/refresh tokens server-side

### `emails`

- normalized email records from Microsoft Graph
- includes scoring/classification fields
- soft archive flags

### `email_highlights`

- one-to-many AI highlights attached to emails

### `overnight_summaries`

- daily morning briefing records
- JSON stored as text for sections
- delivery state and error columns

### `meetings`

- meeting metadata, transcript, summary, decisions, quotes

### `meeting_action_items`

- extracted action items for meetings

### `documents`

- research lake documents from PDF/paste/email-like sources

### `document_chunks`

- chunked document text used for search/RAG
- migration omits vector column for compatibility, but model includes `embedding`

### `positions`

- current or historical portfolio positions

### `scenarios`

- AI-generated scenario analyses and trade ideas

### `clients`

- CRM entities

### `client_interactions`

- logged touchpoints per client

### `research_items`

- structured supplier/internal research summaries

### `economic_events`

- economic calendar items and release analysis

### `chat_conversations`

- persistent AI assistant conversations

### `chat_messages`

- messages inside conversations

## 9.2 Important schema observations

- Many pseudo-structured fields are stored as raw `Text` JSON:
  - `meetings.attendees`
  - `meetings.decisions`
  - `meetings.key_quotes`
  - `documents`/`research` topic-like fields
  - `scenarios.trade_ideas`
  - `overnight_*_section`
  - `chat_messages.tool_calls`
- This keeps SQLite/Postgres compatibility simple, but shifts validation burden into app code.
- `document_chunks.embedding` exists in the ORM but was intentionally omitted from migration `0001`, so migration-state and model-state are not identical.

## 10. Major Features and Workflows

## 10.1 Authentication

- Login page at `/login`
- Microsoft login trigger at `/login/microsoft`
- callback at `/auth/callback`
- logout at `/logout`

Role assignment:

- CEO email -> `ceo`
- hardcoded `rshhadeh@arpglobalcapital.com` -> `dev_lead`
- everyone else -> `staff`

## 10.2 Dashboard

Dashboard combines:

- unread/urgent email counts
- overnight summary widget
- econ events widget
- meeting count widget
- CEO inbox preview

Actual implementation status:

- page exists
- server-side stat aggregation exists
- client-side widget loading has some endpoint mismatches

## 10.3 Email Intelligence

Workflow:

1. User triggers sync
2. Service fetches mailbox messages from Graph
3. Claude classifies each email into one tag
4. Email is stored in DB
5. Optional highlight row is stored
6. Inbox/CEO views query stored emails
7. User can archive selected or all `SKIP` emails

Available capabilities:

- inbox listing
- CEO-email grouping
- stats
- archive by IDs
- archive all skip-tagged emails

## 10.4 Overnight Summary

Workflow:

1. Query overnight emails already stored in DB
2. Fetch mock market data
3. Fetch news via Serper
4. Ask Claude for structured JSON briefing
5. Build WhatsApp text body
6. Save summary
7. Attempt WhatsApp delivery
8. Attempt Graph email fallback if WhatsApp fails

Current state:

- core flow is implemented
- several call signatures are currently broken
- market data is mock only

## 10.5 Meeting Intelligence

Workflow:

1. Create meeting from pasted transcript or audio upload
2. If audio exists, send to Whisper
3. Claude summarizes transcript
4. Decisions/key quotes/action items are extracted
5. User can search across meetings
6. User can ask a chat-style question over meeting excerpts
7. User can mark action items complete

## 10.6 Research Lake

Workflow:

1. Upload PDF/TXT/MD/DOCX or paste text
2. Save source file under `uploads/research`
3. Extract text
4. Chunk content
5. Generate embeddings via OpenAI
6. Store document + chunks
7. Semantic search uses cosine similarity in Python over stored chunk embeddings
8. Q&A retrieves top chunks then asks Claude to answer with citations

## 10.7 Portfolio Intelligence

Workflow:

1. Create positions manually or upload CSV
2. Aggregate portfolio composition
3. Ask Claude for macro scenario analysis
4. Store scenario with trade ideas

## 10.8 Sales / Client Intelligence

Workflow:

1. Create client records
2. Update client profiles
3. Log interactions
4. Search CRM records
5. Generate AI follow-up talking points for stale investor/prospect relationships

## 10.9 Research Intelligence

Workflow:

1. Ingest research note/report/call/podcast text
2. Claude extracts thesis/data points/conviction/topics
3. Store structured research item
4. Rate research
5. View supplier statistics
6. Build weekly digest of recent items

## 10.10 Economic Intelligence

Workflow:

1. Read today’s or ranged economic events from DB
2. Optionally refresh calendar from external source stub
3. Record actual release value
4. Compute beat/miss/in-line heuristically
5. Ask Claude for market-impact analysis
6. Send morning WhatsApp alert for high-importance events

## 10.11 AI Assistant

Workflow:

1. User opens assistant UI
2. Start new or existing conversation
3. Claude classifies which module the question belongs to
4. Another Claude call answers with module-flavored context
5. Conversation/messages are stored in DB

Important limitation:

- this assistant does **not** yet do real tool execution across module data beyond light prompting and DB-backed conversation persistence

## 11. Entry Points and Routes

## 11.1 Browser routes

| Route | Purpose |
|---|---|
| `/` | redirects to dashboard or login |
| `/login` | login page |
| `/login/microsoft` | start SSO |
| `/auth/callback` | OAuth callback |
| `/logout` | clear session |
| `/dashboard` | main dashboard |
| `/email` | inbox page |
| `/email/{email_id}` | email detail page |
| `/overnight` | overnight list page |
| `/overnight/{summary_id}` | overnight detail page |
| `/meetings` | meeting list |
| `/meetings/{meeting_id}` | meeting detail |
| `/datalake` | research lake page |
| `/portfolio` | portfolio page |
| `/clients` | clients page |
| `/clients/{client_id}` | client detail |
| `/research` | research page |
| `/research/{item_id}` | research detail route is referenced, but template is missing |
| `/econ` | economic calendar page |
| `/assistant` | AI assistant page |

## 11.2 API roots

| Prefix | Module |
|---|---|
| `/api/v1/overnight` | overnight summary |
| `/api/v1/emails` | email intelligence |
| `/api/v1/meetings` | meeting intelligence |
| `/api/v1/research` | research lake |
| `/api/v1/portfolio` | portfolio intelligence |
| `/api/v1/clients` | sales intelligence |
| `/api/v1/research-intel` | research intelligence |
| `/api/v1/econ` | economic intelligence |
| `/api/v1/assistant` | AI assistant |

## 12. File and Folder Inventory

This section documents the repository contents. To keep it useful for maintainers, it distinguishes:

- **authored project files**
- **runtime/generated local artifacts**
- **environment-managed directories**

### 12.1 Root

| Path | Type | Purpose |
|---|---|---|
| `.git/` | dir | Git metadata and history |
| `.github/` | dir | CI/CD workflows |
| `.pytest_cache/` | dir | local pytest cache |
| `.venv/` | dir | local Python virtualenv with installed packages |
| `alembic/` | dir | migrations |
| `app/` | dir | application package |
| `logs/` | dir | runtime logs |
| `static/` | dir | JS/CSS assets |
| `tests/` | dir | test suite |
| `.env` | file | local runtime secrets; currently unsafe to commit |
| `.env.example` | file | sample env file |
| `.gitignore` | file | ignore rules |
| `alembic.ini` | file | migration config |
| `ARGO_ARCHITECTURE_PLAN.md` | file | long-form intended architecture/spec document |
| `argo_dev.db` | file | local SQLite dev database |
| `blackbox_mcp_settings.json` | file | local MCP connector config |
| `docker-compose.yml` | file | local app + postgres + adminer stack |
| `Dockerfile` | file | container build |
| `pyproject.toml` | file | dev-tool config |
| `README.md` | file | project overview and quickstart |
| `requirements-dev.txt` | file | dev dependencies |
| `requirements.txt` | file | app dependencies |
| `Info.md` | file | this document |

### 12.2 `.github/workflows`

| Path | Purpose |
|---|---|
| `.github/workflows/ci.yml` | lint/test/coverage pipeline |
| `.github/workflows/deploy.yml` | AWS ECR/ECS deployment pipeline |

### 12.3 `alembic`

| Path | Purpose |
|---|---|
| `alembic/env.py` | Alembic environment bootstrap |
| `alembic/script.py.mako` | migration template |
| `alembic/versions/0001_initial_schema.py` | initial schema migration |
| `alembic/versions/0002_store_graph_tokens_server_side.py` | adds Graph token columns to `users` |

### 12.4 `app`

| Path | Purpose |
|---|---|
| `app/__init__.py` | package marker |
| `app/main.py` | app factory, middleware, startup/shutdown, health/root handlers |
| `app/config.py` | settings model |
| `app/dependencies.py` | DB/auth FastAPI dependencies |

### 12.5 `app/core`

| Path | Purpose |
|---|---|
| `app/core/__init__.py` | package marker |
| `app/core/claude_client.py` | Anthropic client wrapper |
| `app/core/database.py` | SQLAlchemy engine/session lifecycle |
| `app/core/graph_client.py` | Microsoft Graph/MSAL wrapper |
| `app/core/scheduler.py` | APScheduler singleton and job registration |
| `app/core/serper_client.py` | Serper wrapper |
| `app/core/twilio_client.py` | Twilio WhatsApp wrapper |

### 12.6 `app/routes`

| Path | Purpose |
|---|---|
| `app/routes/__init__.py` | package marker |
| `app/routes/auth.py` | login/logout/OAuth callback |
| `app/routes/dashboard.py` | dashboard page + dashboard stats API |
| `app/routes/health.py` | health endpoint |
| `app/routes/pages.py` | browser page routes for all modules |

### 12.7 `app/models`

| Path | Purpose |
|---|---|
| `app/models/__init__.py` | imports package |
| `app/models/base.py` | declarative base, timestamps, UUID helper |
| `app/models/user.py` | user/auth model |
| `app/models/email.py` | email + highlight models |
| `app/models/summary.py` | overnight summary model |
| `app/models/meeting.py` | meeting + action item models |
| `app/models/document.py` | document + document chunk models |
| `app/models/portfolio.py` | position + scenario models |
| `app/models/client.py` | client + client interaction models |
| `app/models/research.py` | research item model |
| `app/models/economic.py` | economic event model |
| `app/models/chat.py` | conversation + message models |

### 12.8 `app/schemas`

| Path | Purpose |
|---|---|
| `app/schemas/__init__.py` | package marker |
| `app/schemas/email.py` | email request/response schemas |
| `app/schemas/summary.py` | overnight summary schemas |
| `app/schemas/meeting.py` | meeting schemas |
| `app/schemas/document.py` | research lake schemas |
| `app/schemas/portfolio.py` | portfolio schemas |
| `app/schemas/client.py` | CRM schemas |
| `app/schemas/research.py` | research intelligence schemas |
| `app/schemas/economic.py` | economic event schemas |
| `app/schemas/chat.py` | assistant chat schemas |

### 12.9 `app/modules`

| Path | Purpose |
|---|---|
| `app/modules/__init__.py` | package marker |
| `app/modules/overnight_summary/__init__.py` | module marker |
| `app/modules/overnight_summary/service.py` | overnight pipeline logic |
| `app/modules/overnight_summary/router.py` | overnight APIs + HTML view |
| `app/modules/overnight_summary/scheduler_job.py` | scheduled job entrypoint |
| `app/modules/overnight_summary/market_data.py` | mock market data generator |
| `app/modules/overnight_summary/prompts.py` | Claude prompt templates |
| `app/modules/email_intelligence/__init__.py` | module marker |
| `app/modules/email_intelligence/service.py` | email sync/classification/query logic |
| `app/modules/email_intelligence/router.py` | email APIs + HTML views |
| `app/modules/email_intelligence/classifier.py` | tag color/priority helpers |
| `app/modules/email_intelligence/prompts.py` | email classification prompts |
| `app/modules/meeting_intelligence/__init__.py` | module marker |
| `app/modules/meeting_intelligence/service.py` | meeting workflows |
| `app/modules/meeting_intelligence/router.py` | meeting APIs + HTML views |
| `app/modules/meeting_intelligence/transcriber.py` | Whisper integration |
| `app/modules/meeting_intelligence/prompts.py` | meeting prompts |
| `app/modules/research_lake/__init__.py` | module marker |
| `app/modules/research_lake/service.py` | ingestion/search/QA logic |
| `app/modules/research_lake/router.py` | research lake APIs + HTML views |
| `app/modules/research_lake/chunker.py` | file extraction + word-based chunking |
| `app/modules/research_lake/embeddings.py` | embedding generation + char-based chunking |
| `app/modules/research_lake/prompts.py` | Q&A prompt |
| `app/modules/portfolio_intelligence/__init__.py` | module marker |
| `app/modules/portfolio_intelligence/service.py` | position/scenario logic |
| `app/modules/portfolio_intelligence/router.py` | portfolio APIs |
| `app/modules/portfolio_intelligence/prompts.py` | scenario prompts |
| `app/modules/sales_intelligence/__init__.py` | module marker |
| `app/modules/sales_intelligence/service.py` | CRM logic |
| `app/modules/sales_intelligence/router.py` | CRM APIs |
| `app/modules/sales_intelligence/prompts.py` | follow-up prompts |
| `app/modules/research_intelligence/__init__.py` | module marker |
| `app/modules/research_intelligence/service.py` | supplier research logic |
| `app/modules/research_intelligence/router.py` | research-intel APIs |
| `app/modules/research_intelligence/prompts.py` | research summarization/digest prompts |
| `app/modules/economic_intelligence/__init__.py` | module marker |
| `app/modules/economic_intelligence/service.py` | econ calendar/release logic |
| `app/modules/economic_intelligence/router.py` | econ APIs |
| `app/modules/economic_intelligence/prompts.py` | econ analysis prompts |
| `app/modules/ai_assistant/__init__.py` | module marker |
| `app/modules/ai_assistant/service.py` | conversation and routing logic |
| `app/modules/ai_assistant/router.py` | assistant APIs |
| `app/modules/ai_assistant/prompts.py` | assistant prompts |

### 12.10 `app/templates`

| Path | Purpose |
|---|---|
| `app/templates/base.html` | base layout with sidebar/topbar |
| `app/templates/dashboard.html` | dashboard UI |
| `app/templates/auth/login.html` | login page |
| `app/templates/email/inbox.html` | inbox page |
| `app/templates/email/detail.html` | email detail page |
| `app/templates/email/ceo_boxes.html` | CEO-focused email page |
| `app/templates/overnight/summaries.html` | overnight summary list |
| `app/templates/overnight/detail.html` | overnight summary detail |
| `app/templates/meetings/list.html` | meeting list/upload page |
| `app/templates/meetings/detail.html` | meeting detail page |
| `app/templates/research_lake/search.html` | research lake main page |
| `app/templates/research_lake/upload.html` | research upload page |
| `app/templates/portfolio/dashboard.html` | portfolio page |
| `app/templates/clients/list.html` | client list page |
| `app/templates/clients/detail.html` | client detail page |
| `app/templates/research/list.html` | research intelligence list page |
| `app/templates/economic/calendar.html` | economic calendar page |
| `app/templates/chat/index.html` | assistant chat page |

Notable missing file:

- `app/templates/research/detail.html` is referenced by `app/routes/pages.py` but is not present in the repo.

### 12.11 `static`

| Path | Purpose |
|---|---|
| `static/js/main.js` | global modal/toast/fetch helpers |
| `static/js/email.js` | inbox filtering/archive/refresh helpers |
| `static/js/chat.js` | assistant chat UX |
| `static/css/main.css` | app-wide styling |
| `static/css/email_cards.css` | specialized email card styling |

### 12.12 `tests`

| Path | Purpose |
|---|---|
| `tests/__init__.py` | package marker |
| `tests/conftest.py` | shared fixtures and test env defaults |
| `tests/test_auth.py` | auth and redirect tests |
| `tests/test_health.py` | health endpoint tests |
| `tests/test_core.py` | settings/chunker/Claude/classifier tests |
| `tests/test_email_intelligence.py` | email module tests |
| `tests/test_overnight_summary.py` | overnight module tests |
| `tests/test_meeting_intelligence.py` | meeting module tests |
| `tests/test_research_lake.py` | research lake tests |
| `tests/test_portfolio_intelligence.py` | portfolio tests |
| `tests/test_sales_intelligence.py` | CRM tests |
| `tests/test_research_intelligence.py` | research-intel tests |
| `tests/test_economic_intelligence.py` | econ tests |
| `tests/test_ai_assistant.py` | assistant tests |

### 12.13 Runtime/generated artifacts in repo

| Path | Purpose |
|---|---|
| `logs/argo.log` | runtime log file |
| `argo_dev.db` | local SQLite DB with developer data |
| `.pytest_cache/*` | pytest cache |
| `.venv/*` | local environment packages and scripts |

## 13. Important Mismatches, Risks, and Potentially Broken Areas

This is the highest-signal section for maintainers.

### Security / hygiene

1. **`.env` is committed with real-looking secrets**
   - includes API keys, Azure IDs/secrets, Serper key, Twilio SID, etc.
   - this should be treated as an incident: rotate secrets and remove from source control history

### Architecture drift

2. **Tests still target old package paths**
   - most failing tests import `app.services.*`
   - current code uses `app.modules.*`
   - test suite is largely out of sync with the implementation

3. **README / architecture plan overstate completeness**
   - several flows are stubbed, mock-backed, or mismatched

### Concrete code issues

4. **`OvernightSummaryService.deliver_summary()` calls Twilio incorrectly**
   - calls `twilio.send_whatsapp(to_number=..., message=...)`
   - actual method signature is `send_whatsapp(to_number, body)`
   - also fails to `await` the async method

5. **`OvernightSummaryService._fetch_news()` calls Serper with unsupported arguments**
   - passes `date_range="d"`
   - `SerperClient.search_news()` does not accept `date_range`

6. **Graph email send return value mismatch**
   - `GraphClient.send_email()` returns `None`
   - callers treat it like `bool success`
   - this affects overnight fallback logic

7. **Assistant service uses nonexistent Claude client method**
   - `AIAssistantService.chat()` calls `complete_with_history()`
   - `ClaudeClient` does not implement it

8. **Chat conversation model lacks a mapped `updated_at` field**
   - service code reads/writes `conversation.updated_at`
   - `ChatConversation` inherits `TimestampMixin`, so field exists at ORM level
   - but workflow logic still appears under-tested and mismatched with expectations around `message_count`

9. **Research intelligence model/service mismatch**
   - service writes `text_content` and `submitted_by_email`
   - model fields are `thesis_summary`/`ingested_by_email`; there is no `text_content` or `submitted_by_email`
   - this module is currently not aligned with its model

10. **Sales intelligence model/service mismatch**
   - `Client` model requires `created_by_email`
   - service `create_client()` does not set it

11. **Portfolio scenario model/service mismatch**
   - `Scenario` model requires `scenario_type` and `created_by_email`
   - service `run_scenario()` does not populate them

12. **Portfolio position model/service mismatch**
   - `Position` model requires `uploaded_by_email`
   - service `create_position()` does not set it

13. **Meeting service/model mismatch**
   - service uses `created_by_email`
   - model field is `uploaded_by_email`

14. **Research item page references missing template**
   - route points to `research/detail.html`
   - file absent

15. **Dashboard frontend targets nonexistent endpoints / shapes**
   - expects `/api/v1/meetings/stats`
   - expects CEO email endpoint to return a flat array, but backend returns grouped dict
   - uses `ev.release_time` while schema field is `release_time_utc`

16. **Email frontend targets old endpoints**
   - `static/js/email.js` and some templates use `/api/v1/email/...`
   - actual router is mounted at `/api/v1/emails/...`

17. **Scheduler ignores configurable timezone setting**
   - `app/core/scheduler.py` hardcodes `Europe/London`

18. **Model override env vars are not actually honored by Claude client**
   - client uses module constants `HAIKU` and `SONNET`
   - settings contain model names, but they are not wired through

19. **Chunking logic is duplicated and inconsistent**
   - `research_lake/chunker.py`: word-based chunking
   - `research_lake/embeddings.py`: character-based chunking
   - service imports the embeddings version, not the file-extraction version

20. **Migration/model state for embeddings diverges**
   - migration omits `document_chunks.embedding`
   - model includes it
   - behavior differs by DB/setup path

## 14. Testing and Verification Status

I ran the local test suite with:

```powershell
.\.venv\Scripts\pytest.exe
```

Result:

- **69 tests collected**
- **18 passed**
- **51 failed**

Primary failure reason:

- most failing tests import nonexistent `app.services.*` modules

Other warnings:

- deprecated custom `event_loop` fixture usage
- Pydantic warning on `model_used`
- Starlette `TemplateResponse` usage deprecation warning

## 15. CI/CD and Automation

## 15.1 CI

`ci.yml` runs:

1. checkout
2. Python 3.11 setup
3. dependency install
4. `ruff check .`
5. `black --check .`
6. `pytest --cov=app --cov-report=xml --cov-report=term-missing --cov-fail-under=80`
7. coverage upload

## 15.2 Deployment

`deploy.yml`:

1. builds Docker image
2. pushes SHA + `latest` tags to ECR
3. runs ECS migration task with `alembic upgrade head`
4. renders ECS task definition with new image
5. deploys ECS service

Hardcoded placeholders/risk:

- ECS subnet/security group values in deploy workflow are placeholder-like (`subnet-xxx`, `sg-xxx`)

## 16. User Flow Summary

From the perspective of a first-time internal user:

1. Open ARGO in the browser.
2. Authenticate via Microsoft login.
3. Land on the dashboard.
4. Review:
   - urgent/unread email counts
   - latest overnight summary
   - today’s economic events
   - meeting activity
5. Navigate to a module:
   - **Email** to sync/triage/archive
   - **Overnight** to read briefings
   - **Meetings** to upload audio or paste transcript
   - **Research Lake** to upload/search/ask questions over documents
   - **Portfolio** to add positions or run scenarios
   - **Clients** to create/update client records and log interactions
   - **Research** to ingest supplier research and review digests
   - **Econ** to inspect calendar and analyze releases
   - **Assistant** to ask ARGO questions conversationally

## 17. Bottom-Line Assessment

ARGO is a solid early-stage internal platform with a coherent domain model and a clear product direction. The codebase has real substance: auth, persistence, scheduled jobs, templates, APIs, and integrations are all present. The main risk is not lack of ambition but **drift**:

- docs vs code
- tests vs code
- frontend vs backend
- services vs models

For a new maintainer, the most important mental model is:

- **the schema and module structure are the backbone**
- **many features are conceptually implemented**
- **several modules need alignment work before they are production-trustworthy**

If this repo is being actively developed, the next highest-value work would be:

1. rotate/remove leaked secrets
2. reconcile service/model mismatches
3. fix broken frontend/backend route mismatches
4. repair assistant and overnight delivery call chains
5. either rewrite or delete stale tests
