"""Connectors that pull open funding opportunities from public APIs.

Each source returns normalised `FeedItem`s; `ingest_items` upserts them into the
opportunity feed as grant calls, de-duplicated by (source, external_id).
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from sqlalchemy.orm import Session

from bid_studio.models import FeedItemLink, FeedSyncRun, OpportunityNotice
from bid_studio.services.domain_logic import summarize_notice

GRANTS_GOV_URL = "https://api.grants.gov/v1/api/search2"
EU_SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
TIMEOUT = 30.0


@dataclass
class FeedItem:
    source: str
    external_id: str
    title: str
    funder: str
    source_portal: str
    url: str = ""
    sector: str = "General"
    region: str = "UK"
    topic: str = "General"
    value: float = 0.0
    currency: str = "GBP"
    deadline: str = ""  # ISO date, or "" when rolling / not stated
    description: str = ""


def _iso_from_us(value: str) -> str:
    """Grants.gov dates are MM/DD/YYYY."""
    try:
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    except (TypeError, ValueError):
        return ""


def _first(meta: dict, key: str) -> str:
    val = meta.get(key) or [""]
    return str(val[0] if isinstance(val, list) else val)


def parse_grants_gov(payload: dict) -> list[FeedItem]:
    hits = (payload.get("data") or {}).get("oppHits") or []
    items = []
    for h in hits:
        opp_id = str(h.get("id") or "")
        if not opp_id or not h.get("title"):
            continue
        items.append(
            FeedItem(
                source="grants_gov",
                external_id=opp_id,
                title=h["title"].strip(),
                funder=(h.get("agency") or h.get("agencyCode") or "US Federal Agency").strip(),
                source_portal="Grants.gov",
                url=f"https://www.grants.gov/search-results-detail/{opp_id}",
                sector="Public Funding (US Federal)",
                region="US",
                topic=h.get("number") or "General",
                currency="USD",
                deadline=_iso_from_us(h.get("closeDate", "")),
                description=(
                    f"Opportunity {h.get('number', '')} ({h.get('oppStatus', '')}) from "
                    f"{h.get('agency', '')}. CFDA: {', '.join(h.get('cfdaList') or []) or 'n/a'}."
                ),
            )
        )
    return items


def _eu_value(budget_json: str) -> float:
    try:
        data = json.loads(budget_json)
    except (TypeError, ValueError):
        return 0.0
    best = 0.0
    for actions in (data.get("budgetTopicActionMap") or {}).values():
        for a in actions:
            grants = a.get("expectedGrants") or 1
            best = max(best, float(a.get("maxContribution") or 0) * grants)
    return best


def parse_eu_funding(payload: dict) -> list[FeedItem]:
    items = []
    for r in payload.get("results") or []:
        meta = r.get("metadata") or {}
        ident = _first(meta, "identifier")
        title = _first(meta, "title") or (r.get("summary") or "")
        if not ident or not title:
            continue
        deadline = _first(meta, "deadlineDate")[:10]
        items.append(
            FeedItem(
                source="eu_funding",
                external_id=ident,
                title=title.strip(),
                funder="European Commission — Horizon Europe",
                source_portal="EU Funding & Tenders Portal",
                url=_first(meta, "url") or r.get("url", ""),
                sector=_first(meta, "callTitle") or "Research & Innovation",
                region="EU",
                topic=ident,
                value=_eu_value(_first(meta, "budgetOverview")),
                currency="EUR",
                deadline=deadline if re.fullmatch(r"\d{4}-\d{2}-\d{2}", deadline) else "",
                description=(r.get("summary") or title).strip(),
            )
        )
    return items


def fetch_grants_gov(limit: int = 50, keyword: str = "") -> list[FeedItem]:
    body = {"rows": limit, "keyword": keyword, "oppStatuses": "forecasted|posted"}
    resp = httpx.post(GRANTS_GOV_URL, json=body, timeout=TIMEOUT)
    resp.raise_for_status()
    return parse_grants_gov(resp.json())


def fetch_eu_funding(limit: int = 50, keyword: str = "") -> list[FeedItem]:
    query = {"bool": {"must": [{"terms": {"type": ["1"]}}, {"terms": {"status": ["31094501", "31094502"]}}]}}
    files = {
        "query": (None, json.dumps(query), "application/json"),
        "languages": (None, json.dumps(["en"]), "application/json"),
        "sort": (None, json.dumps({"order": "DESC", "field": "startDate"}), "application/json"),
    }
    params = {"apiKey": "SEDIA", "text": keyword or "***", "pageSize": limit, "pageNumber": 1}
    resp = httpx.post(EU_SEARCH_URL, params=params, files=files, timeout=TIMEOUT)
    resp.raise_for_status()
    return parse_eu_funding(resp.json())


SOURCES = {"grants_gov": fetch_grants_gov, "eu_funding": fetch_eu_funding}


def ingest_items(db: Session, items: list[FeedItem]) -> tuple[int, int]:
    """Upsert items as global grant calls. Returns (created, updated)."""
    created = updated = 0
    now = datetime.now(UTC)
    for it in items:
        link = (
            db.query(FeedItemLink)
            .filter(FeedItemLink.source == it.source, FeedItemLink.external_id == it.external_id)
            .first()
        )
        notice = db.get(OpportunityNotice, link.notice_id) if link else None
        summary = summarize_notice(
            it.title, it.description, it.funder, it.value, it.currency, it.deadline or "rolling"
        )
        fields = {
            "source_portal": it.source_portal,
            "funder_or_buyer": it.funder[:200],
            "title": it.title[:260],
            "sector": it.sector[:120],
            "region": it.region,
            "cpv_or_topic": it.topic[:120],
            "contract_value": it.value,
            "currency": it.currency,
            "status": "open",
            "deadline": it.deadline,
            "raw_pack_text": it.description,
            "ai_summary": summary,
        }
        if notice is None:
            notice = OpportunityNotice(workspace_id=None, notice_type="grant_call", **fields)
            db.add(notice)
            db.flush()
            db.add(
                FeedItemLink(
                    source=it.source,
                    external_id=it.external_id,
                    notice_id=notice.id,
                    url=it.url[:500],
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            created += 1
        else:
            changed = any(getattr(notice, k) != v for k, v in fields.items() if k != "ai_summary")
            for k, v in fields.items():
                setattr(notice, k, v)
            link.last_seen_at = now
            link.url = it.url[:500]
            updated += int(changed)
    db.commit()
    return created, updated


def sync_source(db: Session, source: str, limit: int = 50, keyword: str = "") -> FeedSyncRun:
    """Fetch and ingest one source, always recording a run (errors included)."""
    run = FeedSyncRun(source=source)
    db.add(run)
    db.commit()  # persist the run first so a failed ingest can still be recorded
    run_id = run.id
    try:
        items = SOURCES[source](limit=limit, keyword=keyword)
        run.fetched = len(items)
        run.created, run.updated = ingest_items(db, items)
        run.status = "ok"
    except Exception as exc:  # network, schema or parsing failure must not break callers
        db.rollback()
        run = db.get(FeedSyncRun, run_id)
        run.status = "error"
        run.error = f"{type(exc).__name__}: {exc}"[:1000]
    run.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(run)
    return run


def parse_iso(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
