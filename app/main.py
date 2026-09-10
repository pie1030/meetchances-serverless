import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.website.sites import ALLOWED_ORIGINS

# 本地开发从 .env 读凭证；线上由平台注入真实环境变量，load_dotenv 不会覆盖。
load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


def create_app() -> FastAPI:
    app = FastAPI(title="MeetChances Serverless")

    # 显式白名单，绝不用 "*"：这些接口会写共享的飞书表格。加站点只改
    # app/api/website/sites.py，那里同时喂给这个白名单和来源判定。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    app.include_router(api_router)
    return app


app = create_app()
