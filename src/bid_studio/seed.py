from sqlalchemy.orm import Session

from bid_studio.models import (
    AnswerLibraryItem,
    BidOutcome,
    EvidenceItem,
    OpportunityNotice,
    PricingTemplate,
    Workspace,
    WorkspaceMember,
)
from bid_studio.services.domain_logic import summarize_notice


def seed_database(db: Session) -> None:
    if db.query(Workspace).count() > 0:
        return

    ws_default = Workspace(
        slug="primus-demo",
        name="Bid Studio Demo Consultancy",
        is_white_label=False,
        brand_name="Bid Studio",
        primary_color="#0f172a",
        accent_color="#2563eb",
        support_email="ops@bidstudio.example",
        client_isolation_enforced=True,
    )
    ws_whitelabel = Workspace(
        slug="northstar-advisory",
        name="NorthStar Bid Advisory",
        is_white_label=True,
        brand_name="NorthStar Bids",
        primary_color="#14532d",
        accent_color="#16a34a",
        custom_domain="bids.northstar-advisory.example",
        support_email="team@northstar-advisory.example",
        client_isolation_enforced=True,
    )
    db.add_all([ws_default, ws_whitelabel])
    db.flush()

    db.add_all(
        [
            WorkspaceMember(
                workspace_id=ws_default.id,
                email="lead@bidstudio.example",
                full_name="Hannah Mercer",
                role="owner",
                status="active",
            ),
            WorkspaceMember(
                workspace_id=ws_default.id,
                email="reviewer@bidstudio.example",
                full_name="David Okafor",
                role="reviewer",
                status="active",
            ),
            WorkspaceMember(
                workspace_id=ws_whitelabel.id,
                email="director@northstar-advisory.example",
                full_name="Claire Vance",
                role="owner",
                status="active",
            ),
        ]
    )

    notices_data = [
        # Grant calls: EU, UKRI, World Bank, Foundation
        {
            "notice_type": "grant_call",
            "source_portal": "EU Funding & Tenders Portal",
            "funder_or_buyer": "European Commission — Horizon Europe",
            "title": "HORIZON-CL4-2026: AI-Assisted Public Procurement & Civic Transparency",
            "sector": "GovTech & AI",
            "region": "EU",
            "cpv_or_topic": "HORIZON-CL4-DIGITAL",
            "contract_value": 2500000.0,
            "currency": "EUR",
            "status": "open",
            "deadline": "2026-12-18",
            "raw_pack_text": (
                "Horizon Europe Research & Innovation Action. Evaluation criteria: "
                "Excellence & Novelty (40%), Impact & Exploitation (35%), "
                "Quality & Efficiency of Implementation (25%). Consortium must include at least 3 EU member states."
            ),
            "structured_criteria": [
                {
                    "criterion_id": "EU-1",
                    "title": "Excellence & Novelty",
                    "weight": 40.0,
                    "max_score": 5.0,
                    "guidance": "Clarity of objectives, methodology, and state-of-the-art advance.",
                },
                {
                    "criterion_id": "EU-2",
                    "title": "Impact & Exploitation",
                    "weight": 35.0,
                    "max_score": 5.0,
                    "guidance": "Credible scale-up pathway, open science, and EU societal impact.",
                },
                {
                    "criterion_id": "EU-3",
                    "title": "Quality & Efficiency of Implementation",
                    "weight": 25.0,
                    "max_score": 5.0,
                    "guidance": "Work packages, consortium governance, risk mitigation, and budget realism.",
                },
            ],
        },
        {
            "notice_type": "grant_call",
            "source_portal": "UKRI Innovation Funding Service",
            "funder_or_buyer": "UKRI — Innovate UK",
            "title": "Smart Sustainable Cities & Net Zero Fleet Decarbonisation Grant",
            "sector": "CleanTech & Transport",
            "region": "UK",
            "cpv_or_topic": "UKRI-NZ-2026",
            "contract_value": 650000.0,
            "currency": "GBP",
            "status": "open",
            "deadline": "2026-12-12",
            "raw_pack_text": (
                "Innovate UK Smart Grant. Vision & Approach (40%), Team & Capability (30%), "
                "Value for Money & UK Economic Impact (30%). Match funding 30% required."
            ),
            "structured_criteria": [
                {
                    "criterion_id": "UKRI-1",
                    "title": "Vision & Technical Approach",
                    "weight": 40.0,
                    "max_score": 10.0,
                    "guidance": "Innovation step-change, technical feasibility, and carbon abatement.",
                },
                {
                    "criterion_id": "UKRI-2",
                    "title": "Team & Delivery Capability",
                    "weight": 30.0,
                    "max_score": 10.0,
                    "guidance": "Relevant track record, leadership, and partner commitments.",
                },
                {
                    "criterion_id": "UKRI-3",
                    "title": "Value for Money & Impact",
                    "weight": 30.0,
                    "max_score": 10.0,
                    "guidance": "Commercialisation plan, UK jobs, and costed work packages.",
                },
            ],
        },
        {
            "notice_type": "grant_call",
            "source_portal": "World Bank Procurement & Grants",
            "funder_or_buyer": "World Bank — Digital Development Partnership",
            "title": "Sub-Saharan Municipal E-Procurement & Open Contracting Modernisation",
            "sector": "GovTech & AI",
            "region": "Global",
            "cpv_or_topic": "WB-DDP-2026",
            "contract_value": 1200000.0,
            "currency": "USD",
            "status": "open",
            "deadline": "2027-01-15",
            "raw_pack_text": (
                "World Bank structured call. Technical Methodology & Context (40%), "
                "Key Experts & Institutional Capacity (35%), Safeguards & Sustainability (25%)."
            ),
            "structured_criteria": [
                {
                    "criterion_id": "WB-1",
                    "title": "Technical Methodology & Context",
                    "weight": 40.0,
                    "max_score": 100.0,
                    "guidance": "OCDS data alignment, local capacity transfer, and phased rollout.",
                },
                {
                    "criterion_id": "WB-2",
                    "title": "Key Experts & Institutional Capacity",
                    "weight": 35.0,
                    "max_score": 100.0,
                    "guidance": "Comparable public finance/e-procurement deployments and CVs.",
                },
                {
                    "criterion_id": "WB-3",
                    "title": "Safeguards, Fiduciary & Sustainability",
                    "weight": 25.0,
                    "max_score": 100.0,
                    "guidance": "ESF compliance, data privacy, and post-grant sustainability.",
                },
            ],
        },
        {
            "notice_type": "grant_call",
            "source_portal": "Foundation Philanthropy Directory",
            "funder_or_buyer": "Civic Climate & Community Foundation",
            "title": "Community Heat Networks & Green Skills Workforce Fund",
            "sector": "CleanTech & Transport",
            "region": "UK",
            "cpv_or_topic": "FOUND-CLIMATE-26",
            "contract_value": 250000.0,
            "currency": "GBP",
            "status": "open",
            "deadline": "2026-12-22",
            "raw_pack_text": (
                "Foundation grant. Mission Alignment & Theory of Change (40%), "
                "Evidence & Measurement Plan (30%), Delivery Readiness & Budget Realism (30%)."
            ),
            "structured_criteria": [
                {
                    "criterion_id": "FOUND-1",
                    "title": "Mission Alignment & Theory of Change",
                    "weight": 40.0,
                    "max_score": 5.0,
                    "guidance": "Clear link between the project, the foundation's climate mission, and a credible theory of change.",
                },
                {
                    "criterion_id": "FOUND-2",
                    "title": "Evidence & Measurement Plan",
                    "weight": 30.0,
                    "max_score": 5.0,
                    "guidance": "Baseline evidence, measurable outcomes, and a realistic monitoring and evaluation approach.",
                },
                {
                    "criterion_id": "FOUND-3",
                    "title": "Delivery Readiness & Budget Realism",
                    "weight": 30.0,
                    "max_score": 5.0,
                    "guidance": "Deliverable workplan, named partners, risk management, and a costed, proportionate budget.",
                },
            ],
        },
        # Open Tenders (including Riverbend pack)
        {
            "notice_type": "tender",
            "source_portal": "Find a Tender",
            "funder_or_buyer": "Riverbend Borough Council",
            "title": "Riverbend Municipal Fleet Electrification & Waste Route Optimisation",
            "sector": "CleanTech & Transport",
            "region": "UK",
            "cpv_or_topic": "34144900-Electric Vehicles",
            "contract_value": 1850000.0,
            "currency": "GBP",
            "status": "open",
            "deadline": "2026-12-10",
            "raw_pack_text": (
                "Riverbend Borough Council invites bids for electric refuse collection fleet support and routing software. "
                "The supplier shall maintain reasonable response times across all depots. "
                "Additional ancillary hardware, telematics, etc. shall be supplied as required at no extra charge. "
                "Go-live date is TBD subject to depot grid upgrade."
            ),
            "structured_criteria": [
                {"criterion_id": "T-1", "title": "Technical Delivery & Mobilisation", "weight": 40.0, "max_score": 5.0},
                {"criterion_id": "T-2", "title": "Social Value & Net Zero", "weight": 20.0, "max_score": 5.0},
                {"criterion_id": "T-3", "title": "Commercial Price", "weight": 40.0, "max_score": 5.0},
            ],
        },
        {
            "notice_type": "tender",
            "source_portal": "Contracts Finder",
            "funder_or_buyer": "NHS Digital Transformation Trust",
            "title": "Cloud Security & API Documentation Modernisation Partner",
            "sector": "Digital & Cloud",
            "region": "UK",
            "cpv_or_topic": "72222300-IT Services",
            "contract_value": 420000.0,
            "currency": "GBP",
            "status": "open",
            "deadline": "2026-12-05",
            "raw_pack_text": (
                "ISO 27001 compliant supplier required to overhaul patient API developer portal and clinical SOPs."
            ),
            "structured_criteria": [],
        },
        # Awarded Notices for Buyer & Competitor Intelligence
        {
            "notice_type": "awarded_tender",
            "source_portal": "Find a Tender",
            "funder_or_buyer": "Riverbend Borough Council",
            "title": "Riverbend Smart Streetlighting & IoT Telemetry Lot 1",
            "sector": "CleanTech & Transport",
            "region": "UK",
            "cpv_or_topic": "34993000",
            "contract_value": 920000.0,
            "currency": "GBP",
            "status": "awarded",
            "awarded_supplier": "GreenGrid Systems Ltd",
            "deadline": "2026-04-15",
            "raw_pack_text": "Awarded following competitive procedure with 60% quality / 40% price.",
        },
        {
            "notice_type": "awarded_tender",
            "source_portal": "Find a Tender",
            "funder_or_buyer": "Riverbend Borough Council",
            "title": "Riverbend Depot EV Charging Infrastructure Phase 1",
            "sector": "CleanTech & Transport",
            "region": "UK",
            "cpv_or_topic": "31681500",
            "contract_value": 1340000.0,
            "currency": "GBP",
            "status": "awarded",
            "awarded_supplier": "GreenGrid Systems Ltd",
            "deadline": "2026-07-01",
            "raw_pack_text": "Awarded under Crown Commercial Service DPS.",
        },
        {
            "notice_type": "awarded_tender",
            "source_portal": "Find a Tender",
            "funder_or_buyer": "Riverbend Borough Council",
            "title": "Riverbend Citizen Portal & Cloud Hosting Migration",
            "sector": "Digital & Cloud",
            "region": "UK",
            "cpv_or_topic": "72222300",
            "contract_value": 510000.0,
            "currency": "GBP",
            "status": "awarded",
            "awarded_supplier": "CivicCloud Partners",
            "deadline": "2026-09-20",
            "raw_pack_text": "Awarded via G-Cloud 14 framework.",
        },
    ]

    for nd in notices_data:
        summary = summarize_notice(
            nd["title"],
            nd["raw_pack_text"],
            nd["funder_or_buyer"],
            nd["contract_value"],
            nd["currency"],
            nd["deadline"],
        )
        db.add(OpportunityNotice(**nd, ai_summary=summary))

    db.add_all(
        [
            AnswerLibraryItem(
                workspace_id=ws_default.id,
                category="security",
                question_pattern="Do you hold ISO 27001 certification and how is your ISMS governed?",
                answer_text=(
                    "Yes. Our Information Security Management System (ISMS) is certified to ISO/IEC 27001:2022 "
                    "by a UKAS-accredited body, reviewed quarterly by the Information Security Committee and audited annually."
                ),
                tags=["iso27001", "isms", "certification", "governance", "security"],
                owner_name="CISO Office",
            ),
            AnswerLibraryItem(
                workspace_id=ws_default.id,
                category="security",
                question_pattern="How is data encrypted at rest and in transit?",
                answer_text=(
                    "All customer data is encrypted in transit using TLS 1.3 and at rest using AES-256 with "
                    "customer-isolated KMS keys rotated every 90 days."
                ),
                tags=["encryption", "tls", "aes256", "transit", "rest", "data"],
                owner_name="Cloud Platform Team",
            ),
            AnswerLibraryItem(
                workspace_id=ws_default.id,
                category="compliance",
                question_pattern="How do you comply with UK GDPR and data retention requirements?",
                answer_text=(
                    "We operate under UK GDPR and Data Protection Act 2018 controls, maintaining a Data Processing "
                    "Register, automated retention purging, DPIA workflows, and UK/EEA data residency guarantees."
                ),
                tags=["gdpr", "privacy", "data", "protection", "retention", "dpia"],
                owner_name="Data Protection Officer",
            ),
            AnswerLibraryItem(
                workspace_id=ws_default.id,
                category="security",
                question_pattern="What is your incident response SLA and penetration testing cadence?",
                answer_text=(
                    "CREST-accredited independent penetration testing is conducted bi-annually and after major releases. "
                    "Critical P1 security incidents are triaged within 15 minutes and notified to buyers within 2 hours."
                ),
                tags=["incident", "response", "penetration", "testing", "crest", "sla"],
                owner_name="SecOps Team",
            ),
        ]
    )

    db.add(
        EvidenceItem(
            workspace_id=ws_default.id,
            evidence_type="case_study",
            title="Camden Zero-Emission Fleet Routing Rollout",
            summary="Delivered 24% mileage reduction and 99.4% collection SLA across 42 electric vehicles.",
            buyer_format="Find a Tender / Cabinet Office Case Study",
            metrics={"mileage_reduction_pct": 24, "sla_pct": 99.4, "co2_saved_tonnes": 310},
        )
    )

    db.add_all(
        [
            PricingTemplate(
                name="Public Sector Digital Delivery (Day-Rate)",
                sector="Digital & Cloud",
                default_margin_pct=18.0,
                default_lines=[
                    {"line_id": "L1", "category": "Mobilisation", "description": "Discovery & Stakeholder Onboarding", "unit": "day", "quantity": 10, "unit_rate": 750.0},
                    {"line_id": "L2", "category": "Delivery", "description": "Lead Technical Architect", "unit": "day", "quantity": 25, "unit_rate": 900.0},
                    {"line_id": "L3", "category": "Quality", "description": "QA, Security & Handover", "unit": "day", "quantity": 8, "unit_rate": 680.0},
                ],
                narrative_guidance="Emphasise SFIA day-rate benchmarking and fixed milestone acceptance.",
            ),
            PricingTemplate(
                name="Grant Project Work-Package Budget",
                sector="GovTech & AI",
                default_margin_pct=12.0,
                default_lines=[
                    {"line_id": "L1", "category": "Research", "description": "WP1 Technical Research & Architecture", "unit": "month", "quantity": 6, "unit_rate": 8500.0},
                    {"line_id": "L2", "category": "Pilot", "description": "WP2 Municipal Pilot Deployment", "unit": "month", "quantity": 6, "unit_rate": 9500.0},
                    {"line_id": "L3", "category": "Dissemination", "description": "WP3 Impact Evaluation & Dissemination", "unit": "month", "quantity": 3, "unit_rate": 4200.0},
                ],
                narrative_guidance="Justify personnel months, travel, and equipment against funder eligibility rules.",
            ),
        ]
    )

    db.add(
        BidOutcome(
            workspace_id=ws_default.id,
            bid_title="Midlands Waste Analytics Pilot",
            buyer_name="Midlands Combined Authority",
            outcome="lost",
            contract_value=380000.0,
            internal_score=84.0,
            buyer_score=69.5,
            feedback_requested=True,
            feedback_request_letter="Feedback received from Midlands Combined Authority.",
            criterion_comparisons=[
                {"criterion": "Mobilisation Plan", "internal_score": 88, "buyer_score": 65},
                {"criterion": "Social Value", "internal_score": 80, "buyer_score": 74},
            ],
            next_bid_fixes=[
                {
                    "criterion": "Mobilisation Plan",
                    "score_delta": -23.0,
                    "severity": "High",
                    "action": "Include named mobilisation lead, week-by-week RACI, and signed depot readiness checklist.",
                }
            ],
        )
    )

    db.commit()
