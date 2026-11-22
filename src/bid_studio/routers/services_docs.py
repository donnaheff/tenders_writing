from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import (
    AnswerLibraryItem,
    DocProject,
    EvidenceItem,
    GrantProposal,
    OpportunityNotice,
    QualityQueueItem,
    Workspace,
)
from bid_studio.services import assistant as ai
from bid_studio.services import questionnaire as qn
from bid_studio.services import report_prefill, ux_copy
from bid_studio.services import service_templates as tpl
from bid_studio.services.access import doc_project_guard
from bid_studio.services.domain_logic import tokenize
from bid_studio.services.mailer import deliver

router = APIRouter(prefix="/api/v1/services", tags=["documentation-services"])
# Routes for one project live on their own router so the marketplace access guard covers them all.
project_router = APIRouter(
    prefix="/api/v1/services/projects/{project_id}",
    tags=["documentation-services"],
    dependencies=[Depends(doc_project_guard)],
)

PLACEHOLDER = "[TO CONFIRM"
EDITABLE = ("drafting",)


class ProjectCreate(BaseModel):
    workspace_id: int = 1
    doc_type: str = Field(max_length=40)
    title: str = Field(min_length=3, max_length=240)
    client_name: str = Field(default="", max_length=200)
    client_email: str = Field(default="", pattern=r"^([^@\s]+@[^@\s]+\.[^@\s]+)?$", max_length=200)
    brief: str = Field(default="", max_length=8000)
    fixed_fee: float = Field(default=0.0, ge=0, le=10_000_000)
    currency: str = Field(default="GBP", min_length=3, max_length=10)
    questions: str = Field(default="", max_length=60000)  # security questionnaire: one per line
    proposal_id: int | None = None  # funder reports: pre-fill from this proposal's plan
    notice_id: int | None = None  # method statements: pre-fill this tender's criteria


class SectionIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    title: str = Field(default="", max_length=200)
    prompt: str = Field(default="", max_length=1000)
    text: str = Field(default="", max_length=60000)


class ItemIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    question: str = Field(max_length=600)
    answer: str = Field(default="", max_length=8000)
    status: str = Field(default="unanswered", pattern="^(unanswered|matched|needs_review|approved)$")
    confidence: float = Field(default=0.0, ge=0, le=1)
    source_answer_id: int | None = None


class CopyItemIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    screen: str = Field(default="", max_length=120)
    element: str = Field(default="label", max_length=30)
    text: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=300)
    max_chars: int | None = Field(default=None, ge=1, le=2000)
    status: str = Field(default="draft", pattern="^(draft|approved)$")


class StringsIn(BaseModel):
    text: str = Field(min_length=1, max_length=40000)


class ProjectSave(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=240)
    client_name: str | None = Field(default=None, max_length=200)
    client_email: str | None = Field(default=None, pattern=r"^([^@\s]+@[^@\s]+\.[^@\s]+)?$", max_length=200)
    brief: str | None = Field(default=None, max_length=8000)
    fixed_fee: float | None = Field(default=None, ge=0, le=10_000_000)
    currency: str | None = Field(default=None, min_length=3, max_length=10)
    sections: list[SectionIn] | None = Field(default=None, max_length=40)
    items: list[dict[str, Any]] | None = Field(default=None, max_length=500)


class AssistIn(BaseModel):
    action: str = Field(pattern="^(draft|improve|shorten|critique|ask)$")
    target_id: str = Field(min_length=1, max_length=40)  # section id, or questionnaire item id
    text: str | None = Field(default=None, max_length=60000)
    instruction: str = Field(default="", max_length=1500)


class PromoteIn(BaseModel):
    item_id: str = Field(min_length=1, max_length=40)
    category: str = Field(default="security", max_length=60)


class AddQuestionsIn(BaseModel):
    questions: str = Field(min_length=3, max_length=60000)


def _get(db: Session, project_id: int) -> DocProject:
    p = db.get(DocProject, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


def _editable(p: DocProject) -> None:
    if p.status not in EDITABLE:
        raise HTTPException(
            status_code=409,
            detail=f"Project is {p.status.replace('_', ' ')} and locked; it reopens if changes are requested.",
        )


def _items_kind(p: DocProject) -> str | None:
    return tpl.TYPES.get(p.doc_type, {}).get("items")


def _is_questionnaire(p: DocProject) -> bool:
    return _items_kind(p) == "questions"


def _is_copydeck(p: DocProject) -> bool:
    return _items_kind(p) == "copy"


def _words(text: str) -> int:
    return len(text.split())


def readiness(p: DocProject) -> dict[str, Any]:
    blockers, warnings = [], []
    if _is_copydeck(p):
        if not p.items:
            blockers.append("No strings yet")
        empty = [i["id"] for i in p.items if not i["text"].strip()]
        if empty:
            blockers.append(f"Empty copy: {', '.join(empty[:8])}{'...' if len(empty) > 8 else ''}")
        over = [i["id"] for i in p.items if i.get("max_chars") and len(i["text"]) > i["max_chars"]]
        if over:
            blockers.append(f"Over the character limit: {', '.join(over[:8])}")
        flagged = ux_copy.lint(p.items, p.sections)
        if flagged:
            warnings.append(f"{len(flagged)} string(s) have style warnings")
        if any(not s["text"].strip() for s in p.sections):
            warnings.append("The style guide is not fully written")
        if any(i["status"] != "approved" for i in p.items if i["text"].strip()):
            warnings.append("Some strings are not yet approved")
    elif _is_questionnaire(p):
        if not p.items:
            blockers.append("No questions yet")
        empty = [i["id"] for i in p.items if not i["answer"].strip()]
        if empty:
            blockers.append(f"Unanswered: {', '.join(empty[:8])}{'...' if len(empty) > 8 else ''}")
        review = [i["id"] for i in p.items if i["status"] in ("matched", "needs_review") and i["answer"].strip()]
        if review:
            warnings.append(f"{len(review)} answer(s) came from the library and are not yet approved")
    else:
        unwritten = [s["title"] for s in p.sections if not s["text"].strip()]
        if unwritten:
            blockers.append("Not yet written: " + ", ".join(unwritten))
        if any(PLACEHOLDER in s["text"] for s in p.sections):
            blockers.append("Contains [TO CONFIRM] placeholders")
    if not p.client_email:
        warnings.append("No client email, so it cannot be emailed on delivery")
    return {"ready": not blockers, "blockers": blockers, "warnings": warnings}


def _dict(p: DocProject) -> dict[str, Any]:
    stats = {}
    if _is_copydeck(p):
        stats = {
            "strings": len(p.items), "approved": sum(1 for i in p.items if i["status"] == "approved"),
            "flagged": len(ux_copy.lint(p.items, p.sections)),
            "written": sum(1 for s in p.sections if s["text"].strip()), "total": len(p.sections),
        }
    elif _is_questionnaire(p):
        stats = {
            "answered": sum(1 for i in p.items if i["answer"].strip()),
            "approved": sum(1 for i in p.items if i["status"] == "approved"),
            "total": len(p.items),
        }
    else:
        stats = {
            "written": sum(1 for s in p.sections if s["text"].strip()),
            "total": len(p.sections),
            "words": sum(_words(s["text"]) for s in p.sections),
        }
    return {
        "id": p.id, "workspace_id": p.workspace_id, "kind": p.kind, "doc_type": p.doc_type,
        "type_title": tpl.TYPES.get(p.doc_type, {}).get("title", p.doc_type),
        "questionnaire": _is_questionnaire(p), "copydeck": _is_copydeck(p),
        "lint": ux_copy.lint(p.items, p.sections) if _is_copydeck(p) else {},
        "element_rules": ux_copy.ELEMENTS if _is_copydeck(p) else {}, "title": p.title, "client_name": p.client_name,
        "client_email": p.client_email, "brief": p.brief, "fixed_fee": p.fixed_fee,
        "currency": p.currency, "status": p.status, "locked": p.status not in EDITABLE,
        "sections": p.sections, "items": p.items, "reviewer_notes": p.reviewer_notes,
        "delivered_at": p.delivered_at, "created_at": p.created_at, "stats": stats,
        "readiness": readiness(p), "evidence_item_id": p.evidence_item_id,
        "proposal_id": p.proposal_id, "notice_id": p.notice_id,
        "promotable": "evidence_type" in tpl.TYPES.get(p.doc_type, {}),
        "can_promote": "evidence_type" in tpl.TYPES.get(p.doc_type, {})
        and p.status in tpl.PROMOTABLE_STATUSES and p.evidence_item_id is None,
    }


def _summary(p: DocProject) -> dict[str, Any]:
    d = _dict(p)
    return {k: d[k] for k in ("id", "kind", "doc_type", "type_title", "title", "client_name",
                              "fixed_fee", "currency", "status", "stats", "created_at")}


@router.get("/assistant-status")
def assistant_status():
    return ai.provider_status()


@router.get("/templates")
def list_templates():
    return tpl.catalogue()


@router.get("/projects")
def list_projects(workspace_id: int = 1, kind: str | None = None, db: Session = Depends(get_db)):
    q = db.query(DocProject).filter(DocProject.workspace_id == workspace_id)
    if kind:
        q = q.filter(DocProject.kind == kind)
    return [_summary(p) for p in q.order_by(DocProject.id.desc()).all()]


@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    if payload.doc_type not in tpl.TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown document type {payload.doc_type!r}")
    if not db.get(Workspace, payload.workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    t = tpl.TYPES[payload.doc_type]
    items: list[dict] = []
    kind_of_items = t.get("items")
    if kind_of_items == "copy":
        items = ux_copy.assign_ids([], ux_copy.parse_strings(payload.questions))
    if kind_of_items == "questions":
        questions = qn.parse_questions(payload.questions)
        if not questions:
            raise HTTPException(status_code=422, detail="Paste at least one question (one per line)")
        items = qn.new_items(questions)
        qn.auto_match(items, _library(db, payload.workspace_id))  # before the row exists
    link_kind = t.get("link")
    if (payload.proposal_id is not None or payload.notice_id is not None) and not link_kind:
        raise HTTPException(status_code=422, detail="This document type cannot be linked to a proposal or tender")
    sections = tpl.instantiate_sections(payload.doc_type)
    prefill: dict[str, str] = {}
    if payload.proposal_id is not None:
        if link_kind != "proposal":
            raise HTTPException(status_code=422, detail="This document type links to a tender, not a proposal")
        proposal = db.get(GrantProposal, payload.proposal_id)
        if not proposal or proposal.workspace_id != payload.workspace_id:
            raise HTTPException(status_code=404, detail="Proposal not found in this workspace")
        prefill = report_prefill.funder_report(db, proposal, final=payload.doc_type == "funder_final_report")
    if payload.notice_id is not None:
        if link_kind != "notice":
            raise HTTPException(status_code=422, detail="This document type links to a proposal, not a tender")
        notice = db.get(OpportunityNotice, payload.notice_id)
        if not notice or notice.workspace_id not in (None, payload.workspace_id):
            raise HTTPException(status_code=404, detail="Tender not found in this workspace")
        prefill = report_prefill.method_statement(notice)
    for sec in sections:
        if sec["id"] in prefill:
            sec["text"] = prefill[sec["id"]]
    p = DocProject(
        workspace_id=payload.workspace_id, kind=t["kind"], doc_type=payload.doc_type,
        proposal_id=payload.proposal_id, notice_id=payload.notice_id,
        title=payload.title, client_name=payload.client_name, client_email=payload.client_email,
        brief=payload.brief, fixed_fee=payload.fixed_fee, currency=payload.currency,
        sections=sections, items=items,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _dict(p)


@project_router.get("")
def get_project(project_id: int, db: Session = Depends(get_db)):
    return _dict(_get(db, project_id))


@project_router.put("")
def save_project(project_id: int, payload: ProjectSave, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    _editable(p)
    for field in ("title", "client_name", "client_email", "brief", "fixed_fee", "currency"):
        value = getattr(payload, field)
        if value is not None:
            setattr(p, field, value)
    if payload.sections is not None:
        if [s.id for s in payload.sections] != [s["id"] for s in p.sections]:
            raise HTTPException(status_code=422, detail="Sections cannot be added, removed or reordered")
        p.sections = [s.model_dump() for s in payload.sections]
    if payload.items is not None:
        model = ItemIn if _is_questionnaire(p) else CopyItemIn if _is_copydeck(p) else None
        if model is None:
            raise HTTPException(status_code=422, detail="This document type has no list items")
        try:
            parsed = [model(**i).model_dump() for i in payload.items]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid item: {exc}") from exc
        if _is_copydeck(p) and any(i["element"] not in ux_copy.ELEMENTS for i in parsed):
            raise HTTPException(status_code=422, detail="Unknown element type")
        p.items = parsed
    p.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(p)
    return _dict(p)


def _library(db: Session, workspace_id: int) -> list[AnswerLibraryItem]:
    return db.query(AnswerLibraryItem).filter(AnswerLibraryItem.workspace_id == workspace_id).all()


@project_router.post("/questions")
def add_questions(project_id: int, payload: AddQuestionsIn, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    _editable(p)
    if not _is_questionnaire(p):
        raise HTTPException(status_code=409, detail="Only questionnaires and FAQ sets have questions")
    existing = {i["question"].lower() for i in p.items}
    fresh = [q for q in qn.parse_questions(payload.questions) if q.lower() not in existing]
    start = len(p.items)
    new = qn.new_items(fresh)
    for k, it in enumerate(new, start=start + 1):
        it["id"] = f"Q{k}"
    items = [dict(i) for i in p.items] + new
    qn.auto_match(items, _library(db, p.workspace_id))
    p.items = items
    db.commit()
    return _dict(p)


@project_router.post("/strings")
def add_strings(project_id: int, payload: StringsIn, db: Session = Depends(get_db)):
    """Bulk-add copy strings, one per line as 'screen | element | copy'."""
    p = _get(db, project_id)
    _editable(p)
    if not _is_copydeck(p):
        raise HTTPException(status_code=409, detail="Only UX copy decks have strings")
    fresh = ux_copy.assign_ids(p.items, ux_copy.parse_strings(payload.text))
    if not fresh:
        raise HTTPException(status_code=422, detail="No strings found")
    if len(p.items) + len(fresh) > 500:
        raise HTTPException(status_code=422, detail="A copy deck holds at most 500 strings")
    p.items = [*p.items, *fresh]
    db.commit()
    return _dict(p)


@project_router.post("/auto-match")
def auto_match_project(project_id: int, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    _editable(p)
    if not _is_questionnaire(p):
        raise HTTPException(status_code=409, detail="Auto-match is for questionnaires and FAQ sets")
    items = [dict(i) for i in p.items]
    changed = qn.auto_match(items, _library(db, p.workspace_id))
    p.items = items
    db.commit()
    return {"changed": changed, "project": _dict(p)}


@project_router.post("/promote-answer", status_code=201)
def promote_answer(project_id: int, payload: PromoteIn, db: Session = Depends(get_db)):
    """Save an approved answer into the workspace's answer library for reuse."""
    p = _get(db, project_id)
    item = next((i for i in p.items if i["id"] == payload.item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Question not found")
    if item["status"] != "approved" or not item["answer"].strip():
        raise HTTPException(status_code=409, detail="Only approved answers can be saved to the library")
    lib = AnswerLibraryItem(
        workspace_id=p.workspace_id, category=payload.category, question_pattern=item["question"][:300],
        answer_text=item["answer"], tags=sorted(tokenize(item["question"]))[:8],
        owner_name="Documentation service",
    )
    db.add(lib)
    db.commit()
    return {"id": lib.id}


@project_router.post("/promote-evidence", status_code=201)
def promote_evidence(project_id: int, db: Session = Depends(get_db)):
    """Save an approved CV, capability statement or case study into the evidence library."""
    p = _get(db, project_id)
    spec = tpl.TYPES.get(p.doc_type, {})
    if "evidence_type" not in spec:
        raise HTTPException(status_code=422, detail="Only CVs, capability statements and case studies can be saved as evidence")
    if p.status not in tpl.PROMOTABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Evidence must be quality-approved before it is added to the library")
    if p.evidence_item_id is not None:
        raise HTTPException(status_code=409, detail=f"Already in the evidence library (#{p.evidence_item_id})")
    by_id = {s["id"]: s["text"].strip() for s in p.sections}
    summary = " ".join(by_id.get(sid, "") for sid in spec["summary_sections"]).strip()[:600]
    metrics = tpl.parse_metrics(by_id.get(spec.get("metrics_section", ""), ""))
    item = EvidenceItem(
        workspace_id=p.workspace_id, evidence_type=spec["evidence_type"], title=p.title[:220],
        summary=summary, buyer_format=p.client_name or "Standard", metrics=metrics,
    )
    db.add(item)
    db.flush()
    p.evidence_item_id = item.id
    db.commit()
    return {"evidence_item_id": item.id, "metrics": metrics}


@project_router.post("/assistant")
def assistant(project_id: int, payload: AssistIn, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    copy_item = next((i for i in p.items if i["id"] == payload.target_id), None) if _is_copydeck(p) else None
    if copy_item:
        rule = ux_copy.ELEMENTS.get(copy_item["element"], "")
        limit = f" Maximum {copy_item['max_chars']} characters." if copy_item.get("max_chars") else ""
        title = f"{copy_item['screen'] or 'Interface'}: {copy_item['element'].replace('_', ' ')}"
        guidance = f"{rule}{limit} Follow the style guide's voice, terminology and rules."
        current = copy_item["text"] if payload.text is None else payload.text
        if payload.action in ("draft", "improve") and copy_item.get("notes"):
            payload = payload.model_copy(update={"instruction": f"{payload.instruction} Context: {copy_item['notes']}".strip()})
    elif _is_questionnaire(p):
        item = next((i for i in p.items if i["id"] == payload.target_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Question not found")
        if p.doc_type == "faq":
            guidance = (
                "Answer this user question directly in the first sentence, then give any steps in a "
                "short numbered list. Use plain language and only facts from the verified material; "
                "use [TO CONFIRM: ...] for anything else."
            )
        else:
            guidance = (
                "Answer this customer security question truthfully and concisely. Only state controls "
                "that appear in the verified material; use [TO CONFIRM: ...] for anything else."
            )
        title = item["question"]
        current = item["answer"] if payload.text is None else payload.text
    else:
        sec = next((s for s in p.sections if s["id"] == payload.target_id), None)
        if not sec:
            raise HTTPException(status_code=404, detail="Section not found")
        title, guidance = sec["title"], sec["prompt"]
        current = sec["text"] if payload.text is None else payload.text
    hits = qn.best_match(f"{title} {guidance}", _library(db, p.workspace_id))
    material = [{"title": hits[0].question_pattern, "text": hits[0].answer_text}] if hits[0] and hits[1] >= 0.3 else []
    req = ai.AssistantRequest(
        action=payload.action,
        section={"title": title, "draft_text": current, "is_doc": True,
                 "doc_title": tpl.TYPES[p.doc_type]["title"], "max_score": 5},
        guidance=guidance, call_title=p.title, funder=p.client_name,
        call_summary=p.brief[:600], applicant="", instruction=payload.instruction, material=material,
    )
    try:
        return ai.run(req).as_dict()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"AI provider returned HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach the AI provider") from exc


@project_router.post("/submit-quality")
def submit_quality(project_id: int, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    _editable(p)
    r = readiness(p)
    if not r["ready"]:
        raise HTTPException(status_code=422, detail={"message": "Not ready for quality review", "blockers": r["blockers"]})
    item = QualityQueueItem(
        workspace_id=p.workspace_id, item_type="doc_project", reference_id=p.id, title=p.title,
        status="queued", review_notes=f"{p.kind}: {tpl.TYPES[p.doc_type]['title']}",
    )
    db.add(item)
    db.flush()
    p.status = "quality_review"
    p.quality_queue_id = item.id
    db.commit()
    return {"project_id": p.id, "status": p.status, "quality_queue_id": item.id}


def _markdown(p: DocProject) -> str:
    if _is_copydeck(p):
        return ux_copy.export_markdown(p.title, p.sections, p.items)
    if _is_questionnaire(p):
        return qn.export_markdown(p.title, p.items)
    out = [f"# {p.title}", ""]
    if p.client_name:
        out += [f"_Prepared for {p.client_name}_", ""]
    for s in p.sections:
        out += [f"## {s['title']}", "", s["text"].strip() or "_Not yet written._", ""]
    return "\n".join(out).rstrip() + "\n"


@project_router.get("/export")
def export_project(project_id: int, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    return {"project_id": p.id, "title": p.title, "markdown": _markdown(p)}


@project_router.post("/deliver")
def deliver_project(project_id: int, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    if p.status != "approved":
        raise HTTPException(status_code=409, detail="Only quality-approved projects can be delivered")
    if p.client_email:
        deliver(
            db, workspace_id=p.workspace_id, to=p.client_email,
            subject=f"Delivered: {p.title}", body=_markdown(p), delivery_type="doc_delivery",
            reference_id=p.id,
        )
    p.status = "delivered"
    p.delivered_at = datetime.now(UTC)
    db.commit()
    return {**_dict(p), "emailed": bool(p.client_email)}


@router.get("/stats")
def stats(workspace_id: int = Query(default=1), db: Session = Depends(get_db)):
    rows = db.query(DocProject).filter(DocProject.workspace_id == workspace_id).all()
    return {
        "projects": len(rows),
        "by_status": {s: sum(1 for r in rows if r.status == s) for s in ("drafting", "quality_review", "approved", "delivered")},
        "fees_delivered": round(sum(r.fixed_fee for r in rows if r.status == "delivered"), 2),
    }
