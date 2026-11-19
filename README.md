# Bid Studio (`tenders_writing`)

Bid Studio is a Python + FastAPI platform for tender writing, grant and funding proposals, compliance packs, technical documentation, procurement intelligence, training cohorts, white-label bid consultancies, and public-sector buyer drafting.

---

## Core Platform & Implemented Modules

### Core Infrastructure
- **Multi-Tenant Workspaces & Access Review:** Client-isolated workspaces, member role management (`owner`, `admin`, `writer`, `reviewer`, `client`), white-label branding, workspace KPI summaries (`/api/v1/workspaces/{id}/summary`), and timestamped access reviews.
- **Unified Opportunity Feed:** Stores open tenders, awarded notices, and structured funding calls with AI-style summaries, SQL keyword search (`q`), and `limit`/`offset` pagination.
- **Answer & Evidence Libraries:** Reusable verified answers and buyer-formatted evidence items.
- **Quality Review Queue, Orders & Email Delivery Log:** Shared QA pipeline, order tracking (including `training_enrolment`), and outbound delivery audit logs.
- **Markdown Export Endpoints:** Export deliverables directly as Markdown across Grant Proposals (`/api/v1/grants/proposals/{id}/export`), Technical Docs (`/api/v1/tech-docs/{id}/export`), Win/Loss Debriefs (`/api/v1/debriefs/outcomes/{id}/export`), Social Value Statements (`/api/v1/social-value/{id}/export`), and Public Sector Packs (`/api/v1/public-sector/drafts/{id}/export-pack`).

### Primary Product
0. **Grant and Funding Proposal Writing (`/api/v1/grants`)**
   - Structured funding calls from **EU (Horizon Europe)**, **UKRI**, **World Bank**, and **Foundations**.
   - Automatic criteria & scoring rubric extraction (`/calls/{id}/extract-criteria`), section drafting against criterion weights, weighted score calculation, and submission to the Quality Review Queue.

### New Service Lines
1. **Technical Documentation & API Docs (`/api/v1/tech-docs`)** — Fixed-fee packages (`user_guide`, `api_reference`, `sop`, `release_notes`), staff pipeline (`intake` → `drafting` → `quality_review` → `approved` → `delivered`), QA gate, and email delivery logging.
2. **Compliance & Policy Writing (`/api/v1/compliance`)** — ISO 9001/27001 manuals, data protection policies, and security questionnaires with automated matching against the **Answer Library**.
3. **CV, Capability Statement & Case Study Writing (`/api/v1/bidder-assets`)** — Buyer-formatted team CVs, capability statements, and case studies with one-click promotion to the **Evidence Library**.
4. **Bid Review Marketplace (`/api/v1/marketplace`)** — Independent reviewer directory, criterion-by-criterion pre-submission scoring, and integration with Bid Studio's Quality Queue.

### Closest to Bid Studio
5. **Win/Loss Debrief Service (`/api/v1/debriefs`)** — Outcome tracking (`won`, `lost`, `withdrawn`), buyer feedback request letters, internal-vs-buyer criterion comparison, and prioritized next-bid fixes.
6. **Clarification Question Service (`/api/v1/clarifications`)** — Pack reader that detects ambiguous phrases (`TBD`, `reasonable`, `etc.`, unstated weightings) and drafts prioritized clarification questions before deadline.
7. **Pricing & Cost-Narrative Writing (`/api/v1/pricing`)** — Reusable pricing templates, margin/contingency price matrices, and evaluator-ready cost-justification narratives.
8. **Social Value & Sustainability Statements (`/api/v1/social-value`)** — UK PPN 06/20 & EU GPP statements covering Net Zero targets, Real Living Wage commitments, supply-chain pledges, and measurable KPIs.

### Tender Data Products
9. **Tender Alerts & Weekly Digest (`/api/v1/alerts`)** — Paid alert subscriptions filtered by sector, notice type, value band, and keywords, generating AI-summarized digests and email logs.
10. **Competitor & Buyer Intelligence Reports (`/api/v1/intelligence`)** — Aggregates stored awarded notices per buyer to surface total/average/min/max contract values, repeat winners, and win-share concentration.
11. **Framework & DPS Onboarding (`/api/v1/frameworks`)** — Guided checklists for Frameworks, Dynamic Purchasing Systems (DPS), and Approved Supplier Lists with live completion percentage.

### New Audiences
12. **Training & Workshops (`/api/v1/training`)** — Cohort courses built on the seeded **Riverbend** municipal tender pack, backed by `Order(source="training_enrolment")`.
13. **White-Label for Bid Consultancies (`/api/v1/workspaces/{id}/white-label`, `/api/v1/white-label/consultancies`)** — Custom consultancy branding (brand name, colors, custom domain) with strict client workspace isolation and access review.
14. **Public Sector Side (`/api/v1/public-sector`)** — Buyer-side tender drafting with evaluation criteria weight validation (must sum to 100%), specification clarity scoring, and structured scorecard export.

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
│   ├── models.py                 # Relational models for core + 15 capabilities
│   ├── schemas.py                # Pydantic v2 request/response contracts
│   ├── seed.py                   # Idempotent seed data (Riverbend, grants, awards)
│   ├── routers/                  # Modular API routers
│   ├── services/domain_logic.py  # Pure domain & scoring/matching engines
│   └── templates/index.html      # Interactive Bid Studio web dashboard
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
ruff check src tests
pytest -v
```

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
