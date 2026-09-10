"""群通知：卡片内容、发送时机、失败不影响表单。"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.website.card import (
    REQUIREMENT_MAX_CHARS,
    build_lead_card,
    record_url,
)
from app.api.website.service import CST
from app.api.website.sites import SITE_BY_HOST, UNKNOWN_SITE
from app.feishu import FeishuAPIError
from app.feishu_bot import FeishuWebhookBot, _sign
from tests.conftest import (
    FULL_HI,
    FULL_MC,
    HI,
    HI_STAGING,
    MC,
    StubBot,
    StubFeishuClient,
)

HI_SITE = SITE_BY_HOST["human-intelligence.cn"]
AT = datetime(2026, 9, 10, 14, 30, tzinfo=CST)

FULL_VALUES: dict[str, str | None] = {
    "name": "张三",
    "job_title": "技术总监",
    "company": "某某科技",
    "contact": "13800138000",
    "requirement": "想了解报价",
}


def texts(card: dict[str, Any]) -> list[str]:
    """卡片里所有普通文本的内容，用于断言显示了什么。"""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("tag") == "plain_text" and "content" in node:
                found.append(node["content"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(card)
    return found


# ---------------- 卡片内容 ----------------


def test_card_shows_every_submitted_field() -> None:
    card = build_lead_card(FULL_VALUES, HI_SITE, AT, "rec123")
    shown = texts(card)

    for expected in ("张三", "技术总监", "某某科技", "13800138000", "想了解报价"):
        assert expected in shown, expected
    # 标签也要在，否则群里看不出哪个值是什么。
    for label in ("姓名", "职位", "公司", "联系方式", "需求说明"):
        assert label in shown, label


def test_card_header_carries_title_and_source() -> None:
    card = build_lead_card(FULL_VALUES, HI_SITE, AT, "rec123")

    assert card["header"]["title"]["content"] == "官网新联络意向"
    assert card["header"]["subtitle"]["content"] == "智能知识官网"


def test_card_omits_fields_that_were_not_filled() -> None:
    """未填的可选项不显示空行，也不显示光秃秃的标签。"""
    card = build_lead_card(
        {"name": "李四", "contact": "lisi@example.com"}, UNKNOWN_SITE, AT, "rec123"
    )
    shown = texts(card)

    assert "李四" in shown
    for absent in ("职位", "公司", "需求说明"):
        assert absent not in shown, absent


def test_card_shows_submitted_time() -> None:
    card = build_lead_card(FULL_VALUES, HI_SITE, AT, "rec123")

    assert "提交时间 2026-09-10 14:30" in texts(card)


def test_long_requirement_is_truncated() -> None:
    """卡片请求体上限 20KB，需求说明最长 5000 字，必须截断。"""
    card = build_lead_card(
        {**FULL_VALUES, "requirement": "长" * 5000}, HI_SITE, AT, "rec123"
    )

    shown = next(t for t in texts(card) if t.startswith("长"))
    assert len(shown) == REQUIREMENT_MAX_CHARS + 1  # 截断后加一个省略号
    assert shown.endswith("…")


def test_real_leads_are_blue_and_test_traffic_is_grey() -> None:
    """群里要能一眼分出真实线索和测试数据。"""
    real = build_lead_card(FULL_VALUES, HI_SITE, AT, "rec123")
    staging = build_lead_card(
        FULL_VALUES, SITE_BY_HOST["human-intelligence.xpertiise.com"], AT, "rec123"
    )
    unknown = build_lead_card(FULL_VALUES, UNKNOWN_SITE, AT, "rec123")

    assert real["header"]["template"] == "blue"
    assert staging["header"]["template"] == "grey"
    assert unknown["header"]["template"] == "grey"


def test_card_contains_no_emoji() -> None:
    """通知要求不带 emoji。"""
    emoji = re.compile(
        "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f000-\U0001f2ff]"
    )
    for content in texts(build_lead_card(FULL_VALUES, HI_SITE, AT, "rec123")):
        assert not emoji.search(content), content


def test_plain_text_is_never_used_as_a_standalone_element() -> None:
    """卡片 2.0 没有 plain_text 组件，普通文本得是 div + text。

    直接把 {"tag": "plain_text"} 当元素用，飞书会整张卡片拒收（200621）。
    """
    card = build_lead_card(FULL_VALUES, HI_SITE, AT, "rec123")

    for element in card["body"]["elements"]:
        assert element["tag"] != "plain_text"
        for column in element.get("columns", []):
            for nested in column.get("elements", []):
                assert nested["tag"] != "plain_text"


def test_card_declares_schema_2() -> None:
    """不显式声明就按 1.0 解析，2.0 的字段会被忽略。"""
    assert build_lead_card(FULL_VALUES, HI_SITE, AT, "rec123")["schema"] == "2.0"


# ---------------- 查看记录按钮 ----------------


def test_record_button_links_to_the_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "FEISHU_BITABLE_VIEW_URL",
        "https://example.feishu.cn/base/appX?table=tblY&view=vewZ",
    )
    card = build_lead_card(FULL_VALUES, HI_SITE, AT, "rec123")

    button = next(e for e in card["body"]["elements"] if e["tag"] == "button")
    url = button["behaviors"][0]["default_url"]
    assert url == (
        "https://example.feishu.cn/base/appX?table=tblY&view=vewZ&record=rec123"
    )


def test_record_url_appends_when_view_has_no_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEISHU_BITABLE_VIEW_URL", "https://example.feishu.cn/base/appX")

    assert record_url("rec1") == "https://example.feishu.cn/base/appX?record=rec1"


def test_button_omitted_when_view_url_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FEISHU_BITABLE_VIEW_URL", raising=False)
    card = build_lead_card(FULL_VALUES, HI_SITE, AT, "rec123")

    assert all(e["tag"] != "button" for e in card["body"]["elements"])


# ---------------- 发送时机 ----------------


def test_card_sent_after_successful_submission(api: TestClient, bot: StubBot) -> None:
    resp = api.post("/contact", json=FULL_HI, headers={"Origin": HI})

    assert resp.status_code == 200, resp.text
    assert len(bot.cards) == 1
    shown = texts(bot.cards[0])
    assert "张三" in shown
    assert "某某科技" in shown


def test_no_card_when_validation_fails(api: TestClient, bot: StubBot) -> None:
    body = {k: v for k, v in FULL_HI.items() if k != "company"}
    resp = api.post("/contact", json=body, headers={"Origin": HI})

    assert resp.status_code == 422
    assert bot.cards == []


def test_no_card_when_the_table_write_fails(
    api: TestClient, bot: StubBot, stub: StubFeishuClient
) -> None:
    """表格里没有的线索，群里也不该出现。"""
    stub.error = FeishuAPIError("新增记录失败", code=1254005)
    resp = api.post("/contact", json=FULL_HI, headers={"Origin": HI})

    assert resp.status_code == 502
    assert bot.cards == []


def test_submission_still_succeeds_when_the_card_fails(
    api: TestClient, bot: StubBot
) -> None:
    """群通知是附带的，发不出去不能影响表单提交结果。"""
    bot.fail = True
    resp = api.post("/contact", json=FULL_HI, headers={"Origin": HI})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_card_time_matches_the_timestamp_written_to_the_table(
    api: TestClient, bot: StubBot, stub: StubFeishuClient
) -> None:
    """两处的「提交时间」取自同一时刻，不能各调一次 now()。"""
    api.post("/contact", json=FULL_HI, headers={"Origin": HI})

    written = datetime.fromtimestamp(stub.calls[0]["提交时间"] / 1000, tz=CST)
    assert f"提交时间 {written:%Y-%m-%d %H:%M}" in texts(bot.cards[0])


def test_staging_submission_is_marked_grey(api: TestClient, bot: StubBot) -> None:
    api.post("/contact", json=FULL_HI, headers={"Origin": HI_STAGING})

    assert bot.cards[0]["header"]["template"] == "grey"


def test_mc_submission_omits_job_title_row(api: TestClient, bot: StubBot) -> None:
    """一面千识官网没有「职位」字段。"""
    api.post("/contact", json=FULL_MC, headers={"Origin": MC})

    assert "职位" not in texts(bot.cards[0])


# ---------------- 机器人客户端 ----------------


def test_from_env_returns_none_without_a_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没配 Webhook 时不发通知，而不是让 /contact 报错。"""
    monkeypatch.delenv("FEISHU_BOT_WEBHOOK_URL", raising=False)

    assert FeishuWebhookBot.from_env() is None


def test_from_env_ignores_a_blank_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEISHU_BOT_WEBHOOK_URL", "   ")

    assert FeishuWebhookBot.from_env() is None


def test_body_is_unsigned_without_a_secret() -> None:
    """没开签名校验却带 sign，飞书会拒收。"""
    body = FeishuWebhookBot("https://example.com/hook").build_body({"schema": "2.0"})

    assert body["msg_type"] == "interactive"
    assert "sign" not in body
    assert "timestamp" not in body


def test_body_is_signed_with_a_secret() -> None:
    body = FeishuWebhookBot("https://example.com/hook", secret="s3cret").build_body(
        {"schema": "2.0"}
    )

    assert body["sign"] == _sign(body["timestamp"], "s3cret")


def test_signature_signs_an_empty_payload_keyed_by_timestamp_and_secret() -> None:
    """密钥是 "timestamp\\nsecret"、被签名的是空串，反过来写会一直 19021。"""
    import base64
    import hashlib
    import hmac

    expected = base64.b64encode(
        hmac.new(b"1599360473\nsecret", b"", hashlib.sha256).digest()
    ).decode()

    assert _sign("1599360473", "secret") == expected


def test_try_send_card_swallows_errors() -> None:
    """后台任务里抛异常没人接，只会在日志里留一段无用堆栈。"""
    bot = FeishuWebhookBot("https://example.com/hook")

    async def boom(_card: dict[str, Any]) -> None:
        raise httpx.ConnectTimeout("timed out")

    bot.send_card = boom  # type: ignore[method-assign]

    asyncio.run(bot.try_send_card({"schema": "2.0"}))  # 不抛即通过
