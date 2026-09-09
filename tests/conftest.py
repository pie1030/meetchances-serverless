"""Shared fixtures.

The Feishu client is replaced with a stub via dependency_overrides, so the
suite makes no network calls, needs no credentials, and never writes to the
shared table. Live checks against the real table live in test_feishu_live.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.website.router import get_feishu_client
from app.main import app

# A complete, valid submission for each site.
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

HI = "http://human-intelligence.cn"  # live site serves HTTP without redirecting
HI_STAGING = "https://human-intelligence.xpertiise.com"
MC = "https://meetchances.com"
MC_STAGING = "https://testwebsite.meetchances.com"


class StubFeishuClient:
    """Records the fields it was asked to write; can be told to raise instead."""

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
