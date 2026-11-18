from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import (
    BidOutcome,
    ClarificationPack,
    EmailDeliveryLog,
    OpportunityNotice,
    PriceMatrix,
    PricingTemplate,
    SocialValueStatement,
)
from bid_studio.schemas import (
    ClarificationAnalyzeInput,
    ClarificationStatusUpdate,
    DebriefCompareInput,
    PriceMatrixCreate,
    SocialValueCreate,
)
from bid_studio.services.domain_logic import (
    analyze_pack_for_clarifications,
    build_cost_narrative,
    build_social_value_narrative,
    calculate_price_matrix,
    compare_win_loss_debrief,
)

router = APIRouter(prefix="/api/v1", tags=["bid-enhancements"])


# --- 5. Win/Loss Debrief Service ---
@router.get("/debriefs/outcomes")
def list_bid_outcomes(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(BidOutcome)
        .filter(BidOutcome.workspace_id == workspace_id)
        .order_by(BidOutcome.id.desc())
        .all()
    )


@router.post("/debriefs/compare", status_code=201)
def create_and_compare_debrief(payload: DebriefCompareInput, db: Session = Depends(get_db)):
    letter, fixes, avg_internal, avg_buyer = compare_win_loss_debrief(
        payload.bid_title,
        payload.buyer_name,
        payload.outcome,
        payload.criterion_comparisons,
    )
    record = BidOutcome(
        workspace_id=payload.workspace_id,
        bid_title=payload.bid_title,
        buyer_name=payload.buyer_name,
        outcome=payload.outcome,
        contract_value=payload.contract_value,
        internal_score=avg_internal,
        buyer_score=avg_buyer,
        feedback_requested=payload.send_feedback_request,
        feedback_request_letter=letter,
        criterion_comparisons=payload.criterion_comparisons,
        next_bid_fixes=fixes,
    )
    db.add(record)
    db.flush()

    if payload.send_feedback_request:
        db.add(
            EmailDeliveryLog(
                workspace_id=payload.workspace_id,
                recipient_email="procurement@buyer.example",
                subject=f"Debrief Feedback Request — {payload.bid_title}",
                delivery_type="debrief_request",
                reference_id=record.id,
                body_preview=letter[:300],
                status="sent",
            )
        )
    db.commit()
    db.refresh(record)
    return record


# --- 6. Clarification Question Service ---
@router.get("/clarifications")
def list_clarification_packs(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(ClarificationPack)
        .filter(ClarificationPack.workspace_id == workspace_id)
        .order_by(ClarificationPack.id.desc())
        .all()
    )


@router.post("/clarifications/analyze-pack", status_code=201)
def analyze_pack_clarifications(payload: ClarificationAnalyzeInput, db: Session = Depends(get_db)):
    text = payload.source_text
    title = payload.tender_title
    if payload.notice_id and not text.strip():
        notice = db.get(OpportunityNotice, payload.notice_id)
        if not notice:
            raise HTTPException(status_code=404, detail="Notice not found")
        text = notice.raw_pack_text
        title = title or notice.title

    questions = analyze_pack_for_clarifications(text)
    pack = ClarificationPack(
        workspace_id=payload.workspace_id,
        notice_id=payload.notice_id,
        tender_title=title,
        clarification_deadline=payload.clarification_deadline,
        source_text=text,
        questions=questions,
    )
    db.add(pack)
    db.commit()
    db.refresh(pack)
    return pack


@router.patch("/clarifications/{pack_id}/questions")
def update_clarification_question_status(
    pack_id: int,
    payload: ClarificationStatusUpdate,
    db: Session = Depends(get_db),
):
    pack = db.get(ClarificationPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Clarification pack not found")

    updated: list[dict] = []
    found = False
    for q in pack.questions:
        item = dict(q)
        if item.get("id") == payload.question_id:
            item["status"] = payload.status
            item["buyer_response"] = payload.buyer_response
            found = True
        updated.append(item)
    if not found:
        raise HTTPException(status_code=404, detail="Clarification question ID not found")

    pack.questions = updated
    db.commit()
    db.refresh(pack)
    return pack


# --- 7. Pricing & Cost-Narrative Writing ---
@router.get("/pricing/templates")
def list_pricing_templates(db: Session = Depends(get_db)):
    return db.query(PricingTemplate).order_by(PricingTemplate.id).all()


@router.get("/pricing/matrices")
def list_price_matrices(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(PriceMatrix)
        .filter(PriceMatrix.workspace_id == workspace_id)
        .order_by(PriceMatrix.id.desc())
        .all()
    )


@router.post("/pricing/matrices", status_code=201)
def create_price_matrix(payload: PriceMatrixCreate, db: Session = Depends(get_db)):
    raw_lines = [line.model_dump() for line in payload.lines]
    norm_lines, subtotal, total_price = calculate_price_matrix(
        raw_lines, payload.margin_pct, payload.contingency_pct
    )
    narrative = build_cost_narrative(
        payload.bid_title,
        payload.currency,
        subtotal,
        payload.margin_pct,
        payload.contingency_pct,
        total_price,
        norm_lines,
    )
    matrix = PriceMatrix(
        workspace_id=payload.workspace_id,
        bid_title=payload.bid_title,
        template_id=payload.template_id,
        currency=payload.currency,
        margin_pct=payload.margin_pct,
        contingency_pct=payload.contingency_pct,
        lines=norm_lines,
        subtotal=subtotal,
        total_price=total_price,
        cost_narrative=narrative,
    )
    db.add(matrix)
    db.commit()
    db.refresh(matrix)
    return matrix


# --- 8. Social Value & Sustainability Statements ---
@router.get("/social-value")
def list_social_value_statements(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(SocialValueStatement)
        .filter(SocialValueStatement.workspace_id == workspace_id)
        .order_by(SocialValueStatement.id.desc())
        .all()
    )


@router.post("/social-value", status_code=201)
def create_social_value_statement(payload: SocialValueCreate, db: Session = Depends(get_db)):
    kpis = payload.kpis or [
        {"metric": "Scope 1-3 Carbon Intensity Reduction", "target": f"{payload.annual_reduction_pct:.1f}% YoY"},
        {"metric": "Real Living Wage Compliance", "target": "100% direct & Tier-1 staff"},
        {"metric": "Apprenticeships / Green Skills Hours", "target": "240 hrs per £1m contract value"},
    ]
    narrative = build_social_value_narrative(
        payload.bid_title,
        payload.buyer_framework,
        payload.themes,
        payload.net_zero_target_year,
        payload.baseline_emissions_tco2e,
        payload.annual_reduction_pct,
        payload.real_living_wage_accredited,
        payload.supply_chain_commitments,
        kpis,
    )
    stmt = SocialValueStatement(
        workspace_id=payload.workspace_id,
        bid_title=payload.bid_title,
        buyer_framework=payload.buyer_framework,
        themes=payload.themes,
        net_zero_target_year=payload.net_zero_target_year,
        baseline_emissions_tco2e=payload.baseline_emissions_tco2e,
        annual_reduction_pct=payload.annual_reduction_pct,
        real_living_wage_accredited=payload.real_living_wage_accredited,
        supply_chain_commitments=payload.supply_chain_commitments,
        kpis=kpis,
        generated_statement=narrative,
    )
    db.add(stmt)
    db.commit()
    db.refresh(stmt)
    return stmt
