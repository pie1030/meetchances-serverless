"""Minimal async client for Feishu Bitable.

Shared infrastructure, not tied to any single API module: token acquisition and
record creation are the same for every table. Table-specific field names belong
with the module that owns the table (see app/api/website/service.py).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final = "https://open.feishu.cn/open-apis"
# Tokens last ~2h; refresh 5 minutes early so an in-flight request never uses
# a token that expires mid-call.
TOKEN_REFRESH_MARGIN_SECONDS: Final = 300

REQUIRED_ENV_VARS: Final = (
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_APP_TOKEN",
    "FEISHU_TABLE_ID",
)


class FeishuConfigError(RuntimeError):
    """Required Feishu environment variables are missing."""


class FeishuAPIError(RuntimeError):
    """Feishu returned a non-zero code, or the response could not be parsed."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class FeishuBitableClient:
    """Reads and writes one Bitable table.

    Instances cache the tenant access token, so callers should reuse a single
    instance rather than building one per request.
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
        """Build a client from environment variables.

        Raises FeishuConfigError when anything required is missing, so the
        caller can answer with a clear status instead of a stack trace.
        """
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
        """Return a cached token, fetching a new one only once it nears expiry."""
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
        # Never log the token itself.
        logger.info("飞书访问令牌获取成功，%s 秒后过期", expire)
        return self._access_token

    async def _headers(self) -> dict[str, str]:
        token = await self.get_tenant_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def create_record(self, fields: dict[str, Any]) -> str:
        """Append one record and return its record_id."""
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
        """Return the table's field definitions (name and ui_type).

        Used to check that the live table still matches what the code writes.
        """
        url = (
            f"{self.base_url}/bitable/v1/apps/{self.app_token}"
            f"/tables/{self.table_id}/fields"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=await self._headers())
        payload = self._parse(response, "读取字段定义")
        return list(payload.get("data", {}).get("items", []))
