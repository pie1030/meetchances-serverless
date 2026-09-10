"""群机器人 Webhook 客户端。

和 app/feishu.py 分开：那个用应用凭证读写多维表格，这个只往一个群发消息，
不需要 app_id/app_secret，也没有令牌可缓存。Webhook 地址本身就决定了发到哪个
群，所以不需要群 ID。

Webhook 地址等同于「谁拿到就能往群里发消息」的凭证，只放环境变量，不进代码。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _sign(timestamp: str, secret: str) -> str:
    """按飞书的签名校验算法计算 sign。

    和常见的「签名请求体」相反：被签名的是空字节串，`timestamp\\nsecret` 才是密钥。
    """
    key = f"{timestamp}\n{secret}".encode()
    digest = hmac.new(key, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


class FeishuBotError(RuntimeError):
    """飞书返回非 0 code，或响应无法解析。"""


class FeishuWebhookBot:
    """往一个群发卡片消息。

    无状态，可以每次新建，也可以复用。
    """

    def __init__(
        self,
        webhook_url: str,
        secret: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.webhook_url = webhook_url
        self.secret = secret
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> FeishuWebhookBot | None:
        """没配 Webhook 地址就返回 None。

        群通知是锦上添花，不配置时表单照常写入表格，不该让 /contact 报错。
        """
        url = (os.getenv("FEISHU_BOT_WEBHOOK_URL") or "").strip()
        if not url:
            return None
        secret = (os.getenv("FEISHU_BOT_WEBHOOK_SECRET") or "").strip() or None
        return cls(webhook_url=url, secret=secret)

    def build_body(self, card: dict[str, Any]) -> dict[str, Any]:
        """组装请求体。只在开了签名校验时才带 timestamp/sign。

        没开校验却带上这两个字段，飞书会直接拒收，所以不能无条件加。
        """
        body: dict[str, Any] = {"msg_type": "interactive", "card": card}
        if self.secret:
            timestamp = str(int(time.time()))
            body["timestamp"] = timestamp
            body["sign"] = _sign(timestamp, self.secret)
        return body

    async def send_card(self, card: dict[str, Any]) -> None:
        """发送一张卡片，失败抛异常。"""
        body = self.build_body(card)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.webhook_url, json=body)

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise FeishuBotError(
                f"发送群消息失败：响应不是合法 JSON（HTTP {response.status_code}）"
            ) from exc
        if payload.get("code") != 0:
            raise FeishuBotError(
                f"发送群消息失败：code={payload.get('code')} msg={payload.get('msg')}"
            )

    async def try_send_card(self, card: dict[str, Any]) -> None:
        """发送并吞掉所有异常。

        给后台任务用：这时候 HTTP 响应已经发给前端了，抛异常只会在日志里留一段
        没人处理的堆栈，而群里没收到通知不影响表单已经写入表格这件事。
        """
        try:
            await self.send_card(card)
        except (FeishuBotError, httpx.HTTPError) as exc:
            # 预期内的失败（飞书报错、超时、连不上）记一行就够，不需要堆栈。
            logger.error("群通知发送失败：%r", exc)
        except Exception:  # noqa: BLE001 - 后台任务里漏一个异常就没人接了
            logger.exception("群通知发送异常")
        else:
            logger.info("群通知已发送")
