"""联系表单的业务逻辑，不依赖 FastAPI。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Final
from urllib.parse import urlparse

from app.api.website.sites import FIELD_LABELS, SITE_BY_HOST, UNKNOWN_SITE, Site

logger = logging.getLogger(__name__)

# 飞书列名，与表格严格一致。
# 表格没有「编号」列：飞书没有自动编号字段类型，索引列已改为「姓名」。
FIELD_NAME: Final = "姓名"
FIELD_JOB_TITLE: Final = "职位"
FIELD_COMPANY: Final = "公司"
FIELD_CONTACT: Final = "联系方式"
FIELD_REQUIREMENT: Final = "需求说明"
FIELD_SOURCE: Final = "来源网站"
# 普通 DateTime 列，飞书不会自动填，必须由本服务写入。
FIELD_SUBMITTED_AT: Final = "提交时间"

CST: Final = timezone(timedelta(hours=8))


def resolve_site(origin: str | None, referer: str | None) -> Site:
    """从请求头判断提交来源。

    浏览器会自动为跨域 POST 带上 Origin，Referer 是兜底。由后端判断而不是前端
    传参，两个站才能共用一个接口，也避免前端传错或伪造。
    """
    raw = origin or referer or ""
    host = (urlparse(raw).hostname or "").lower()
    site = SITE_BY_HOST.get(host)
    if site is None:
        if raw:
            logger.warning("无法识别来源域名：%s", raw)
        return UNKNOWN_SITE
    return site


def normalize(values: dict[str, Any]) -> dict[str, str | None]:
    """去掉首尾空白，纯空白视为未填写。"""
    return {key: (value or "").strip() or None for key, value in values.items()}


def missing_required(values: dict[str, str | None], site: Site) -> list[str]:
    """返回该站要求但没收到的字段的中文标签。"""
    return [FIELD_LABELS[key] for key in site.required if not values.get(key)]


def build_fields(
    values: dict[str, str | None],
    source: str,
    *,
    submitted_at: datetime | None = None,
) -> dict[str, Any]:
    """把表单值映射成飞书 records 接口的 fields。

    submitted_at 只为测试固定时间用，调用方不传即取当前时间。
    """
    moment = submitted_at or datetime.now(CST)
    fields: dict[str, Any] = {
        FIELD_NAME: values["name"] or "",
        FIELD_CONTACT: values["contact"] or "",
        FIELD_SOURCE: source,
        FIELD_SUBMITTED_AT: int(moment.timestamp() * 1000),
    }
    # 可选项为空时省略该键，不在表格里留空字符串。一面千识官网没有「职位」，
    # 所以那一列它永远不写。
    for column, value in (
        (FIELD_JOB_TITLE, values["job_title"]),
        (FIELD_COMPANY, values["company"]),
        (FIELD_REQUIREMENT, values["requirement"]),
    ):
        if value:
            fields[column] = value
    return fields
