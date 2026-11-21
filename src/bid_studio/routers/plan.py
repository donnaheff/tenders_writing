from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import GrantProposal, OpportunityNotice, ProposalPlan
from bid_studio.services import assistant as ai
from bid_studio.services import doc_templates
from bid_studio.services import plan as planlib
from bid_studio.services.access import proposal_guard
from bid_studio.services.studio import maybe_snapshot, suggest

router = APIRouter(
    prefix="/api/v1/grants/proposals/{proposal_id}/plan",
    tags=["grant-plan"],
    dependencies=[Depends(proposal_guard)],
)


class DocAssistIn(BaseModel):
    action: str = Field(pattern="^(draft|improve|shorten|critique|ask)$")
    section_id: str = Field(min_length=1, max_length=40)
    text: str | None = Field(default=None, max_length=40000)
    instruction: str = Field(default="", max_length=1500)


def _proposal(db: Session, proposal_id: int) -> GrantProposal:
    p = db.get(GrantProposal, proposal_id)
    if not p:
        raise HTTPException(status_code=404, detail="Grant proposal not found")
    return p


def _row(db: Session, proposal_id: int) -> ProposalPlan | None:
    return db.query(ProposalPlan).filter(ProposalPlan.proposal_id == proposal_id).first()


def load_plan(db: Session, proposal_id: int) -> planlib.Plan:
    row = _row(db, proposal_id)
    return planlib.Plan.model_validate(row.data) if row and row.data else planlib.Plan()


def _payload(db: Session, proposal: GrantProposal, plan: planlib.Plan) -> dict:
    return {
        "plan": plan.model_dump(),
        "analysis": planlib.analyze(plan, proposal.requested_amount or 0.0),
        "currency": proposal.currency,
        "templates": doc_templates.catalogue(),
        "locked": proposal.status != "draft",
    }


def _require_editable(proposal: GrantProposal) -> None:
    if proposal.status != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Proposal is {proposal.status} and locked; it can be edited again if changes are requested.",
        )


def _store(db: Session, proposal: GrantProposal, plan: planlib.Plan) -> None:
    row = _row(db, proposal.id)
    data = plan.model_dump()
    if row is None:
        db.add(ProposalPlan(proposal_id=proposal.id, data=data))
    else:
        row.data = data
        row.updated_at = datetime.now(UTC)
    db.flush()
    maybe_snapshot(db, proposal)


@router.get("")
def get_plan(proposal_id: int, db: Session = Depends(get_db)):
    proposal = _proposal(db, proposal_id)
    return _payload(db, proposal, load_plan(db, proposal_id))


@router.put("")
def save_plan(proposal_id: int, plan: planlib.Plan, db: Session = Depends(get_db)):
    proposal = _proposal(db, proposal_id)
    _require_editable(proposal)
    _store(db, proposal, plan)
    db.commit()
    return _payload(db, proposal, plan)


@router.post("/documents/{key}", status_code=201)
def add_document(proposal_id: int, key: str, db: Session = Depends(get_db)):
    proposal = _proposal(db, proposal_id)
    _require_editable(proposal)
    if key not in doc_templates.TEMPLATES:
        raise HTTPException(status_code=404, detail="Unknown document template")
    plan = load_plan(db, proposal_id)
    if any(d.key == key for d in plan.documents):
        raise HTTPException(status_code=409, detail="This document has already been added")
    plan.documents.append(planlib.Document.model_validate(doc_templates.instantiate(key)))
    _store(db, proposal, plan)
    db.commit()
    return _payload(db, proposal, plan)


@router.delete("/documents/{key}")
def remove_document(proposal_id: int, key: str, db: Session = Depends(get_db)):
    proposal = _proposal(db, proposal_id)
    _require_editable(proposal)
    plan = load_plan(db, proposal_id)
    plan.documents = [d for d in plan.documents if d.key != key]
    _store(db, proposal, plan)
    db.commit()
    return _payload(db, proposal, plan)


@router.post("/documents/{key}/assistant")
def document_assistant(
    proposal_id: int, key: str, payload: DocAssistIn, db: Session = Depends(get_db)
):
    proposal = _proposal(db, proposal_id)
    plan = load_plan(db, proposal_id)
    doc = next((d for d in plan.documents if d.key == key), None)
    sec = next((s for s in doc.sections if s.id == payload.section_id), None) if doc else None
    if not doc or not sec:
        raise HTTPException(status_code=404, detail="Document section not found")
    text = sec.text if payload.text is None else payload.text
    notice = db.get(OpportunityNotice, proposal.notice_id)
    hits = suggest(db, proposal, 0, q=f"{sec.title} {sec.prompt}", limit=3)
    material = [
        {"title": i["title"], "text": i["text"]}
        for i in hits["answers"] + hits["evidence"]
        if i["match"] >= 2
    ]
    req = ai.AssistantRequest(
        action=payload.action,
        section={
            "title": sec.title,
            "draft_text": text,
            "is_doc": True,
            "doc_title": doc.title,
            "max_score": 5,
        },
        guidance=sec.prompt,
        call_title=notice.title if notice else "",
        funder=notice.funder_or_buyer if notice else "",
        call_summary=(notice.ai_summary if notice else "")[:600],
        applicant=proposal.applicant_org,
        instruction=payload.instruction,
        material=material[:4],
    )
    try:
        return ai.run(req).as_dict()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"AI provider returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach the AI provider") from exc


@router.get("/export")
def export_plan(proposal_id: int, db: Session = Depends(get_db)):
    proposal = _proposal(db, proposal_id)
    plan = load_plan(db, proposal_id)
    analysis = planlib.analyze(plan, proposal.requested_amount or 0.0)
    return {
        "proposal_id": proposal.id,
        "title": proposal.title,
        "markdown": planlib.export_markdown(proposal.title, proposal.currency, plan, analysis),
    }
