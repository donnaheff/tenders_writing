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
    QualityQueueItem,
    Workspace,
)
from bid_studio.services import assistant as ai
from bid_studio.services import questionnaire as qn
from bid_studio.services import service_templates as tpl
from bid_studio.services.domain_logic import tokenize
from bid_studio.services.mailer import deliver

router = APIRouter(prefix="/api/v1/services", tags=["documentation-services"])

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


class ProjectSave(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=240)
    client_name: str | None = Field(default=None, max_length=200)
    client_email: str | None = Field(default=None, pattern=r"^([^@\s]+@[^@\s]+\.[^@\s]+)?$", max_length=200)
    brief: str | None = Field(default=None, max_length=8000)
    fixed_fee: float | None = Field(default=None, ge=0, le=10_000_000)
    currency: str | None = Field(default=None, min_length=3, max_length=10)
    sections: list[SectionIn] | None = Field(default=None, max_length=40)
    items: list[ItemIn] | None = Field(default=None, max_length=300)


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


def _is_questionnaire(p: DocProject) -> bool:
    return p.doc_type == "security_questionnaire"


def _words(text: str) -> int:
    return len(text.split())


def readiness(p: DocProject) -> dict[str, Any]:
    blockers, warnings = [], []
    if _is_questionnaire(p):
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
    if _is_questionnaire(p):
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
        "questionnaire": _is_questionnaire(p), "title": p.title, "client_name": p.client_name,
        "client_email": p.client_email, "brief": p.brief, "fixed_fee": p.fixed_fee,
        "currency": p.currency, "status": p.status, "locked": p.status not in EDITABLE,
        "sections": p.sections, "items": p.items, "reviewer_notes": p.reviewer_notes,
        "delivered_at": p.delivered_at, "created_at": p.created_at, "stats": stats,
        "readiness": readiness(p),
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
    if payload.doc_type == "security_questionnaire":
        questions = qn.parse_questions(payload.questions)
        if not questions:
            raise HTTPException(status_code=422, detail="Paste at least one question (one per line)")
        items = qn.new_items(questions)
        qn.auto_match(items, _library(db, payload.workspace_id))  # before the row exists
    p = DocProject(
        workspace_id=payload.workspace_id, kind=t["kind"], doc_type=payload.doc_type,
        title=payload.title, client_name=payload.client_name, client_email=payload.client_email,
        brief=payload.brief, fixed_fee=payload.fixed_fee, currency=payload.currency,
        sections=tpl.instantiate_sections(payload.doc_type), items=items,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _dict(p)


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    return _dict(_get(db, project_id))


@router.put("/projects/{project_id}")
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
        p.items = [i.model_dump() for i in payload.items]
    p.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(p)
    return _dict(p)


def _library(db: Session, workspace_id: int) -> list[AnswerLibraryItem]:
    return db.query(AnswerLibraryItem).filter(AnswerLibraryItem.workspace_id == workspace_id).all()


@router.post("/projects/{project_id}/questions")
def add_questions(project_id: int, payload: AddQuestionsIn, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    _editable(p)
    if not _is_questionnaire(p):
        raise HTTPException(status_code=409, detail="Only security questionnaires have questions")
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


@router.post("/projects/{project_id}/auto-match")
def auto_match_project(project_id: int, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    _editable(p)
    if not _is_questionnaire(p):
        raise HTTPException(status_code=409, detail="Auto-match is for security questionnaires")
    items = [dict(i) for i in p.items]
    changed = qn.auto_match(items, _library(db, p.workspace_id))
    p.items = items
    db.commit()
    return {"changed": changed, "project": _dict(p)}


@router.post("/projects/{project_id}/promote-answer", status_code=201)
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


@router.post("/projects/{project_id}/assistant")
def assistant(project_id: int, payload: AssistIn, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    if _is_questionnaire(p):
        item = next((i for i in p.items if i["id"] == payload.target_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Question not found")
        title, guidance = item["question"], (
            "Answer this customer security question truthfully and concisely. Only state controls "
            "that appear in the verified material; use [TO CONFIRM: ...] for anything else."
        )
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


@router.post("/projects/{project_id}/submit-quality")
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
    if _is_questionnaire(p):
        return qn.export_markdown(p.title, p.items)
    out = [f"# {p.title}", ""]
    if p.client_name:
        out += [f"_Prepared for {p.client_name}_", ""]
    for s in p.sections:
        out += [f"## {s['title']}", "", s["text"].strip() or "_Not yet written._", ""]
    return "\n".join(out).rstrip() + "\n"


@router.get("/projects/{project_id}/export")
def export_project(project_id: int, db: Session = Depends(get_db)):
    p = _get(db, project_id)
    return {"project_id": p.id, "title": p.title, "markdown": _markdown(p)}


@router.post("/projects/{project_id}/deliver")
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
