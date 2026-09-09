"""公共 fixture。

飞书客户端通过 dependency_overrides 换成 stub，所以整个套件不发网络请求、不需要
凭证、不会写共享表格。真连表格的检查在 test_feishu_live.py。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.website.router import get_feishu_client
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


@pytest.fixture()
def stub() -> Iterator[StubFeishuClient]:
    client = StubFeishuClient()
    app.dependency_overrides[get_feishu_client] = lambda: client
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def api(stub: StubFeishuClient) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
