from fastapi import APIRouter

from app.api.health.router import router as health_router
from app.api.website.router import router as website_router

# Single place where every module's router gets mounted.
api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(website_router)
