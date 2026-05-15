# ARGO — AI Operations Platform

**ARGO** is the internal AI operations platform for **ARP Global Capital** (macro hedge fund, Dubai).  
It centralises intelligence across email, markets, meetings, research, portfolio, clients, economics, and conversation — all powered by Anthropic Claude.

---

## Modules

| #   | Module                          | Description                                                                                                            |
| --- | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 1   | **Email Intelligence**          | Monitors team mailboxes via Microsoft Graph, scores relevance, flags CEO mail, and surfaces AI-generated highlights    |
| 2   | **Overnight Market Summary**    | Generates a pre-open briefing covering overnight emails, market moves, and macro news; delivers via WhatsApp and email |
| 3   | **Meeting Intelligence**        | Accepts audio uploads, transcribes, and produces structured summaries with decisions and action items                  |
| 4   | **Research Data Lake**          | Ingests PDF/text research from brokers and internal sources, chunks and embeds for semantic search                     |
| 5   | **Portfolio Intelligence**      | Tracks positions, runs scenario analysis, and generates trade-idea commentary using current macro views                |
| 6   | **Sales & Client Intelligence** | CRM layer for investor relations — tracks interactions, surfaces follow-up priorities, and logs engagement history     |
| 7   | **Research Intelligence**       | Cross-references broker research against internal views, rates conviction levels, and tracks supply vs thesis          |
| 8   | **Economic Data Intelligence**  | Monitors economic calendar releases, detects surprises, and dispatches AI-powered market-impact analysis               |
| 9   | **AI Assistant**                | Context-aware chat assistant with module routing, tool use, and persistent conversation history                        |

---

## Tech Stack

| Layer                   | Technology                            |
| ----------------------- | ------------------------------------- |
| API framework           | Python 3.11 + FastAPI                 |
| AI model                | Anthropic Claude API (Haiku + Sonnet) |
| Auth / Email / Calendar | Microsoft Graph API via MSAL          |
| Templates               | Jinja2                                |
| Task scheduling         | APScheduler                           |
| WhatsApp delivery       | Twilio WhatsApp API                   |
| News search             | Serper API                            |
| Database (dev)          | SQLite via aiosqlite                  |
| Database (prod)         | PostgreSQL 16 + pgvector              |
| ORM / migrations        | SQLAlchemy 2 async + Alembic          |
| Server                  | Uvicorn                               |
| Containerisation        | Docker + Docker Compose               |
| CI/CD                   | GitHub Actions → AWS ECS (Fargate)    |

---

## Setup (Local Development)

### Prerequisites

- Python 3.11+
- Git
- (Optional for full stack) Docker Desktop

### Step-by-step

**1. Clone the repository**

```bash
git clone https://github.com/your-org/argo.git
cd argo
```

**2. Create and activate a virtual environment**

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

**3. Install dependencies**

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

**4. Configure environment variables**

```bash
cp .env.example .env
# Open .env and fill in all required values (see table below)
```

**5. Run database migrations**

```bash
alembic upgrade head
```

**6. Start the development server**

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

---

## Running Tests

```bash
pytest --cov=app --cov-report=term-missing
```

Coverage must pass 80 % to succeed. To generate an HTML report:

```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

---

## Docker (Local Full Stack)

Spins up the app, a PostgreSQL 16 database, and Adminer (DB browser at port 8080):

```bash
docker-compose up --build
```

To run migrations inside the container after first boot:

```bash
docker-compose exec app alembic upgrade head
```

To run Section 5 Option B (WhatsApp bridge), the compose stack also starts
`whatsapp-bridge` on port `3001`. On first boot, open bridge logs and scan the QR:

```bash
docker-compose logs -f whatsapp-bridge
```

Health check:

```bash
curl http://localhost:3001/health
```

---

## Environment Variables

| Variable                     | Required | Description                                                   |
| ---------------------------- | -------- | ------------------------------------------------------------- |
| `APP_ENV`                    | yes      | `development` / `production` / `test`                         |
| `SECRET_KEY`                 | yes      | Random 32-byte hex string — used for session signing          |
| `DATABASE_URL`               | yes      | SQLAlchemy async DSN (sqlite+aiosqlite or postgresql+asyncpg) |
| `ANTHROPIC_API_KEY`          | yes      | Anthropic API key                                             |
| `CLAUDE_HAIKU_MODEL`         | yes      | Model ID for fast/cheap calls (e.g. `claude-haiku-4-5`)       |
| `CLAUDE_SONNET_MODEL`        | yes      | Model ID for high-quality calls (e.g. `claude-sonnet-4-5`)    |
| `AZURE_TENANT_ID`            | yes      | Azure AD tenant GUID                                          |
| `AZURE_CLIENT_ID`            | yes      | Azure AD app registration client ID                           |
| `AZURE_CLIENT_SECRET`        | yes      | Azure AD client secret                                        |
| `AZURE_REDIRECT_URI`         | yes      | OAuth redirect URI (must match app registration)              |
| `GRAPH_SCOPES`               | yes      | Space-separated Microsoft Graph permission scopes             |
| `CEO_EMAIL`                  | yes      | CEO email address — triggers priority flagging                |
| `TEAM_EMAILS`                | yes      | Comma-separated list of team mailboxes to monitor             |
| `TWILIO_ACCOUNT_SID`         | no       | Twilio account SID (required for WhatsApp delivery)           |
| `TWILIO_AUTH_TOKEN`          | no       | Twilio auth token                                             |
| `TWILIO_WHATSAPP_FROM`       | no       | Twilio sandbox/production WhatsApp number                     |
| `PM_WHATSAPP_NUMBER`         | no       | Portfolio manager's WhatsApp number for overnight summary     |
| `WHATSAPP_BRIDGE_SECRET`     | no       | Shared secret between bridge and `/api/whatsapp/incoming`     |
| `WHATSAPP_BRIDGE_URL`        | no       | URL of the `whatsapp-web.js` bridge (default `http://localhost:3001`) |
| `BRIDGE_ALLOWED_GROUP_IDS`   | no       | Comma-separated WhatsApp group IDs allowed to forward         |
| `BRIDGE_ALLOWED_GROUP_NAMES` | no       | Comma-separated group names allowed to forward (fallback)      |
| `NEWSAPI_KEY`                | no       | NewsAPI key for Section 6/9 ingestion                         |
| `FRED_API_KEY`               | no       | FRED API key for Section 6/8/9 macro series                   |
| `ALPHA_VANTAGE_KEY`          | no       | Alpha Vantage key for alternative market data                 |
| `TRADING_ECONOMICS_KEY`      | no       | TradingEconomics API key for economic calendar                |
| `GRAPH_EMAIL_WEBHOOK_SECRET` | no       | Graph email webhook validation secret                         |
| `GRAPH_CALENDAR_WEBHOOK_SECRET` | no    | Graph calendar webhook validation secret                      |
| `GRAPH_RECORDINGS_WEBHOOK_SECRET` | no  | Graph recordings webhook validation secret                    |
| `META_WHATSAPP_TOKEN`        | no       | Meta Cloud API token (if not using bridge mode)              |
| `META_PHONE_NUMBER_ID`       | no       | Meta Cloud API phone number ID                                |
| `SERPER_API_KEY`             | no       | Serper.dev API key for news search in overnight summary       |
| `OVERNIGHT_SUMMARY_CRON`     | no       | APScheduler cron expression for summary generation            |
| `OVERNIGHT_SUMMARY_TIMEZONE` | no       | Timezone for the overnight summary scheduler                  |
| `AWS_REGION`                 | no       | AWS region for ECR/ECS deployment                             |
| `ECR_REGISTRY`               | no       | AWS ECR registry URL                                          |
| `ECR_REPOSITORY`             | no       | ECR repository name                                           |

---

## Project Structure

```
argo/
├── app/
│   ├── main.py              # FastAPI application factory
│   ├── config.py            # Pydantic settings
│   ├── database.py          # Async engine + session factory
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response schemas
│   ├── routers/             # FastAPI route handlers (one per module)
│   ├── services/            # Business logic layer
│   ├── integrations/        # External API clients (Graph, Claude, Twilio…)
│   ├── tasks/               # APScheduler background tasks
│   └── templates/           # Jinja2 HTML email templates
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── tests/
├── .env.example
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

---

## CI / CD

- **CI** (`ci.yml`): runs on every push to `main`/`develop` and on PRs — linting (ruff), formatting (black), pytest with coverage gate.
- **Deploy** (`deploy.yml`): triggered on push to `main` — builds Docker image, pushes to AWS ECR, runs Alembic migrations via ECS task, deploys updated task definition to ECS Fargate.

Required GitHub Actions secrets for deployment:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

---

## License

Proprietary — ARP Global Capital. All rights reserved.
