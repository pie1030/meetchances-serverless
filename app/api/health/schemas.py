from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Response contract for the health check endpoint."""

    status: str
