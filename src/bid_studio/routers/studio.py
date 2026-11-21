from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import (
    FeedItemLink,
    GrantProposal,
    OpportunityNotice,
    ProposalVersion,
    Workspace,
)
from bid_studio.schemas import AssistantRequestIn, StudioSave, VersionCreate
from bid_studio.services import assistant as ai
from bid_studio.services.access import proposal_guard
from bid_studio.services.feed_sources import parse_iso
from bid_studio.services.pipeline import queue_for_review
from bid_studio.services.studio import (
    AUTOSNAPSHOT_MINUTES,
    enrich_sections,
    readiness,
    rescore,
    snapshot_of,
    suggest,
    take_snapshot,
    word_count,
)

router = APIRouter(
    prefix="/api/v1/grants/proposals/{proposal_id}",
    tags=["grant-studio"],
    dependencies=[Depends(proposal_guard)],
)

EDITABLE_STATUSES = {"draft"}
MIN_MATERIAL_MATCH = 2


def _get(db: Session, proposal_id: int) -> GrantProposal:
    proposal = db.get(GrantProposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Grant proposal not found")
    return proposal


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _payload(db: Session, proposal: GrantProposal) -> dict:
    today = datetime.now(UTC).date()
    notice = db.get(OpportunityNotice, proposal.notice_id)
    deadline = parse_iso(notice.deadline) if notice else None
    link = (
        db.query(FeedItemLink).filter(FeedItemLink.notice_id == proposal.notice_id).first()
        if notice
        else None
    )
    ws = db.get(Workspace, proposal.workspace_id)
    versions = db.query(ProposalVersion).filter(ProposalVersion.proposal_id == proposal.id).count()
    return {
        "proposal": {
            "id": proposal.id,
            "workspace_id": proposal.workspace_id,
            "title": proposal.title,
            "applicant_org": proposal.applicant_org,
            "requested_amount": proposal.requested_amount,
            "currency": proposal.currency,
            "status": proposal.status,
            "funder_type": proposal.funder_type,
            "total_weighted_score": proposal.total_weighted_score,
        },
        "sections": enrich_sections(proposal.sections or []),
        "criteria": proposal.extracted_criteria or [],
        "call": {
            "notice_id": proposal.notice_id,
            "title": notice.title if notice else "",
            "funder": notice.funder_or_buyer if notice else "",
            "deadline": (notice.deadline or None) if notice else None,
            "days_left": (deadline - today).days if deadline else None,
            "summary": notice.ai_summary if notice else "",
            "url": link.url if link and link.url else None,
        },
        "readiness": readiness(proposal, deadline, today),
        "versions_count": versions,
        "locked": proposal.status not in EDITABLE_STATUSES,
        "branding": {
            "brand_name": ws.brand_name if ws else "Bid Studio",
            "primary_color": ws.primary_color if ws else "#0f172a",
            "accent_color": ws.accent_color if ws else "#2563eb",
        },
    }


@router.get("/studio")
def get_studio(proposal_id: int, db: Session = Depends(get_db)):
    return _payload(db, _get(db, proposal_id))


@router.put("/studio/save")
def save_studio(proposal_id: int, payload: StudioSave, db: Session = Depends(get_db)):
    """Save sections (and optionally proposal details); snapshots a version when due."""
    proposal = _get(db, proposal_id)
    if proposal.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Proposal is {proposal.status} and locked; it can be edited again if changes are requested.",
        )
    if len(payload.sections) != len(proposal.sections or []):
        raise HTTPException(status_code=422, detail="Sections cannot be added or removed here")

    sections = [s.model_dump() for s in payload.sections]
    changed = sections != (proposal.sections or [])
    if payload.meta:
        for field, value in payload.meta.model_dump(exclude_none=True).items():
            if getattr(proposal, field) != value:
                changed = True
            setattr(proposal, field, value)
    proposal.sections = sections
    proposal.total_weighted_score = rescore(sections)

    version_created = None
    last = (
        db.query(ProposalVersion)
        .filter(ProposalVersion.proposal_id == proposal.id)
        .order_by(ProposalVersion.version_no.desc())
        .first()
    )
    due = (
        last is None
        or bool(payload.label)
        or (
            changed
            and snapshot_of(proposal) != last.snapshot
            and datetime.now(UTC) - _aware(last.created_at) >= timedelta(minutes=AUTOSNAPSHOT_MINUTES)
        )
    )
    if due:
        version_created = take_snapshot(db, proposal, payload.label).version_no
    db.commit()
    db.refresh(proposal)
    return {**_payload(db, proposal), "version_created": version_created}


@router.get("/studio/suggestions")
def get_suggestions(
    proposal_id: int,
    section: int = Query(default=0, ge=0),
    q: str = "",
    db: Session = Depends(get_db),
):
    return suggest(db, _get(db, proposal_id), section, q)


@router.post("/studio/submit")
def submit_from_studio(proposal_id: int, db: Session = Depends(get_db)):
    proposal = _get(db, proposal_id)
    if proposal.status != "draft":
        raise HTTPException(status_code=409, detail=f"Proposal is already {proposal.status}")
    payload = _payload(db, proposal)
    failing = [c for c in payload["readiness"]["checks"] if c["severity"] == "blocker" and not c["ok"]]
    if failing:
        raise HTTPException(
            status_code=422,
            detail={"message": "Proposal is not ready to submit", "failing": failing},
        )
    take_snapshot(db, proposal, "Submitted for review")
    item = queue_for_review(db, proposal)
    db.commit()
    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "quality_queue_id": item.id,
        "total_weighted_score": proposal.total_weighted_score,
    }


@router.get("/versions")
def list_versions(proposal_id: int, db: Session = Depends(get_db)):
    _get(db, proposal_id)
    rows = (
        db.query(ProposalVersion)
        .filter(ProposalVersion.proposal_id == proposal_id)
        .order_by(ProposalVersion.version_no.desc())
        .all()
    )
    return [
        {
            "version_no": v.version_no,
            "label": v.label,
            "created_at": v.created_at,
            "score": v.snapshot.get("score"),
            "word_count": sum(word_count(s.get("draft_text", "")) for s in v.snapshot.get("sections", [])),
        }
        for v in rows
    ]


@router.get("/versions/{version_no}")
def get_version(proposal_id: int, version_no: int, db: Session = Depends(get_db)):
    v = (
        db.query(ProposalVersion)
        .filter(ProposalVersion.proposal_id == proposal_id, ProposalVersion.version_no == version_no)
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    return {
        "version_no": v.version_no,
        "label": v.label,
        "created_at": v.created_at,
        "snapshot": v.snapshot,
    }


@router.post("/versions", status_code=201)
def create_version(proposal_id: int, payload: VersionCreate, db: Session = Depends(get_db)):
    proposal = _get(db, proposal_id)
    v = take_snapshot(db, proposal, payload.label or "Manual snapshot")
    db.commit()
    return {"version_no": v.version_no, "label": v.label}


@router.post("/versions/{version_no}/restore")
def restore_version(proposal_id: int, version_no: int, db: Session = Depends(get_db)):
    proposal = _get(db, proposal_id)
    if proposal.status not in EDITABLE_STATUSES:
        raise HTTPException(status_code=409, detail=f"Proposal is {proposal.status} and locked")
    v = (
        db.query(ProposalVersion)
        .filter(ProposalVersion.proposal_id == proposal_id, ProposalVersion.version_no == version_no)
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    take_snapshot(db, proposal, f"Before restoring v{version_no}")
    snap = v.snapshot
    proposal.title = snap.get("title", proposal.title)
    proposal.applicant_org = snap.get("applicant_org", proposal.applicant_org)
    proposal.requested_amount = snap.get("requested_amount", proposal.requested_amount)
    proposal.currency = snap.get("currency", proposal.currency)
    proposal.sections = snap.get("sections", proposal.sections)
    proposal.total_weighted_score = rescore(proposal.sections)
    db.commit()
    db.refresh(proposal)
    return _payload(db, proposal)


@router.get("/assistant/status")
def assistant_status(proposal_id: int, db: Session = Depends(get_db)):
    _get(db, proposal_id)
    return ai.provider_status()


@router.post("/assistant")
def run_assistant(proposal_id: int, payload: AssistantRequestIn, db: Session = Depends(get_db)):
    proposal = _get(db, proposal_id)
    secs = proposal.sections or []
    if payload.section_index >= len(secs):
        raise HTTPException(status_code=422, detail="Section not found")
    section = dict(secs[payload.section_index])
    if payload.text is not None:  # use what is on screen, which may not be saved yet
        section["draft_text"] = payload.text
    if payload.word_limit:
        section["word_limit"] = payload.word_limit

    guidance = ""
    for c in proposal.extracted_criteria or []:
        if c.get("criterion_id") == section.get("criterion_id"):
            guidance = c.get("guidance", "")
    notice = db.get(OpportunityNotice, proposal.notice_id)
    sugg = suggest(db, proposal, payload.section_index, limit=3)
    # Only strong matches (2+ shared terms) are offered as material; one shared word is noise.
    material = [
        {"title": i["title"], "text": i["text"]}
        for i in sugg["answers"] + sugg["evidence"]
        if i["match"] >= MIN_MATERIAL_MATCH
    ]
    req = ai.AssistantRequest(
        action=payload.action,
        section=section,
        guidance=guidance,
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
