"""Unit tests for FacebookCollector using respx."""

from __future__ import annotations

import httpx
import respx

from social_stats.collectors.facebook import FacebookCollector
from social_stats.config.profiles import AccountConfig
from social_stats.config.settings import Settings


@respx.mock
async def test_facebook_level_a_graph_api_bearer_header() -> None:
    """
    Verify FacebookCollector queries Meta Graph API v21.0 with Authorization Bearer
    header (never in query string) when FB_MAIN_PAGE_ID and token are configured.
    """
    def graph_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer fb_sys_token_secret"
        assert "fb_sys_token_secret" not in str(request.url)
        return httpx.Response(
            200,
            json={
                "id": "1122334455",
                "name": "Raul Caro Pastorino",
                "followers_count": 590,
                "fan_count": 545,
            },
        )

    respx.get("https://graph.facebook.com/v21.0/1122334455").mock(side_effect=graph_handler)

    settings = Settings(
        fb_main_page_id="1122334455",
        fb_main_access_token="fb_sys_token_secret",
        _env_file=None,  # type: ignore[call-arg]
    )
    collector = FacebookCollector(settings=settings)
    acc = AccountConfig(handle="raupulus", account_key="raupulus", platform="facebook")
    results = await collector.collect_batch([acc])

    assert "raupulus" in results
    assert results["raupulus"].followers_total == 590
    assert results["raupulus"].stars_total == 545


@respx.mock
async def test_facebook_level_b_opengraph_html_bilingual_fallback() -> None:
    """
    Verify FacebookCollector extracts followers and optional page likes from
    public OpenGraph meta tags in both English and Spanish locales.
    """
    respx.get("https://www.facebook.com/raupulus/").mock(
        return_value=httpx.Response(
            200,
            text=(
                '<html><head>'
                '<meta property="og:description" '
                'content="Raúl Caro Pastorino. 590 followers." />'
                '</head></html>'
            ),
        )
    )
    respx.get("https://www.facebook.com/comunidad_es/").mock(
        return_value=httpx.Response(
            200,
            text=(
                '<html><head>'
                '<meta name="description" '
                'content="Comunidad Tech. 1,2 mil Me gusta &#x2022; 1.540 seguidores." />'
                '</head></html>'
            ),
        )
    )

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    collector = FacebookCollector(settings=settings)
    accounts = [
        AccountConfig(handle="raupulus", account_key="raupulus", platform="facebook"),
        AccountConfig(handle="comunidad_es", account_key="comunidad_es", platform="facebook"),
    ]
    results = await collector.collect_batch(accounts)

    assert results["raupulus"].followers_total == 590
    assert results["raupulus"].stars_total is None

    assert results["comunidad_es"].followers_total == 1540
    assert results["comunidad_es"].stars_total == 1200
