from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=160)
    is_white_label: bool = False
    brand_name: str = "Bid Studio"
    logo_url: str | None = None
    primary_color: str = "#0f172a"
    accent_color: str = "#2563eb"
    custom_domain: str | None = None
    support_email: str = "support@bidstudio.example"


class WhiteLabelUpdate(BaseModel):
    is_white_label: bool = True
    brand_name: str = Field(min_length=2, max_length=160)
    logo_url: str | None = None
    primary_color: str = "#0f172a"
    accent_color: str = "#2563eb"
    custom_domain: str | None = None
    support_email: str = "support@bidstudio.example"
    client_isolation_enforced: bool = True


class WorkspaceMemberCreate(BaseModel):
    email: str
    full_name: str
    role: Literal["owner", "admin", "writer", "reviewer", "client"] = "writer"


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    name: str
    is_white_label: bool
    brand_name: str
    logo_url: str | None
    primary_color: str
    accent_color: str
    custom_domain: str | None
    support_email: str
    client_isolation_enforced: bool
    created_at: datetime


class NoticeCreate(BaseModel):
    workspace_id: int | None = None
    notice_type: Literal["tender", "awarded_tender", "grant_call"] = "tender"
    source_portal: str = "Find a Tender"
    funder_or_buyer: str
    title: str
    sector: str
    region: str = "UK"
    cpv_or_topic: str = "General"
    contract_value: float = 0.0
    currency: str = "GBP"
    status: Literal["open", "awarded", "closed"] = "open"
    awarded_supplier: str | None = None
    deadline: str = "2026-12-31"
    raw_pack_text: str = ""
    structured_criteria: list[dict[str, Any]] = Field(default_factory=list)


class NoticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    workspace_id: int | None
    notice_type: str
    source_portal: str
    funder_or_buyer: str
    title: str
    sector: str
    region: str
    cpv_or_topic: str
    contract_value: float
    currency: str
    status: str
    awarded_supplier: str | None
    deadline: str
    raw_pack_text: str
    structured_criteria: list[dict[str, Any]]
    ai_summary: str
    created_at: datetime


class AnswerLibraryCreate(BaseModel):
    workspace_id: int = 1
    category: str = "security"
    question_pattern: str
    answer_text: str
    tags: list[str] = Field(default_factory=list)
    owner_name: str = "Bid Team"


class EvidenceCreate(BaseModel):
    workspace_id: int = 1
    evidence_type: str = "case_study"
    title: str
    summary: str
    buyer_format: str = "Standard"
    metrics: dict[str, Any] = Field(default_factory=dict)


class QualityReviewAction(BaseModel):
    assigned_reviewer: str
    status: Literal["queued", "in_review", "changes_requested", "approved"]
    review_score: float | None = Field(default=None, ge=0, le=100)
    review_notes: str = ""


class GrantSectionInput(BaseModel):
    criterion_id: str
    title: str
    weight: float
    max_score: float = 5.0
    draft_text: str
    self_score: float = 0.0
    evidence_refs: list[str] = Field(default_factory=list)


class GrantProposalCreate(BaseModel):
    workspace_id: int = 1
    notice_id: int
    title: str | None = None
    applicant_org: str
    requested_amount: float = 0.0
    currency: str = "EUR"
    sections: list[GrantSectionInput] = Field(default_factory=list)


class GrantProposalSectionUpdate(BaseModel):
    sections: list[GrantSectionInput]


class TechDocCreate(BaseModel):
    workspace_id: int = 1
    doc_type: Literal["user_guide", "api_reference", "sop", "release_notes"]
    title: str
    client_email: str
    fixed_fee: float = 950.0
    currency: str = "GBP"
    draft_content: str = ""


class TechDocReviewInput(BaseModel):
    approved: bool
    reviewer_notes: str = ""
    draft_content: str | None = None


class CompliancePackCreate(BaseModel):
    workspace_id: int = 1
    pack_type: Literal["iso_9001", "iso_27001", "security_questionnaire", "data_protection_policy"]
    title: str
    standard_ref: str = "ISO/IEC 27001:2022"
    policy_sections: list[dict[str, Any]] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class BidderAssetCreate(BaseModel):
    workspace_id: int = 1
    asset_type: Literal["cv", "capability_statement", "case_study"]
    title: str
    subject_name: str
    buyer_format: str = "Crown Commercial Service"
    content: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class MarketplaceReviewCreate(BaseModel):
    workspace_id: int = 1
    reviewer_id: int
    quality_queue_id: int | None = None
    target_title: str
    buyer_criteria: list[dict[str, Any]]
    draft_excerpt: str


class MarketplaceScoreSubmit(BaseModel):
    criterion_scores: list[dict[str, Any]]
    feedback_summary: str


class DebriefCompareInput(BaseModel):
    workspace_id: int = 1
    bid_title: str
    buyer_name: str
    outcome: Literal["won", "lost", "withdrawn"]
    contract_value: float = 0.0
    criterion_comparisons: list[dict[str, Any]]
    send_feedback_request: bool = True


class ClarificationAnalyzeInput(BaseModel):
    workspace_id: int = 1
    notice_id: int | None = None
    tender_title: str
    clarification_deadline: str = "2026-12-01"
    source_text: str


class ClarificationStatusUpdate(BaseModel):
    question_id: str
    status: Literal["draft", "submitted", "answered"]
    buyer_response: str = ""


class PriceMatrixLineInput(BaseModel):
    line_id: str | None = None
    category: str = "Delivery"
    description: str
    unit: str = "day"
    quantity: float = Field(gt=0)
    unit_rate: float = Field(ge=0)


class PriceMatrixCreate(BaseModel):
    workspace_id: int = 1
    bid_title: str
    template_id: int | None = None
    currency: str = "GBP"
    margin_pct: float | None = Field(default=None, ge=0, le=100)
    contingency_pct: float = Field(default=5.0, ge=0, le=100)
    lines: list[PriceMatrixLineInput] = Field(default_factory=list)


class SocialValueCreate(BaseModel):
    workspace_id: int = 1
    bid_title: str
    buyer_framework: Literal["UK_PPN_06_20", "EU_GPP", "Custom"] = "UK_PPN_06_20"
    themes: list[str] = Field(default_factory=lambda: ["Fighting Climate Change", "Equal Opportunity"])
    net_zero_target_year: int = 2035
    baseline_emissions_tco2e: float = 120.0
    annual_reduction_pct: float = 8.0
    real_living_wage_accredited: bool = True
    supply_chain_commitments: str = "30-day SME prompt payment and local supply-chain ring-fencing."
    kpis: list[dict[str, Any]] = Field(default_factory=list)


class AlertSubscriptionCreate(BaseModel):
    workspace_id: int = 1
    subscriber_email: str
    plan_tier: str = "weekly_digest_pro"
    cadence: Literal["daily", "weekly"] = "weekly"
    sectors: list[str] = Field(default_factory=list)
    notice_types: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    min_value: float = 0.0
    max_value: float | None = None


class BuyerIntelRequest(BaseModel):
    workspace_id: int = 1
    buyer_name: str
    sector: str | None = None


class FrameworkOnboardingCreate(BaseModel):
    workspace_id: int = 1
    vehicle_type: Literal["framework", "dps", "approved_supplier_list"]
    vehicle_name: str
    authority_name: str
    lots: list[str] = Field(default_factory=list)


class FrameworkChecklistToggle(BaseModel):
    item_id: str
    completed: bool
    notes: str = ""


class TrainingEnrolmentCreate(BaseModel):
    workspace_id: int = 1
    learner_name: str
    learner_email: str


class TrainingModuleComplete(BaseModel):
    module_name: str


class BuyerTenderDraftCreate(BaseModel):
    workspace_id: int = 1
    authority_name: str
    title: str
    budget_value: float = 0.0
    currency: str = "GBP"
    specification_text: str
    evaluation_criteria: list[dict[str, Any]] = Field(default_factory=list)
