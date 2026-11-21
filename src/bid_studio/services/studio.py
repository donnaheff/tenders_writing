"""Grant Studio logic: word counts, submission readiness and library suggestions."""

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from bid_studio.models import (
    AnswerLibraryItem,
    EvidenceItem,
    GrantProposal,
    ProposalPlan,
    ProposalVersion,
)
from bid_studio.services.domain_logic import compute_proposal_weighted_score, tokenize

PLACEHOLDER_PREFIX = "Draft response for"
AUTOSNAPSHOT_MINUTES = 10
MAX_VERSIONS = 50


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def is_unwritten(text: str) -> bool:
    t = (text or "").strip()
    return not t or t.startswith(PLACEHOLDER_PREFIX)


def enrich_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for s in sections:
        limit = s.get("word_limit")
        wc = word_count(s.get("draft_text", ""))
        out.append(
            {
                **s,
                "word_limit": limit,
                "notes": s.get("notes", ""),
                "word_count": wc,
                "over_limit": bool(limit and wc > limit),
                "unwritten": is_unwritten(s.get("draft_text", "")),
            }
        )
    return out


def readiness(
    proposal: GrantProposal,
    deadline: date | None,
    today: date,
    plan_analysis: dict[str, Any] | None = None,
    has_plan: bool = False,
) -> dict[str, Any]:
    secs = enrich_sections(proposal.sections or [])
    checks: list[dict[str, Any]] = []

    def add(cid, label, severity, ok, detail=""):
        checks.append(
            {"id": cid, "label": label, "severity": severity, "ok": bool(ok), "detail": detail}
        )

    unwritten = [s["title"] for s in secs if s["unwritten"]]
    add(
        "drafted",
        "Every section has been written",
        "blocker",
        not unwritten and bool(secs),
        "Still placeholder or empty: " + ", ".join(unwritten) if unwritten else "",
    )
    over = [f"{s['title']} ({s['word_count']}/{s['word_limit']})" for s in secs if s["over_limit"]]
    add("limits", "All sections are within their word limits", "blocker", not over, "; ".join(over))
    bad_scores = [
        s["title"]
        for s in secs
        if not (0 <= float(s.get("self_score", 0)) <= float(s.get("max_score", 5)))
    ]
    add("scores", "Self-scores are within range", "blocker", not bad_scores, ", ".join(bad_scores))
    add(
        "applicant",
        "Applicant organisation is set",
        "blocker",
        bool((proposal.applicant_org or "").strip()),
    )
    add("amount", "Requested amount is set", "blocker", (proposal.requested_amount or 0) > 0)

    if deadline is None:
        add("deadline", "Call deadline", "warning", True, "Rolling or no stated deadline")
    else:
        days = (deadline - today).days
        if days < 0:
            add("deadline", "Call deadline has not passed", "blocker", False, f"Closed {-days} day(s) ago")
        elif days <= 7:
            add("deadline", "Call closes in more than 7 days", "warning", False, f"{days} day(s) left")
        else:
            add("deadline", "Call closes in more than 7 days", "warning", True, f"{days} days left")

    weight_total = sum(float(s.get("weight", 0)) for s in secs)
    add(
        "weights",
        "Criteria weights total 100%",
        "warning",
        abs(weight_total - 100.0) < 0.5,
        f"Weights total {weight_total:g}%",
    )
    no_evidence = [s["title"] for s in secs if not s.get("evidence_refs")]
    add(
        "evidence",
        "Every section cites evidence",
        "warning",
        not no_evidence and bool(secs),
        "No evidence cited in: " + ", ".join(no_evidence) if no_evidence else "",
    )
    add(
        "score",
        "Self-assessed score is at least 60%",
        "warning",
        proposal.total_weighted_score >= 60,
        f"Currently {proposal.total_weighted_score:g}%",
    )
    if plan_analysis is not None:
        add(
            "plan_wp",
            "Work packages are defined",
            "warning",
            has_plan,
            "" if has_plan else "Add work packages under the Work packages tab",
        )
        errors = [c["message"] for c in plan_analysis["checks"] if c["level"] == "error"]
        add("plan_consistent", "Plan has no consistency errors", "warning", not errors, " ".join(errors[:3]))
        budget = plan_analysis["budget"]
        has_budget = bool(budget["total"])
        within = proposal.requested_amount <= 0 or abs(budget["variance"]) <= max(1.0, proposal.requested_amount * 0.01)
        add(
            "plan_budget",
            "Budget matches the requested amount",
            "warning",
            has_budget and within,
            "" if has_budget and within else f"Budget requests {budget['requested']:,.2f}; proposal requests {proposal.requested_amount:,.2f}",
        )
    ready = all(c["ok"] for c in checks if c["severity"] == "blocker")
    return {"ready": ready, "checks": checks}


def suggest(
    db: Session, proposal: GrantProposal, section_index: int, q: str = "", limit: int = 6
) -> dict[str, list[dict[str, Any]]]:
    """Rank the workspace's answers and evidence against a section (or a search query)."""
    secs = proposal.sections or []
    if q.strip():
        query_tokens = tokenize(q)
    else:
        sec = secs[section_index] if 0 <= section_index < len(secs) else {}
        guidance = ""
        for c in proposal.extracted_criteria or []:
            if c.get("criterion_id") == sec.get("criterion_id"):
                guidance = c.get("guidance", "")
        query_tokens = tokenize(f"{sec.get('title', '')} {guidance} {sec.get('draft_text', '')[:400]}")

    def rank(items, text_of):
        scored = []
        for it in items:
            overlap = len(query_tokens & tokenize(text_of(it)))
            if overlap:
                scored.append((overlap, it))
        scored.sort(key=lambda p: (-p[0], p[1].id))
        return scored[:limit]

    answers = db.query(AnswerLibraryItem).filter(
        AnswerLibraryItem.workspace_id == proposal.workspace_id
    )
    evidence = db.query(EvidenceItem).filter(EvidenceItem.workspace_id == proposal.workspace_id)
    return {
        "answers": [
            {
                "id": a.id,
                "title": a.question_pattern,
                "text": a.answer_text,
                "category": a.category,
                "match": score,
            }
            for score, a in rank(
                answers.all(),
                lambda a: f"{a.question_pattern} {a.answer_text} {' '.join(a.tags or [])}",
            )
        ],
        "evidence": [
            {
                "id": e.id,
                "title": e.title,
                "text": e.summary,
                "type": e.evidence_type,
                "match": score,
            }
            for score, e in rank(evidence.all(), lambda e: f"{e.title} {e.summary}")
        ],
    }


def snapshot_of(proposal: GrantProposal) -> dict[str, Any]:
    return {
        "title": proposal.title,
        "applicant_org": proposal.applicant_org,
        "requested_amount": proposal.requested_amount,
        "currency": proposal.currency,
        "sections": proposal.sections,
        "score": proposal.total_weighted_score,
    }


def core_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    """A snapshot without the plan, so section-only comparisons ignore plan changes."""
    return {k: v for k, v in snap.items() if k != "plan"}


def maybe_snapshot(db: Session, proposal: GrantProposal) -> ProposalVersion | None:
    """Snapshot when none exists yet, or the last one is old and the content has changed."""
    last = (
        db.query(ProposalVersion)
        .filter(ProposalVersion.proposal_id == proposal.id)
        .order_by(ProposalVersion.version_no.desc())
        .first()
    )
    if last is None:
        return take_snapshot(db, proposal)
    created = last.created_at if last.created_at.tzinfo else last.created_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - created < timedelta(minutes=AUTOSNAPSHOT_MINUTES):
        return None
    row = db.query(ProposalPlan).filter(ProposalPlan.proposal_id == proposal.id).first()
    current = {**snapshot_of(proposal), **({"plan": row.data} if row else {})}
    return take_snapshot(db, proposal) if current != last.snapshot else None


def take_snapshot(db: Session, proposal: GrantProposal, label: str = "") -> ProposalVersion:
    last_no = (
        db.query(ProposalVersion.version_no)
        .filter(ProposalVersion.proposal_id == proposal.id)
        .order_by(ProposalVersion.version_no.desc())
        .limit(1)
        .scalar()
        or 0
    )
    version = ProposalVersion(
        proposal_id=proposal.id,
        version_no=last_no + 1,
        label=label,
        snapshot=_with_plan(db, proposal),
    )
    db.add(version)
    db.flush()
    # prune oldest unlabeled versions beyond the cap
    extra = (
        db.query(ProposalVersion)
        .filter(ProposalVersion.proposal_id == proposal.id)
        .order_by(ProposalVersion.version_no.desc())
        .offset(MAX_VERSIONS)
        .all()
    )
    for old in extra:
        if not old.label:
            db.delete(old)
    return version


def _with_plan(db: Session, proposal: GrantProposal) -> dict[str, Any]:
    snap = snapshot_of(proposal)
    row = db.query(ProposalPlan).filter(ProposalPlan.proposal_id == proposal.id).first()
    if row:
        snap["plan"] = row.data
    return snap


def rescore(sections: list[dict[str, Any]]) -> float:
    return compute_proposal_weighted_score(sections)
