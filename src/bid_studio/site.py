"""Public website and multi-page app routes (server-rendered)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from bid_studio.catalog import (
    GROUPS,
    OVERVIEW_NEEDS,
    SERVICE_BY_SLUG,
    SERVICES,
    grouped_services,
)
from bid_studio.config import settings
from bid_studio.database import get_db
from bid_studio.models import OpportunityNotice, Workspace

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
router = APIRouter(include_in_schema=False)

SITE_PAGES = ["/", "/services", "/pricing", "/about", "/contact", "/developers"]


def site_base(request: Request) -> str:
    return (settings.public_base_url or str(request.base_url)).rstrip("/")


def brand(db: Session, workspace_id: int | None = None) -> dict[str, Any]:
    ws = db.get(Workspace, workspace_id) if workspace_id else None
    ws = ws or db.query(Workspace).order_by(Workspace.id).first()
    return {
        "workspace_id": ws.id if ws else 1,
        "brand_name": ws.brand_name if ws else settings.app_name,
        "primary_color": ws.primary_color if ws else "#0f172a",
        "accent_color": ws.accent_color if ws else "#2563eb",
        "support_email": ws.support_email if ws else "support@bidstudio.example",
    }


def render(request: Request, name: str, db: Session, status_code: int = 200, **ctx: Any):
    context = {
        **brand(db, ctx.pop("workspace_id", None)),
        "groups": grouped_services(),
        "all_services": SERVICES,
        "site_url": site_base(request),
        "now_year": datetime.now().year,
        **ctx,
    }
    return templates.TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
    )


# ----------------------------------------------------------------------- marketing


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    latest = (
        db.query(OpportunityNotice)
        .filter(OpportunityNotice.workspace_id.is_(None))
        .order_by(OpportunityNotice.id.desc())
        .limit(3)
        .all()
    )
    return render(request, "site/home.html", db, active="home", latest=latest)


@router.get("/services", response_class=HTMLResponse)
def services_index(request: Request, db: Session = Depends(get_db)):
    return render(request, "site/services.html", db, active="services")


@router.get("/services/{slug}", response_class=HTMLResponse)
def service_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    service = SERVICE_BY_SLUG.get(slug)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    related = [s for s in SERVICES if s.group == service.group and s.slug != slug]
    return render(
        request, "site/service_detail.html", db, active="services", service=service, related=related
    )


@router.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request, db: Session = Depends(get_db)):
    return render(request, "site/pricing.html", db, active="pricing")


@router.get("/about", response_class=HTMLResponse)
def about(request: Request, db: Session = Depends(get_db)):
    return render(request, "site/about.html", db, active="about")


@router.get("/contact", response_class=HTMLResponse)
def contact(request: Request, db: Session = Depends(get_db)):
    return render(request, "site/contact.html", db, active="contact")


# --------------------------------------------------------------------------- app


def _app_page(
    request: Request, db: Session, workspace_id: int | None, section_id: str, title: str,
    needs: list[str], current: str, intro: str = "", notice: str = "",
    lawyer_required: bool = False,
):
    return render(
        request, "app/page.html", db, workspace_id=workspace_id,
        section_id=section_id, page_title=title, needs=needs, current=current, intro=intro,
        notice=notice, lawyer_required=lawyer_required,
        ws_query=f"?workspace_id={workspace_id}" if workspace_id else "",
    )


@router.get("/app", response_class=HTMLResponse)
def app_overview(request: Request, workspace_id: int | None = None, db: Session = Depends(get_db)):
    return _app_page(
        request, db, workspace_id, "overview", "Overview, Feed & QA", OVERVIEW_NEEDS, "overview",
        "Live opportunity feed, reusable answer and evidence libraries, and the quality queue.",
    )


@router.get("/app/{slug}", response_class=HTMLResponse)
def app_section(
    slug: str, request: Request, workspace_id: int | None = None, db: Session = Depends(get_db)
):
    service = SERVICE_BY_SLUG.get(slug)
    if not service:
        raise HTTPException(status_code=404, detail="Page not found")
    return _app_page(
        request, db, workspace_id, service.app_id, service.title, service.needs, slug,
        service.summary, notice=service.notice, lawyer_required=service.lawyer_required,
    )


# --------------------------------------------------------------------------- SEO


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request):
    return f"User-agent: *\nDisallow: /app\nDisallow: /api/\nSitemap: {site_base(request)}/sitemap.xml\n"


@router.get("/sitemap.xml")
def sitemap(request: Request):
    base = site_base(request)
    urls = SITE_PAGES + [f"/services/{s.slug}" for s in SERVICES]
    body = "".join(f"<url><loc>{base}{u}</loc></url>" for u in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    )
    return Response(content=xml, media_type="application/xml")


__all__ = ["router", "templates", "render", "GROUPS"]
