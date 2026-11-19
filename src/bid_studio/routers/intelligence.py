from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import (
    AlertSubscription,
    DigestDispatch,
    EmailDeliveryLog,
    FrameworkOnboarding,
    IntelligenceReport,
    OpportunityNotice,
    Order,
)
from bid_studio.schemas import (
    AlertSubscriptionCreate,
    BuyerIntelRequest,
    FrameworkChecklistToggle,
    FrameworkOnboardingCreate,
)
from bid_studio.services.domain_logic import (
    build_buyer_intelligence_report,
    default_framework_checklist,
    match_notices_for_subscription,
)

router = APIRouter(prefix="/api/v1", tags=["tender-data-products"])


# --- 9. Tender Alerts & Weekly Digest ---
@router.get("/alerts/subscriptions")
def list_alert_subscriptions(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(AlertSubscription)
        .filter(AlertSubscription.workspace_id == workspace_id)
        .order_by(AlertSubscription.id.desc())
        .all()
    )


@router.post("/alerts/subscriptions", status_code=201)
def create_alert_subscription(payload: AlertSubscriptionCreate, db: Session = Depends(get_db)):
    sub = AlertSubscription(**payload.model_dump())
    db.add(sub)
    db.flush()

    price = 49.0 if payload.cadence == "weekly" else 89.0
    db.add(
        Order(
            workspace_id=payload.workspace_id,
            customer_email=payload.subscriber_email,
            service_type=f"alert_subscription_{payload.cadence}",
            source="subscription",
            amount=price,
            currency="GBP",
            status="paid",
            metadata_json={"subscription_id": sub.id},
        )
    )
    db.commit()
    db.refresh(sub)
    return sub


@router.post("/alerts/subscriptions/{subscription_id}/generate-digest")
def generate_subscription_digest(subscription_id: int, db: Session = Depends(get_db)):
    sub = db.get(AlertSubscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Alert subscription not found")

    notices = (
        db.query(OpportunityNotice)
        .filter(
            or_(
                OpportunityNotice.workspace_id.is_(None),
                OpportunityNotice.workspace_id == sub.workspace_id,
            )
        )
        .order_by(OpportunityNotice.id.desc())
        .all()
    )
    matched = match_notices_for_subscription(sub, notices)
    now = datetime.now(UTC)

    dispatch = DigestDispatch(
        subscription_id=sub.id,
        workspace_id=sub.workspace_id,
        matched_count=len(matched),
        items=matched,
        sent_at=now,
    )
    db.add(dispatch)
    sub.last_sent_at = now

    preview = "; ".join(f"{m['title']} ({m['funder_or_buyer']})" for m in matched[:3])
    db.add(
        EmailDeliveryLog(
            workspace_id=sub.workspace_id,
            recipient_email=sub.subscriber_email,
            subject=f"Bid Studio {sub.cadence.title()} Digest: {len(matched)} matched opportunities",
            delivery_type="digest",
            reference_id=sub.id,
            body_preview=preview or "No matching notices in this window.",
            status="sent",
            sent_at=now,
        )
    )
    db.commit()
    db.refresh(dispatch)
    return dispatch


# --- 10. Competitor & Buyer Intelligence Reports ---
@router.get("/intelligence/reports")
def list_intelligence_reports(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(IntelligenceReport)
        .filter(IntelligenceReport.workspace_id == workspace_id)
        .order_by(IntelligenceReport.id.desc())
        .all()
    )


@router.post("/intelligence/buyer-report", status_code=201)
def generate_buyer_intelligence_report(payload: BuyerIntelRequest, db: Session = Depends(get_db)):
    awarded = (
        db.query(OpportunityNotice)
        .filter(
            OpportunityNotice.notice_type == "awarded_tender",
            or_(
                OpportunityNotice.workspace_id.is_(None),
                OpportunityNotice.workspace_id == payload.workspace_id,
            ),
        )
        .all()
    )
    computed = build_buyer_intelligence_report(payload.buyer_name, payload.sector, awarded)
    report = IntelligenceReport(
        workspace_id=payload.workspace_id,
        buyer_name=payload.buyer_name,
        sector=payload.sector,
        **computed,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("/intelligence/reports/{report_id}/export")
def export_intelligence_report_markdown(report_id: int, db: Session = Depends(get_db)):
    report = db.get(IntelligenceReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Intelligence report not found")
    winners = "\n".join(
        f"| {w.get('supplier')} | {w.get('wins')} | {w.get('share_pct')}% | {w.get('total_value', 0):,.2f} |"
        for w in (report.top_winners or [])
    )
    insights = "\n".join(f"- {i}" for i in (report.insights or []))
    md = (
        f"# Buyer & Competitor Intelligence: {report.buyer_name}\n"
        f"- **Awards Analyzed:** {report.awards_analyzed}\n"
        f"- **Total Spend:** {report.total_spend:,.2f}\n"
        f"- **Average Award Value:** {report.average_award_value:,.2f}\n\n"
        f"## Top Winning Suppliers\n"
        f"| Supplier | Wins | Share | Total Value |\n| --- | --- | --- | --- |\n{winners or '| - | 0 | 0% | 0.00 |'}\n\n"
        f"## Strategic Insights\n{insights}\n"
    )
    return {"report_id": report.id, "markdown": md}


# --- 11. Framework & DPS Onboarding ---
@router.get("/frameworks")
def list_framework_onboardings(workspace_id: int = 1, db: Session = Depends(get_db)):
    return (
        db.query(FrameworkOnboarding)
        .filter(FrameworkOnboarding.workspace_id == workspace_id)
        .order_by(FrameworkOnboarding.id.desc())
        .all()
    )


@router.post("/frameworks", status_code=201)
def create_framework_onboarding(payload: FrameworkOnboardingCreate, db: Session = Depends(get_db)):
    checklist = default_framework_checklist(payload.vehicle_type)
    onboarding = FrameworkOnboarding(
        workspace_id=payload.workspace_id,
        vehicle_type=payload.vehicle_type,
        vehicle_name=payload.vehicle_name,
        authority_name=payload.authority_name,
        lots=payload.lots or ["Lot 1: Core Delivery"],
        checklist=checklist,
        completion_pct=0.0,
        readiness_status="in_progress",
    )
    db.add(onboarding)
    db.commit()
    db.refresh(onboarding)
    return onboarding


@router.patch("/frameworks/{onboarding_id}/checklist")
def toggle_framework_checklist(
    onboarding_id: int,
    payload: FrameworkChecklistToggle,
    db: Session = Depends(get_db),
):
    onboarding = db.get(FrameworkOnboarding, onboarding_id)
    if not onboarding:
        raise HTTPException(status_code=404, detail="Framework onboarding record not found")

    updated: list[dict] = []
    found = False
    for row in onboarding.checklist:
        item = dict(row)
        if item.get("item_id") == payload.item_id:
            item["completed"] = payload.completed
            item["notes"] = payload.notes
            found = True
        updated.append(item)

    if not found:
        raise HTTPException(status_code=404, detail="Checklist item ID not found")

    completed_count = sum(1 for r in updated if r.get("completed"))
    pct = round((completed_count / max(1, len(updated))) * 100.0, 1)
    onboarding.checklist = updated
    onboarding.completion_pct = pct
    onboarding.readiness_status = "ready_to_submit" if pct == 100.0 else "in_progress"
    db.commit()
    db.refresh(onboarding)
    return onboarding


@router.get("/frameworks/{onboarding_id}/export")
def export_framework_onboarding_markdown(onboarding_id: int, db: Session = Depends(get_db)):
    onboarding = db.get(FrameworkOnboarding, onboarding_id)
    if not onboarding:
        raise HTTPException(status_code=404, detail="Framework onboarding record not found")
    rows = "\n".join(
        f"| {c.get('item_id')} | {c.get('title')} | {'Done' if c.get('completed') else 'Pending'} | {c.get('notes') or '-'} |"
        for c in (onboarding.checklist or [])
    )
    md = (
        f"# {onboarding.vehicle_name} ({onboarding.vehicle_type.upper()})\n"
        f"- **Contracting Authority:** {onboarding.authority_name}\n"
        f"- **Completion:** {onboarding.completion_pct}% ({onboarding.readiness_status})\n"
        f"- **Target Lots:** {', '.join(onboarding.lots or [])}\n\n"
        f"## Onboarding Readiness Checklist\n"
        f"| ID | Requirement | Status | Notes |\n| --- | --- | --- | --- |\n{rows}\n"
    )
    return {"onboarding_id": onboarding.id, "markdown": md}
