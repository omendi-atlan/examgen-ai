"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.academic import router as academic_router
from app.api.routes.auth import router as auth_router
from app.api.routes.blueprints import router as blueprints_router
from app.api.routes.health import router as health_router
from app.api.routes.question_bank import router as question_bank_router
from app.api.routes.student_coursework import router as student_coursework_router
from app.api.routes.workspaces import router as workspaces_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    description="Authoritative API for EXAMGEN AI academic and assessment workflows.",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(workspaces_router, prefix=settings.api_v1_prefix)
app.include_router(academic_router, prefix=settings.api_v1_prefix)
app.include_router(student_coursework_router, prefix=settings.api_v1_prefix)
app.include_router(blueprints_router, prefix=settings.api_v1_prefix)
app.include_router(question_bank_router, prefix=settings.api_v1_prefix)
