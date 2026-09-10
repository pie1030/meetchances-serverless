"""可以提交联系表单的官网清单。

CORS 白名单、写入飞书的「来源网站」、各站必填项都从 SITES 派生，改域名只需
改这一处。
"""

from __future__ import annotations

from typing import Final, NamedTuple

# 表单字段名 -> 校验提示里的中文标签，与飞书列名一致。
FIELD_LABELS: Final[dict[str, str]] = {
    "name": "姓名",
    "job_title": "职位",
    "company": "公司",
    "contact": "联系方式",
    "requirement": "需求说明",
}


class Site(NamedTuple):
    source: str
    hosts: tuple[str, ...]
    schemes: tuple[str, ...]
    required: tuple[str, ...]
    # 是否算真实线索。测试站和未知来源为 False，群通知卡片据此降为灰色标题，
    # 不靠匹配 source 里的「（测试）」字样来判断。
    is_lead: bool = True


# 认不出来源的请求未必是恶意的（可能是 curl 或服务端调用），只校验最低限度的
# 两项，不直接拒绝。不放进 SITES：它没有域名，也不该进 CORS 白名单。
UNKNOWN_SITE: Final = Site(
    source="未知来源",
    hosts=(),
    schemes=(),
    required=("name", "contact"),
    is_lead=False,
)


# 必填项以线上表单的 * 标记为准（2026-09-04 核对）：
#   智能知识官网：姓名 职位 联系方式 公司，需求说明可选
#   一面千识官网：姓名 公司 联系方式 需求说明，无「职位」字段
_REQUIRED_HI: Final[tuple[str, ...]] = ("name", "job_title", "contact", "company")
_REQUIRED_MC: Final[tuple[str, ...]] = ("name", "company", "contact", "requirement")

# 测试站单独用带「（测试）」的来源值，方便在共享表格里筛掉测试数据；必填项直接
# 复用正式站的元组，避免两边改一处忘一处。
#
# human-intelligence.cn 和 meetchances.com 的 http 不跳转 https，浏览器会带
# http:// 的 Origin，两种协议都得放行。测试站只有 https。
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
        is_lead=False,
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
        is_lead=False,
    ),
)

# 本地开发服务器。只给 CORS 放行，不进 SITE_BY_HOST，所以本地提交会记成
# 「未知来源」，不会在表格里冒充真实线索。
LOCAL_DEV_ORIGINS: Final[tuple[str, ...]] = (
    "http://localhost:5173",
    "http://localhost:3000",
)

SITE_BY_HOST: Final[dict[str, Site]] = {
    host: site for site in SITES for host in site.hosts
}

ALLOWED_ORIGINS: Final[tuple[str, ...]] = tuple(
    f"{scheme}://{host}"
    for site in SITES
    for host in site.hosts
    for scheme in site.schemes
) + LOCAL_DEV_ORIGINS
