from fastapi import APIRouter, HTTPException, status
from app.core.database import database_is_ready

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "alive"}

@router.get("/ready")
def ready() -> dict[str, str]:
    if not database_is_ready():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"status": "not_ready", "dependency": "database"})
    return {"status": "ready"}
