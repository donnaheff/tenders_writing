from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import GrantProposal, OpportunityNotice, QualityQueueItem
from bid_studio.schemas import GrantProposalCreate, GrantProposalSectionUpdate
from bid_studio.services.domain_logic import (
    compute_proposal_weighted_score,
    extract_grant_criteria,
)

router = APIRouter(prefix="/api/v1/grants", tags=["grants"])


def infer_funder_type(funder_name: str) -> str:
    low = funder_name.lower()
    if "european" in low or "horizon" in low or "eu" in low:
        return "EU"
    if "ukri" in low or "innovate" in low:
        return "UKRI"
    if "world bank" in low:
        return "World Bank"
    return "Foundation"


@router.get("/calls")
def list_funding_calls(funder: str | None = None, db: Session = Depends(get_db)):
    calls = (
        db.query(OpportunityNotice)
        .filter(OpportunityNotice.notice_type == "grant_call")
        .order_by(OpportunityNotice.id.desc())
        .all()
    )
    if funder:
        f_low = funder.lower()
        calls = [
            c
            for c in calls
            if f_low in c.funder_or_buyer.lower() or f_low in c.source_portal.lower()
        ]
    return calls


@router.post("/calls/{notice_id}/extract-criteria")
def extract_call_criteria(notice_id: int, db: Session = Depends(get_db)):
    notice = db.get(OpportunityNotice, notice_id)
    if not notice or notice.notice_type != "grant_call":
        raise HTTPException(status_code=404, detail="Funding call notice not found")

    funder_type = infer_funder_type(notice.funder_or_buyer)
    criteria = extract_grant_criteria(
        notice.structured_criteria,
        notice.raw_pack_text,
        funder_type,
    )
    notice.structured_criteria = criteria
    db.commit()
    db.refresh(notice)
    return {
        "notice_id": notice.id,
        "funder_type": funder_type,
        "criteria": criteria,
    }


@router.get("/proposals")
def list_grant_proposals(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(GrantProposal)
        .filter(GrantProposal.workspace_id == workspace_id)
        .order_by(GrantProposal.id.desc())
        .all()
    )


@router.post("/proposals", status_code=201)
def create_grant_proposal(payload: GrantProposalCreate, db: Session = Depends(get_db)):
    notice = db.get(OpportunityNotice, payload.notice_id)
    if not notice or notice.notice_type != "grant_call":
        raise HTTPException(status_code=404, detail="Funding call notice not found")

    funder_type = infer_funder_type(notice.funder_or_buyer)
    criteria = extract_grant_criteria(
        notice.structured_criteria,
        notice.raw_pack_text,
        funder_type,
    )
    if not notice.structured_criteria:
        notice.structured_criteria = criteria

    if payload.sections:
        sections = [s.model_dump() for s in payload.sections]
    else:
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

    weighted_score = compute_proposal_weighted_score(sections)
    proposal = GrantProposal(
        workspace_id=payload.workspace_id,
        notice_id=notice.id,
        funder_type=funder_type,
        title=payload.title or f"{notice.title} — Proposal",
        applicant_org=payload.applicant_org,
        requested_amount=payload.requested_amount or notice.contract_value,
        currency=payload.currency or notice.currency,
        status="draft",
        extracted_criteria=criteria,
        sections=sections,
        total_weighted_score=weighted_score,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


@router.put("/proposals/{proposal_id}/sections")
def update_proposal_sections(
    proposal_id: int,
    payload: GrantProposalSectionUpdate,
    db: Session = Depends(get_db),
):
    proposal = db.get(GrantProposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Grant proposal not found")
    sections = [s.model_dump() for s in payload.sections]
    proposal.sections = sections
    proposal.total_weighted_score = compute_proposal_weighted_score(sections)
    db.commit()
    db.refresh(proposal)
    return proposal


@router.post("/proposals/{proposal_id}/submit-review")
def submit_proposal_for_review(proposal_id: int, db: Session = Depends(get_db)):
    proposal = db.get(GrantProposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Grant proposal not found")

    queue_item = QualityQueueItem(
        workspace_id=proposal.workspace_id,
        item_type="grant_proposal",
        reference_id=proposal.id,
        title=proposal.title,
        status="queued",
        review_score=proposal.total_weighted_score,
        review_notes=f"Funder: {proposal.funder_type}; self-assessed score {proposal.total_weighted_score}%",
    )
    db.add(queue_item)
    db.flush()
    proposal.status = "in_review"
    proposal.quality_queue_id = queue_item.id
    db.commit()
    db.refresh(proposal)
    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "quality_queue_id": queue_item.id,
        "total_weighted_score": proposal.total_weighted_score,
    }
