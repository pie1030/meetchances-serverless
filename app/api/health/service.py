from app.api.health.schemas import HealthStatus


def get_health_status() -> HealthStatus:
    """Report whether the service is able to handle requests."""
    return HealthStatus(status="ok")
