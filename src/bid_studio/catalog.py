"""Single source of truth for the website: services, app sections and navigation groups.

Every claim here mirrors behaviour that exists in the API (see the routers) — pages are
generated from this catalog so the marketing copy, the app navigation and the sitemap
cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field

GROUPS = [
    "Primary Product",
    "Writing & Review Services",
    "Bid Strategy & Response",
    "Tender Data Products",
    "New Audiences",
]


@dataclass(frozen=True)
class Service:
    slug: str
    app_id: str  # id of the partial in templates/app/sections/
    title: str
    nav_label: str
    group: str
    tagline: str
    summary: str
    features: list[str]
    steps: list[str]
    api: list[str]
    mcp_tools: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)  # datasets the app page fetches
    audience: str = "Bid teams"


SERVICES: list[Service] = [
    Service(
        slug="grants", app_id="grants", title="Grant & Funding Proposal Writing",
        nav_label="Grant & Funding Calls", group="Primary Product",
        tagline="From funding call to scored draft, criterion by criterion.",
        summary="Structured funding calls from Horizon Europe, UKRI, the World Bank and foundations, "
                "with automatic criteria extraction and weighted scoring.",
        features=[
            "Funding calls from EU (Horizon Europe), UKRI, World Bank and foundations",
            "Automatic extraction of evaluation criteria and scoring rubrics",
            "Section drafting against each criterion's weight",
            "Weighted self-score recalculated as sections change",
            "One-click submission to the Quality Review Queue",
            "Markdown export of the full proposal",
        ],
        steps=["Pick a funding call", "Extract the criteria and weights", "Draft each section",
               "Review the weighted score", "Submit for human quality review"],
        api=["GET /api/v1/grants/calls", "POST /api/v1/grants/calls/{id}/extract-criteria",
             "POST /api/v1/grants/proposals", "PUT /api/v1/grants/proposals/{id}/sections",
             "POST /api/v1/grants/proposals/{id}/submit-review",
             "GET /api/v1/grants/proposals/{id}/export"],
        mcp_tools=["list_grant_calls", "extract_grant_criteria", "create_grant_proposal",
                   "update_grant_proposal_sections", "submit_grant_proposal_for_review",
                   "export_grant_proposal"],
        needs=["grants", "proposals"], audience="Grant writers & applicants",
    ),
    Service(
        slug="tech-docs", app_id="techdocs", title="Technical Documentation & API Docs",
        nav_label="Technical & API Docs", group="Writing & Review Services",
        tagline="Fixed-fee documentation with a QA gate before delivery.",
        summary="User guides, API references, SOPs, release notes, whitepapers, runbooks and "
                "architecture documents delivered as fixed-fee projects through a tracked pipeline.",
        features=[
            "Seven packages: user guide, API reference, SOP, release notes, whitepaper, runbook "
            "and architecture document",
            "Whitepapers, runbooks and architecture documents start from a section outline",
            "Fixed fee per project (default GBP 950, adjustable per order)",
            "Pipeline: intake → drafting → quality review → approved → delivered",
            "QA gate: nothing is delivered until a reviewer approves it",
            "Email delivery logged for audit",
            "Markdown export",
        ],
        steps=["Create the fixed-fee project", "Draft the document", "Submit to quality review",
               "Reviewer approves", "Deliver by email"],
        api=["GET|POST /api/v1/tech-docs", "POST /api/v1/tech-docs/{id}/submit-quality",
             "POST /api/v1/tech-docs/{id}/review", "POST /api/v1/tech-docs/{id}/deliver",
             "GET /api/v1/tech-docs/{id}/export"],
        needs=["techdocs"], audience="Product & engineering teams",
    ),
    Service(
        slug="compliance", app_id="compliance", title="Compliance & Policy Writing",
        nav_label="Compliance & Security Qs", group="Writing & Review Services",
        tagline="Policies and security questionnaires, answered from your own library.",
        summary="ISO 9001 and ISO 27001 manuals, data protection policies and security "
                "questionnaires, matched automatically against your Answer Library.",
        features=[
            "ISO 9001 / ISO 27001 manuals and data protection policies",
            "Security questionnaires with automatic answer matching",
            "Match confidence per question; unmatched questions are flagged for authoring",
            "Reusable verified answers shared across bids",
            "Markdown export of the pack",
        ],
        steps=["Create a compliance pack", "Paste the questionnaire", "Auto-match to the Answer Library",
               "Author the unmatched answers", "Export"],
        api=["GET|POST /api/v1/compliance/packs", "POST /api/v1/compliance/packs/{id}/auto-match",
             "GET /api/v1/compliance/packs/{id}/export", "GET|POST /api/v1/answer-library"],
        mcp_tools=["create_compliance_pack", "auto_match_compliance_pack",
                   "search_answer_library", "add_answer_library_item"],
        needs=["compliance"], audience="Security & compliance leads",
    ),
    Service(
        slug="cvs-case-studies", app_id="assets", title="CV, Capability Statement & Case Study Writing",
        nav_label="CVs & Case Studies", group="Writing & Review Services",
        tagline="Buyer-formatted bid assets that feed your Evidence Library.",
        summary="Team CVs, capability statements and case studies written in the format each "
                "buyer expects, then promoted into the Evidence Library.",
        features=[
            "Team CVs, capability statements and case studies",
            "Formatted to the buyer's template (for example Crown Commercial Service)",
            "One-click promotion into the Evidence Library",
            "Markdown export",
        ],
        steps=["Choose the asset type and buyer format", "Write or import the content",
               "Promote to evidence", "Reuse across bids"],
        api=["GET|POST /api/v1/bidder-assets", "POST /api/v1/bidder-assets/{id}/promote-to-evidence",
             "GET /api/v1/bidder-assets/{id}/export", "GET|POST /api/v1/evidence-library"],
        needs=["assets"],
    ),
    Service(
        slug="bid-review", app_id="marketplace", title="Bid Review Marketplace",
        nav_label="Bid Review Marketplace", group="Writing & Review Services",
        tagline="Independent pre-submission scoring from specialist reviewers.",
        summary="A directory of independent reviewers who score your bid against each "
                "criterion before you submit.",
        features=[
            "Independent reviewer directory with specialisms, flat fees and ratings",
            "Criterion-by-criterion pre-submission scoring",
            "Reviews tracked through Bid Studio's Quality Queue",
            "Markdown export of the review",
        ],
        steps=["Pick a reviewer", "Request a review", "Reviewer scores each criterion",
               "Act on the feedback"],
        api=["GET /api/v1/marketplace/reviewers", "GET|POST /api/v1/marketplace/reviews",
             "POST /api/v1/marketplace/reviews/{id}/score",
             "GET /api/v1/marketplace/reviews/{id}/export"],
        needs=["reviewers", "reviews"],
    ),
    Service(
        slug="debriefs", app_id="debriefs", title="Win/Loss Debrief Service",
        nav_label="Win/Loss Debriefs", group="Bid Strategy & Response",
        tagline="Learn from every outcome and fix the next bid first.",
        summary="Track won, lost and withdrawn bids, request buyer feedback, and compare "
                "your internal score with the buyer's.",
        features=[
            "Outcome tracking: won, lost or withdrawn",
            "Buyer feedback request letters",
            "Internal-versus-buyer criterion comparison",
            "Prioritised next-bid fixes",
            "Markdown export",
        ],
        steps=["Record the outcome", "Enter internal and buyer scores", "Review the gaps",
               "Apply the prioritised fixes"],
        api=["GET /api/v1/debriefs/outcomes", "POST /api/v1/debriefs/compare",
             "GET /api/v1/debriefs/outcomes/{id}/export"],
        needs=["debriefs"],
    ),
    Service(
        slug="clarifications", app_id="clarifications", title="Clarification Question Service",
        nav_label="Clarification Questions", group="Bid Strategy & Response",
        tagline="Find the ambiguity before the clarification deadline.",
        summary="Reads a tender pack, detects vague wording and drafts prioritised questions "
                "for the buyer.",
        features=[
            "Detects ambiguous phrases such as TBD, 'reasonable' and 'etc.'",
            "Flags unstated evaluation weightings",
            "Drafts prioritised clarification questions",
            "Tracks each question: draft, submitted, answered",
            "Markdown export",
        ],
        steps=["Paste the tender text", "Review the detected ambiguities",
               "Send the prioritised questions", "Record the buyer's answers"],
        api=["GET /api/v1/clarifications", "POST /api/v1/clarifications/analyze-pack",
             "PATCH /api/v1/clarifications/{id}/questions",
             "GET /api/v1/clarifications/{id}/export"],
        mcp_tools=["analyze_tender_for_clarifications"],
        needs=["clarifs"],
    ),
    Service(
        slug="pricing", app_id="pricing", title="Pricing & Cost-Narrative Writing",
        nav_label="Pricing & Cost Narrative", group="Bid Strategy & Response",
        tagline="Price matrices with the story evaluators need to score them.",
        summary="Reusable pricing templates, margin and contingency price matrices, and "
                "evaluator-ready cost justifications.",
        features=[
            "Reusable pricing templates with default margins",
            "Price matrices with margin and contingency",
            "Cost-justification narrative generated with the numbers",
            "Markdown export",
        ],
        steps=["Choose a template or custom lines", "Set margin and contingency",
               "Generate the matrix and narrative", "Export into the bid"],
        api=["GET /api/v1/pricing/templates", "GET|POST /api/v1/pricing/matrices",
             "GET /api/v1/pricing/matrices/{id}/export"],
        needs=["pricingTemplates", "matrices"],
    ),
    Service(
        slug="social-value", app_id="socialvalue", title="Social Value & Sustainability Statements",
        nav_label="Social Value & Net Zero", group="Bid Strategy & Response",
        tagline="Measurable commitments, written to the buyer's framework.",
        summary="UK PPN 06/20 and EU GPP statements covering Net Zero, Real Living Wage and "
                "supply-chain commitments with KPIs.",
        features=[
            "UK PPN 06/20 and EU GPP frameworks, or a custom one",
            "Net Zero target year and annual reduction path",
            "Real Living Wage accreditation and supply-chain pledges",
            "Measurable KPIs generated or supplied",
            "Markdown export",
        ],
        steps=["Choose the buyer framework", "Enter emissions baseline and targets",
               "Add supply-chain commitments", "Generate and export the statement"],
        api=["GET|POST /api/v1/social-value", "GET /api/v1/social-value/{id}/export"],
        mcp_tools=["create_social_value_statement"],
        needs=["svs"],
    ),
    Service(
        slug="alerts", app_id="alerts", title="Tender Alerts & Weekly Digest",
        nav_label="Tender Alerts & Digest", group="Tender Data Products",
        tagline="The notices that match you, summarised and delivered.",
        summary="Alert subscriptions filtered by sector, notice type, value band and keywords, "
                "with AI-summarised digests.",
        features=[
            "Filters: sector, notice type, value band and keywords",
            "Daily or weekly cadence",
            "AI-summarised digest of matching notices",
            "Every send recorded in the email log",
        ],
        steps=["Create a subscription", "Set your filters", "Generate the digest",
               "Receive it on your cadence"],
        api=["GET|POST /api/v1/alerts/subscriptions",
             "POST /api/v1/alerts/subscriptions/{id}/generate-digest"],
        needs=["alertSubs"],
    ),
    Service(
        slug="intelligence", app_id="intel", title="Competitor & Buyer Intelligence Reports",
        nav_label="Buyer & Competitor Intel", group="Tender Data Products",
        tagline="See who a buyer really awards to, and how much.",
        summary="Aggregates stored awarded notices per buyer to show spend, repeat winners and "
                "win-share concentration.",
        features=[
            "Total, average, minimum and maximum contract values per buyer",
            "Repeat winners and win-share concentration",
            "Optional sector filter",
            "Reports saved and exportable as Markdown",
        ],
        steps=["Name the buyer", "Choose an optional sector", "Generate the report",
               "Use it to shape your bid"],
        api=["GET /api/v1/intelligence/reports", "POST /api/v1/intelligence/buyer-report",
             "GET /api/v1/intelligence/reports/{id}/export"],
        mcp_tools=["generate_buyer_intelligence_report"],
        needs=["intelReports"],
    ),
    Service(
        slug="frameworks", app_id="frameworks", title="Framework & DPS Onboarding",
        nav_label="Framework & DPS Onboarding", group="Tender Data Products",
        tagline="Get onto the vehicle before the opportunities appear on it.",
        summary="Guided checklists for frameworks, Dynamic Purchasing Systems and approved "
                "supplier lists, with live completion tracking.",
        features=[
            "Framework, DPS and approved-supplier-list checklists",
            "Per-lot tracking",
            "Live completion percentage and readiness status",
            "Markdown export",
        ],
        steps=["Add the vehicle and authority", "Work through the checklist",
               "Track readiness", "Export for your records"],
        api=["GET|POST /api/v1/frameworks", "PATCH /api/v1/frameworks/{id}/checklist",
             "GET /api/v1/frameworks/{id}/export"],
        needs=["frameworks"],
    ),
    Service(
        slug="training", app_id="training", title="Training & Workshops",
        nav_label="Training", group="New Audiences",
        tagline="Learn bid writing on a realistic municipal tender.",
        summary="Cohort courses built on the seeded Riverbend municipal tender pack, with "
                "module-by-module progress.",
        features=[
            "Cohort courses with seat limits",
            "Built on the Riverbend municipal tender pack",
            "Module completion and progress tracking",
            "Each enrolment is recorded as an order",
        ],
        steps=["Pick a cohort", "Enrol learners", "Complete the modules", "Track progress"],
        api=["GET /api/v1/training/cohorts", "GET /api/v1/training/enrolments",
             "POST /api/v1/training/cohorts/{id}/enrol",
             "POST /api/v1/training/enrolments/{id}/complete-module"],
        needs=["cohorts", "enrolments"], audience="Learners & trainers",
    ),
    Service(
        slug="white-label", app_id="whitelabel", title="White-Label for Bid Consultancies",
        nav_label="White-Label & Access Review", group="New Audiences",
        tagline="Run your own branded bid studio for each client.",
        summary="Consultancy branding, isolated client workspaces, role-based members and "
                "timestamped access reviews.",
        features=[
            "Custom brand name, colours and domain",
            "Strict client workspace isolation",
            "Roles: owner, admin, writer, reviewer and client",
            "Timestamped access reviews",
            "Per-workspace KPI summary",
        ],
        steps=["Create the client workspace", "Apply your branding", "Add members and roles",
               "Run an access review"],
        api=["GET|POST /api/v1/workspaces", "PUT /api/v1/workspaces/{id}/white-label",
             "GET|POST /api/v1/workspaces/{id}/members",
             "GET /api/v1/workspaces/{id}/access-review",
             "GET /api/v1/white-label/consultancies"],
        needs=["members"], audience="Bid consultancies",
    ),
    Service(
        slug="public-sector", app_id="publicsector", title="Public Sector Buyer Drafting",
        nav_label="Public Sector Buyer Side", group="New Audiences",
        tagline="Write tenders suppliers can actually answer.",
        summary="Draft a tender specification and evaluation criteria, and validate clarity "
                "and weighting before you publish.",
        features=[
            "Specification and evaluation-criteria drafting",
            "Clarity score with listed issues",
            "Checks that criteria weights sum to 100%",
            "Re-validate after every edit",
            "Export the tender pack as Markdown",
        ],
        steps=["Enter the authority and specification", "Set the criteria and weights",
               "Validate", "Fix the flagged issues", "Export the pack"],
        api=["GET|POST /api/v1/public-sector/drafts",
             "POST /api/v1/public-sector/drafts/{id}/validate",
             "GET /api/v1/public-sector/drafts/{id}/export-pack"],
        needs=["buyerDrafts"], audience="Public-sector buyers",
    ),
]

SERVICE_BY_SLUG = {s.slug: s for s in SERVICES}

# The app overview is not a marketed service but is a page.
OVERVIEW_NEEDS = ["summary", "notices", "grants", "answers", "evidence", "orders", "queue",
                  "deliveries"]


def grouped_services() -> list[tuple[str, list[Service]]]:
    return [(g, [s for s in SERVICES if s.group == g]) for g in GROUPS]
