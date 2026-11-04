"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import get_settings
from ..db import init_db
from .routers import auth, exams, workspaces

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EXAMGEN AI",
        version="0.1.0",
        description="AI-powered academic examination generation, simulation, "
                    "visual assessment and subject mastery platform.",
    )
    init_db()
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    app.include_router(auth.router)
    app.include_router(workspaces.router)
    app.include_router(exams.router)

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "service": "examgen-ai", "version": app.version,
                "llm_enabled": bool(settings.llm_api_key)}

    @app.get("/", include_in_schema=False)
    def index(request: Request):
        return templates.TemplateResponse(request, "index.html", {"app_version": app.version})

    @app.get("/exam/{examination_id}", include_in_schema=False)
    def exam_site(request: Request, examination_id: str):
        return templates.TemplateResponse(
            request, "exam.html", {"examination_id": examination_id})

    return app
