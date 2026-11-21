from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bid_studio.config import settings
from bid_studio.database import Base, SessionLocal, engine, get_db
from bid_studio.models import Workspace
from bid_studio.routers import (
    bid_enhancements,
    core,
    grants,
    intelligence,
)
from bid_studio.seed import seed_database

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
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

    app.include_router(core.router)
    app.include_router(grants.router)
    app.include_router(bid_enhancements.router)
    app.include_router(intelligence.router)

    @app.get("/", response_class=HTMLResponse)
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

    return app


app = create_app()
