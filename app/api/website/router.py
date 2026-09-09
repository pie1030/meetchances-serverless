from fastapi import APIRouter

# Routes for the public website live here. Add endpoints to this router, and
# create service.py / schemas.py alongside it as the module grows.
router = APIRouter(prefix="/website", tags=["website"])
