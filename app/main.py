import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.website.sites import ALLOWED_ORIGINS

# Local development reads credentials from .env; deployed environments inject
# them as real environment variables, which load_dotenv leaves untouched.
load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


def create_app() -> FastAPI:
    app = FastAPI(title="MeetChances Serverless")

    # Explicit allowlist, never "*": these endpoints write to shared Feishu
    # tables. Adding a site means adding it to app/api/website/sites.py, which
    # feeds this list and the source mapping at once.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    app.include_router(api_router)
    return app


app = create_app()
