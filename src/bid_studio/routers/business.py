"""Business Documents and Legal Contracts.

Business documents reuse the technical-document pipeline (fixed fee, QA gate, delivery).

Legal contracts are different by design: Bid Studio never drafts them. A matter records the
client's instructions, a lawyer is assigned, the lawyer writes the contract, and only a lawyer's
recorded sign-off allows export or delivery. Any edit after sign-off voids the sign-off.
Nothing here is exposed to AI clients (see mcp_server.py).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import (
    EmailDeliveryLog,
    LegalContractMatter,
    Order,
    QualityQueueItem,
    TechDocProject,
)
from bid_studio.schemas import (
    BusinessDocCreate,
    LegalAssignLawyer,
    LegalDraftUpdate,
    LegalMatterCreate,
    LegalSignOff,
    TechDocReviewInput,
)
from bid_studio.services.domain_logic import BUSINESS_DOC_LABELS, business_doc_starter

router = APIRouter(prefix="/api/v1", tags=["business-and-legal"])

LEGAL_NOTICE = (
    "Bid Studio does not draft legal contracts and this is not legal advice. Every contract is "
    "written or approved by a qualified lawyer and cannot be exported or delivered without a "
    "recorded lawyer sign-off."
)


# ------------------------------------------------------------------ business documents


def _business_doc(db: Session, doc_id: int) -> TechDocProject:
    doc = db.get(TechDocProject, doc_id)
    if not doc or doc.doc_type not in BUSINESS_DOC_LABELS:
        raise HTTPException(status_code=404, detail="Business document not found")
    return doc


@router.get("/business-docs")
def list_business_docs(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(TechDocProject)
        .filter(
            TechDocProject.workspace_id == workspace_id,
            TechDocProject.doc_type.in_(list(BUSINESS_DOC_LABELS)),
        )
        .order_by(TechDocProject.id.desc())
        .all()
    )


@router.post("/business-docs", status_code=201)
def create_business_doc(payload: BusinessDocCreate, db: Session = Depends(get_db)):
    doc = TechDocProject(
        workspace_id=payload.workspace_id,
        doc_type=payload.doc_type,
        title=payload.title,
        client_email=payload.client_email,
        fixed_fee=payload.fixed_fee,
        currency=payload.currency,
        pipeline_stage="drafting" if payload.draft_content else "intake",
        draft_content=payload.draft_content or business_doc_starter(payload.doc_type, payload.title),
    )
    db.add(doc)
    db.flush()
    db.add(
        Order(
            workspace_id=payload.workspace_id,
            customer_email=payload.client_email,
            service_type=f"business_doc_{payload.doc_type}",
            source="direct",
            amount=payload.fixed_fee,
            currency=payload.currency,
            status="paid",
            metadata_json={"business_doc_id": doc.id},
        )
    )
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/business-docs/{doc_id}/submit-quality")
def submit_business_doc_quality(doc_id: int, db: Session = Depends(get_db)):
    doc = _business_doc(db, doc_id)
    if doc.pipeline_stage == "quality_review":
        raise HTTPException(status_code=409, detail="Business document is already in quality review")
    doc.pipeline_stage = "quality_review"
    item = QualityQueueItem(
        workspace_id=doc.workspace_id,
        item_type="business_doc",
        reference_id=doc.id,
        title=doc.title,
        status="queued",
        review_notes=f"Fixed-fee {doc.doc_type} awaiting QA.",
    )
    db.add(item)
    db.commit()
    db.refresh(doc)
    return {"doc_id": doc.id, "pipeline_stage": doc.pipeline_stage, "quality_queue_id": item.id}


@router.post("/business-docs/{doc_id}/review")
def review_business_doc(doc_id: int, payload: TechDocReviewInput, db: Session = Depends(get_db)):
    doc = _business_doc(db, doc_id)
    if payload.draft_content is not None:
        doc.draft_content = payload.draft_content
    doc.reviewer_notes = payload.reviewer_notes
    doc.quality_approved = payload.approved
    doc.pipeline_stage = "approved" if payload.approved else "drafting"
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/business-docs/{doc_id}/deliver")
def deliver_business_doc(doc_id: int, db: Session = Depends(get_db)):
    doc = _business_doc(db, doc_id)
    if not doc.quality_approved:
        raise HTTPException(
            status_code=400,
            detail="Business document must pass the quality review stage before email delivery.",
        )
    now = datetime.now(UTC)
    doc.pipeline_stage = "delivered"
    doc.delivered_at = now
    log = EmailDeliveryLog(
        workspace_id=doc.workspace_id,
        recipient_email=doc.client_email,
        subject=f"[Bid Studio Delivery] {doc.title}",
        delivery_type="business_doc_delivery",
        reference_id=doc.id,
        body_preview=doc.draft_content[:300],
        status="sent",
        sent_at=now,
    )
    db.add(log)
    db.commit()
    db.refresh(doc)
    return {"doc_id": doc.id, "pipeline_stage": doc.pipeline_stage, "delivery_log_id": log.id}


@router.get("/business-docs/{doc_id}/export")
def export_business_doc_markdown(doc_id: int, db: Session = Depends(get_db)):
    doc = _business_doc(db, doc_id)
    md = (
        f"# {doc.title}\n"
        f"- **Document Type:** {BUSINESS_DOC_LABELS[doc.doc_type]}\n"
        f"- **Fixed Fee:** {doc.currency} {doc.fixed_fee:,.2f}\n"
        f"- **Pipeline Stage:** {doc.pipeline_stage}\n"
        f"- **Quality Approved:** {'Yes' if doc.quality_approved else 'No'}\n\n"
        f"{doc.draft_content}\n"
    )
    return {"doc_id": doc.id, "markdown": md}


# ------------------------------------------------------------------- legal contracts


def _matter(db: Session, matter_id: int) -> LegalContractMatter:
    matter = db.get(LegalContractMatter, matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="Legal contract matter not found")
    return matter


def _require_assigned_lawyer(matter: LegalContractMatter, lawyer_name: str) -> None:
    if not matter.assigned_lawyer_name:
        raise HTTPException(status_code=409, detail="Assign a lawyer to this matter first.")
    if lawyer_name.strip().casefold() != matter.assigned_lawyer_name.strip().casefold():
        raise HTTPException(
            status_code=403,
            detail="Only the lawyer assigned to this matter can change or sign it off.",
        )


@router.get("/legal-contracts")
def list_legal_matters(workspace_id: int = 1, db: Session = Depends(get_db)):
    return {
        "notice": LEGAL_NOTICE,
        "items": (
            db.query(LegalContractMatter)
            .filter(LegalContractMatter.workspace_id == workspace_id)
            .order_by(LegalContractMatter.id.desc())
            .all()
        ),
    }


@router.post("/legal-contracts", status_code=201)
def create_legal_matter(payload: LegalMatterCreate, db: Session = Depends(get_db)):
    """Opens a matter with the client's instructions only. No contract text is generated."""
    matter = LegalContractMatter(**payload.model_dump(), status="intake", draft_content="")
    db.add(matter)
    db.commit()
    db.refresh(matter)
    return matter


@router.post("/legal-contracts/{matter_id}/assign-lawyer")
def assign_lawyer(matter_id: int, payload: LegalAssignLawyer, db: Session = Depends(get_db)):
    """Records the lawyer and their registration reference. The reference is recorded as
    given; this API cannot verify it, so staff must check credentials before assigning."""
    matter = _matter(db, matter_id)
    if matter.status in {"lawyer_signed_off", "delivered"}:
        raise HTTPException(status_code=409, detail="Matter is already signed off.")
    matter.assigned_lawyer_name = payload.lawyer_name.strip()
    matter.assigned_lawyer_ref = payload.registration_ref.strip()
    matter.status = "lawyer_assigned" if not matter.draft_content else "in_progress"
    db.commit()
    db.refresh(matter)
    return matter


@router.put("/legal-contracts/{matter_id}/draft")
def save_lawyer_draft(matter_id: int, payload: LegalDraftUpdate, db: Session = Depends(get_db)):
    matter = _matter(db, matter_id)
    _require_assigned_lawyer(matter, payload.lawyer_name)
    if matter.status == "delivered":
        raise HTTPException(status_code=409, detail="A delivered contract cannot be edited.")
    matter.draft_content = payload.draft_content
    # Any change voids an earlier sign-off: the signed text must be exactly what ships.
    matter.status = "in_progress"
    matter.signed_off_by = ""
    matter.signoff_notes = ""
    matter.signed_off_at = None
    db.commit()
    db.refresh(matter)
    return matter


@router.post("/legal-contracts/{matter_id}/sign-off")
def lawyer_sign_off(matter_id: int, payload: LegalSignOff, db: Session = Depends(get_db)):
    matter = _matter(db, matter_id)
    _require_assigned_lawyer(matter, payload.lawyer_name)
    if not payload.confirm_qualified_and_reviewed:
        raise HTTPException(
            status_code=400,
            detail="The lawyer must confirm they are qualified for this jurisdiction and have "
            "reviewed the contract.",
        )
    if not matter.draft_content.strip():
        raise HTTPException(status_code=409, detail="There is no contract text to sign off.")
    matter.status = "lawyer_signed_off"
    matter.signed_off_by = matter.assigned_lawyer_name
    matter.signoff_notes = payload.notes
    matter.signed_off_at = datetime.now(UTC)
    db.commit()
    db.refresh(matter)
    return matter


@router.post("/legal-contracts/{matter_id}/deliver")
def deliver_legal_contract(matter_id: int, db: Session = Depends(get_db)):
    matter = _matter(db, matter_id)
    if matter.status != "lawyer_signed_off" or not matter.signed_off_at:
        raise HTTPException(
            status_code=400,
            detail="A legal contract can only be delivered after a lawyer has signed it off.",
        )
    now = datetime.now(UTC)
    matter.status = "delivered"
    matter.delivered_at = now
    log = EmailDeliveryLog(
        workspace_id=matter.workspace_id,
        recipient_email=matter.client_email,
        subject=f"[Bid Studio Delivery] {matter.title}",
        delivery_type="legal_contract_delivery",
        reference_id=matter.id,
        body_preview=f"Signed off by {matter.signed_off_by}. {matter.draft_content[:240]}",
        status="sent",
        sent_at=now,
    )
    db.add(log)
    db.commit()
    db.refresh(matter)
    return {"matter_id": matter.id, "status": matter.status, "delivery_log_id": log.id}


@router.get("/legal-contracts/{matter_id}/export")
def export_legal_contract(matter_id: int, db: Session = Depends(get_db)):
    matter = _matter(db, matter_id)
    if matter.status not in {"lawyer_signed_off", "delivered"} or not matter.signed_off_at:
        raise HTTPException(
            status_code=409,
            detail="Only a lawyer-signed-off contract can be exported.",
        )
    md = (
        f"# {matter.title}\n"
        f"- **Contract Type:** {matter.contract_type.replace('_', ' ')}\n"
        f"- **Jurisdiction:** {matter.jurisdiction}\n"
        f"- **Signed off by:** {matter.signed_off_by} "
        f"(registration ref: {matter.assigned_lawyer_ref})\n"
        f"- **Signed off at:** {matter.signed_off_at.isoformat()}\n\n"
        f"> {LEGAL_NOTICE}\n\n"
        f"{matter.draft_content}\n"
    )
    return {"matter_id": matter.id, "markdown": md}
