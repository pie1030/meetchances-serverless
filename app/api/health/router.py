from fastapi import APIRouter

from app.api.health import service
from app.api.health.schemas import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus, summary="Health check")
def health() -> HealthStatus:
    return service.get_health_status()
