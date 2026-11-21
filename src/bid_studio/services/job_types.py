"""Kinds of writing work that can be commissioned through the marketplace."""

JOB_TYPES: dict[str, dict] = {
    "grant_proposal": {"label": "Grant proposal writing", "link": "proposal"},
    "technical_docs": {"label": "Technical documentation", "link": "doc", "kind": "techdoc"},
    "compliance_policy": {
        "label": "Compliance and policy writing", "link": "doc", "kind": "compliance",
        "exclude": ("security_questionnaire",),
    },
    "security_questionnaire": {
        "label": "Security questionnaire response", "link": "doc",
        "doc_types": ("security_questionnaire",),
    },
    "bid_assets": {
        "label": "CVs, capability statements and case studies", "link": "doc", "kind": "bidasset",
    },
    "other": {"label": "Other writing", "link": None},
}


def catalogue() -> list[dict]:
    return [{"key": k, "label": v["label"], "link": v["link"]} for k, v in JOB_TYPES.items()]


def doc_project_fits(job_type: str, kind: str, doc_type: str) -> bool:
    spec = JOB_TYPES.get(job_type, {})
    if spec.get("link") != "doc":
        return False
    if "doc_types" in spec:
        return doc_type in spec["doc_types"]
    return kind == spec["kind"] and doc_type not in spec.get("exclude", ())
