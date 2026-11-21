# Bid Studio (`tenders_writing`)

Bid Studio is a Python + FastAPI platform focused on grant and funding applications, with tender writing support: opportunity feed, answer and evidence libraries, bid review tools, procurement intelligence, and white-label consultancy workspaces.

---

## Public Website

The app serves a public marketing site (`/`, `/features`, `/pricing`, `/about`, `/contact`) with the dashboard at `/app`. The contact form posts to `POST /api/v1/contact` and stores requests in the `contact_requests` table. Pricing figures on `/pricing` are placeholders; edit `src/bid_studio/templates/site_pricing.html`.

---

## Core Platform & Implemented Modules

### Core Infrastructure
- **Multi-Tenant Workspaces & Access Review:** Client-isolated workspaces, member role management (`owner`, `admin`, `writer`, `reviewer`, `client`), `GET /api/v1/workspaces/{id}/members`, white-label branding, workspace KPI summaries (`/api/v1/workspaces/{id}/summary`), and timestamped access reviews.
- **Unified Opportunity Feed:** Stores open tenders, awarded notices, and structured funding calls with AI-style summaries, SQL keyword search (`q`), `limit`/`offset` pagination, and `X-Total-Count` response header.
- **Answer & Evidence Libraries:** Reusable verified answers and buyer-formatted evidence items.
- **Quality Review Queue, Orders & Email Delivery Log:** Shared QA pipeline, order tracking and outbound delivery audit logs.
- **Markdown Export Endpoints:** Export deliverables directly as Markdown across Grant Proposals (`/api/v1/grants/proposals/{id}/export`), Win/Loss Debriefs (`/api/v1/debriefs/outcomes/{id}/export`), Clarification Registers (`/api/v1/clarifications/{id}/export`), Pricing Matrices (`/api/v1/pricing/matrices/{id}/export`), Social Value Statements (`/api/v1/social-value/{id}/export`), Intelligence Reports (`/api/v1/intelligence/reports/{id}/export`), and Framework Checklists (`/api/v1/frameworks/{id}/export`).

### Primary Product
1. **Grant and Funding Proposal Writing (`/api/v1/grants`)**
   - Structured funding calls from **EU (Horizon Europe)**, **UKRI**, **World Bank**, and **Foundations**.
   - Automatic criteria & scoring rubric extraction (`/calls/{id}/extract-criteria`), section drafting against criterion weights, weighted score calculation, and submission to the Quality Review Queue.

### Closest to Bid Studio
2. **Win/Loss Debrief Service (`/api/v1/debriefs`)** — Outcome tracking (`won`, `lost`, `withdrawn`), buyer feedback request letters, internal-vs-buyer criterion comparison, and prioritized next-bid fixes.
3. **Clarification Question Service (`/api/v1/clarifications`)** — Pack reader that detects ambiguous phrases (`TBD`, `reasonable`, `etc.`, unstated weightings) and drafts prioritized clarification questions before deadline.
4. **Pricing & Cost-Narrative Writing (`/api/v1/pricing`)** — Reusable pricing templates, margin/contingency price matrices, and evaluator-ready cost-justification narratives.
5. **Social Value & Sustainability Statements (`/api/v1/social-value`)** — UK PPN 06/20 & EU GPP statements covering Net Zero targets, Real Living Wage commitments, supply-chain pledges, and measurable KPIs.

### Tender Data Products
6. **Tender Alerts & Weekly Digest (`/api/v1/alerts`)** — Paid alert subscriptions filtered by sector, notice type, value band, and keywords, generating AI-summarized digests and email logs.
7. **Competitor & Buyer Intelligence Reports (`/api/v1/intelligence`)** — Aggregates stored awarded notices per buyer to surface total/average/min/max contract values, repeat winners, and win-share concentration.
8. **Framework & DPS Onboarding (`/api/v1/frameworks`)** — Guided checklists for Frameworks, Dynamic Purchasing Systems (DPS), and Approved Supplier Lists with live completion percentage.

---

## Project Structure

```text
.
├── api/index.py                  # Vercel Python serverless ASGI entrypoint
├── docs/ci.yml.example           # GitHub Actions CI template (copy to .github/workflows/ci.yml)
├── .env.example                  # Sample environment variables
├── .gitignore
├── LICENSE                       # MIT License
├── pyproject.toml                # Package metadata, pytest & ruff config
├── requirements.txt              # Serverless / pip dependency manifest (incl. psycopg[binary])
├── vercel.json                   # Vercel serverless routing configuration
├── src/bid_studio/
│   ├── config.py                 # Pydantic settings
│   ├── database.py               # SQLAlchemy engine (SQLite FK + Postgres pool_pre_ping) & session
│   ├── main.py                   # FastAPI app & dashboard route
│   ├── models.py                 # Relational models for grants, tenders and intelligence
│   ├── schemas.py                # Pydantic v2 request/response contracts
│   ├── seed.py                   # Idempotent seed data (Riverbend, grants, awards)
│   ├── routers/                  # Modular API routers
│   ├── services/domain_logic.py  # Pure domain & scoring/matching engines
│   ├── static/site.css           # Public website styles
│   └── templates/                # index.html (dashboard at /app) and site_*.html (public pages)
└── tests/                        # Pytest integration & unit test suite
```

---

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

### Run the Server & Web Dashboard

```bash
uvicorn bid_studio.main:app --reload --host 0.0.0.0 --port 8000
```

- Dashboard UI: `http://localhost:8000/`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`

### Run Linting & Tests

```bash
ruff check src tests api
pytest -v
```

### Vercel & PostgreSQL (Supabase) Deployment

The repository includes `api/index.py`, `vercel.json`, and `requirements.txt` (with `psycopg[binary]`) for serverless deployment on Vercel:
- Set `DATABASE_URL` in Vercel environment variables to your PostgreSQL connection string (`postgresql://...` or `postgres://...`).
- If `DATABASE_URL` is omitted on Vercel, SQLite falls back to `/tmp/bid_studio.db` for ephemeral previews.

---

## Environment Variables

See `.env.example`:

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `Bid Studio` | Default application name |
| `APP_ENV` | `development` | Environment label |
| `DATABASE_URL` | `sqlite:///./bid_studio.db` | SQLAlchemy database URL |
| `DEFAULT_WORKSPACE_SLUG` | `primus-demo` | Default workspace slug |
| `DIGEST_SENDER_EMAIL` | `digest@bidstudio.example` | Outbound digest sender address |
| `DELIVERY_SENDER_EMAIL` | `delivery@bidstudio.example` | Outbound delivery sender address |
| `SEED_ON_STARTUP` | `true` | Seed sample notices, grants, Riverbend pack, and templates on empty DB |
