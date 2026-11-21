from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import GrantProposal, OpportunityNotice
from bid_studio.schemas import GrantProposalCreate, GrantProposalSectionUpdate
from bid_studio.services.domain_logic import (
    compute_proposal_weighted_score,
    extract_grant_criteria,
)
from bid_studio.services.pipeline import (
    auto_process_call,
    build_proposal,
    infer_funder_type,
    queue_for_review,
)

router = APIRouter(prefix="/api/v1/grants", tags=["grants"])


@router.get("/calls")
def list_funding_calls(
    funder: str | None = None,
    workspace_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(OpportunityNotice).filter(OpportunityNotice.notice_type == "grant_call")
    if workspace_id is not None:
        query = query.filter(
            or_(
                OpportunityNotice.workspace_id.is_(None),
                OpportunityNotice.workspace_id == workspace_id,
            )
        )
    calls = query.order_by(OpportunityNotice.id.desc()).all()
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
    if notice.workspace_id is not None and notice.workspace_id != payload.workspace_id:
        raise HTTPException(status_code=404, detail="Funding call notice not found in workspace")

    proposal = build_proposal(
        db,
        notice,
        payload.workspace_id,
        title=payload.title,
        applicant_org=payload.applicant_org,
        requested_amount=payload.requested_amount,
        currency=payload.currency,
        sections=[s.model_dump() for s in payload.sections] if payload.sections else None,
    )
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
    if proposal.status == "in_review":
        raise HTTPException(status_code=409, detail="Grant proposal is already in quality review")

    queue_item = queue_for_review(db, proposal)
    db.commit()
    db.refresh(proposal)
    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "quality_queue_id": queue_item.id,
        "total_weighted_score": proposal.total_weighted_score,
    }


@router.post("/calls/{notice_id}/auto-process")
def auto_process_funding_call(
    notice_id: int,
    workspace_id: int = 1,
    applicant_org: str = "",
    submit_for_review: bool = True,
    db: Session = Depends(get_db),
):
    """Extract criteria, draft and score a proposal, and queue it for QA in one step."""
    notice = db.get(OpportunityNotice, notice_id)
    if not notice or notice.notice_type != "grant_call":
        raise HTTPException(status_code=404, detail="Funding call notice not found")
    if notice.workspace_id is not None and notice.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Funding call notice not found in workspace")
    proposal, created = auto_process_call(
        db,
        notice,
        workspace_id,
        applicant_org=applicant_org,
        submit_for_review=submit_for_review,
    )
    return {"created": created, "proposal": proposal}


@router.post("/auto-process")
def auto_process_open_calls(
    workspace_id: int = 1,
    applicant_org: str = "",
    submit_for_review: bool = True,
    db: Session = Depends(get_db),
):
    """Run the workflow for every open funding call that has no proposal yet."""
    calls = (
        db.query(OpportunityNotice)
        .filter(
            OpportunityNotice.notice_type == "grant_call",
            OpportunityNotice.status == "open",
            or_(
                OpportunityNotice.workspace_id.is_(None),
                OpportunityNotice.workspace_id == workspace_id,
            ),
        )
        .order_by(OpportunityNotice.id)
        .all()
    )
    created_ids = []
    for call in calls:
        proposal, created = auto_process_call(
            db, call, workspace_id, applicant_org=applicant_org, submit_for_review=submit_for_review
        )
        if created:
            created_ids.append(proposal.id)
    return {"processed": len(calls), "created_proposal_ids": created_ids}


@router.get("/proposals/{proposal_id}/export")
def export_grant_proposal_markdown(proposal_id: int, db: Session = Depends(get_db)):
    proposal = db.get(GrantProposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Grant proposal not found")

    lines = [
        f"# {proposal.title}",
        f"- **Funder Type:** {proposal.funder_type}",
        f"- **Applicant Organisation:** {proposal.applicant_org}",
        f"- **Requested Amount:** {proposal.currency} {proposal.requested_amount:,.2f}",
        f"- **Status:** {proposal.status}",
        f"- **Total Weighted Self-Score:** {proposal.total_weighted_score:.2f}%",
        "",
    ]
    for sec in proposal.sections:
        lines.extend(
            [
                f"## {sec.get('criterion_id')} — {sec.get('title')} (Weight {sec.get('weight')}%)",
                f"**Score:** {sec.get('self_score')} / {sec.get('max_score')}",
                "",
                str(sec.get("draft_text", "")),
                "",
            ]
        )
    return {
        "proposal_id": proposal.id,
        "title": proposal.title,
        "markdown": "\n".join(lines),
    }
