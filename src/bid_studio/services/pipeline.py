"""Grant workflow automation: call -> criteria -> drafted proposal -> QA queue."""

from sqlalchemy.orm import Session

from bid_studio.models import GrantProposal, OpportunityNotice, QualityQueueItem
from bid_studio.services.domain_logic import (
    compute_proposal_weighted_score,
    extract_grant_criteria,
)


def infer_funder_type(funder_name: str) -> str:
    low = funder_name.lower()
    if "european" in low or "horizon" in low or "eu" in low:
        return "EU"
    if "ukri" in low or "innovate" in low:
        return "UKRI"
    if "world bank" in low:
        return "World Bank"
    return "Foundation"


def build_proposal(
    db: Session,
    notice: OpportunityNotice,
    workspace_id: int,
    *,
    title: str | None = None,
    applicant_org: str = "",
    requested_amount: float | None = None,
    currency: str | None = None,
    sections: list[dict] | None = None,
) -> GrantProposal:
    """Extract criteria (persisting them on the call) and create a draft proposal."""
    funder_type = infer_funder_type(notice.funder_or_buyer)
    criteria = extract_grant_criteria(
        notice.structured_criteria, notice.raw_pack_text, funder_type
    )
    if not notice.structured_criteria:
        notice.structured_criteria = criteria

    if not sections:
        sections = [
            {
                "criterion_id": c["criterion_id"],
                "title": c["title"],
                "weight": c["weight"],
                "max_score": c["max_score"],
                "draft_text": f"Draft response for {c['title']} addressing: {c['guidance']}",
                "self_score": round(float(c["max_score"]) * 0.75, 2),
                "evidence_refs": [],
            }
            for c in criteria
        ]

    proposal = GrantProposal(
        workspace_id=workspace_id,
        notice_id=notice.id,
        funder_type=funder_type,
        title=title or f"{notice.title} — Proposal",
        applicant_org=applicant_org,
        requested_amount=requested_amount or notice.contract_value,
        currency=currency or notice.currency,
        status="draft",
        extracted_criteria=criteria,
        sections=sections,
        total_weighted_score=compute_proposal_weighted_score(sections),
    )
    db.add(proposal)
    db.flush()
    return proposal


def queue_for_review(db: Session, proposal: GrantProposal) -> QualityQueueItem:
    item = QualityQueueItem(
        workspace_id=proposal.workspace_id,
        item_type="grant_proposal",
        reference_id=proposal.id,
        title=proposal.title,
        status="queued",
        review_score=proposal.total_weighted_score,
        review_notes=(
            f"Funder: {proposal.funder_type}; self-assessed score {proposal.total_weighted_score}%"
        ),
    )
    db.add(item)
    db.flush()
    proposal.status = "in_review"
    proposal.quality_queue_id = item.id
    return item


def auto_process_call(
    db: Session,
    notice: OpportunityNotice,
    workspace_id: int,
    *,
    applicant_org: str = "",
    submit_for_review: bool = True,
) -> tuple[GrantProposal, bool]:
    """Run the whole workflow for one call. Idempotent per (call, workspace).

    Returns (proposal, created).
    """
    existing = (
        db.query(GrantProposal)
        .filter(GrantProposal.notice_id == notice.id, GrantProposal.workspace_id == workspace_id)
        .order_by(GrantProposal.id)
        .first()
    )
    if existing:
        return existing, False

    proposal = build_proposal(db, notice, workspace_id, applicant_org=applicant_org)
    if submit_for_review:
        queue_for_review(db, proposal)
    db.commit()
    db.refresh(proposal)
    return proposal, True
