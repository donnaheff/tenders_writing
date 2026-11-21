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
    # ---- batch 1: grant-adjacent documents
    "logic_model": {
        "kind": "grantdoc", "title": "Logic model / theory of change",
        "description": "How inputs and activities lead to outputs, outcomes and impact, and what you are assuming.",
        "sections": [
            ("problem", "Problem and long-term goal", "The problem being addressed, who is affected, and the long-term change you want to contribute to."),
            ("inputs", "Inputs", "The resources the project uses: funding, people, partners, facilities, data and existing assets."),
            ("activities", "Activities", "What the project does with those inputs, grouped by work package or workstream."),
            ("outputs", "Outputs", "The direct, countable products of the activities: services delivered, people reached, tools built."),
            ("outcomes", "Outcomes (short and medium term)", "The changes in behaviour, capability or conditions that the outputs cause, with a timeframe for each."),
            ("impact", "Impact", "The longer-term, wider change and how this project contributes to it, without overclaiming attribution."),
            ("assumptions", "Assumptions and external factors", "What must hold true for each step to lead to the next, and the outside factors you do not control."),
            ("evidence", "Evidence base", "Research, pilots or experience that support the causal links in this model."),
        ],
    },
    "evaluation_plan": {
        "kind": "grantdoc", "title": "Evaluation and monitoring plan",
        "description": "How you will measure progress and judge success, and what you will do with the findings.",
        "sections": [
            ("purpose", "Purpose and evaluation questions", "What the evaluation is for, who will use it, and the three to five questions it must answer."),
            ("indicators", "Indicators and targets", "For each outcome: the indicator, baseline, target and date. Prefer a small set of meaningful indicators."),
            ("methods", "Data collection methods", "How each indicator will be measured: surveys, administrative data, interviews, sensors. Include sample sizes and frequency."),
            ("design", "Evaluation design", "Whether it is a process, outcome or impact evaluation, any comparison group, and why the design is proportionate."),
            ("ethics", "Ethics and data protection", "Consent, anonymisation, storage and who has access to the evaluation data."),
            ("roles", "Roles and independence", "Who runs the evaluation, whether it is internal or external, and how independence is protected."),
            ("learning", "Reporting and learning", "Reporting schedule, how findings change delivery, and how results are shared publicly."),
            ("budget", "Resources and timeline", "Budget share, effort and key dates for the evaluation."),
        ],
    },
    "sustainability_plan": {
        "kind": "grantdoc", "title": "Sustainability and exploitation plan",
        "description": "What continues after the funding ends, and who pays for and owns it.",
        "sections": [
            ("what", "What will be sustained", "The specific services, products, practices or partnerships that will continue, and the evidence people will keep using them."),
            ("model", "Funding and business model", "How ongoing costs will be covered: income, other funders, public budgets or in-kind support, with the first year's figures."),
            ("ownership", "Ownership and governance", "Who owns and maintains results after the project, and the agreements that secure this."),
            ("adoption", "Adoption and scale-up", "Who will adopt the results, the route to reach them and the barriers you will remove."),
            ("ip", "Intellectual property and openness", "IP ownership, licensing, open-source or open-access commitments and exceptions."),
            ("risks", "Risks to sustainability", "What could stop the benefits continuing and how each risk is reduced."),
            ("exit", "Exit and handover", "What is handed over, to whom, and when, so the work does not depend on the project team."),
        ],
    },
    "funder_progress_report": {
        "kind": "grantdoc", "title": "Funder progress report", "link": "proposal",
        "description": "A periodic report to the funder. Link a proposal to pre-fill deliverables and budget from its plan.",
        "sections": [
            ("summary", "Summary of the period", "Two or three sentences: reporting period, headline progress and anything the funder must know."),
            ("progress", "Progress against objectives", "For each objective or work package: what was planned, what was achieved and any variance with reasons."),
            ("deliverables", "Deliverables and milestones", "Status of each deliverable and milestone: complete, in progress or delayed, with revised dates."),
            ("budget", "Budget and expenditure", "Spend to date against budget by work package, forecast to the end and any virement requested."),
            ("risks", "Risks and issues", "Risks that have materialised, new risks, and the action taken or needed."),
            ("outcomes", "Outcomes and early impact", "Evidence of change so far against the agreed indicators."),
            ("lessons", "Lessons learned", "What is working, what is not, and what has changed as a result."),
            ("next", "Plans for the next period", "Planned activity, deliverables due and any decisions needed from the funder."),
        ],
    },
    "funder_final_report": {
        "kind": "grantdoc", "title": "Funder final report", "link": "proposal",
        "description": "The end-of-grant report. Link a proposal to pre-fill deliverables and budget from its plan.",
        "sections": [
            ("summary", "Executive summary", "What the project set out to do, what it achieved and its main impact, in one page."),
            ("progress", "Achievements against objectives", "Each objective, the result and the evidence, with honest comment on anything not achieved."),
            ("deliverables", "Deliverables and milestones", "Final status of every deliverable and milestone, with links to the outputs."),
            ("budget", "Final budget and expenditure", "Total spend against budget by work package and category, explanations for variances and any unspent funds."),
            ("outcomes", "Outcomes and impact", "Results against each indicator with data, plus unintended effects."),
            ("dissemination", "Dissemination and engagement", "Publications, events, media, open data and who was reached."),
            ("sustainability", "Sustainability and next steps", "What continues, who is responsible and what follow-on funding or activity is planned."),
            ("lessons", "Lessons learned", "What you would do differently and advice for future projects."),
        ],
    },
    "lay_summary": {
        "kind": "grantdoc", "title": "Lay summary and abstract",
        "description": "The plain-language summary and short technical abstract funders and the public read first.",
        "sections": [
            ("lay", "Lay summary (about 150-200 words)", "Plain English for a general reader: the problem, what you will do, why it matters and who benefits. No jargon or acronyms."),
            ("abstract", "Technical abstract (about 200-250 words)", "Objectives, methods, expected results and significance, for a specialist reader."),
            ("keywords", "Keywords and plain-language glossary", "Five to eight keywords, and a one-line plain definition of each technical term used."),
            ("impact_line", "One-sentence impact statement", "A single sentence a non-specialist could repeat to explain why this project matters."),
        ],
    },
    "safeguarding_policy": {
        "kind": "grantdoc", "title": "Safeguarding policy",
        "description": "How the organisation protects children and adults at risk, as many funders require.",
        "sections": [
            ("purpose", "Purpose, scope and principles", "Who the policy covers, the commitment to protect people from harm and the principles that guide it."),
            ("roles", "Roles and responsibilities", "The designated safeguarding lead, trustees or board oversight, and every person's duty to report."),
            ("recruitment", "Safer recruitment and vetting", "Checks, references, vetting (for example DBS) and induction for staff and volunteers."),
            ("training", "Training and awareness", "What training each role receives, how often, and how it is recorded."),
            ("conduct", "Code of conduct", "Expected behaviour, and what is never acceptable, including online and one-to-one contact."),
            ("reporting", "Reporting concerns and incident handling", "How to raise a concern, who responds, timescales, record keeping and referral to statutory agencies."),
            ("partners", "Partners and third parties", "Safeguarding expectations of partners, subcontractors and delivery sites."),
            ("review", "Monitoring, review and whistleblowing", "How the policy is reviewed, who audits it and how people can raise concerns about misconduct safely."),
        ],
    },
    "gender_equality_plan": {
        "kind": "grantdoc", "title": "Gender equality plan (Horizon Europe)",
        "description": "Covers the building blocks public bodies and research organisations need for Horizon Europe eligibility.",
        "sections": [
            ("commitment", "Public commitment and dedicated resources", "The formal commitment signed off by leadership, and the people and budget assigned to gender equality."),
            ("data", "Data collection and monitoring", "Sex-disaggregated data you collect on staff and leadership, how often, and how it is reported."),
            ("worklife", "Work-life balance and organisational culture", "Policies on flexibility, leave and caring responsibilities, and actions on culture."),
            ("recruitment", "Gender balance in leadership and decision-making", "Targets and actions for leadership roles, committees and recruitment."),
            ("dimension", "Gender dimension in research and teaching", "How the gender dimension is considered in research content and training."),
            ("violence", "Measures against gender-based violence and harassment", "Policies, reporting routes, support and sanctions."),
            ("training", "Training and awareness", "Gender-bias training for staff and decision-makers, and how uptake is tracked."),
            ("review", "Targets, review and publication", "Targets, how progress is reviewed, and where the plan is published."),
        ],
    },
    # ---- batch 2: tender technical responses
    "method_statement": {
        "kind": "tenderdoc", "title": "Method statement", "link": "notice",
        "description": "A technical response scored against the evaluation criteria. Link a tender to pre-fill its criteria.",
        "sections": [
            ("criteria_map", "Evaluation criteria and where we answer them", "List each scored criterion and its weight, and note which section of this response answers it."),
            ("understanding", "Understanding of the requirement", "Show you understand the buyer's goals, context and constraints, in their own terms rather than yours."),
            ("approach", "Approach and methodology", "Step by step, how the service will be delivered, with the reason for each choice and the outcome each step produces."),
            ("team", "Team, roles and governance", "Who does what, named key people, reporting lines and how the buyer will be kept informed."),
            ("quality", "Quality assurance and performance management", "Standards followed, checks, KPIs, reporting and how problems are corrected."),
            ("risk", "Risk management", "The main risks to delivery, their likelihood and impact, and the mitigation and owner for each."),
            ("social_value", "Social value and sustainability", "Measurable commitments to local jobs, skills, SMEs, carbon and wellbeing, tied to the buyer's priorities."),
            ("added_value", "Added value and innovation", "What you offer beyond the specification, and the evidence that it works."),
        ],
    },
    "mobilisation_plan": {
        "kind": "tenderdoc", "title": "Mobilisation and transition plan",
        "description": "How you start delivery quickly and safely after award.",
        "sections": [
            ("overview", "Overview and objectives", "What a successful start looks like and the date you will be fully operational."),
            ("timeline", "Mobilisation timeline", "Week-by-week activities from contract signature to go-live, with owners and dependencies."),
            ("people", "People and TUPE", "Recruitment, onboarding, training and any transfer of staff, with the timetable."),
            ("systems", "Systems, data and access", "Environments, accounts, data migration and security checks required before go-live."),
            ("governance", "Mobilisation governance", "Meetings, reporting, a named mobilisation lead and the buyer's involvement."),
            ("risks", "Mobilisation risks", "The risks to a smooth start and the contingency for each."),
            ("acceptance", "Go-live criteria and handover", "The tests and sign-offs that confirm readiness, and what happens if they are missed."),
        ],
    },
    "exit_plan": {
        "kind": "tenderdoc", "title": "Exit and handover plan",
        "description": "How the service is handed back or to a successor at the end of the contract.",
        "sections": [
            ("principles", "Principles and triggers", "Your commitment to a smooth exit, and the events (expiry, early termination) that start the plan."),
            ("assets", "Assets, data and documentation", "What is handed over, in what format, how it is verified and when."),
            ("knowledge", "Knowledge transfer", "Training, shadowing and documentation so the successor can run the service."),
            ("people", "People and transfer obligations", "Staffing implications, TUPE information and cooperation with the incoming supplier."),
            ("continuity", "Service continuity during exit", "How service levels are maintained while responsibility moves."),
            ("timeline", "Exit timeline and costs", "Key dates, who does what, and any exit charges (or confirmation there are none)."),
        ],
    },
    "bcp_dr_plan": {
        "kind": "tenderdoc", "title": "Business continuity and disaster recovery plan",
        "description": "How critical services keep running, and recover, when something goes wrong.",
        "sections": [
            ("scope", "Scope, objectives and critical services", "The services covered, what must keep running and the impact if each stops."),
            ("rto_rpo", "Recovery objectives (RTO and RPO)", "For each critical service: the maximum tolerable downtime, recovery time objective and recovery point objective."),
            ("risks", "Threats and risk assessment", "The scenarios planned for (loss of site, people, supplier, IT, cyber attack) and their likelihood and impact."),
            ("strategies", "Continuity and recovery strategies", "Alternate sites and remote working, backup and failover, supplier alternatives, and manual workarounds."),
            ("response", "Incident response and invocation", "Who can invoke the plan, the decision criteria, the call tree and the first-hour actions."),
            ("comms", "Communications", "Internal, customer and regulator communications, with owners and templates."),
            ("testing", "Testing, training and maintenance", "How often the plan is tested, results recorded, staff trained and the plan updated."),
        ],
    },
    "rams": {
        "kind": "tenderdoc", "title": "Risk assessment and method statement (RAMS)",
        "description": "Site or task safety documentation. Must be reviewed and signed off by a competent person before use.",
        "sections": [
            ("scope", "Scope, location and activities", "The task, the site, the people and equipment involved, and the dates."),
            ("hazards", "Hazards and risk assessment", "For each hazard: who may be harmed, likelihood and severity, existing controls and residual risk. A Markdown table works well."),
            ("controls", "Control measures", "The controls chosen, following the hierarchy of control, and who is responsible for each."),
            ("method", "Safe system of work (method)", "Step-by-step sequence of work, with the controls that apply at each step."),
            ("ppe", "Equipment, PPE and permits", "Plant, tools, personal protective equipment, and any permits or isolations required."),
            ("emergency", "Emergency procedures", "First aid, fire, spill and evacuation arrangements, and who to call."),
            ("competence", "Competence, supervision and briefing", "Qualifications and training needed, supervision, and how operatives are briefed and sign on."),
            ("review", "Monitoring, review and sign-off", "How compliance is checked, when the RAMS is reviewed and who approves it."),
        ],
    },
    "service_description": {
        "kind": "tenderdoc", "title": "Service description and SLA",
        "description": "What is delivered, to what standard, and what happens when it is not.",
        "sections": [
            ("overview", "Service overview", "What the service is, who it is for and what is included and excluded."),
            ("components", "Service components and deliverables", "Each component of the service, with a short description and its owner."),
            ("hours", "Service hours and support model", "Operating hours, support channels, response and resolution targets by priority."),
            ("levels", "Service levels and KPIs", "Measurable targets (availability, response, quality), how they are measured and reported."),
            ("credits", "Service credits and remedies", "What the customer receives if targets are missed, and how it is calculated."),
            ("responsibilities", "Customer responsibilities and dependencies", "What the customer must provide for the service levels to apply."),
            ("changes", "Change control and review", "How changes are requested, assessed and approved, and how performance is reviewed."),
        ],
    },
    "statement_of_work": {
        "kind": "tenderdoc", "title": "Statement of work",
        "description": "A precise description of the work, deliverables, timeline and acceptance.",
        "sections": [
            ("background", "Background and objectives", "Why the work is needed and what a successful outcome is."),
            ("scope", "Scope of work", "The work in scope, and explicitly what is out of scope."),
            ("deliverables", "Deliverables", "Each deliverable with a description, format and acceptance criteria."),
            ("schedule", "Schedule and milestones", "Start and end dates, milestones and dependencies."),
            ("roles", "Roles, responsibilities and assumptions", "Who does what on each side, and the assumptions the plan relies on."),
            ("acceptance", "Acceptance and change control", "How deliverables are reviewed and accepted, and how changes to scope are agreed."),
            ("commercials", "Commercial terms summary", "Price model, payment milestones and expenses, referring to the contract for legal terms."),
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
         "promotable": "evidence_type" in v, "link": v.get("link")}
        for k, v in TYPES.items()
    ]
