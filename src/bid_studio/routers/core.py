from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import (
    AnswerLibraryItem,
    BidOutcome,
    EmailDeliveryLog,
    EvidenceItem,
    GrantProposal,
    OpportunityNotice,
    Order,
    QualityQueueItem,
    TechDocProject,
    Workspace,
    WorkspaceMember,
)
from bid_studio.schemas import (
    AnswerLibraryCreate,
    EvidenceCreate,
    NoticeCreate,
    NoticeRead,
    QualityReviewAction,
    WhiteLabelUpdate,
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceRead,
)
from bid_studio.services.domain_logic import summarize_notice

router = APIRouter(prefix="/api/v1", tags=["core"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "bid-studio"}


# --- Workspaces, White-Label & Access Review ---
@router.get("/workspaces", response_model=list[WorkspaceRead])
def list_workspaces(db: Session = Depends(get_db)):
    return db.query(Workspace).order_by(Workspace.id).all()


@router.post("/workspaces", response_model=WorkspaceRead, status_code=201)
def create_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db)):
    if db.query(Workspace).filter(Workspace.slug == payload.slug).first():
        raise HTTPException(status_code=409, detail="Workspace slug already exists")
    ws = Workspace(**payload.model_dump())
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@router.put("/workspaces/{workspace_id}/white-label", response_model=WorkspaceRead)
def update_white_label(
    workspace_id: int,
    payload: WhiteLabelUpdate,
    db: Session = Depends(get_db),
):
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    for k, v in payload.model_dump().items():
        setattr(ws, k, v)
    db.commit()
    db.refresh(ws)
    return ws


@router.post("/workspaces/{workspace_id}/members", status_code=201)
def add_workspace_member(
    workspace_id: int,
    payload: WorkspaceMemberCreate,
    db: Session = Depends(get_db),
):
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    existing = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.email == payload.email,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Member email already exists in workspace")
    member = WorkspaceMember(workspace_id=workspace_id, **payload.model_dump())
    db.add(member)
    db.commit()
    db.refresh(member)
    return {
        "id": member.id,
        "workspace_id": member.workspace_id,
        "email": member.email,
        "full_name": member.full_name,
        "role": member.role,
        "status": member.status,
    }


@router.get("/workspaces/{workspace_id}/summary")
def get_workspace_summary(workspace_id: int, db: Session = Depends(get_db)):
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    proposals = db.query(GrantProposal).filter(GrantProposal.workspace_id == workspace_id).all()
    orders = db.query(Order).filter(Order.workspace_id == workspace_id).all()
    outcomes = db.query(BidOutcome).filter(BidOutcome.workspace_id == workspace_id).all()
    pending_qa = (
        db.query(QualityQueueItem)
        .filter(
            QualityQueueItem.workspace_id == workspace_id,
            QualityQueueItem.status.in_(["queued", "in_review"]),
        )
        .count()
    )
    decided = [o for o in outcomes if o.outcome in ("won", "lost")]
    won_count = sum(1 for o in decided if o.outcome == "won")
    win_rate_pct = round((won_count / len(decided)) * 100.0, 1) if decided else 0.0

    return {
        "workspace_id": ws.id,
        "brand_name": ws.brand_name,
        "grant_proposals_count": len(proposals),
        "requested_grant_total": round(sum(p.requested_amount for p in proposals), 2),
        "orders_count": len(orders),
        "total_order_revenue": round(sum(o.amount for o in orders), 2),
        "training_enrolment_orders": sum(1 for o in orders if o.source == "training_enrolment"),
        "pending_qa_count": pending_qa,
        "win_rate_pct": win_rate_pct,
    }


@router.get("/workspaces/{workspace_id}/access-review")
def run_access_review(workspace_id: int, db: Session = Depends(get_db)):
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    members = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .all()
    )
    now = datetime.now(UTC)
    for m in members:
        m.last_access_review_at = now
    db.commit()
    return {
        "workspace_id": ws.id,
        "workspace_slug": ws.slug,
        "brand_name": ws.brand_name,
        "is_white_label": ws.is_white_label,
        "client_isolation_enforced": ws.client_isolation_enforced,
        "reviewed_at": now.isoformat(),
        "member_count": len(members),
        "members": [
            {
                "id": m.id,
                "email": m.email,
                "full_name": m.full_name,
                "role": m.role,
                "status": m.status,
            }
            for m in members
        ],
    }


# --- Opportunity Feed ---
@router.get("/notices", response_model=list[NoticeRead])
def list_notices(
    workspace_id: int | None = Query(default=None),
    notice_type: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(OpportunityNotice)
    if workspace_id is not None:
        query = query.filter(
            or_(
                OpportunityNotice.workspace_id.is_(None),
                OpportunityNotice.workspace_id == workspace_id,
            )
        )
    if notice_type:
        query = query.filter(OpportunityNotice.notice_type == notice_type)
    if sector:
        query = query.filter(OpportunityNotice.sector == sector)
    if status:
        query = query.filter(OpportunityNotice.status == status)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                OpportunityNotice.title.ilike(pattern),
                OpportunityNotice.funder_or_buyer.ilike(pattern),
                OpportunityNotice.raw_pack_text.ilike(pattern),
            )
        )
    return (
        query.order_by(OpportunityNotice.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.post("/notices", response_model=NoticeRead, status_code=201)
def create_notice(payload: NoticeCreate, db: Session = Depends(get_db)):
    summary = summarize_notice(
        payload.title,
        payload.raw_pack_text,
        payload.funder_or_buyer,
        payload.contract_value,
        payload.currency,
        payload.deadline,
    )
    notice = OpportunityNotice(**payload.model_dump(), ai_summary=summary)
    db.add(notice)
    db.commit()
    db.refresh(notice)
    return notice


# --- Answer & Evidence Libraries ---
@router.get("/answer-library")
def list_answer_library(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(AnswerLibraryItem)
        .filter(AnswerLibraryItem.workspace_id == workspace_id)
        .order_by(AnswerLibraryItem.id.desc())
        .all()
    )


@router.post("/answer-library", status_code=201)
def create_answer_library_item(payload: AnswerLibraryCreate, db: Session = Depends(get_db)):
    item = AnswerLibraryItem(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/evidence-library")
def list_evidence_library(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(EvidenceItem)
        .filter(EvidenceItem.workspace_id == workspace_id)
        .order_by(EvidenceItem.id.desc())
        .all()
    )


@router.post("/evidence-library", status_code=201)
def create_evidence_item(payload: EvidenceCreate, db: Session = Depends(get_db)):
    item = EvidenceItem(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


# --- Quality Queue, Orders & Delivery Log ---
@router.get("/quality-queue")
def list_quality_queue(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(QualityQueueItem)
        .filter(QualityQueueItem.workspace_id == workspace_id)
        .order_by(QualityQueueItem.id.desc())
        .all()
    )


@router.post("/quality-queue/{item_id}/review")
def review_quality_queue_item(
    item_id: int,
    payload: QualityReviewAction,
    db: Session = Depends(get_db),
):
    item = db.get(QualityQueueItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Quality queue item not found")
    item.assigned_reviewer = payload.assigned_reviewer
    item.status = payload.status
    item.review_score = payload.review_score
    item.review_notes = payload.review_notes
    item.updated_at = datetime.now(UTC)

    if item.item_type == "grant_proposal" and item.reference_id:
        proposal = db.get(GrantProposal, item.reference_id)
        if proposal:
            if payload.status == "approved":
                proposal.status = "approved"
            elif payload.status == "changes_requested":
                proposal.status = "draft"
    elif item.item_type == "tech_doc" and item.reference_id:
        doc = db.get(TechDocProject, item.reference_id)
        if doc:
            if payload.status == "approved":
                doc.quality_approved = True
                doc.pipeline_stage = "approved"
                doc.reviewer_notes = payload.review_notes
            elif payload.status == "changes_requested":
                doc.quality_approved = False
                doc.pipeline_stage = "drafting"
                doc.reviewer_notes = payload.review_notes

    db.commit()
    db.refresh(item)
    return item


@router.get("/orders")
def list_orders(workspace_id: int = 1, source: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Order).filter(Order.workspace_id == workspace_id)
    if source:
        q = q.filter(Order.source == source)
    return q.order_by(Order.id.desc()).all()


@router.get("/deliveries")
def list_email_deliveries(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(EmailDeliveryLog)
        .filter(EmailDeliveryLog.workspace_id == workspace_id)
        .order_by(EmailDeliveryLog.id.desc())
        .all()
    )
