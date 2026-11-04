"""Liveness and readiness probes for orchestration and deployment."""

from fastapi import APIRouter, HTTPException, status

from app.core.database import database_is_ready

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", summary="Process liveness")
def live() -> dict[str, str]:
    """Report process liveness without depending on external services."""
    return {"status": "alive"}


@router.get("/ready", summary="Service readiness")
def ready() -> dict[str, str]:
    """Report readiness only when the authoritative database is reachable."""
    if not database_is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "dependency": "database"},
        )
    return {"status": "ready"}
