"""真连飞书表格的检查，默认跳过。

其余测试都把飞书 stub 掉了，抓不到线上真正会挂的那类问题：代码写了一个表格里
没有的列名。这只有对着真实表格才能发现。

    RUN_LIVE_FEISHU=1 uv run pytest tests/test_feishu_live.py -v

凭证从 .env 或环境变量读。只读，除非同时设 FEISHU_LIVE_WRITE=1，那会写一条需要
你手动删掉的记录。
"""

from __future__ import annotations

import os

import pytest

from app.api.website import service
from app.feishu import FeishuBitableClient, FeishuConfigError

pytestmark = [
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_FEISHU") != "1",
        reason="需 RUN_LIVE_FEISHU=1 才会真连飞书",
    ),
    pytest.mark.anyio,
]

# 本服务会写的列。每一列都必须存在，否则写入时报字段不存在。
WRITTEN_COLUMNS = (
    service.FIELD_NAME,
    service.FIELD_JOB_TITLE,
    service.FIELD_COMPANY,
    service.FIELD_CONTACT,
    service.FIELD_REQUIREMENT,
    service.FIELD_SOURCE,
    service.FIELD_SUBMITTED_AT,
)

# 飞书没有自动编号字段类型，表格里也不该再有「编号」列；写一个未知列会让整条
# 记录失败。
FORBIDDEN_COLUMNS = ("编号",)

# 「提交时间」必须保持可写的 DateTime。改成「创建时间」就变只读，每次写入都会
# 被飞书拒绝。
WRITABLE_DATETIME_COLUMNS = {service.FIELD_SUBMITTED_AT: {"DateTime"}}


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def client() -> FeishuBitableClient:
    try:
        return FeishuBitableClient.from_env()
    except FeishuConfigError as exc:
        pytest.skip(f"{exc}（复制 .env.example 为 .env 并填入真实值）")


async def test_tenant_access_token_obtainable(client: FeishuBitableClient) -> None:
    token = await client.get_tenant_access_token()

    # 只断言形状，不打印令牌本身。
    assert token
    assert isinstance(token, str)


async def test_every_written_column_exists(client: FeishuBitableClient) -> None:
    actual = {f["field_name"]: f["ui_type"] for f in await client.list_fields()}

    missing = [name for name in WRITTEN_COLUMNS if name not in actual]
    assert not missing, f"表格缺少本服务要写入的列：{'、'.join(missing)}"


async def test_submitted_at_stays_writable(client: FeishuBitableClient) -> None:
    """「提交时间」须为可写的 DateTime。"""
    actual = {f["field_name"]: f["ui_type"] for f in await client.list_fields()}

    for name, allowed in WRITABLE_DATETIME_COLUMNS.items():
        assert name in actual, f"表格缺少「{name}」列"
        assert actual[name] in allowed, (
            f"「{name}」当前类型为 {actual[name]}，不在 {allowed} 中。"
            "改成「创建时间」会变为只读，导致每次写入都被飞书拒绝。"
        )


async def test_no_unwritable_columns_expected(client: FeishuBitableClient) -> None:
    """「编号」若被加回来需要重新决定谁填，别让它静默留空。"""
    actual = {f["field_name"] for f in await client.list_fields()}

    resurrected = [name for name in FORBIDDEN_COLUMNS if name in actual]
    assert not resurrected, (
        f"表格出现了 {'、'.join(resurrected)} 列，但本服务不写它，会留空。"
        "请确认该列由谁填写。"
    )


@pytest.mark.skipif(
    os.getenv("FEISHU_LIVE_WRITE") != "1",
    reason="需 FEISHU_LIVE_WRITE=1 才会真写入共享表格",
)
async def test_create_record_writes_one_row(client: FeishuBitableClient) -> None:
    """真写入一条，跑完请手动删除。"""
    values = service.normalize(
        {
            "name": "测试-勿删",
            "job_title": "测试职位",
            "company": "测试公司",
            "contact": "test@example.com",
            "requirement": "这是 test_feishu_live.py 写入的测试数据，可直接删除。",
        }
    )
    record_id = await client.create_record(
        service.build_fields(values, "未知来源")
    )

    assert record_id
    print(f"\n已写入 record_id={record_id}，请到表格中删除「测试-勿删」这一行。")
