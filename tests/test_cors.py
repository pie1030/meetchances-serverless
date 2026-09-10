"""CORS 行为，以及站点注册表的守卫测试。

预检和 POST 一样重要：OPTIONS 不放行，浏览器根本不会发真正的请求，表单会在页面
上静默失败。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.website.sites import ALLOWED_ORIGINS, SITE_BY_HOST, SITES
from tests.conftest import HI, HI_STAGING, MC, MC_STAGING


def preflight(api: TestClient, origin: str):
    return api.options(
        "/contact",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


@pytest.mark.parametrize("origin", [HI, MC, HI_STAGING, MC_STAGING])
def test_preflight_allowed_for_every_site(api: TestClient, origin: str) -> None:
    resp = preflight(api, origin)

    assert resp.status_code == 200, origin
    assert resp.headers["access-control-allow-origin"] == origin
    assert "POST" in resp.headers["access-control-allow-methods"]


def test_unlisted_origin_gets_no_cors_header(api: TestClient) -> None:
    resp = preflight(api, "https://evil.example.com")

    assert resp.headers.get("access-control-allow-origin") is None


def test_staging_http_not_allowed(api: TestClient) -> None:
    """测试环境只用 HTTPS，HTTP 版 Origin 不应放行。"""
    resp = preflight(api, "http://human-intelligence.xpertiise.com")

    assert resp.headers.get("access-control-allow-origin") is None


def test_wildcard_origin_never_allowed() -> None:
    assert "*" not in ALLOWED_ORIGINS


def test_every_site_host_is_in_the_cors_allowlist() -> None:
    """守住 SITES 到白名单的派生：漏一处会让请求记成「未知来源」或发不出去。"""
    for site in SITES:
        for host in site.hosts:
            for scheme in site.schemes:
                assert f"{scheme}://{host}" in ALLOWED_ORIGINS


def test_staging_required_rules_identical_to_production() -> None:
    hi = SITE_BY_HOST["human-intelligence.cn"]
    hi_staging = SITE_BY_HOST["human-intelligence.xpertiise.com"]
    mc = SITE_BY_HOST["meetchances.com"]
    mc_staging = SITE_BY_HOST["testwebsite.meetchances.com"]

    assert hi_staging.required == hi.required
    assert mc_staging.required == mc.required


def test_staging_sources_are_distinct_from_production() -> None:
    sources = [site.source for site in SITES]
    assert len(sources) == len(set(sources)), "来源取值必须唯一，否则测试数据混入真实线索"
