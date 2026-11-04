"""FastAPI application entry point."""

from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Authoritative API for EXAMGEN AI academic and assessment workflows.",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)
