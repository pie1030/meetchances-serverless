"""公共 fixture。

飞书客户端和群机器人都通过 dependency_overrides 换成 stub，所以整个套件不发网络
请求、不需要凭证、不会写共享表格、不会往群里发消息。真连表格的检查在
test_feishu_live.py。

群机器人的 stub 是 autouse 的：导入 app.main 会执行 load_dotenv()，本地 .env 里
有真实 Webhook 地址，漏一个 override 就会把测试数据发进群。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.website.router import get_bot, get_feishu_client
from app.main import app

# 每个站点一份完整合法的提交内容。
FULL_HI = {
    "name": "张三",
    "job_title": "技术总监",
    "company": "某某科技",
    "contact": "13800138000",
    "requirement": "想了解报价",
}
FULL_MC = {
    "name": "李四",
    "company": "另一家公司",
    "contact": "lisi@example.com",
    "requirement": "招聘合作",
}

HI = "http://human-intelligence.cn"  # 线上不跳转 https
HI_STAGING = "https://human-intelligence.xpertiise.com"
MC = "https://meetchances.com"
MC_STAGING = "https://testwebsite.meetchances.com"


class StubFeishuClient:
    """记录被要求写入的字段，也可以设成抛异常。"""

    def __init__(self) -> None:
        self.table_id = "tbl_stub"
        self.calls: list[dict[str, Any]] = []
        self.error: Exception | None = None

    async def create_record(self, fields: dict[str, Any]) -> str:
        if self.error:
            raise self.error
        self.calls.append(fields)
        return "rec_stub_123"


class StubBot:
    """记录被要求发送的卡片，也可以设成发不出去。"""

    def __init__(self) -> None:
        self.cards: list[dict[str, Any]] = []
        self.fail = False

    async def try_send_card(self, card: dict[str, Any]) -> None:
        """和真实的 try_send_card 一样不抛异常：发不出去就只是没有卡片。"""
        if not self.fail:
            self.cards.append(card)


@pytest.fixture()
def stub() -> Iterator[StubFeishuClient]:
    client = StubFeishuClient()
    app.dependency_overrides[get_feishu_client] = lambda: client
    yield client
    # 只摘掉自己那一项，不 clear()：否则会顺手清掉 bot fixture 的 override。
    app.dependency_overrides.pop(get_feishu_client, None)


@pytest.fixture(autouse=True)
def bot() -> Iterator[StubBot]:
    stub_bot = StubBot()
    app.dependency_overrides[get_bot] = lambda: stub_bot
    yield stub_bot
    app.dependency_overrides.pop(get_bot, None)


@pytest.fixture()
def api(stub: StubFeishuClient) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
