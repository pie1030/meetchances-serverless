from pydantic import BaseModel


class HealthStatus(BaseModel):
    """健康检查接口的响应契约。"""

    status: str
