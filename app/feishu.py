"""飞书多维表格的异步客户端。

放在 app/ 顶层而不是 website 模块下：取 token、写记录对任何表格都一样。表格
特有的列名归属于用这张表的模块（见 app/api/website/service.py）。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final = "https://open.feishu.cn/open-apis"
# 令牌有效期约 2 小时，提前 5 分钟刷新，避免请求执行到一半令牌过期。
TOKEN_REFRESH_MARGIN_SECONDS: Final = 300

REQUIRED_ENV_VARS: Final = (
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_APP_TOKEN",
    "FEISHU_TABLE_ID",
)


class FeishuConfigError(RuntimeError):
    """必需的飞书环境变量缺失。"""


class FeishuAPIError(RuntimeError):
    """飞书返回非 0 code，或响应无法解析。"""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class FeishuBitableClient:
    """读写一张多维表格。

    实例会缓存 tenant_access_token，所以要复用同一个实例，不要每个请求新建。
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    @classmethod
    def from_env(cls) -> FeishuBitableClient:
        """从环境变量构建客户端，缺任何一项都抛 FeishuConfigError。"""
        missing = [key for key in REQUIRED_ENV_VARS if not os.getenv(key)]
        if missing:
            raise FeishuConfigError(f"缺少环境变量：{', '.join(missing)}")
        return cls(
            app_id=os.environ["FEISHU_APP_ID"],
            app_secret=os.environ["FEISHU_APP_SECRET"],
            app_token=os.environ["FEISHU_APP_TOKEN"],
            table_id=os.environ["FEISHU_TABLE_ID"],
            base_url=os.getenv("FEISHU_BASE_URL", DEFAULT_BASE_URL),
        )

    @property
    def _records_url(self) -> str:
        return (
            f"{self.base_url}/bitable/v1/apps/{self.app_token}"
            f"/tables/{self.table_id}/records"
        )

    @staticmethod
    def _parse(response: httpx.Response, action: str) -> dict[str, Any]:
        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise FeishuAPIError(
                f"{action}失败：响应不是合法 JSON（HTTP {response.status_code}）"
            ) from exc
        code = payload.get("code")
        if code != 0:
            raise FeishuAPIError(
                f"{action}失败：code={code} msg={payload.get('msg')}", code=code
            )
        return payload

    async def get_tenant_access_token(self) -> str:
        """返回缓存的令牌，接近过期才重新获取。"""
        now = time.time()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
        payload = self._parse(response, "获取 tenant_access_token")

        token = payload.get("tenant_access_token")
        if not token:
            raise FeishuAPIError("获取 tenant_access_token 失败：响应中无该字段")
        self._access_token = str(token)
        expire = int(payload.get("expire", 7200))
        self._token_expires_at = now + expire - TOKEN_REFRESH_MARGIN_SECONDS
        # 只记过期时间，不记令牌本身。
        logger.info("飞书访问令牌获取成功，%s 秒后过期", expire)
        return self._access_token

    async def _headers(self) -> dict[str, str]:
        token = await self.get_tenant_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def create_record(self, fields: dict[str, Any]) -> str:
        """新增一条记录，返回 record_id。"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self._records_url, headers=await self._headers(), json={"fields": fields}
            )
        payload = self._parse(response, "新增记录")

        record_id = payload.get("data", {}).get("record", {}).get("record_id")
        if not record_id:
            raise FeishuAPIError("新增记录失败：响应中无 record_id")
        return str(record_id)

    async def list_fields(self) -> list[dict[str, Any]]:
        """返回表格的字段定义（含 field_name 和 ui_type）。

        用于核对线上表格是否还和代码写入的列一致。
        """
        url = (
            f"{self.base_url}/bitable/v1/apps/{self.app_token}"
            f"/tables/{self.table_id}/fields"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=await self._headers())
        payload = self._parse(response, "读取字段定义")
        return list(payload.get("data", {}).get("items", []))
