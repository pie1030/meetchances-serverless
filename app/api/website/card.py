"""把一条联系表单渲染成飞书卡片。

卡片长什么样属于官网模块自己的事（它知道有哪些列、哪些可以为空），所以放在这里，
不放进 app/feishu_bot.py —— 那个只负责把卡片发出去。

用卡片 JSON 2.0（`schema` 必须显式声明，否则按 1.0 解析）。注意 2.0 并没有把文本
组件扁平化：普通文本仍是 `div` + `text` 嵌套，见 _text。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Final
from urllib.parse import urlencode, urlparse, urlunparse

from app.api.website.sites import Site

# 需求说明在卡片里截断，全文在表格里。卡片请求体上限 20KB，正文再长群里也没人读。
REQUIREMENT_MAX_CHARS: Final = 400

# 左列固定宽度，保证各行标签左右对齐；最长的标签是 4 个汉字（联系方式 / 提交时间）。
LABEL_WIDTH: Final = "72px"


def _text(
    content: str, *, size: str | None = None, color: str | None = None
) -> dict[str, Any]:
    """一个普通文本组件，只写非默认的样式。

    卡片 2.0 里普通文本的 tag 仍是 div、文本挂在 text 下，没有独立的 plain_text
    组件 —— 直接用 {"tag": "plain_text"} 当元素会被飞书判为非法卡片。
    """
    text: dict[str, Any] = {"tag": "plain_text", "content": content}
    if size:
        text["text_size"] = size
    if color:
        text["text_color"] = color
    return {"tag": "div", "text": text}


def _row(label: str, value: str) -> dict[str, Any]:
    """一行「标签 + 值」。

    每行各自一个分栏、左列宽度固定：值换行时只有那一行变高，标签仍然对齐。
    """
    return {
        "tag": "column_set",
        "horizontal_spacing": "12px",
        "margin": "0px 0px 8px 0px",
        "columns": [
            {
                "tag": "column",
                "width": LABEL_WIDTH,
                "elements": [_text(label, color="grey")],
            },
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [_text(value)],
            },
        ],
    }


def record_url(record_id: str) -> str | None:
    """表格里这条记录的直达链接，没配置视图地址就返回 None。

    在视图地址上追加 record 参数，飞书打开后会定位到该行。
    """
    base = (os.getenv("FEISHU_BITABLE_VIEW_URL") or "").strip()
    if not base:
        return None
    parts = urlparse(base)
    query = f"{parts.query}&" if parts.query else ""
    return urlunparse(parts._replace(query=query + urlencode({"record": record_id})))


def build_lead_card(
    values: dict[str, str | None],
    site: Site,
    submitted_at: datetime,
    record_id: str,
) -> dict[str, Any]:
    """渲染新消息卡片。

    values 是 service.normalize 之后的表单值：未填写的项为 None，直接省略该行，
    不显示空行。
    """
    elements: list[dict[str, Any]] = [
        _row(label, value)
        for label, value in (
            ("姓名", values.get("name")),
            ("职位", values.get("job_title")),
            ("公司", values.get("company")),
            ("联系方式", values.get("contact")),
        )
        if value
    ]

    requirement = values.get("requirement")
    if requirement:
        if len(requirement) > REQUIREMENT_MAX_CHARS:
            requirement = requirement[:REQUIREMENT_MAX_CHARS] + "…"
        elements.append(_row("需求说明", requirement))

    elements.append({"tag": "hr", "margin": "4px 0px 8px 0px"})
    elements.append(
        _text(
            f"提交时间 {submitted_at:%Y-%m-%d %H:%M}", size="notation", color="grey"
        )
    )

    url = record_url(record_id)
    if url:
        elements.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看记录"},
                "size": "small",
                "margin": "12px 0px 0px 0px",
                "behaviors": [{"type": "open_url", "default_url": url}],
            }
        )

    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": "官网新联络意向"},
            "subtitle": {"tag": "plain_text", "content": site.source},
            # 测试站和未知来源用灰色，一眼区分真实线索。
            "template": "blue" if site.is_lead else "grey",
        },
        "body": {"elements": elements},
    }
