from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from bid_studio.database import get_db
from bid_studio.models import (
    FeedItemLink,
    FeedSyncRun,
    GrantProposal,
    OpportunityNotice,
    SavedGrant,
    Workspace,
)
from bid_studio.services.feed_sources import SOURCES, parse_iso, sync_source

router = APIRouter(prefix="/api/v1/grants/feed", tags=["grants-feed"])


def _visible(query, workspace_id: int | None):
    """Global notices, plus the workspace's own when one is given."""
    query = query.filter(OpportunityNotice.notice_type == "grant_call")
    if workspace_id is None:
        return query.filter(OpportunityNotice.workspace_id.is_(None))
    return query.filter(
        or_(
            OpportunityNotice.workspace_id.is_(None),
            OpportunityNotice.workspace_id == workspace_id,
        )
    )


def _serialize(n: OpportunityNotice, url: str, saved: bool, proposal_id: int | None, today):
    deadline = parse_iso(n.deadline)
    return {
        "id": n.id,
        "title": n.title,
        "funder": n.funder_or_buyer,
        "source": n.source_portal,
        "sector": n.sector,
        "region": n.region,
        "topic": n.cpv_or_topic,
        "value": n.contract_value,
        "currency": n.currency,
        "deadline": n.deadline or None,
        "days_left": (deadline - today).days if deadline else None,
        "summary": n.ai_summary,
        "url": url or None,
        "criteria_count": len(n.structured_criteria or []),
        "saved": saved,
        "has_proposal": proposal_id is not None,
        "proposal_id": proposal_id,
    }


def _run_dict(r: FeedSyncRun) -> dict:
    return {
        "id": r.id,
        "source": r.source,
        "status": r.status,
        "fetched": r.fetched,
        "created": r.created,
        "updated": r.updated,
        "error": r.error,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
    }


@router.get("")
def grants_feed(
    response: Response,
    workspace_id: int | None = None,
    q: str | None = None,
    funder: str | None = None,
    sector: str | None = None,
    region: str | None = None,
    source: str | None = None,
    min_value: float | None = Query(default=None, ge=0),
    max_value: float | None = Query(default=None, ge=0),
    closing_within_days: int | None = Query(default=None, ge=0, le=3650),
    include_expired: bool = False,
    saved_only: bool = False,
    sort: str = Query(default="deadline", pattern="^(deadline|value|newest)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    today = datetime.now(UTC).date()
    today_iso = today.isoformat()
    query = _visible(db.query(OpportunityNotice), workspace_id)

    if not include_expired:
        query = query.filter(
            or_(OpportunityNotice.deadline == "", OpportunityNotice.deadline >= today_iso)
        )
    if closing_within_days is not None:
        end_iso = (today + timedelta(days=closing_within_days)).isoformat()
        query = query.filter(
            OpportunityNotice.deadline != "",
            OpportunityNotice.deadline >= today_iso,
            OpportunityNotice.deadline <= end_iso,
        )
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                OpportunityNotice.title.ilike(pattern),
                OpportunityNotice.funder_or_buyer.ilike(pattern),
                OpportunityNotice.sector.ilike(pattern),
                OpportunityNotice.cpv_or_topic.ilike(pattern),
                OpportunityNotice.raw_pack_text.ilike(pattern),
            )
        )
    if funder:
        query = query.filter(OpportunityNotice.funder_or_buyer == funder)
    if sector:
        query = query.filter(OpportunityNotice.sector == sector)
    if region:
        query = query.filter(OpportunityNotice.region == region)
    if source:
        query = query.filter(OpportunityNotice.source_portal == source)
    if min_value is not None:
        query = query.filter(OpportunityNotice.contract_value >= min_value)
    if max_value is not None:
        query = query.filter(OpportunityNotice.contract_value <= max_value)
    if saved_only:
        if workspace_id is None:
            raise HTTPException(status_code=422, detail="saved_only requires workspace_id")
        query = query.join(
            SavedGrant,
            (SavedGrant.notice_id == OpportunityNotice.id)
            & (SavedGrant.workspace_id == workspace_id),
        )

    if sort == "value":
        order = [OpportunityNotice.contract_value.desc(), OpportunityNotice.id.desc()]
    elif sort == "newest":
        order = [OpportunityNotice.id.desc()]
    else:  # soonest deadline first, rolling (no deadline) last
        order = [
            case((OpportunityNotice.deadline == "", 1), else_=0),
            OpportunityNotice.deadline.asc(),
            OpportunityNotice.id.asc(),
        ]

    response.headers["X-Total-Count"] = str(query.count())
    rows = query.order_by(*order).offset(offset).limit(limit).all()
    ids = [n.id for n in rows]

    links = {}
    saved_ids: set[int] = set()
    proposal_ids: dict[int, int] = {}
    if ids:
        links = {
            link.notice_id: link.url
            for link in db.query(FeedItemLink).filter(FeedItemLink.notice_id.in_(ids)).all()
        }
        if workspace_id is not None:
            saved_ids = {
                s.notice_id
                for s in db.query(SavedGrant).filter(
                    SavedGrant.workspace_id == workspace_id, SavedGrant.notice_id.in_(ids)
                )
            }
            for p in (
                db.query(GrantProposal)
                .filter(GrantProposal.workspace_id == workspace_id, GrantProposal.notice_id.in_(ids))
                .order_by(GrantProposal.id.desc())
            ):
                proposal_ids[p.notice_id] = p.id
    return [
        _serialize(n, links.get(n.id, ""), n.id in saved_ids, proposal_ids.get(n.id), today)
        for n in rows
    ]


@router.get("/facets")
def grants_feed_facets(workspace_id: int | None = None, db: Session = Depends(get_db)):
    """Distinct filter values with counts for the open (non-expired) feed."""
    today_iso = datetime.now(UTC).date().isoformat()
    base = _visible(db.query(OpportunityNotice), workspace_id).filter(
        or_(OpportunityNotice.deadline == "", OpportunityNotice.deadline >= today_iso)
    )

    def count_by(column):
        rows = (
            base.with_entities(column, func.count(OpportunityNotice.id))
            .group_by(column)
            .order_by(func.count(OpportunityNotice.id).desc(), column)
            .all()
        )
        return [{"value": v, "count": c} for v, c in rows if v]

    return {
        "funders": count_by(OpportunityNotice.funder_or_buyer),
        "sectors": count_by(OpportunityNotice.sector),
        "regions": count_by(OpportunityNotice.region),
        "sources": count_by(OpportunityNotice.source_portal),
    }


@router.post("/{notice_id}/save")
def save_grant(notice_id: int, workspace_id: int = 1, db: Session = Depends(get_db)):
    notice = db.get(OpportunityNotice, notice_id)
    if not notice or notice.notice_type != "grant_call":
        raise HTTPException(status_code=404, detail="Funding call notice not found")
    if not db.get(Workspace, workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    exists = (
        db.query(SavedGrant)
        .filter(SavedGrant.workspace_id == workspace_id, SavedGrant.notice_id == notice_id)
        .first()
    )
    if not exists:
        db.add(SavedGrant(workspace_id=workspace_id, notice_id=notice_id))
        db.commit()
    return {"notice_id": notice_id, "saved": True}


@router.delete("/{notice_id}/save")
def unsave_grant(notice_id: int, workspace_id: int = 1, db: Session = Depends(get_db)):
    db.query(SavedGrant).filter(
        SavedGrant.workspace_id == workspace_id, SavedGrant.notice_id == notice_id
    ).delete()
    db.commit()
    return {"notice_id": notice_id, "saved": False}


@router.post("/sync")
def sync_feed(
    source: str = "all",
    limit: int = Query(default=50, ge=1, le=200),
    keyword: str = "",
    db: Session = Depends(get_db),
):
    """Pull the latest opportunities from external sources into the feed."""
    names = list(SOURCES) if source == "all" else [source]
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown source {unknown[0]!r}; use one of {sorted(SOURCES)}"
        )
    results = []
    for name in names:
        run = sync_source(db, name, limit=limit, keyword=keyword)
        # Serialise now: the next source's commit would expire this ORM object.
        results.append(_run_dict(run))
    return results


@router.get("/sync/runs")
def list_sync_runs(limit: int = Query(default=10, ge=1, le=100), db: Session = Depends(get_db)):
    runs = db.query(FeedSyncRun).order_by(FeedSyncRun.id.desc()).limit(limit).all()
    return [_run_dict(r) for r in runs]
