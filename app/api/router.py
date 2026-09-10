from fastapi import APIRouter

from app.api.health.router import router as health_router
from app.api.website.router import router as website_router

# 唯一的路由注册点：新增业务模块只需在这里 include_router 一行。
api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(website_router)
