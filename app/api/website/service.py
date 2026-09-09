"""Business logic for the website contact form. No FastAPI imports here."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Final
from urllib.parse import urlparse

from app.api.website.sites import FIELD_LABELS, SITE_BY_HOST, UNKNOWN_SITE, Site

logger = logging.getLogger(__name__)

# Feishu column names, exactly as they appear in the table.
#
# There is no 「编号」 column: Bitable offers no auto-number field type, and the
# index column was repurposed as 「姓名」. Records are identified by record_id.
FIELD_NAME: Final = "姓名"
FIELD_JOB_TITLE: Final = "职位"
FIELD_COMPANY: Final = "公司"
FIELD_CONTACT: Final = "联系方式"
FIELD_REQUIREMENT: Final = "需求说明"
FIELD_SOURCE: Final = "来源网站"
# A plain DateTime column, so nothing fills it in unless we do.
FIELD_SUBMITTED_AT: Final = "提交时间"

# Leads are read in Beijing time; a DateTime column takes epoch milliseconds.
CST: Final = timezone(timedelta(hours=8))


def resolve_site(origin: str | None, referer: str | None) -> Site:
    """Identify the submitting website from request headers.

    Browsers attach Origin to cross-origin POSTs automatically; Referer is the
    fallback for cases where they do not. Deciding this server-side means both
    sites can share one endpoint without the frontend sending an identifier it
    could get wrong or forge.
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
    """Trim surrounding whitespace and treat a blank string as not filled in."""
    return {key: (value or "").strip() or None for key, value in values.items()}


def missing_required(values: dict[str, str | None], site: Site) -> list[str]:
    """Return the Chinese labels of fields this site requires but did not receive."""
    return [FIELD_LABELS[key] for key in site.required if not values.get(key)]


def build_fields(
    values: dict[str, str | None],
    source: str,
    *,
    submitted_at: datetime | None = None,
) -> dict[str, Any]:
    """Map normalized form values onto the Feishu records payload.

    ``submitted_at`` exists so tests can pin the timestamp; callers leave it
    unset and get the current time.
    """
    moment = submitted_at or datetime.now(CST)
    fields: dict[str, Any] = {
        FIELD_NAME: values["name"] or "",
        FIELD_CONTACT: values["contact"] or "",
        FIELD_SOURCE: source,
        FIELD_SUBMITTED_AT: int(moment.timestamp() * 1000),
    }
    # Omit empty optional columns rather than writing empty strings. 一面千识官网
    # has no 「职位」 field at all, so it simply never sets that column.
    for column, value in (
        (FIELD_JOB_TITLE, values["job_title"]),
        (FIELD_COMPANY, values["company"]),
        (FIELD_REQUIREMENT, values["requirement"]),
    ):
        if value:
            fields[column] = value
    return fields
