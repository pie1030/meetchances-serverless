"""官网相关路由。

接口路径是 /contact 而不是挂在 /website 前缀下：两个线上站点已经在往这个绝对
路径提交，保持不变才能直接替换旧服务，前端不用改。
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
    """只建一次，复用它缓存的 tenant_access_token。"""
    return FeishuBitableClient.from_env()


def get_feishu_client() -> FeishuBitableClient:
    """按请求获取客户端，配置缺失时只让这个请求失败。

    不在启动时建：这个仓库还会放其它无关的 Serverless 模块，飞书凭证缺失不该
    让整个应用（包括 /health）起不来。
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
        # 飞书返回的错误码记进日志，不返回给调用方。
        logger.error("写入飞书失败：%s", exc)
        raise HTTPException(status_code=502, detail="提交失败，请稍后重试") from exc
    except httpx.HTTPError as exc:
        # 超时和连接失败，否则会以 500 暴露堆栈。
        logger.error("请求飞书网络异常：%r", exc)
        raise HTTPException(status_code=504, detail="提交超时，请稍后重试") from exc

    logger.info("表单已写入 record_id=%s source=%s", record_id, site.source)
    return ContactResponse(ok=True, record_id=record_id, source=site.source)
