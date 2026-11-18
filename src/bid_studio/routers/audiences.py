from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import (
    BuyerTenderDraft,
    Order,
    TrainingCohort,
    TrainingEnrolment,
    Workspace,
)
from bid_studio.schemas import (
    BuyerTenderDraftCreate,
    TrainingEnrolmentCreate,
    TrainingModuleComplete,
)
from bid_studio.services.domain_logic import validate_public_sector_draft

router = APIRouter(prefix="/api/v1", tags=["new-audiences"])


# --- 12. Training & Workshops (Riverbend Pack & training_enrolment Orders) ---
@router.get("/training/cohorts")
def list_training_cohorts(db: Session = Depends(get_db)):
    return db.query(TrainingCohort).order_by(TrainingCohort.id).all()


@router.get("/training/enrolments")
def list_training_enrolments(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(TrainingEnrolment)
        .filter(TrainingEnrolment.workspace_id == workspace_id)
        .order_by(TrainingEnrolment.id.desc())
        .all()
    )


@router.post("/training/cohorts/{cohort_id}/enrol", status_code=201)
def enrol_in_training_cohort(
    cohort_id: int,
    payload: TrainingEnrolmentCreate,
    db: Session = Depends(get_db),
):
    cohort = db.get(TrainingCohort, cohort_id)
    if not cohort:
        raise HTTPException(status_code=404, detail="Training cohort not found")
    if cohort.enrolled_count >= cohort.max_seats:
        raise HTTPException(status_code=400, detail="Training cohort is full")

    order = Order(
        workspace_id=payload.workspace_id,
        customer_email=payload.learner_email,
        service_type="bid_writing_workshop",
        source="training_enrolment",
        amount=cohort.price,
        currency=cohort.currency,
        status="paid",
        metadata_json={"cohort_id": cohort.id, "pack_name": cohort.pack_name},
    )
    db.add(order)
    db.flush()

    enrolment = TrainingEnrolment(
        cohort_id=cohort.id,
        workspace_id=payload.workspace_id,
        order_id=order.id,
        learner_name=payload.learner_name,
        learner_email=payload.learner_email,
        progress_pct=0.0,
        completed_modules=[],
    )
    db.add(enrolment)
    cohort.enrolled_count += 1
    db.commit()
    db.refresh(enrolment)
    return {
        "enrolment_id": enrolment.id,
        "order_id": order.id,
        "order_source": order.source,
        "cohort_title": cohort.title,
        "pack_name": cohort.pack_name,
        "learner_email": enrolment.learner_email,
    }


@router.post("/training/enrolments/{enrolment_id}/complete-module")
def complete_training_module(
    enrolment_id: int,
    payload: TrainingModuleComplete,
    db: Session = Depends(get_db),
):
    enrolment = db.get(TrainingEnrolment, enrolment_id)
    if not enrolment:
        raise HTTPException(status_code=404, detail="Training enrolment not found")
    cohort = db.get(TrainingCohort, enrolment.cohort_id)
    if not cohort:
        raise HTTPException(status_code=404, detail="Training cohort not found")
    if payload.module_name not in cohort.modules:
        raise HTTPException(status_code=400, detail="Module does not belong to this cohort")

    completed = list(enrolment.completed_modules or [])
    if payload.module_name not in completed:
        completed.append(payload.module_name)
    enrolment.completed_modules = completed
    enrolment.progress_pct = round((len(completed) / max(1, len(cohort.modules))) * 100.0, 1)
    db.commit()
    db.refresh(enrolment)
    return {
        "enrolment_id": enrolment.id,
        "completed_modules": enrolment.completed_modules,
        "progress_pct": enrolment.progress_pct,
    }


# --- 13. White-Label Overview for Bid Consultancies ---
@router.get("/white-label/consultancies")
def list_white_label_consultancies(db: Session = Depends(get_db)):
    tenants = db.query(Workspace).order_by(Workspace.id).all()
    return [
        {
            "id": w.id,
            "slug": w.slug,
            "name": w.name,
            "is_white_label": w.is_white_label,
            "brand_name": w.brand_name,
            "custom_domain": w.custom_domain,
            "primary_color": w.primary_color,
            "accent_color": w.accent_color,
            "client_isolation_enforced": w.client_isolation_enforced,
        }
        for w in tenants
    ]


# --- 14. Public Sector Buyer Side ---
@router.get("/public-sector/drafts")
def list_buyer_tender_drafts(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(BuyerTenderDraft)
        .filter(BuyerTenderDraft.workspace_id == workspace_id)
        .order_by(BuyerTenderDraft.id.desc())
        .all()
    )


@router.post("/public-sector/drafts", status_code=201)
def create_buyer_tender_draft(payload: BuyerTenderDraftCreate, db: Session = Depends(get_db)):
    clarity_score, issues, status = validate_public_sector_draft(
        payload.specification_text,
        payload.evaluation_criteria,
    )
    draft = BuyerTenderDraft(
        workspace_id=payload.workspace_id,
        authority_name=payload.authority_name,
        title=payload.title,
        budget_value=payload.budget_value,
        currency=payload.currency,
        specification_text=payload.specification_text,
        evaluation_criteria=payload.evaluation_criteria,
        clarity_score=clarity_score,
        validation_issues=issues,
        status=status,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


@router.post("/public-sector/drafts/{draft_id}/validate")
def validate_existing_buyer_draft(draft_id: int, db: Session = Depends(get_db)):
    draft = db.get(BuyerTenderDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Buyer tender draft not found")
    clarity_score, issues, status = validate_public_sector_draft(
        draft.specification_text,
        draft.evaluation_criteria,
    )
    draft.clarity_score = clarity_score
    draft.validation_issues = issues
    draft.status = status
    db.commit()
    db.refresh(draft)
    return {
        "draft_id": draft.id,
        "clarity_score": draft.clarity_score,
        "validation_issues": draft.validation_issues,
        "status": draft.status,
        "scorecard": [
            {
                "criterion": c.get("name"),
                "weight_pct": c.get("weight_pct"),
                "max_score": c.get("max_score"),
                "scoring_guidance": c.get("scoring_guidance"),
            }
            for c in draft.evaluation_criteria
        ],
    }


@router.get("/public-sector/drafts/{draft_id}/export-pack")
def export_buyer_tender_pack(draft_id: int, db: Session = Depends(get_db)):
    draft = db.get(BuyerTenderDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Buyer tender draft not found")
    rows = "\n".join(
        f"| {c.get('name')} | {c.get('weight_pct')}% | {c.get('max_score')} | {c.get('scoring_guidance')} |"
        for c in draft.evaluation_criteria
    )
    md = (
        f"# {draft.title}\n"
        f"- **Contracting Authority:** {draft.authority_name}\n"
        f"- **Estimated Budget:** {draft.currency} {draft.budget_value:,.2f}\n"
        f"- **Clarity Score:** {draft.clarity_score}%\n"
        f"- **Status:** {draft.status}\n\n"
        f"## Specification\n{draft.specification_text}\n\n"
        f"## Evaluation Scorecard\n"
        f"| Criterion | Weight | Max Score | Scoring Guidance |\n| --- | --- | --- | --- |\n{rows}\n"
    )
    return {"draft_id": draft.id, "markdown": md}
