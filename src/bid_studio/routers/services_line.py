from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import (
    AnswerLibraryItem,
    BidderAsset,
    CompliancePack,
    EmailDeliveryLog,
    EvidenceItem,
    MarketplaceReview,
    Order,
    QualityQueueItem,
    ReviewerProfile,
    TechDocProject,
)
from bid_studio.schemas import (
    BidderAssetCreate,
    CompliancePackCreate,
    MarketplaceReviewCreate,
    MarketplaceScoreSubmit,
    TechDocCreate,
    TechDocReviewInput,
)
from bid_studio.services.domain_logic import match_security_questionnaire

router = APIRouter(prefix="/api/v1", tags=["service-lines"])


# --- 1. Technical Documentation & API Docs ---
@router.get("/tech-docs")
def list_tech_docs(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(TechDocProject)
        .filter(TechDocProject.workspace_id == workspace_id)
        .order_by(TechDocProject.id.desc())
        .all()
    )


@router.post("/tech-docs", status_code=201)
def create_tech_doc_project(payload: TechDocCreate, db: Session = Depends(get_db)):
    doc = TechDocProject(
        workspace_id=payload.workspace_id,
        doc_type=payload.doc_type,
        title=payload.title,
        client_email=payload.client_email,
        fixed_fee=payload.fixed_fee,
        currency=payload.currency,
        pipeline_stage="drafting" if payload.draft_content else "intake",
        draft_content=payload.draft_content
        or f"# {payload.title}\n\nStructured {payload.doc_type.replace('_', ' ')} draft ready for staff pipeline.",
    )
    db.add(doc)
    db.flush()

    order = Order(
        workspace_id=payload.workspace_id,
        customer_email=payload.client_email,
        service_type=f"tech_doc_{payload.doc_type}",
        source="direct",
        amount=payload.fixed_fee,
        currency=payload.currency,
        status="paid",
        metadata_json={"tech_doc_id": doc.id},
    )
    db.add(order)
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/tech-docs/{doc_id}/submit-quality")
def submit_tech_doc_quality(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(TechDocProject, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Technical doc project not found")
    doc.pipeline_stage = "quality_review"
    queue_item = QualityQueueItem(
        workspace_id=doc.workspace_id,
        item_type="tech_doc",
        reference_id=doc.id,
        title=doc.title,
        status="queued",
        review_notes=f"Fixed-fee {doc.doc_type} documentation awaiting QA.",
    )
    db.add(queue_item)
    db.commit()
    db.refresh(doc)
    return {"doc_id": doc.id, "pipeline_stage": doc.pipeline_stage, "quality_queue_id": queue_item.id}


@router.post("/tech-docs/{doc_id}/review")
def review_tech_doc(doc_id: int, payload: TechDocReviewInput, db: Session = Depends(get_db)):
    doc = db.get(TechDocProject, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Technical doc project not found")
    if payload.draft_content is not None:
        doc.draft_content = payload.draft_content
    doc.reviewer_notes = payload.reviewer_notes
    doc.quality_approved = payload.approved
    doc.pipeline_stage = "approved" if payload.approved else "drafting"
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/tech-docs/{doc_id}/deliver")
def deliver_tech_doc(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(TechDocProject, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Technical doc project not found")
    if not doc.quality_approved:
        raise HTTPException(
            status_code=400,
            detail="Technical doc must pass the quality review stage before email delivery.",
        )
    now = datetime.now(UTC)
    doc.pipeline_stage = "delivered"
    doc.delivered_at = now
    log = EmailDeliveryLog(
        workspace_id=doc.workspace_id,
        recipient_email=doc.client_email,
        subject=f"[Bid Studio Delivery] {doc.title}",
        delivery_type="tech_doc_delivery",
        reference_id=doc.id,
        body_preview=doc.draft_content[:300],
        status="sent",
        sent_at=now,
    )
    db.add(log)
    db.commit()
    db.refresh(doc)
    return {"doc_id": doc.id, "pipeline_stage": doc.pipeline_stage, "delivery_log_id": log.id}


# --- 2. Compliance & Policy Writing ---
@router.get("/compliance/packs")
def list_compliance_packs(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(CompliancePack)
        .filter(CompliancePack.workspace_id == workspace_id)
        .order_by(CompliancePack.id.desc())
        .all()
    )


@router.post("/compliance/packs", status_code=201)
def create_compliance_pack(payload: CompliancePackCreate, db: Session = Depends(get_db)):
    default_sections = payload.policy_sections or [
        {"section": "Scope & Governance", "content": f"Applies to {payload.standard_ref} controls."},
        {"section": "Operational Controls", "content": "Access control, encryption, incident SLA, and audit."},
    ]
    q_items = [
        {
            "id": f"SQ-{idx}",
            "question": q,
            "matched_answer_id": None,
            "matched_answer_text": "",
            "confidence": 0.0,
            "status": "pending",
        }
        for idx, q in enumerate(payload.questions, start=1)
    ]
    pack = CompliancePack(
        workspace_id=payload.workspace_id,
        pack_type=payload.pack_type,
        title=payload.title,
        standard_ref=payload.standard_ref,
        status="draft",
        policy_sections=default_sections,
        questionnaire_items=q_items,
    )
    db.add(pack)
    db.commit()
    db.refresh(pack)
    return pack


@router.post("/compliance/packs/{pack_id}/auto-match")
def auto_match_compliance_pack(pack_id: int, db: Session = Depends(get_db)):
    pack = db.get(CompliancePack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Compliance pack not found")

    library = (
        db.query(AnswerLibraryItem)
        .filter(AnswerLibraryItem.workspace_id == pack.workspace_id)
        .all()
    )
    matched_items = match_security_questionnaire(pack.questionnaire_items, library)
    pack.questionnaire_items = matched_items
    matched_count = sum(1 for item in matched_items if item["status"] == "matched")
    pack.status = "matched" if matched_count > 0 else "draft"
    db.commit()
    db.refresh(pack)
    return {
        "pack_id": pack.id,
        "matched_count": matched_count,
        "total_questions": len(matched_items),
        "questionnaire_items": matched_items,
    }


# --- 3. CV, Capability Statement & Case Study Writing ---
@router.get("/bidder-assets")
def list_bidder_assets(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(BidderAsset)
        .filter(BidderAsset.workspace_id == workspace_id)
        .order_by(BidderAsset.id.desc())
        .all()
    )


@router.post("/bidder-assets", status_code=201)
def create_bidder_asset(payload: BidderAssetCreate, db: Session = Depends(get_db)):
    asset = BidderAsset(**payload.model_dump(), status="ready")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/bidder-assets/{asset_id}/promote-to-evidence")
def promote_asset_to_evidence(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(BidderAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Bidder asset not found")

    if asset.promoted_evidence_id:
        existing = db.get(EvidenceItem, asset.promoted_evidence_id)
        if existing:
            return {"asset_id": asset.id, "evidence_id": existing.id, "already_promoted": True}

    evidence = EvidenceItem(
        workspace_id=asset.workspace_id,
        evidence_type=asset.asset_type,
        title=f"{asset.title} ({asset.subject_name})",
        summary=asset.content,
        buyer_format=asset.buyer_format,
        metrics=asset.metrics,
        source_asset_id=asset.id,
    )
    db.add(evidence)
    db.flush()
    asset.promoted_evidence_id = evidence.id
    asset.status = "promoted"
    db.commit()
    db.refresh(asset)
    return {"asset_id": asset.id, "evidence_id": evidence.id, "status": asset.status}


# --- 4. Bid Review Marketplace ---
@router.get("/marketplace/reviewers")
def list_reviewers(db: Session = Depends(get_db)):
    return db.query(ReviewerProfile).order_by(ReviewerProfile.rating.desc()).all()


@router.get("/marketplace/reviews")
def list_marketplace_reviews(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(MarketplaceReview)
        .filter(MarketplaceReview.workspace_id == workspace_id)
        .order_by(MarketplaceReview.id.desc())
        .all()
    )


@router.post("/marketplace/reviews", status_code=201)
def request_marketplace_review(payload: MarketplaceReviewCreate, db: Session = Depends(get_db)):
    reviewer = db.get(ReviewerProfile, payload.reviewer_id)
    if not reviewer:
        raise HTTPException(status_code=404, detail="Reviewer profile not found")

    queue_id = payload.quality_queue_id
    if queue_id is None:
        q_item = QualityQueueItem(
            workspace_id=payload.workspace_id,
            item_type="marketplace_review",
            reference_id=0,
            title=payload.target_title,
            assigned_reviewer=reviewer.full_name,
            status="in_review",
        )
        db.add(q_item)
        db.flush()
        queue_id = q_item.id

    review = MarketplaceReview(
        workspace_id=payload.workspace_id,
        reviewer_id=reviewer.id,
        quality_queue_id=queue_id,
        target_title=payload.target_title,
        buyer_criteria=payload.buyer_criteria,
        draft_excerpt=payload.draft_excerpt,
        status="requested",
        fee=reviewer.flat_fee,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.post("/marketplace/reviews/{review_id}/score")
def submit_marketplace_score(
    review_id: int,
    payload: MarketplaceScoreSubmit,
    db: Session = Depends(get_db),
):
    review = db.get(MarketplaceReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Marketplace review not found")

    scores = payload.criterion_scores
    total_weight = sum(float(c.get("weight", 1.0)) for c in scores) or 1.0
    weighted = 0.0
    for c in scores:
        weight = float(c.get("weight", 1.0))
        max_s = float(c.get("max_score", 100.0)) or 100.0
        s = float(c.get("score", 0.0))
        weighted += (max(0.0, min(1.0, s / max_s))) * weight
    overall = round((weighted / total_weight) * 100.0, 2)

    review.criterion_scores = scores
    review.overall_score = overall
    review.feedback_summary = payload.feedback_summary
    review.status = "completed"

    if review.quality_queue_id:
        q_item = db.get(QualityQueueItem, review.quality_queue_id)
        if q_item:
            q_item.review_score = overall
            q_item.review_notes = payload.feedback_summary
            q_item.status = "approved" if overall >= 70.0 else "changes_requested"
            q_item.updated_at = datetime.now(UTC)

    db.commit()
    db.refresh(review)
    return review
