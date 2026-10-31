"""Integration tests for the Read-Only REST API v1 endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from social_stats.config.profiles import ProfilesRegistry
from social_stats.config.settings import Settings
from social_stats.main import create_app
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics
from social_stats.services.aggregator import ProfileAggregator
from social_stats.storage.database import Database
from social_stats.storage.snapshot_repo import SnapshotRepository
from social_stats.storage.state_store import StateStore


@pytest.fixture
async def seeded_api_app(
    memory_db: Database,
    snapshot_repo: SnapshotRepository,
    sample_registry: ProfilesRegistry,
    state_store: StateStore,
    aggregator: ProfileAggregator,
) -> httpx.AsyncClient:
    """Provide an httpx.AsyncClient connected to a seeded FastAPI app."""
    now = datetime.now(UTC)
    now_ts = int(now.timestamp())

    # Seed metrics for raupulus YouTube channels and proyecto_secundario YouTube channel
    m1 = await snapshot_repo.enrich_and_record(
        Platform.YOUTUBE,
        "UC1111111111111111111111",
        AccountMetrics(followers_total=15200, posts_total=280, views_total=2_100_000),
        timestamp=now_ts,
    )
    await state_store.update_account_success(
        Platform.YOUTUBE,
        "UC1111111111111111111111",
        m1,
        now=now,
    )

    m2 = await snapshot_repo.enrich_and_record(
        Platform.YOUTUBE,
        "UC2222222222222222222222",
        AccountMetrics(followers_total=3300, posts_total=60, views_total=350_120),
        timestamp=now_ts,
    )
    await state_store.update_account_success(
        Platform.YOUTUBE,
        "UC2222222222222222222222",
        m2,
        now=now,
    )

    m_sec = await snapshot_repo.enrich_and_record(
        Platform.YOUTUBE,
        "UC4444444444444444444444",
        AccountMetrics(followers_total=900, posts_total=15, views_total=12_000),
        timestamp=now_ts,
    )
    await state_store.update_account_success(
        Platform.YOUTUBE,
        "UC4444444444444444444444",
        m_sec,
        now=now,
    )

    m_btc = await snapshot_repo.enrich_and_record(
        Platform.CRYPTO,
        "btc",
        AccountMetrics(
            price_usd=81285.45,
            price_eur=72791.52,
            price_change_24h_usd=497.86,
            price_change_24h_pct=0.616,
            price_change_24h_eur=335.61,
            price_change_24h_eur_pct=0.463,
            high_24h_usd=81823.0,
            low_24h_usd=80397.14,
            high_24h_eur=73471.72,
            low_24h_eur=72050.0,
        ),
        timestamp=now_ts,
    )
    await state_store.update_account_success(
        Platform.CRYPTO,
        "btc",
        m_btc,
        now=now,
    )

    m_kc = AccountMetrics(
        pulsations_total=12_845_620,
        pulsations_today=15_420,
        pulsations_last_1h=1_850,
        clicks_total=450_120,
        clicks_today=1_200,
        clicks_last_1h=150,
        window_1h_complete=True,
        window_24h_complete=True,
    )
    await snapshot_repo.insert_snapshot(
        Platform.KEYCOUNTER,
        "raupulus",
        m_kc,
        timestamp=now_ts,
    )
    await state_store.update_account_success(
        Platform.KEYCOUNTER,
        "raupulus",
        m_kc,
        now=now,
    )

    settings = Settings(_env_file=None, api_bearer_token="test-private-token-123")
    app = create_app(
        settings=settings,
        registry=sample_registry,
        db=memory_db,
        state_store=state_store,
        snapshot_repo=snapshot_repo,
        aggregator=aggregator,
        enable_scheduler=False,
    )
    # Populate app.state directly so ASGI transport works with or without lifespan
    app.state.settings = settings
    app.state.db = memory_db
    app.state.registry = sample_registry
    app.state.snapshot_repo = snapshot_repo
    app.state.state_store = state_store
    app.state.aggregator = aggregator
    app.state.start_monotonic = 0.0

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": "Bearer test-private-token-123"},
    ) as client:
        yield client


async def test_health_and_profiles_catalog(seeded_api_app: httpx.AsyncClient) -> None:
    """Verify GET /api/v1/health and GET /api/v1/profiles."""
    health_resp = await seeded_api_app.get("/api/v1/health")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["status"] == "ok"
    assert health_data["database_ok"] is True
    assert "youtube" in health_data["collectors"]
    assert health_resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert health_resp.headers.get("X-Frame-Options") == "DENY"
    assert "default-src 'self'" in health_resp.headers.get(
        "Content-Security-Policy", ""
    )

    profiles_resp = await seeded_api_app.get("/api/v1/profiles")
    assert profiles_resp.status_code == 200
    profiles_data = profiles_resp.json()
    ids = [p["profile_id"] for p in profiles_data["profiles"]]
    assert ids == ["raupulus", "proyecto_secundario"]


async def test_private_rest_api_requires_bearer_token_and_local_healthz_protection(
    seeded_api_app: httpx.AsyncClient,
    memory_db: Database,
    sample_registry: ProfilesRegistry,
    state_store: StateStore,
    snapshot_repo: SnapshotRepository,
    aggregator: ProfileAggregator,
) -> None:
    """
    Verify:
    - /api/v1/* endpoints reject missing or invalid Bearer tokens with 401.
    - When api_bearer_token is empty, /api/v1/* fails closed with 401.
    - /healthz responds 200 on local loopback without token, but returns 403 when
      reverse-proxy headers (X-Forwarded-For, CF-Connecting-IP) or external Host are present.
    - Production mode disables /docs, /redoc, and /openapi.json.
    """
    # 1. Missing or invalid Authorization header -> 401
    for path in (
        "/api/v1/health",
        "/api/v1/profiles",
        "/api/v1/stats",
        "/api/v1/crypto",
        "/api/v1/keycounter",
    ):
        no_auth = await seeded_api_app.get(path, headers={"Authorization": ""})
        assert no_auth.status_code == 401

        bad_auth = await seeded_api_app.get(
            path, headers={"Authorization": "Bearer wrong-token"}
        )
        assert bad_auth.status_code == 401

    # 2. Local /healthz works on loopback without Authorization
    local_hz = await seeded_api_app.get("/healthz", headers={"Authorization": ""})
    assert local_hz.status_code == 200
    assert local_hz.json() == {"status": "ok", "database_ok": True}

    # 3. /healthz rejects requests forwarded by reverse proxy or external Host with 403
    proxied_xff = await seeded_api_app.get(
        "/healthz",
        headers={"Authorization": "", "X-Forwarded-For": "203.0.113.50"},
    )
    assert proxied_xff.status_code == 403

    proxied_cf = await seeded_api_app.get(
        "/healthz",
        headers={"Authorization": "", "CF-Connecting-IP": "198.51.100.12"},
    )
    assert proxied_cf.status_code == 403

    external_host = await seeded_api_app.get(
        "/healthz",
        headers={"Authorization": "", "Host": "stats.raupulus.dev"},
    )
    assert external_host.status_code == 403

    # 4. Production mode hides /docs, /redoc, /openapi.json and empty token fails closed
    prod_settings = Settings(_env_file=None, app_env="production", api_bearer_token="")
    prod_app = create_app(
        settings=prod_settings,
        registry=sample_registry,
        db=memory_db,
        state_store=state_store,
        snapshot_repo=snapshot_repo,
        aggregator=aggregator,
        enable_scheduler=False,
    )
    prod_app.state.settings = prod_settings
    prod_app.state.db = memory_db
    prod_app.state.registry = sample_registry
    prod_app.state.snapshot_repo = snapshot_repo
    prod_app.state.state_store = state_store
    prod_app.state.aggregator = aggregator
    prod_app.state.start_monotonic = 0.0

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=prod_app),
        base_url="http://127.0.0.1:8000",
    ) as prod_client:
        for schema_url in ("/docs", "/redoc", "/openapi.json"):
            r = await prod_client.get(schema_url)
            assert r.status_code == 404

        # Even if client sends a Bearer header, empty configured token fails closed
        r_api = await prod_client.get(
            "/api/v1/stats", headers={"Authorization": "Bearer any-token"}
        )
        assert r_api.status_code == 401


async def test_global_stats_and_profile_filtering(
    seeded_api_app: httpx.AsyncClient,
) -> None:
    """
    Verify GET /api/v1/stats returns all profiles and GET /api/v1/profiles/raupulus/stats
    returns exclusively raupulus's aggregated networks.
    """
    global_resp = await seeded_api_app.get("/api/v1/stats")
    assert global_resp.status_code == 200
    global_data = global_resp.json()
    assert "raupulus" in global_data["profiles"]
    assert "proyecto_secundario" in global_data["profiles"]

    # Query param filter ?profile=raupulus&platform=youtube
    filtered_resp = await seeded_api_app.get(
        "/api/v1/stats", params={"profile": "raupulus", "platform": "youtube"}
    )
    assert filtered_resp.status_code == 200
    filtered_data = filtered_resp.json()
    assert list(filtered_data["profiles"].keys()) == ["raupulus"]
    assert list(filtered_data["profiles"]["raupulus"]["platforms"].keys()) == ["youtube"]

    # Profile-specific route
    raupulus_resp = await seeded_api_app.get("/api/v1/profiles/raupulus/stats")
    assert raupulus_resp.status_code == 200
    raupulus_data = raupulus_resp.json()
    assert raupulus_data["profile_id"] == "raupulus"
    yt = raupulus_data["platforms"]["youtube"]
    assert yt["followers_total"] == 15200 + 3300
    assert yt["views_total"] == 2_100_000 + 350_120
    assert len(yt["accounts"]) == 3


async def test_history_and_404_error_responses(
    seeded_api_app: httpx.AsyncClient,
) -> None:
    """Verify GET /api/v1/profiles/{id}/history and 404/400 error payloads."""
    hist_resp = await seeded_api_app.get(
        "/api/v1/profiles/raupulus/history",
        params={
            "platform": "youtube",
            "account_key": "UC1111111111111111111111",
            "window": "24h",
        },
    )
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["profile_id"] == "raupulus"
    assert len(hist_data["series"]) == 1
    assert len(hist_data["series"][0]["points"]) == 1
    assert hist_data["series"][0]["points"][0]["followers_total"] == 15200

    # Nonexistent profile -> 404
    not_found = await seeded_api_app.get("/api/v1/profiles/inexistente/stats")
    assert not_found.status_code == 404
    assert not_found.json()["error"] == "profile_not_found"

    # Nonexistent platform -> 404
    bad_plat = await seeded_api_app.get(
        "/api/v1/profiles/raupulus/stats", params={"platform": "myspace"}
    )
    assert bad_plat.status_code == 404
    assert bad_plat.json()["error"] == "platform_not_found"

    # Invalid window -> 400
    bad_win = await seeded_api_app.get(
        "/api/v1/profiles/raupulus/history", params={"window": "999y"}
    )
    assert bad_win.status_code == 400
    assert bad_win.json()["error"] == "invalid_window"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
async def test_write_methods_return_405(
    seeded_api_app: httpx.AsyncClient, method: str
) -> None:
    """Verify strict Read-Only enforcement: POST/PUT/DELETE/PATCH return 405 Method Not Allowed."""
    resp = await seeded_api_app.request(method, "/api/v1/stats")
    assert resp.status_code == 405
    assert resp.json()["error"] == "method_not_allowed"
    assert "GET" in resp.headers.get("Allow", "")


async def test_crypto_prices_endpoint(seeded_api_app: httpx.AsyncClient) -> None:
    """Verify GET /api/v1/crypto returns BTC and ADA prices in USD and EUR, and supports ?symbol=."""
    resp = await seeded_api_app.get("/api/v1/crypto")
    assert resp.status_code == 200
    data = resp.json()
    assert "BTC" in data["assets"]
    assert "ADA" in data["assets"]
    btc = data["assets"]["BTC"]
    assert btc["symbol"] == "BTC"
    assert btc["price_usd"] == 81285.45
    assert btc["price_eur"] == 72791.52
    assert btc["price_change_24h_pct"] == 0.616
    assert btc["price_change_24h_eur_pct"] == 0.463

    # Filter by ?symbol=bitcoin (alias for BTC)
    btc_only = await seeded_api_app.get("/api/v1/crypto", params={"symbol": "bitcoin"})
    assert btc_only.status_code == 200
    assert list(btc_only.json()["assets"].keys()) == ["BTC"]

    # Unknown symbol -> 404
    not_found = await seeded_api_app.get("/api/v1/crypto", params={"symbol": "DOGE"})
    assert not_found.status_code == 404
    assert not_found.json()["error"] == "crypto_symbol_not_found"


async def test_keycounter_stats_endpoint(seeded_api_app: httpx.AsyncClient) -> None:
    """Verify GET /api/v1/keycounter returns keystrokes and clicks and supports ?account=."""
    resp = await seeded_api_app.get("/api/v1/keycounter")
    assert resp.status_code == 200
    data = resp.json()
    assert "raupulus" in data["accounts"]
    kc = data["accounts"]["raupulus"]
    assert kc["pulsations_total"] == 12_845_620
    assert kc["pulsations_today"] == 15_420
    assert kc["pulsations_last_1h"] == 1_850
    assert kc["clicks_total"] == 450_120
    assert kc["clicks_today"] == 1_200
    assert kc["clicks_last_1h"] == 150

    # Filter by ?account=raupulus
    filtered = await seeded_api_app.get("/api/v1/keycounter", params={"account": "@raupulus"})
    assert filtered.status_code == 200
    assert list(filtered.json()["accounts"].keys()) == ["raupulus"]

    # Unknown account -> 404
    not_found = await seeded_api_app.get("/api/v1/keycounter", params={"account": "inexistente"})
    assert not_found.status_code == 404
    assert not_found.json()["error"] == "keycounter_account_not_found"


async def test_public_web_entrypoint_and_dom_security(
    seeded_api_app: httpx.AsyncClient,
) -> None:
    """
    Verify:
    - GET / serves public/index.html without requiring Authorization header.
    - GET /css/styles.css contains the exact raupulus.dev blue palette tokens.
    - GET /js/app.js connects to /ws/public and uses zero dangerous DOM sinks.
    """
    import re

    index_resp = await seeded_api_app.get("/", headers={"Authorization": ""})
    assert index_resp.status_code == 200
    assert "stats.raupulus.dev" in index_resp.text
    assert "ÁMBITO DE SUPERVISIÓN" in index_resp.text
    assert "default-src 'self'" in index_resp.headers.get(
        "Content-Security-Policy", ""
    )

    css_resp = await seeded_api_app.get("/css/styles.css", headers={"Authorization": ""})
    assert css_resp.status_code == 200
    for token in (
        "#091421",
        "#050f1c",
        "#a3c9ff",
        "#3272b8",
        "#4cd6ff",
        ".profile-social-group",
        ".profile-group-platforms-grid",
    ):
        assert token in css_resp.text

    js_resp = await seeded_api_app.get("/js/app.js", headers={"Authorization": ""})
    assert js_resp.status_code == 200
    assert "/ws/public" in js_resp.text
    assert "profile-social-group" in js_resp.text
    assert "textContent" in js_resp.text
    # Ensure no executable code uses innerHTML, outerHTML, insertAdjacentHTML, document.write, or eval
    code_lines = [
        line
        for line in js_resp.text.splitlines()
        if not line.strip().startswith(("//", "/*", "*"))
    ]
    executable_js = "\n".join(code_lines)
    assert not re.search(
        r"\b(innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval)\b",
        executable_js,
    )


async def test_agentic_discovery_and_markdown_content_negotiation(
    seeded_api_app: httpx.AsyncClient,
) -> None:
    """
    Verify:
    - GET /llms.txt returns valid Markdown with H1 and links.
    - GET /.well-known/ai-catalog.json and /.well-known/ard.json return valid ARD 1.0 JSON.
    - GET / with Accept: text/markdown returns Markdown and Vary: Accept.
    - GET / with Accept: text/markdown;q=0.9, text/html;q=0.8 returns Markdown.
    - GET / with Accept: application/pdf returns 406 Not Acceptable.
    """
    llms_resp = await seeded_api_app.get("/llms.txt", headers={"Authorization": ""})
    assert llms_resp.status_code == 200
    assert llms_resp.text.startswith("# stats.raupulus.dev")
    assert "](https://" in llms_resp.text

    for catalog_path in ("/.well-known/ai-catalog.json", "/.well-known/ard.json"):
        cat_resp = await seeded_api_app.get(catalog_path, headers={"Authorization": ""})
        assert cat_resp.status_code == 200
        cat_data = cat_resp.json()
        assert cat_data["specVersion"] == "1.0"
        assert len(cat_data["entries"]) >= 2
        for entry in cat_data["entries"]:
            assert entry["identifier"].startswith("urn:air:stats.raupulus.dev:")
            assert entry["displayName"]
            assert entry["type"]
            assert entry["url"].startswith("https://stats.raupulus.dev/")

    md_resp = await seeded_api_app.get(
        "/",
        headers={"Authorization": "", "Accept": "text/markdown"},
    )
    assert md_resp.status_code == 200
    assert "text/markdown" in md_resp.headers.get("content-type", "")
    assert "Accept" in md_resp.headers.get("Vary", "")
    assert md_resp.text.startswith("# stats.raupulus.dev")

    q_resp = await seeded_api_app.get(
        "/",
        headers={
            "Authorization": "",
            "Accept": "text/html;q=0.5, text/markdown;q=0.9",
        },
    )
    assert q_resp.status_code == 200
    assert "text/markdown" in q_resp.headers.get("content-type", "")

    not_acc = await seeded_api_app.get(
        "/",
        headers={"Authorization": "", "Accept": "application/pdf"},
    )
    assert not_acc.status_code == 406

