from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from bid_studio.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    is_white_label: Mapped[bool] = mapped_column(Boolean, default=False)
    brand_name: Mapped[str] = mapped_column(String(160), default="Bid Studio")
    logo_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(20), default="#0f172a")
    accent_color: Mapped[str] = mapped_column(String(20), default="#2563eb")
    custom_domain: Mapped[str | None] = mapped_column(String(200), nullable=True)
    support_email: Mapped[str] = mapped_column(String(160), default="support@bidstudio.example")
    client_isolation_enforced: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    email: Mapped[str] = mapped_column(String(180), index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(40), default="writer")
    status: Mapped[str] = mapped_column(String(40), default="active")
    last_access_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OpportunityNotice(Base):
    __tablename__ = "opportunity_notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspaces.id"), nullable=True, index=True
    )
    notice_type: Mapped[str] = mapped_column(String(40), index=True)
    source_portal: Mapped[str] = mapped_column(String(120))
    funder_or_buyer: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(260))
    sector: Mapped[str] = mapped_column(String(120), index=True)
    region: Mapped[str] = mapped_column(String(80), default="UK")
    cpv_or_topic: Mapped[str] = mapped_column(String(120), default="General")
    contract_value: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="GBP")
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    awarded_supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    deadline: Mapped[str] = mapped_column(String(40), default="2026-12-31")
    raw_pack_text: Mapped[str] = mapped_column(Text, default="")
    structured_criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnswerLibraryItem(Base):
    __tablename__ = "answer_library_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    question_pattern: Mapped[str] = mapped_column(String(300))
    answer_text: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    owner_name: Mapped[str] = mapped_column(String(120), default="Bid Team")
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(220))
    summary: Mapped[str] = mapped_column(Text)
    buyer_format: Mapped[str] = mapped_column(String(120), default="Standard")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QualityQueueItem(Base):
    __tablename__ = "quality_queue_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    item_type: Mapped[str] = mapped_column(String(60), index=True)
    reference_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(240))
    assigned_reviewer: Mapped[str | None] = mapped_column(String(140), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    review_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    customer_email: Mapped[str] = mapped_column(String(180))
    service_type: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(60), default="direct", index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="GBP")
    status: Mapped[str] = mapped_column(String(40), default="paid")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailDeliveryLog(Base):
    __tablename__ = "email_delivery_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    recipient_email: Mapped[str] = mapped_column(String(180))
    subject: Mapped[str] = mapped_column(String(240))
    delivery_type: Mapped[str] = mapped_column(String(60))
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body_preview: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="sent")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GrantProposal(Base):
    __tablename__ = "grant_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    notice_id: Mapped[int] = mapped_column(ForeignKey("opportunity_notices.id"), index=True)
    funder_type: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(240))
    applicant_org: Mapped[str] = mapped_column(String(180))
    requested_amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="EUR")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    extracted_criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    total_weighted_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_queue_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BidOutcome(Base):
    __tablename__ = "bid_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    bid_title: Mapped[str] = mapped_column(String(240))
    buyer_name: Mapped[str] = mapped_column(String(180))
    outcome: Mapped[str] = mapped_column(String(30), index=True)
    contract_value: Mapped[float] = mapped_column(Float, default=0.0)
    internal_score: Mapped[float] = mapped_column(Float, default=0.0)
    buyer_score: Mapped[float] = mapped_column(Float, default=0.0)
    feedback_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback_request_letter: Mapped[str] = mapped_column(Text, default="")
    criterion_comparisons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    next_bid_fixes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClarificationPack(Base):
    __tablename__ = "clarification_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    notice_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunity_notices.id"), nullable=True
    )
    tender_title: Mapped[str] = mapped_column(String(240))
    clarification_deadline: Mapped[str] = mapped_column(String(40))
    source_text: Mapped[str] = mapped_column(Text)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PricingTemplate(Base):
    __tablename__ = "pricing_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    sector: Mapped[str] = mapped_column(String(100))
    default_margin_pct: Mapped[float] = mapped_column(Float, default=18.0)
    default_lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    narrative_guidance: Mapped[str] = mapped_column(Text, default="")


class PriceMatrix(Base):
    __tablename__ = "price_matrices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    bid_title: Mapped[str] = mapped_column(String(240))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("pricing_templates.id"), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="GBP")
    margin_pct: Mapped[float] = mapped_column(Float, default=18.0)
    contingency_pct: Mapped[float] = mapped_column(Float, default=5.0)
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    total_price: Mapped[float] = mapped_column(Float, default=0.0)
    cost_narrative: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SocialValueStatement(Base):
    __tablename__ = "social_value_statements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    bid_title: Mapped[str] = mapped_column(String(240))
    buyer_framework: Mapped[str] = mapped_column(String(80), default="UK_PPN_06_20")
    themes: Mapped[list[str]] = mapped_column(JSON, default=list)
    net_zero_target_year: Mapped[int] = mapped_column(Integer, default=2035)
    baseline_emissions_tco2e: Mapped[float] = mapped_column(Float, default=120.0)
    annual_reduction_pct: Mapped[float] = mapped_column(Float, default=8.0)
    real_living_wage_accredited: Mapped[bool] = mapped_column(Boolean, default=True)
    supply_chain_commitments: Mapped[str] = mapped_column(Text, default="")
    kpis: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    generated_statement: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AlertSubscription(Base):
    __tablename__ = "alert_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    subscriber_email: Mapped[str] = mapped_column(String(180))
    plan_tier: Mapped[str] = mapped_column(String(60), default="weekly_digest_pro")
    cadence: Mapped[str] = mapped_column(String(20), default="weekly")
    sectors: Mapped[list[str]] = mapped_column(JSON, default=list)
    notice_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    min_value: Mapped[float] = mapped_column(Float, default=0.0)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DigestDispatch(Base):
    __tablename__ = "digest_dispatches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("alert_subscriptions.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntelligenceReport(Base):
    __tablename__ = "intelligence_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    buyer_name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    awards_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    total_spend: Mapped[float] = mapped_column(Float, default=0.0)
    average_award_value: Mapped[float] = mapped_column(Float, default=0.0)
    min_award_value: Mapped[float] = mapped_column(Float, default=0.0)
    max_award_value: Mapped[float] = mapped_column(Float, default=0.0)
    top_winners: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    insights: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FrameworkOnboarding(Base):
    __tablename__ = "framework_onboardings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    vehicle_type: Mapped[str] = mapped_column(String(50))
    vehicle_name: Mapped[str] = mapped_column(String(220))
    authority_name: Mapped[str] = mapped_column(String(180))
    lots: Mapped[list[str]] = mapped_column(JSON, default=list)
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    completion_pct: Mapped[float] = mapped_column(Float, default=0.0)
    readiness_status: Mapped[str] = mapped_column(String(40), default="in_progress")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContactRequest(Base):
    __tablename__ = "contact_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(200))
    organisation: Mapped[str] = mapped_column(String(200), default="")
    plan: Mapped[str] = mapped_column(String(40), default="general")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeedItemLink(Base):
    """Maps an external feed record to the grant call it created, for de-duplication."""

    __tablename__ = "feed_item_links"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_feed_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(60), index=True)
    external_id: Mapped[str] = mapped_column(String(120), index=True)
    notice_id: Mapped[int] = mapped_column(ForeignKey("opportunity_notices.id"), index=True)
    url: Mapped[str] = mapped_column(String(500), default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeedSyncRun(Base):
    __tablename__ = "feed_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SavedGrant(Base):
    __tablename__ = "saved_grants"
    __table_args__ = (UniqueConstraint("workspace_id", "notice_id", name="uq_saved_grant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    notice_id: Mapped[int] = mapped_column(ForeignKey("opportunity_notices.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProposalVersion(Base):
    __tablename__ = "proposal_versions"
    __table_args__ = (UniqueConstraint("proposal_id", "version_no", name="uq_proposal_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("grant_proposals.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(120), default="")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
