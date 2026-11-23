from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from bid_studio.config import settings
from bid_studio.database import Base, SessionLocal, engine
from bid_studio.developers import router as developers_router
from bid_studio.mcp_server import (
    BearerKeyMiddleware,
    McpGateway,
    build_http_app,
    build_server,
    set_backend_app,
)
from bid_studio.routers import (
    audiences,
    bid_enhancements,
    business,
    core,
    grants,
    intelligence,
    services_line,
)
from bid_studio.seed import seed_database
from bid_studio.site import render
from bid_studio.site import router as site_router

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    mcp_http_app = build_http_app(build_server())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        Base.metadata.create_all(bind=engine)
        if settings.seed_on_startup:
            with SessionLocal() as db:
                seed_database(db)
        # The mounted MCP app's own lifespan does not run under a parent app.
        async with mcp_http_app.router.lifespan_context(mcp_http_app):
            yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Bid Studio — Tender, Grant Proposal, Compliance, Intelligence & Public-Sector Procurement Writing Platform",
        lifespan=lifespan,
    )
    set_backend_app(app)

    @app.exception_handler(IntegrityError)
    def handle_integrity_error(_request: Request, _exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid reference or duplicate constraint violation."},
        )

    app.include_router(core.router)
    app.include_router(grants.router)
    app.include_router(services_line.router)
    app.include_router(bid_enhancements.router)
    app.include_router(intelligence.router)
    app.include_router(audiences.router)
    app.include_router(business.router)
    app.include_router(developers_router)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(site_router)

    @app.exception_handler(StarletteHTTPException)
    def http_error(request: Request, exc: StarletteHTTPException):
        wants_html = "text/html" in request.headers.get("accept", "")
        if exc.status_code == 404 and wants_html and not request.url.path.startswith("/api/"):
            with SessionLocal() as db:
                return render(request, "site/404.html", db, status_code=404, active="")
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
        )

    # Only /mcp goes to the MCP app; every other path (including 404s) stays with FastAPI.
    app.add_middleware(McpGateway, mcp_app=BearerKeyMiddleware(mcp_http_app, settings.mcp_api_key))

    return app


app = create_app()
