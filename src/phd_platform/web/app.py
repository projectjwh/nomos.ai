"""FastAPI application factory for nomos.ai web product."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from phd_platform.config import get_settings
from phd_platform.persistence.database import get_engine, init_db

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    engine = get_engine()
    await init_db(engine)
    yield


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()

    app = FastAPI(
        title="nomos.ai",
        description="PhD-level adaptive education platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Serve milestones visualization
    docs_dir = WEB_DIR.parents[2] / "docs"
    if docs_dir.exists():
        app.mount("/docs-static", StaticFiles(directory=str(docs_dir)), name="docs")

    # Register routes
    from phd_platform.web.routes import pages, placement, assessment, tutoring, lectures
    app.include_router(pages.router)
    app.include_router(placement.router, prefix="/placement")
    app.include_router(assessment.router, prefix="/assess")
    app.include_router(tutoring.router, prefix="/tutor")
    app.include_router(lectures.router, prefix="/lecture")

    return app


# Templates singleton
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def render(request: "Request", template_name: str, context: dict | None = None):
    """Render a template with Starlette 1.0 compatible API."""
    ctx = context or {}
    return templates.TemplateResponse(request, template_name, ctx)


def run():
    """Entry point for `phd-serve` command."""
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "phd_platform.web.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
