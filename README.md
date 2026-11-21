# Bid Studio (`tenders_writing`)

Bid Studio is a Python + FastAPI platform focused on grant and funding applications, with tender writing support: opportunity feed, answer and evidence libraries, bid review tools, procurement intelligence, and white-label consultancy workspaces.

---

## Database upgrades

There are no migration files. On startup the app creates missing tables and **adds missing columns** to existing tables (never dropping, renaming or retyping anything), so upgrading a database that predates a new field is safe. Foreign-key constraints are not added to existing tables, and a column type change needs a manual migration.

---

## Licence keys

Bid Studio can require a signed licence key. Keys are verified **offline** with Ed25519: the app holds only your *public* key, so it can check keys but never create them.

**Vendor setup (once, on your own machine, not on a customer deployment):**

```bash
python -m bid_studio.tools.license_admin keygen --out license-private.pem
```

This writes the private key (mode 600; `*.pem` is git-ignored) and prints `LICENSE_PUBLIC_KEY=...`. **Back the private key up and keep it secret:** if it is lost you cannot issue keys, and if it leaks anyone can mint them. Never commit it.

**Issue a key for a customer:**

```bash
python -m bid_studio.tools.license_admin issue --private-key license-private.pem \
  --licensee "Acme Ltd" --plan team --days 365
```

Plans: `starter` (1 workspace, 3 members per workspace), `team` (1, 15), `consultancy` (unlimited). Override with `--workspaces` / `--members`, or use `--perpetual`. `inspect KEY --public-key ...` verifies a key.

**Deployment settings:**

| Variable | Meaning |
| --- | --- |
| `LICENSE_ENFORCEMENT` | `off` (default, no checks), `warn` (banner only), `on` (block until a valid key is installed) |
| `LICENSE_PUBLIC_KEY` | your public key from `keygen` (required for `warn`/`on`) |
| `LICENSE_KEY` | the customer's key; overrides any key activated in the app |
| `LICENSE_GRACE_DAYS` | days the app keeps working after expiry (default 14) |
| `LICENSE_REVOKED_IDS` | comma-separated key ids to refuse |

Customers can also paste a key at `/app/license`. With enforcement `on`, the dashboard, Studio and API return 402 (or redirect to `/app/license`) until a valid key is installed. The public website, `/grants`, the contact form, health check, API docs and the public feed read endpoints stay open. Plan limits are enforced when creating workspaces and members.

**Limits you should know about:** this is a licence-compliance mechanism, not copy protection. The code is Python, so a determined user with the source can remove the check. Keys cannot be revoked remotely; revocation needs `LICENSE_REVOKED_IDS` to be updated on each deployment, so prefer short-lived keys (for example one year) for tighter control.

---

## Public Website

The app serves a public marketing site (`/`, `/features`, `/pricing`, `/about`, `/contact`) with the dashboard at `/app`. The contact form posts to `POST /api/v1/contact` and stores requests in the `contact_requests` table. Pricing figures on `/pricing` are placeholders; edit `src/bid_studio/templates/site_pricing.html`.

---

## Documentation & Compliance Writing

A fixed-fee service line for technical documentation and compliance writing, alongside grants. Dashboard tab **Docs & Compliance Writing** (the marketplace has a matching *CVs, capability statements and case studies* job type); editor at `/app/docs/{project_id}`; API under `/api/v1/services`.

- **Technical documentation templates:** user guide, API reference, standard operating procedure, release notes.
- **Compliance and policy templates:** information security policy (ISO 27001 aligned), data protection policy (UK GDPR), incident response plan, quality manual (ISO 9001 aligned).
- **Bid assets:** templates for a team CV (buyer format, with a "fit to the evaluation criteria" section), a capability statement, and a case study (context, challenge, solution, delivery, results, key metrics, testimonial, relevance). Once a project is quality-approved, **Save to evidence library** turns it into an evidence item: a summary from the key sections plus metrics parsed from `Label: value` lines in the case study's Key metrics section. Evidence items then appear in Grant Studio suggestions (Insert & cite) and in the editor's Library tab. Each asset can be saved once.
- **Security questionnaires:** paste the customer's questions (one per line); each is matched against the workspace Answer Library by shared terms and marked *matched* (50%+ of the question's terms found) or *needs review* (25%+). Anything you have approved or answered by hand is never overwritten by re-matching. Approved answers can be saved back to the library. **Matching is keyword overlap, not verification:** a person must confirm every security claim is true before approving, and the app never marks an answer approved by itself.
- **Pipeline:** drafting -> quality review (via the existing Quality Review Queue) -> approved -> delivered. Submitting is blocked until every section or answer is written and no `[TO CONFIRM]` placeholders remain. Reviewer notes reopen the project for edits; delivery emails the Markdown to the client through the same delivery log and mailer as digests (actually sent only if `SMTP_HOST` is set).
- **AI assistant:** the same Claude-or-offline assistant drafts, improves, shortens and critiques sections or questionnaire answers, grounded in your closest library answer. Export any project as Markdown.

---

## Writers Marketplace

Clients hire vetted grant writers; accepted writers work inside the client's Grant Studio proposal.

- **Pages:** `/writers` (public directory with search, specialism, rate and rating filters), `/writers/{id}` (profile and reviews), `/market` (sign in, then role-specific tools). API under `/api/v1/market`.
- **Roles:** *writer* (profile, bids), *client* (briefs, accept, approve, review; registering creates their own workspace), *admin* (approves writers). Set `MARKETPLACE_ADMIN_EMAILS` to a comma-separated list; accounts registering with those emails become admins.
- **Flow:** writer applies with a profile, **pending until an admin approves** (only approved writers appear or can bid) -> client posts a brief (optionally linked to a Studio proposal) -> writers bid -> client accepts one bid (others are declined, the writer is added to the client's workspace) -> messages -> writer delivers -> client approves or requests changes -> client reviews (rating is averaged onto the profile).
- **Grant Studio access:** once a job linked to a proposal is in progress or delivered, the proposal's Studio, save, assistant, versions, export and submit endpoints require a signed-in participant (its client, its accepted writer, or an admin). Proposals without a live job keep the original open behaviour.
- **Accounts:** scrypt-hashed passwords, database-backed sessions in an HttpOnly SameSite=Lax cookie (Secure outside development), Origin checks on state-changing requests, and a per-process login rate limit.
- **Job types:** a brief is one of *grant proposal writing*, *technical documentation*, *compliance and policy writing*, *security questionnaire response* or *other writing*. Writers tick the services they offer on their profile; the public directory filters by service and shows it on cards and profiles. Writers can filter open jobs by type, or by "only jobs matching the services I offer".
- **Work inside the project:** a brief can link a Grant Studio proposal (grant jobs) or a documentation project (the other types, checked to match: technical docs need a technical-documentation project, policies a policy project, and so on). Once the job is in progress or delivered, the linked document editor and its API require a signed-in participant (the client, the accepted writer, or an admin), exactly as for proposals, and it opens up again when the job completes.
- **Payments (v1 is tracking only):** no money moves through Bid Studio. A job records the agreed price, a platform fee (`MARKETPLACE_FEE_PCT`, default 10%, recorded not collected) and a two-step payment status (client marks paid, writer confirms). Because nothing is escrowed, protection for buyers comes from admin vetting, ratings and the job record. **To avoid holding client money yourself, add Stripe Connect** so payment is taken through Stripe, held there, and released to the writer on approval minus your fee; Stripe, not you, is the regulated party. That needs your Stripe account and legal advice for your country, and is not built yet.
- **Not built yet:** email verification and password reset, payments/escrow and disputes, writer-to-client reviews, file attachments, and login for the main dashboard (the dashboard and its other endpoints remain open; only marketplace-linked proposals are protected).

---

## Grant Studio

A focused editor for one proposal at `/app/studio/{proposal_id}`, opened from the Grants Feed, the Grants tab or an auto-process.

- **Editor:** one section at a time with the funder's guidance beside it, live word count against a per-section word limit you set, self-score with a live weighted-score meter, notes, and cited evidence. Autosaves after 1.5 seconds; Ctrl/Cmd+S saves immediately; Export downloads Markdown.
- **Library:** answers and evidence ranked against the section (or your search); one click inserts the text, and evidence is cited on the section.
- **Readiness:** blockers (unwritten sections, over-limit sections, missing applicant or amount, closed call, out-of-range scores) must pass before `POST .../studio/submit` will queue the proposal for QA; warnings cover evidence, weights, a close deadline and a low score.
- **Versions:** snapshots on first save, when named, every 10 minutes of changes, and on submit; preview and restore (restoring first snapshots your current text). Submitted or approved proposals are read-only until a reviewer requests changes.
- **AI assistant:** Draft, Improve, Shorten, Critique and free-form Ask on the current section. With `ANTHROPIC_API_KEY` set it calls Claude (`ASSISTANT_MODEL`, default `claude-sonnet-5-5`) with the funder, call, criterion guidance, word limit and your strongest library matches, and is told never to invent facts (it writes `[TO CONFIRM: ...]` placeholders instead). **Section text is sent to the Anthropic API when a key is set.** Without a key a clearly-labelled offline helper does rule-based scaffolds, filler clean-up, sentence-ranking shortening and a keyword critique; free-form Ask needs a key.
- **Project plan (Studio tabs):** *Work packages* (duration, WPs with leads and month spans, tasks, deliverables, milestones, and a live Gantt-style timeline), *Budget* (lines per work package by category, indirect-cost rate applied to all direct costs or excluding subcontracting, match funding, live totals by work package and category, and a one-click "set requested amount" when the budget and the proposal disagree) and *Documents* (templates for a Data Management Plan (FAIR), Ethics and Compliance Statement, Impact and Dissemination Plan, and a Risk Register scored likelihood x impact). Consistency checks flag tasks outside their work package, work packages that overrun the project, deliverables outside their span, unknown or unassigned budget lines, a budget that does not match the requested amount, and risks scoring 8+ with no mitigation. These appear in Readiness as warnings and never block submission. Document sections work with the AI assistant. Export the whole plan as Markdown. The plan is included in version snapshots and restores with them, and locks with the proposal. API: `GET|PUT /api/v1/grants/proposals/{id}/plan`, `POST|DELETE .../plan/documents/{key}`, `POST .../plan/documents/{key}/assistant`, `GET .../plan/export`.
- **API:** `GET /api/v1/grants/proposals/{id}/studio`, `PUT .../studio/save`, `GET .../studio/suggestions`, `POST .../studio/submit`, `GET|POST .../versions`, `POST .../versions/{n}/restore`, `GET .../assistant/status`, `POST .../assistant`.

---

## Grants Feed

A grants-only feed built from the seeded calls plus live public sources.

- **Sources:** Grants.gov (`api.grants.gov`) and the EU Funding & Tenders Portal (`api.tech.ec.europa.eu`), ingested as global grant calls and de-duplicated by `(source, external_id)`, so re-syncing updates changed records instead of duplicating them. Failed syncs are recorded and never break the app.
- **Sync:** `POST /api/v1/grants/feed/sync?source=all|grants_gov|eu_funding` (also the Sync button on the dashboard's Grants Feed tab). To refresh on the daily cron, set `FEED_SOURCES="grants_gov,eu_funding"`. History is at `GET /api/v1/grants/feed/sync/runs`.
- **Browse:** `GET /api/v1/grants/feed` filters by `q`, `funder`, `sector`, `region`, `source`, `min_value`, `max_value`, `closing_within_days`, `saved_only`, sorts by `deadline` (rolling last), `value` or `newest`, and paginates with `limit`/`offset` and `X-Total-Count`. Expired calls are hidden unless `include_expired=true`. `GET /api/v1/grants/feed/facets` returns filter options with counts.
- **Save and act:** `POST|DELETE /api/v1/grants/feed/{id}/save?workspace_id=` bookmarks a grant; each feed item has an Auto-process button for the grant workflow.
- **Where to see it:** the Grants Feed tab in the dashboard (workspace-aware) and the public `/grants` page (global calls only, so one workspace's private calls never appear).
- **Note:** upstream records give a title, funder, dates and a link rather than full call text or scoring weights, so criteria for ingested calls come from the funder-type presets. Grants.gov does not state award values in search results.

---

## Automation

- **Grant workflow in one step:** `POST /api/v1/grants/calls/{id}/auto-process` extracts criteria, drafts and scores a proposal, and queues it for QA. `POST /api/v1/grants/auto-process` does the same for every open call without a proposal. Both are idempotent and have buttons on the Grants tab.
- **Scheduled jobs:** `GET|POST /api/v1/automation/run` sends due alert digests (daily or weekly), sends one deadline reminder per unfinished proposal whose call closes within `REMINDER_WINDOW_DAYS`, and, when `AUTO_PROCESS_GRANTS=true`, auto-processes open calls in the default workspace. `vercel.json` runs it daily at 07:00 UTC. Set `CRON_SECRET` to require `Authorization: Bearer <secret>` (Vercel cron sends it automatically).
- **Notifications:** contact-form submissions notify `CONTACT_NOTIFY_EMAIL`. Every email is recorded in the delivery log; it is only actually sent when `SMTP_HOST` is set, otherwise its status is `logged`.
- **CI:** `.github/workflows/ci.yml` runs ruff and pytest on every push and pull request. Connect the repo to Vercel with its Git integration to deploy automatically on merge.

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
├── .github/workflows/ci.yml      # CI: ruff + pytest on every push and PR
├── .env.example                  # Sample environment variables
├── .gitignore
├── LICENSE                       # Proprietary licence (all rights reserved)
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

---

## Licence

Proprietary. Copyright (c) 2026 donnaheff. All rights reserved. See `LICENSE`. Third-party dependencies keep their own open-source licences.
