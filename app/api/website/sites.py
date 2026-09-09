"""Registry of the official websites that may submit the contact form.

Single source of truth: the CORS allowlist, the 「来源网站」value written to
Feishu, and the per-site required fields all derive from SITES below. The old
implementation kept three hand-maintained lists, where adding a domain to one
and forgetting another let requests through but silently recorded them as
「未知来源」 — or applied the wrong required-field rules.
"""

from __future__ import annotations

from typing import Final, NamedTuple

# Form field key -> label used in user-facing validation messages. Keys match
# ContactRequest; labels match the Feishu column names.
FIELD_LABELS: Final[dict[str, str]] = {
    "name": "姓名",
    "job_title": "职位",
    "company": "公司",
    "contact": "联系方式",
    "requirement": "需求说明",
}

class Site(NamedTuple):
    source: str
    """Value written to the Feishu 「来源网站」 column."""

    hosts: tuple[str, ...]
    schemes: tuple[str, ...]
    required: tuple[str, ...]
    """Form field keys that must be non-empty for this site."""


# A request whose origin we cannot identify is not necessarily hostile — it may
# be a curl health check or a server-side call. Enforce only the bare minimum
# rather than rejecting it outright. Not part of SITES: it owns no domain and
# contributes nothing to the CORS allowlist.
UNKNOWN_SITE: Final = Site(
    source="未知来源", hosts=(), schemes=(), required=("name", "contact")
)


# Required fields per site, as marked with * on the live forms (2026-09-04):
#   智能知识官网：姓名 职位 联系方式 公司   —— 需求说明可选
#   一面千识官网：姓名 公司 联系方式 需求说明 —— 无「职位」字段
_REQUIRED_HI: Final[tuple[str, ...]] = ("name", "job_title", "contact", "company")
_REQUIRED_MC: Final[tuple[str, ...]] = ("name", "company", "contact", "requirement")

# Staging sites carry a distinct 「来源网站」 value so test submissions can be
# filtered out of the shared table, but reuse the production required-field
# tuple so the two can never drift apart.
#
# human-intelligence.cn serves plain HTTP without redirecting to HTTPS, so
# browsers send an http:// Origin there and both schemes must be allowed. The
# staging hosts are HTTPS-only.
SITES: Final[tuple[Site, ...]] = (
    Site(
        source="智能知识官网",
        hosts=("human-intelligence.cn", "www.human-intelligence.cn"),
        schemes=("https", "http"),
        required=_REQUIRED_HI,
    ),
    Site(
        source="智能知识官网（测试）",
        hosts=("human-intelligence.xpertiise.com",),
        schemes=("https",),
        required=_REQUIRED_HI,
    ),
    Site(
        source="一面千识官网",
        hosts=("meetchances.com", "www.meetchances.com"),
        schemes=("https", "http"),
        required=_REQUIRED_MC,
    ),
    Site(
        source="一面千识官网（测试）",
        hosts=("testwebsite.meetchances.com",),
        schemes=("https",),
        required=_REQUIRED_MC,
    ),
)

# Local dev servers. They get CORS clearance but no entry in SITE_BY_HOST, so
# submissions from a dev machine record as 「未知来源」 rather than polluting the
# table with values that look like real leads.
LOCAL_DEV_ORIGINS: Final[tuple[str, ...]] = (
    "http://localhost:5173",
    "http://localhost:3000",
)

SITE_BY_HOST: Final[dict[str, Site]] = {
    host: site for site in SITES for host in site.hosts
}

# Browsers need this to make the cross-origin POST at all; it is not a
# rate-limiting or anti-abuse measure.
ALLOWED_ORIGINS: Final[tuple[str, ...]] = tuple(
    f"{scheme}://{host}"
    for site in SITES
    for host in site.hosts
    for scheme in site.schemes
) + LOCAL_DEV_ORIGINS
