from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bid_studio.config import settings
from bid_studio.database import Base, SessionLocal, engine, get_db
from bid_studio.models import GrantProposal, Workspace
from bid_studio.routers import (
    automation,
    bid_enhancements,
    core,
    feed,
    grants,
    intelligence,
    site,
    studio,
)
from bid_studio.seed import seed_database

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_startup:
        with SessionLocal() as db:
            seed_database(db)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Bid Studio — Grant Proposal & Tender Writing Platform",
        lifespan=lifespan,
    )

    @app.exception_handler(IntegrityError)
    def handle_integrity_error(_request: Request, _exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid reference or duplicate constraint violation."},
        )

    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(site.router)
    app.include_router(core.router)
    app.include_router(automation.router)
    app.include_router(feed.router)
    app.include_router(grants.router)
    app.include_router(studio.router)
    app.include_router(bid_enhancements.router)
    app.include_router(intelligence.router)

    @app.get("/app", response_class=HTMLResponse, include_in_schema=False)
    def dashboard(request: Request, workspace_id: int | None = None, db: Session = Depends(get_db)):
        ws = (
            db.get(Workspace, workspace_id)
            if workspace_id
            else db.query(Workspace).order_by(Workspace.id).first()
        )
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "workspace_id": ws.id if ws else 1,
                "brand_name": ws.brand_name if ws else settings.app_name,
                "primary_color": ws.primary_color if ws else "#0f172a",
                "accent_color": ws.accent_color if ws else "#2563eb",
            },
        )

    @app.get("/app/studio/{proposal_id}", response_class=HTMLResponse, include_in_schema=False)
    def grant_studio(proposal_id: int, request: Request, db: Session = Depends(get_db)):
        proposal = db.get(GrantProposal, proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="Grant proposal not found")
        ws = db.get(Workspace, proposal.workspace_id)
        return templates.TemplateResponse(
            request=request,
            name="studio.html",
            context={
                "proposal_id": proposal.id,
                "workspace_id": proposal.workspace_id,
                "brand_name": ws.brand_name if ws else settings.app_name,
                "primary_color": ws.primary_color if ws else "#0f172a",
                "accent_color": ws.accent_color if ws else "#2563eb",
            },
        )

    return app


app = create_app()
