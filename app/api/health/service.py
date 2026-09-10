from app.api.health.schemas import HealthStatus


def get_health_status() -> HealthStatus:
    """返回服务是否能正常处理请求。

    刻意不检查飞书凭证或外部依赖：这是存活探针，只要进程起来、路由挂上就该答 ok。
    掺进外部依赖会让一次飞书抖动把整个函数判成不健康。
    """
    return HealthStatus(status="ok")
