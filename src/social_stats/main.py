"""FastAPI entrypoint, lifespan orchestration, and strict Read-Only middleware."""

from __future__ import annotations

import logging
import mimetypes
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from social_stats import __version__
from social_stats.api.router import api_v1_router, local_health_router, ws_router
from social_stats.collectors.base import BaseCollector
from social_stats.collectors.bluesky import BlueskyCollector
from social_stats.collectors.crypto import CryptoCollector
from social_stats.collectors.facebook import FacebookCollector
from social_stats.collectors.github import GitHubCollector
from social_stats.collectors.gitlab import GitLabCollector
from social_stats.collectors.instagram import InstagramCollector
from social_stats.collectors.keycounter import KeycounterCollector
from social_stats.collectors.linkedin import LinkedInCollector
from social_stats.collectors.mastodon import MastodonCollector
from social_stats.collectors.telegram import TelegramCollector
from social_stats.collectors.tiktok import TikTokCollector
from social_stats.collectors.twitch import TwitchCollector
from social_stats.collectors.twitter import TwitterCollector
from social_stats.collectors.youtube import YouTubeCollector
from social_stats.config.profiles import ProfilesRegistry, load_profiles_config
from social_stats.config.settings import Settings, get_settings
from social_stats.models.enums import Platform
from social_stats.services.aggregator import ProfileAggregator
from social_stats.services.scheduler import CollectorScheduler
from social_stats.services.ws_manager import WSManager
from social_stats.storage.database import Database
from social_stats.storage.snapshot_repo import SnapshotRepository
from social_stats.storage.state_store import StateStore

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("text/markdown", ".md")

ALLOWED_READONLY_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})
CACHEABLE_STATIC_PREFIXES: tuple[str, ...] = (
    "/css/",
    "/js/",
    "/images/",
    "/.well-known/",
    "/favicon.svg",
    "/logo.svg",
    "/icon-192.png",
    "/icon-192.webp",
    "/og-preview.png",
    "/og-preview.webp",
    "/site.webmanifest",
    "/robots.txt",
    "/sitemap.xml",
    "/llms.txt",
    "/index.md",
)
PUBLIC_CSP_POLICY = (
    "default-src 'self'; "
    "connect-src 'self' ws: wss: https://cloudflareinsights.com https://*.cloudflareinsights.com; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data:; "
    "script-src 'self' https://static.cloudflareinsights.com; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'none'"
)


def configure_logging(level: str = "INFO") -> None:
    """Configure structured UTC logging format and silence verbose HTTP client URL logs."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)sZ %(levelname)s [%(name)s] %(message)s",
    )
    logging.Formatter.converter = time.gmtime
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def build_default_collectors(
    settings: Settings,
    snapshot_repo: SnapshotRepository,
    db: Database | None = None,
) -> dict[Platform, BaseCollector]:
    """Instantiate all registered platform collectors."""
    collectors: dict[Platform, BaseCollector] = {
        Platform.YOUTUBE: YouTubeCollector(
            api_key=settings.youtube_api_key,
            snapshot_repo=snapshot_repo,
        ),
        Platform.BLUESKY: BlueskyCollector(snapshot_repo=snapshot_repo),
        Platform.MASTODON: MastodonCollector(snapshot_repo=snapshot_repo),
        Platform.TWITTER: TwitterCollector(
            auth_token_cookie=settings.twitter_auth_token_cookie,
            ct0_cookie=settings.twitter_ct0_cookie,
            snapshot_repo=snapshot_repo,
        ),
        Platform.INSTAGRAM: InstagramCollector(
            settings=settings,
            snapshot_repo=snapshot_repo,
            use_curl_cffi=True,
        ),
        Platform.TIKTOK: TikTokCollector(
            client_key=settings.tiktok_client_key,
            client_secret=settings.tiktok_client_secret,
            db=db,
            snapshot_repo=snapshot_repo,
            use_curl_cffi=True,
        ),
        Platform.LINKEDIN: LinkedInCollector(
            access_token=settings.linkedin_access_token,
            li_at_cookie=settings.linkedin_li_at_cookie,
            db=db,
            snapshot_repo=snapshot_repo,
        ),
        Platform.GITHUB: GitHubCollector(
            settings=settings,
            snapshot_repo=snapshot_repo,
        ),
        Platform.GITLAB: GitLabCollector(
            settings=settings,
            snapshot_repo=snapshot_repo,
        ),
        Platform.TELEGRAM: TelegramCollector(
            snapshot_repo=snapshot_repo,
        ),
        Platform.TWITCH: TwitchCollector(
            client_id=settings.twitch_client_id,
            client_secret=settings.twitch_client_secret,
            snapshot_repo=snapshot_repo,
        ),
        Platform.FACEBOOK: FacebookCollector(
            settings=settings,
            snapshot_repo=snapshot_repo,
            use_curl_cffi=True,
        ),
        Platform.CRYPTO: CryptoCollector(
            snapshot_repo=snapshot_repo,
        ),
        Platform.KEYCOUNTER: KeycounterCollector(
            settings=settings,
            snapshot_repo=snapshot_repo,
        ),
    }
    return collectors


PACKAGE_ROOT: Path = Path(__file__).resolve().parents[2]


def _resolve_profiles_path(configured_path: Path) -> Path:
    """Resolve profiles configuration path (.json or .yaml), falling back to example templates."""
    if configured_path.exists():
        return configured_path
    if not configured_path.is_absolute():
        pkg_configured = PACKAGE_ROOT / configured_path
        if pkg_configured.exists():
            return pkg_configured
    for rel in (
        "config/profiles.json",
        "config/profiles.yaml",
        "config/profiles.production.json",
        "config/profiles.example.json",
        "config/profiles.example.yaml",
    ):
        for candidate in (Path(rel), PACKAGE_ROOT / rel):
            if candidate.exists():
                return candidate
    return configured_path


def _resolve_public_dir(configured_path: Path) -> Path | None:
    """Resolve public/ static directory if present."""
    candidates: list[Path] = [configured_path]
    if not configured_path.is_absolute():
        candidates.append(PACKAGE_ROOT / configured_path)
    candidates.extend([Path("public"), PACKAGE_ROOT / "public", Path("/app/public")])
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
    return None


def _negotiate_root_accept(accept_header: str) -> str:
    """
    Evaluate HTTP Accept header for '/' or '/index.html' content negotiation.
    Returns 'html', 'markdown', or 'not_acceptable' (RFC 9110).
    """
    raw = accept_header.strip()
    if not raw:
        return "html"

    best_q: dict[str, float] = {}
    for item in raw.split(","):
        parts = [p.strip() for p in item.split(";") if p.strip()]
        if not parts:
            continue
        media_range = parts[0].lower()
        q = 1.0
        for param in parts[1:]:
            if param.lower().startswith("q="):
                try:
                    q = float(param[2:].strip())
                except ValueError:
                    q = 0.0
        q = max(0.0, min(1.0, q))
        if media_range not in best_q or q > best_q[media_range]:
            best_q[media_range] = q

    def _effective_q(mime: str, subtype_wildcard: str) -> float:
        if mime in best_q:
            return best_q[mime]
        if subtype_wildcard in best_q:
            return best_q[subtype_wildcard]
        if "*/*" in best_q:
            return best_q["*/*"]
        return 0.0

    q_html = max(
        _effective_q("text/html", "text/*"),
        _effective_q("application/xhtml+xml", "application/*"),
    )
    q_md = max(
        _effective_q("text/markdown", "text/*"),
        _effective_q("text/x-markdown", "text/*"),
    )

    if q_md <= 0.0 and q_html <= 0.0:
        return "not_acceptable"
    if q_md > q_html and ("text/markdown" in best_q or "text/x-markdown" in best_q):
        return "markdown"
    return "html"


def create_app(
    *,
    settings: Settings | None = None,
    registry: ProfilesRegistry | None = None,
    db: Database | None = None,
    state_store: StateStore | None = None,
    snapshot_repo: SnapshotRepository | None = None,
    aggregator: ProfileAggregator | None = None,
    ws_manager: WSManager | None = None,
    scheduler: CollectorScheduler | None = None,
    enable_scheduler: bool = True,
) -> FastAPI:
    """Create and configure the Read-Only FastAPI application."""
    cfg = settings if settings is not None else get_settings()
    configure_logging(cfg.log_level)
    is_production = cfg.app_env.strip().lower() == "production"

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        app_instance.state.start_monotonic = time.monotonic()

        active_db = db if db is not None else Database(cfg.sqlite_db_path)
        await active_db.connect()

        active_registry = (
            registry
            if registry is not None
            else load_profiles_config(_resolve_profiles_path(cfg.profiles_config_path))
        )
        active_snapshot_repo = (
            snapshot_repo
            if snapshot_repo is not None
            else SnapshotRepository(active_db)
        )
        active_store = (
            state_store if state_store is not None else StateStore(active_db)
        )
        await active_store.initialize_from_config_and_db(active_registry)

        active_aggregator = (
            aggregator
            if aggregator is not None
            else ProfileAggregator(active_registry, active_store)
        )
        active_ws = (
            ws_manager
            if ws_manager is not None
            else WSManager(active_aggregator)
        )
        active_collectors = build_default_collectors(
            cfg, active_snapshot_repo, active_db
        )
        active_scheduler = (
            scheduler
            if scheduler is not None
            else CollectorScheduler(
                settings=cfg,
                registry=active_registry,
                collectors=active_collectors,
                snapshot_repo=active_snapshot_repo,
                state_store=active_store,
                aggregator=active_aggregator,
                on_metric_update=active_ws.broadcast_update,
                on_status_change=active_ws.broadcast_collector_status,
            )
        )

        app_instance.state.settings = cfg
        app_instance.state.db = active_db
        app_instance.state.registry = active_registry
        app_instance.state.snapshot_repo = active_snapshot_repo
        app_instance.state.state_store = active_store
        app_instance.state.aggregator = active_aggregator
        app_instance.state.ws_manager = active_ws
        app_instance.state.scheduler = active_scheduler

        active_ws.start_heartbeat(
            lambda: max(0, int(time.monotonic() - app_instance.state.start_monotonic))
        )
        if enable_scheduler:
            active_scheduler.start()

        try:
            yield
        finally:
            if enable_scheduler:
                await active_scheduler.stop()
            await active_ws.stop_heartbeat()
            if db is None:
                await active_db.close()

    fastapi_app = FastAPI(
        title="Social Stats Read-Only API & WebSockets",
        version=__version__,
        description="Unidirectional Read-Only server for social media metrics monitoring",
        lifespan=lifespan,
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

    public_dir = _resolve_public_dir(cfg.public_dir_path)

    @fastapi_app.middleware("http")
    async def enforce_readonly_and_security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        req_path = request.url.path
        if request.method.upper() not in ALLOWED_READONLY_METHODS:
            response: Response = JSONResponse(
                status_code=405,
                headers={"Allow": "GET, HEAD, OPTIONS"},
                content={
                    "error": "method_not_allowed",
                    "message": (
                        f"El método HTTP '{request.method}' está deshabilitado. "
                        "Esta API es estrictamente de solo lectura (Read-Only)."
                    ),
                },
            )
        elif public_dir is not None and req_path in ("/", "/index.html"):
            decision = _negotiate_root_accept(request.headers.get("accept", ""))
            if decision == "not_acceptable":
                response = JSONResponse(
                    status_code=406,
                    content={
                        "error": "not_acceptable",
                        "message": "Formatos soportados: text/html, text/markdown.",
                    },
                )
            elif decision == "markdown" and (public_dir / "index.md").is_file():
                response = FileResponse(
                    public_dir / "index.md",
                    media_type="text/markdown; charset=utf-8",
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload",
            )
        if not req_path.startswith(("/docs", "/redoc")):
            response.headers.setdefault(
                "Content-Security-Policy", PUBLIC_CSP_POLICY
            )
        if req_path.startswith(CACHEABLE_STATIC_PREFIXES):
            response.headers.setdefault(
                "Cache-Control", "public, max-age=31536000"
            )
        elif req_path in ("/", "/index.html"):
            response.headers.setdefault("Cache-Control", "no-cache")
            response.headers.setdefault("Vary", "Accept")
            response.headers.setdefault(
                "Link",
                '</.well-known/ai-catalog.json>; rel="ai-catalog", '
                '</.well-known/ard.json>; rel="ard", '
                '</llms.txt>; rel="llms-txt", '
                '</index.md>; rel="alternate"; type="text/markdown"',
            )
        return response

    fastapi_app.include_router(local_health_router)
    fastapi_app.include_router(api_v1_router)
    fastapi_app.include_router(ws_router)

    if public_dir is not None:
        fastapi_app.mount(
            "/",
            StaticFiles(directory=str(public_dir), html=True, follow_symlink=False),
            name="public",
        )

    return fastapi_app


app = create_app()


def run() -> None:
    """CLI entrypoint for launching uvicorn."""
    settings = get_settings()
    uvicorn.run(
        "social_stats.main:app",
        host=settings.app_host,
        port=settings.app_port,
        ws_ping_interval=20.0,
        ws_ping_timeout=20.0,
        ws_max_size=1024,
    )
