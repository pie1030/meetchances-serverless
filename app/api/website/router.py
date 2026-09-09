"""Routes for the official websites.

The contact endpoint sits at /contact rather than under a /website prefix
because both live sites already POST to that absolute URL. Keeping the path
means this service can replace the old one without a frontend release.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.website import service
from app.api.website.schemas import ContactRequest, ContactResponse
from app.feishu import FeishuAPIError, FeishuBitableClient, FeishuConfigError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["website"])


@lru_cache(maxsize=1)
def _client() -> FeishuBitableClient:
    """Build the client once so its tenant_access_token cache is reused."""
    return FeishuBitableClient.from_env()


def get_feishu_client() -> FeishuBitableClient:
    """Provide the Bitable client, or fail this request only.

    Resolved per request rather than at startup: this repo hosts several
    unrelated Serverless modules, and missing Feishu credentials should not stop
    the whole app (or /health) from coming up.
    """
    try:
        return _client()
    except FeishuConfigError as exc:
        logger.error("飞书配置缺失：%s", exc)
        raise HTTPException(status_code=503, detail="服务暂不可用") from exc


@router.post("/contact", response_model=ContactResponse, summary="提交联系我们表单")
async def create_contact(
    payload: ContactRequest,
    client: Annotated[FeishuBitableClient, Depends(get_feishu_client)],
    origin: Annotated[str | None, Header()] = None,
    referer: Annotated[str | None, Header()] = None,
) -> ContactResponse:
    site = service.resolve_site(origin, referer)
    values = service.normalize(payload.model_dump())

    missing = service.missing_required(values, site)
    if missing:
        raise HTTPException(status_code=422, detail=f"缺少必填项：{'、'.join(missing)}")

    fields = service.build_fields(values, site.source)
    try:
        record_id = await client.create_record(fields)
    except FeishuAPIError as exc:
        # Log the Feishu error code, but do not surface it to the caller.
        logger.error("写入飞书失败：%s", exc)
        raise HTTPException(status_code=502, detail="提交失败，请稍后重试") from exc
    except httpx.HTTPError as exc:
        # Timeouts and connection failures, which would otherwise surface as 500.
        logger.error("请求飞书网络异常：%r", exc)
        raise HTTPException(status_code=504, detail="提交超时，请稍后重试") from exc

    logger.info("表单已写入 record_id=%s source=%s", record_id, site.source)
    return ContactResponse(ok=True, record_id=record_id, source=site.source)
