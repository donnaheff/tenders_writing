"""Templates for the technical-documentation and compliance writing services."""

TYPES: dict[str, dict] = {
    # ---- technical documentation
    "user_guide": {
        "kind": "techdoc", "title": "User guide",
        "description": "Task-based guide for the people who use a product.",
        "sections": [
            ("overview", "Overview and audience", "Who this guide is for, what the product does, and what readers should already know."),
            ("getting_started", "Getting started", "Installation or sign-up, first-run setup and a first successful task, in numbered steps."),
            ("core_tasks", "Core tasks", "The main jobs users do, each as a short procedure with the expected result."),
            ("troubleshooting", "Troubleshooting", "Common problems as symptom, cause and fix, plus where to get help."),
            ("faq", "Frequently asked questions", "Short answers to the questions users ask most."),
            ("glossary", "Glossary", "Terms and abbreviations used in the product and this guide."),
        ],
    },
    "api_reference": {
        "kind": "techdoc", "title": "API reference",
        "description": "Reference documentation for developers integrating with an API.",
        "sections": [
            ("intro", "Introduction and base URL", "What the API does, base URL, versioning and supported formats."),
            ("auth", "Authentication", "How to obtain and send credentials, scopes and token lifetime, with a working example."),
            ("quickstart", "Quickstart", "The shortest path to a first successful request, with copy-pasteable code."),
            ("endpoints", "Endpoints", "For each endpoint: method and path, parameters, request body, response, and an example."),
            ("errors", "Errors and rate limits", "Error format and codes, what causes them, retry guidance and rate limits."),
            ("webhooks", "Webhooks and events", "Events, payload shapes, signature verification and retry behaviour."),
            ("changelog", "Changelog and deprecations", "Versioning policy, recent changes and deprecation timelines."),
        ],
    },
    "sop": {
        "kind": "techdoc", "title": "Standard operating procedure",
        "description": "A repeatable procedure with owners, checks and records.",
        "sections": [
            ("purpose", "Purpose and scope", "What this procedure achieves, where it applies and where it does not."),
            ("roles", "Roles and responsibilities", "Who performs, approves and is informed at each stage."),
            ("prereqs", "Prerequisites", "Access, tools, training and inputs needed before starting."),
            ("procedure", "Procedure", "Numbered steps, each with one action, the responsible role and the expected outcome."),
            ("controls", "Controls and checks", "Verification points, acceptance criteria and who signs off."),
            ("records", "Records and forms", "What evidence is kept, where, and for how long."),
            ("exceptions", "Exceptions and escalation", "What to do when something goes wrong, and who to contact."),
            ("revisions", "Revision history", "Version, date, author and summary of each change."),
        ],
    },
    "release_notes": {
        "kind": "techdoc", "title": "Release notes",
        "description": "What changed in a release, written for customers.",
        "sections": [
            ("summary", "Summary", "The release in two or three sentences: version, date and the headline change."),
            ("features", "New features", "Each new capability and the problem it solves for the user."),
            ("improvements", "Improvements", "Changes to existing behaviour, performance or usability."),
            ("fixes", "Bug fixes", "Problems that are now resolved, described from the user's point of view."),
            ("breaking", "Breaking changes and migration", "Anything that needs action from users, with exact migration steps."),
            ("known_issues", "Known issues", "Open problems and workarounds."),
        ],
    },
    # ---- compliance and policy writing
    "infosec_policy": {
        "kind": "compliance", "title": "Information security policy (ISO 27001 aligned)",
        "description": "Top-level security policy covering the ISMS.",
        "sections": [
            ("purpose", "Purpose, scope and objectives", "Why the policy exists, which systems, people and data it covers, and the security objectives."),
            ("governance", "Governance and responsibilities", "Management commitment, security roles, review cycle and how exceptions are approved."),
            ("risk", "Risk management", "How risks are identified, assessed, treated and accepted, and how often."),
            ("access", "Access control", "Joiner-mover-leaver, least privilege, authentication standards and privileged access."),
            ("data", "Data classification and handling", "Classification levels, handling rules, encryption in transit and at rest, retention and disposal."),
            ("operations", "Operations and technical controls", "Patching, malware protection, logging and monitoring, backup, change management and vulnerability management."),
            ("suppliers", "Supplier and third-party security", "Due diligence, contractual security requirements and ongoing monitoring."),
            ("incidents", "Incident management", "Reporting, triage, response, notification duties and lessons learned."),
            ("compliance", "Compliance, audit and enforcement", "Legal and contractual obligations, internal audit, and consequences of breaches."),
        ],
    },
    "data_protection_policy": {
        "kind": "compliance", "title": "Data protection policy (UK GDPR)",
        "description": "How personal data is handled lawfully, fairly and securely.",
        "sections": [
            ("scope", "Scope and definitions", "What personal data is processed, by whom, and the key terms used."),
            ("principles", "Principles and lawful bases", "The data protection principles and the lawful basis for each type of processing."),
            ("rights", "Individual rights", "How requests for access, correction, erasure, restriction and objection are handled, and within what time."),
            ("security", "Security of processing", "Technical and organisational measures protecting personal data."),
            ("transfers", "Sharing and international transfers", "Processors, sub-processors, contracts and safeguards for transfers outside the UK."),
            ("retention", "Retention and deletion", "Retention periods by data type and how deletion is carried out and evidenced."),
            ("breaches", "Personal data breaches", "Detection, internal reporting, the 72-hour regulator notification and informing individuals."),
            ("accountability", "Accountability and governance", "DPO or lead, records of processing, DPIAs, training and audit."),
        ],
    },
    "incident_response_plan": {
        "kind": "compliance", "title": "Incident response plan",
        "description": "What the organisation does when a security incident happens.",
        "sections": [
            ("scope", "Purpose and scope", "What counts as an incident, severity levels and the systems covered."),
            ("team", "Response team and contacts", "Roles, on-call arrangements and escalation contacts, including external parties."),
            ("detection", "Detection and reporting", "How incidents are detected and how staff report them."),
            ("response", "Containment, eradication and recovery", "Step-by-step actions by severity, and criteria for declaring recovery."),
            ("communication", "Communication and notification", "Internal, customer and regulator communication, with timelines and templates."),
            ("review", "Post-incident review", "Root-cause analysis, evidence preservation, lessons learned and tracking of fixes."),
        ],
    },
    "quality_manual": {
        "kind": "compliance", "title": "Quality manual (ISO 9001 aligned)",
        "description": "The quality management system in one document.",
        "sections": [
            ("context", "Context, scope and interested parties", "The organisation, its customers and stakeholders, and the scope of the QMS."),
            ("leadership", "Leadership and quality policy", "Management commitment, the quality policy and quality objectives."),
            ("planning", "Planning: risks and objectives", "Risks and opportunities, objectives and how they are measured."),
            ("support", "Resources, competence and documented information", "People, infrastructure, training and document control."),
            ("operation", "Operational planning and control", "How products or services are planned, delivered and controlled, including suppliers."),
            ("evaluation", "Performance evaluation", "Monitoring, customer satisfaction, internal audit and management review."),
            ("improvement", "Nonconformity and continual improvement", "Corrective action, root-cause analysis and improvement activities."),
        ],
    },
    # ---- bid assets: reusable proof for tenders and grants
    "team_cv": {
        "kind": "bidasset", "title": "Team member CV (buyer format)",
        "description": "A tender-ready CV: relevant experience first, tailored to the evaluation criteria.",
        "evidence_type": "cv", "summary_sections": ["profile"],
        "sections": [
            ("profile", "Profile and role in this bid", "Two or three sentences: who this person is, their seniority, and the role they will play on this contract."),
            ("skills", "Key skills and expertise", "The skills the buyer is scoring, each backed by a concrete example rather than a bare claim."),
            ("experience", "Relevant experience", "Most relevant roles first. For each: organisation, role, dates, and one or two measurable achievements."),
            ("qualifications", "Qualifications, certifications and memberships", "Degrees, professional certifications and memberships, with the awarding body and year."),
            ("tailoring", "Fit to the evaluation criteria", "How this person's experience answers each scored criterion in the tender or call."),
            ("availability", "Availability and commitment", "Percentage of time committed, start date and any constraints."),
        ],
    },
    "capability_statement": {
        "kind": "bidasset", "title": "Capability statement",
        "description": "A one- or two-page summary of what the organisation does best and can prove.",
        "evidence_type": "capability_statement", "summary_sections": ["overview", "competencies"],
        "sections": [
            ("overview", "Company overview", "Who you are, what you do, who you serve, and how long you have been doing it."),
            ("competencies", "Core competencies", "Three to six capabilities, each in one line with the outcome it delivers."),
            ("differentiators", "What sets us apart", "Concrete differentiators a buyer can verify: methods, accreditations, speed, price model, track record."),
            ("past_performance", "Past performance highlights", "Short examples of similar work: client, scope, value and result."),
            ("accreditations", "Certifications and accreditations", "Standards held (for example ISO 9001/27001, Cyber Essentials Plus) with certificate details."),
            ("company_data", "Company data", "Registration numbers, turnover band, headcount, locations, insurance and frameworks you are on."),
            ("contact", "Contact", "Named contact, email, phone and website."),
        ],
    },
    "case_study": {
        "kind": "bidasset", "title": "Case study",
        "description": "A proof point showing what you delivered, how, and what changed. Can be saved to the evidence library.",
        "evidence_type": "case_study", "summary_sections": ["challenge", "results"], "metrics_section": "metrics",
        "sections": [
            ("context", "Client and context", "Who the client is (or an anonymised description), their sector and the situation."),
            ("challenge", "The challenge", "The problem or goal, why it mattered, and any constraints such as budget, time or risk."),
            ("solution", "Our approach and solution", "What you did and why, including the methods and people involved."),
            ("delivery", "Delivery and timeline", "How the work was delivered, key milestones and how risks were managed."),
            ("results", "Results and impact", "What changed, in the client's terms. Prefer measured outcomes over adjectives."),
            ("metrics", "Key metrics", "One metric per line as 'Label: value', for example 'Mileage reduction: 24%'. These are saved with the case study."),
            ("testimonial", "Client testimonial", "A short quote with the person's name and role, only if they have agreed to it."),
            ("relevance", "Relevance to future bids", "Which kinds of tender or grant this case study supports, and which criteria it evidences."),
        ],
    },
    "security_questionnaire": {
        "kind": "compliance", "title": "Security questionnaire response",
        "description": "Answer a customer's security questionnaire, matched against your answer library.",
        "sections": [],
    },
}

FINAL_STATUSES = ("quality_review", "approved", "delivered")
PROMOTABLE_STATUSES = ("approved", "delivered")


def parse_metrics(text: str) -> dict[str, str]:
    """'Label: value' lines -> {label: value}. Ignores blanks and lines without a value."""
    out: dict[str, str] = {}
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-*\u2022 ").strip()
        if ":" not in line:
            continue
        label, value = (part.strip() for part in line.split(":", 1))
        if label and value and len(out) < 12:
            out[label[:80]] = value[:120]
    return out


def instantiate_sections(doc_type: str) -> list[dict]:
    return [
        {"id": sid, "title": title, "prompt": prompt, "text": ""}
        for sid, title, prompt in TYPES[doc_type]["sections"]
    ]


def catalogue() -> list[dict]:
    return [
        {"key": k, "kind": v["kind"], "title": v["title"], "description": v["description"],
         "questionnaire": k == "security_questionnaire", "sections": len(v["sections"]),
         "promotable": "evidence_type" in v}
        for k, v in TYPES.items()
    ]
