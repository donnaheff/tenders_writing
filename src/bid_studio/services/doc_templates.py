"""Templates for supporting documents funders commonly require."""

# (section id, title, prompt shown as guidance and given to the assistant)
TEMPLATES: dict[str, dict] = {
    "dmp": {
        "title": "Data Management Plan",
        "kind": "sections",
        "description": "Required by most research funders. Follows the FAIR principles.",
        "sections": [
            ("summary", "Data summary", "What data will be collected or generated, in what formats and volumes, and why it is needed."),
            ("findable", "Findable", "Persistent identifiers, metadata standards, naming conventions and where the data will be discoverable."),
            ("accessible", "Accessible", "Which data is open, which is restricted and why, the repository used, and how access is requested."),
            ("interoperable", "Interoperable", "Standard formats, vocabularies and ontologies so the data can be combined and reused."),
            ("reusable", "Reusable", "Licences, documentation, quality assurance and how long the data stays reusable."),
            ("storage", "Storage, backup and security", "Where data is stored during the project, backup routine, access control and encryption."),
            ("legal", "Legal and ethical aspects", "Personal data (GDPR), consent, intellectual property and confidentiality."),
            ("resources", "Responsibilities and resources", "Who manages the data, and the costs and effort budgeted for data management."),
        ],
    },
    "ethics": {
        "title": "Ethics and Compliance Statement",
        "kind": "sections",
        "description": "Addresses the ethics self-assessment funders ask for.",
        "sections": [
            ("participants", "Human participants", "Whether people take part, how they are recruited, informed consent, and safeguards for vulnerable groups."),
            ("personal_data", "Personal data protection", "Personal data processed, lawful basis, minimisation, retention, DPIA and data protection officer."),
            ("animals_env", "Animals, environment, health and safety", "Any animal work, environmental impact, and health and safety risks with controls."),
            ("misuse", "Potential for misuse and dual use", "Whether results could be misused and how that risk is managed."),
            ("ai", "AI and algorithmic ethics", "Fairness, transparency and human oversight of any automated decision-making."),
            ("approvals", "Approvals and oversight", "Ethics committee approvals needed or obtained, and who is accountable."),
        ],
    },
    "impact": {
        "title": "Impact and Dissemination Plan",
        "kind": "sections",
        "description": "How outcomes become measurable change, and how results reach the right people.",
        "sections": [
            ("outcomes", "Expected outcomes", "The specific, measurable changes the project will cause, and by when."),
            ("beneficiaries", "Target groups and beneficiaries", "Who benefits, how many, and how they were consulted."),
            ("pathway", "Pathway to impact", "The steps from project outputs to outcomes and wider impact, with the assumptions each step relies on."),
            ("dissemination", "Dissemination and communication", "Channels, audiences, timing and responsibilities for sharing results."),
            ("exploitation", "Exploitation and sustainability", "How results continue to be used after funding ends: adoption, scale-up and funding model."),
            ("measurement", "Measurement and evaluation", "KPIs, baselines, data sources and how progress is reported."),
        ],
    },
    "risk_register": {
        "title": "Risk Register",
        "kind": "risk",
        "description": "Likelihood x impact scoring with mitigations and owners.",
        "sections": [],
    },
}

RISK_CATEGORIES = ("technical", "delivery", "financial", "legal", "ethical", "partnership", "other")


def instantiate(key: str) -> dict:
    t = TEMPLATES[key]
    return {
        "key": key,
        "title": t["title"],
        "sections": [
            {"id": sid, "title": title, "prompt": prompt, "text": ""}
            for sid, title, prompt in t["sections"]
        ],
        "rows": [],
    }


def catalogue() -> list[dict]:
    return [
        {"key": k, "title": v["title"], "description": v["description"], "kind": v["kind"]}
        for k, v in TEMPLATES.items()
    ]
