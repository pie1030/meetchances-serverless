"""Tests for POST /contact."""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.feishu import FeishuAPIError
from tests.conftest import (
    FULL_HI,
    FULL_MC,
    HI,
    HI_STAGING,
    MC,
    MC_STAGING,
    StubFeishuClient,
)


def post(api: TestClient, origin: str, body: dict[str, Any]) -> httpx.Response:
    return api.post("/contact", json=body, headers={"Origin": origin})


# ---------------- 智能知识官网：姓名 职位 联系方式 公司 必填，需求说明可选 ----------------


def test_hi_full_submission_written(api: TestClient, stub: StubFeishuClient) -> None:
    resp = post(api, HI, FULL_HI)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "ok": True,
        "record_id": "rec_stub_123",
        "source": "智能知识官网",
    }
    written = stub.calls[0]
    assert written["姓名"] == "张三"
    assert written["职位"] == "技术总监"
    assert written["公司"] == "某某科技"
    assert written["联系方式"] == "13800138000"
    assert written["需求说明"] == "想了解报价"
    assert written["来源网站"] == "智能知识官网"


def test_no_serial_column_is_written(api: TestClient, stub: StubFeishuClient) -> None:
    """表格没有「编号」列，写入它会让整条记录失败。"""
    post(api, HI, FULL_HI)

    assert "编号" not in stub.calls[0]


def test_submitted_at_is_written_as_epoch_millis(
    api: TestClient, stub: StubFeishuClient
) -> None:
    """「提交时间」是普通 DateTime 列，飞书不会自动填，必须由后端写入。"""
    before = int(time.time() * 1000)
    post(api, HI, FULL_HI)
    after = int(time.time() * 1000)

    written = stub.calls[0]["提交时间"]
    assert isinstance(written, int)
    # Milliseconds, not seconds: a seconds value would land in 1970.
    assert before <= written <= after


def test_hi_requirement_is_optional(api: TestClient, stub: StubFeishuClient) -> None:
    body = {k: v for k, v in FULL_HI.items() if k != "requirement"}
    resp = post(api, HI, body)

    assert resp.status_code == 200, resp.text
    # Absent optional values must not be written as empty strings.
    assert "需求说明" not in stub.calls[0]


@pytest.mark.parametrize(
    ("missing", "label"),
    [
        ("name", "姓名"),
        ("job_title", "职位"),
        ("company", "公司"),
        ("contact", "联系方式"),
    ],
)
def test_hi_rejects_missing_required(
    api: TestClient, stub: StubFeishuClient, missing: str, label: str
) -> None:
    body = {k: v for k, v in FULL_HI.items() if k != missing}
    resp = post(api, HI, body)

    assert resp.status_code == 422, f"缺 {label} 应被拒绝，实际 {resp.status_code}"
    assert label in resp.json()["detail"]
    assert stub.calls == []  # a failed check must not reach Feishu


# ---------------- 一面千识官网：姓名 公司 联系方式 需求说明 必填，无职位 ----------------


def test_mc_full_submission_written(api: TestClient, stub: StubFeishuClient) -> None:
    resp = post(api, MC, FULL_MC)

    assert resp.status_code == 200, resp.text
    assert resp.json()["source"] == "一面千识官网"
    written = stub.calls[0]
    assert written["姓名"] == "李四"
    assert written["来源网站"] == "一面千识官网"
    assert "职位" not in written  # this site has no such field


@pytest.mark.parametrize(
    ("missing", "label"),
    [
        ("name", "姓名"),
        ("company", "公司"),
        ("contact", "联系方式"),
        ("requirement", "需求说明"),
    ],
)
def test_mc_rejects_missing_required(
    api: TestClient, stub: StubFeishuClient, missing: str, label: str
) -> None:
    body = {k: v for k, v in FULL_MC.items() if k != missing}
    resp = post(api, MC, body)

    assert resp.status_code == 422, f"缺 {label} 应被拒绝，实际 {resp.status_code}"
    assert label in resp.json()["detail"]
    assert stub.calls == []


def test_mc_accepts_unexpected_job_title(
    api: TestClient, stub: StubFeishuClient
) -> None:
    """该站无「职位」，但前端若误传也不应报错。"""
    resp = post(api, MC, {**FULL_MC, "job_title": "误传的职位"})

    assert resp.status_code == 200
    assert stub.calls[0]["职位"] == "误传的职位"


# ---------------- 归一化与来源判定 ----------------


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_whitespace_only_counts_as_missing(
    api: TestClient, stub: StubFeishuClient, blank: str
) -> None:
    resp = post(api, MC, {**FULL_MC, "name": blank})

    assert resp.status_code == 422
    assert "姓名" in resp.json()["detail"]
    assert stub.calls == []


def test_values_are_trimmed(api: TestClient, stub: StubFeishuClient) -> None:
    resp = post(api, MC, {**FULL_MC, "name": "  李四  "})

    assert resp.status_code == 200
    assert stub.calls[0]["姓名"] == "李四"


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("https://human-intelligence.cn", "智能知识官网"),
        ("http://human-intelligence.cn", "智能知识官网"),
        ("https://www.human-intelligence.cn", "智能知识官网"),
        ("https://www.meetchances.com", "一面千识官网"),
        ("http://meetchances.com", "一面千识官网"),
    ],
)
def test_www_and_scheme_variants_resolve(
    api: TestClient, stub: StubFeishuClient, origin: str, expected: str
) -> None:
    body = FULL_HI if expected == "智能知识官网" else FULL_MC
    resp = post(api, origin, body)

    assert resp.status_code == 200, f"{origin}: {resp.text}"
    assert resp.json()["source"] == expected


def test_referer_used_when_origin_absent(
    api: TestClient, stub: StubFeishuClient
) -> None:
    resp = api.post(
        "/contact", json=FULL_MC, headers={"Referer": f"{MC}/home?utm_source=x"}
    )

    assert resp.status_code == 200
    assert resp.json()["source"] == "一面千识官网"


def test_unknown_source_requires_only_name_and_contact(
    api: TestClient, stub: StubFeishuClient
) -> None:
    """无 Origin 的直连调用：仅强制姓名 + 联系方式，不误拒非浏览器请求。"""
    resp = api.post("/contact", json={"name": "王五", "contact": "w@example.com"})

    assert resp.status_code == 200
    assert resp.json()["source"] == "未知来源"
    assert stub.calls[0]["来源网站"] == "未知来源"


def test_unknown_source_still_requires_name(
    api: TestClient, stub: StubFeishuClient
) -> None:
    resp = api.post("/contact", json={"contact": "w@example.com"})

    assert resp.status_code == 422
    assert "姓名" in resp.json()["detail"]


def test_localhost_records_as_unknown_source(
    api: TestClient, stub: StubFeishuClient
) -> None:
    """本地开发可跨域，但不应伪装成真实线索。"""
    resp = post(api, "http://localhost:5173", FULL_MC)

    assert resp.status_code == 200
    assert resp.json()["source"] == "未知来源"


def test_over_max_length_rejected(api: TestClient, stub: StubFeishuClient) -> None:
    resp = post(api, MC, {**FULL_MC, "requirement": "x" * 5001})

    assert resp.status_code == 422
    assert stub.calls == []


# ---------------- 错误处理 ----------------


def test_feishu_api_error_maps_to_502(api: TestClient, stub: StubFeishuClient) -> None:
    stub.error = FeishuAPIError("新增记录失败：code=1254005", code=1254005)
    resp = post(api, MC, FULL_MC)

    assert resp.status_code == 502
    assert resp.json()["detail"] == "提交失败，请稍后重试"
    # Feishu internals must not leak to the caller.
    assert "code" not in resp.text
    assert "1254005" not in resp.text


def test_network_error_maps_to_504(api: TestClient, stub: StubFeishuClient) -> None:
    stub.error = httpx.ConnectTimeout("timed out")
    resp = post(api, MC, FULL_MC)

    assert resp.status_code == 504
    assert resp.json()["detail"] == "提交超时，请稍后重试"


# ---------------- 测试环境域名 ----------------


@pytest.mark.parametrize(
    ("origin", "body", "expected"),
    [
        (HI_STAGING, FULL_HI, "智能知识官网（测试）"),
        (MC_STAGING, FULL_MC, "一面千识官网（测试）"),
    ],
)
def test_staging_writes_distinct_source(
    api: TestClient,
    stub: StubFeishuClient,
    origin: str,
    body: dict[str, Any],
    expected: str,
) -> None:
    """测试环境写入独立取值，便于在表格里筛掉测试数据。"""
    resp = post(api, origin, body)

    assert resp.status_code == 200, f"{origin}: {resp.text}"
    assert resp.json()["source"] == expected
    assert stub.calls[-1]["来源网站"] == expected


def test_staging_enforces_production_required_fields(
    api: TestClient, stub: StubFeishuClient
) -> None:
    """测试环境必填规则须与对应正式站一致。"""
    hi_no_title = {k: v for k, v in FULL_HI.items() if k != "job_title"}
    resp = post(api, HI_STAGING, hi_no_title)
    assert resp.status_code == 422
    assert "职位" in resp.json()["detail"]

    mc_no_req = {k: v for k, v in FULL_MC.items() if k != "requirement"}
    resp = post(api, MC_STAGING, mc_no_req)
    assert resp.status_code == 422
    assert "需求说明" in resp.json()["detail"]

    assert stub.calls == []
