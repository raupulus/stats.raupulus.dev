"""Authentication, Origin verification, and loopback guards for REST and WebSockets."""

from __future__ import annotations

import ipaddress
import secrets
from typing import cast

from fastapi import HTTPException, Request, WebSocket, status

from social_stats.config.settings import Settings

LOOPBACK_HOSTS: frozenset[str] = frozenset(
    {"127.0.0.1", "::1", "[::1]", "localhost", "testclient", "testserver"}
)
PROXY_FORWARDING_HEADERS: tuple[str, ...] = (
    "x-forwarded-for",
    "x-real-ip",
    "forwarded",
    "cf-connecting-ip",
    "true-client-ip",
    "x-client-ip",
)


def verify_bearer_token(candidate: str | None, expected: str) -> bool:
    """
    Compare candidate token against expected token in constant time.
    Fails closed (returns False) if expected or candidate token is empty.
    """
    expected_clean = expected.strip()
    if not expected_clean or candidate is None:
        return False
    candidate_clean = candidate.strip()
    if not candidate_clean:
        return False
    return secrets.compare_digest(candidate_clean.encode("utf-8"), expected_clean.encode("utf-8"))


def extract_http_bearer_token(request: Request) -> str | None:
    """Extract Bearer token from HTTP Authorization header."""
    auth_header = request.headers.get("authorization", "").strip()
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def require_private_api_token(request: Request) -> None:
    """FastAPI dependency enforcing valid Authorization: Bearer <API_BEARER_TOKEN>."""
    settings = cast(Settings, request.app.state.settings)
    token = extract_http_bearer_token(request)
    if not verify_bearer_token(token, settings.api_bearer_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado: se requiere un token Bearer válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def extract_ws_bearer_token(websocket: WebSocket) -> tuple[str | None, str | None]:
    """
    Extract Bearer token for private WebSocket endpoints from:
    1. Authorization: Bearer <token> header
    2. Sec-WebSocket-Protocol header (e.g. 'bearer, <token>' or 'bearer.<token>')
    3. ?token=<token> query parameter
    Returns (token, subprotocol_to_echo).
    """
    auth_header = websocket.headers.get("authorization", "").strip()
    if auth_header:
        parts = auth_header.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip(), None

    proto_header = websocket.headers.get("sec-websocket-protocol", "").strip()
    if proto_header:
        protocols = [p.strip() for p in proto_header.split(",") if p.strip()]
        if len(protocols) >= 2 and protocols[0].lower() == "bearer":
            return protocols[1], protocols[0]
        for proto in protocols:
            if proto.lower().startswith("bearer.") and len(proto) > 7:
                return proto[7:], proto

    query_token = websocket.query_params.get("token", "").strip()
    if query_token:
        return query_token, None

    return None, None


def is_local_loopback_request(request: Request) -> bool:
    """
    Verify that a request originates strictly from local container loopback (127.0.0.1 / ::1 / localhost)
    and was NOT forwarded by an external reverse proxy.
    """
    for header_name in PROXY_FORWARDING_HEADERS:
        if request.headers.get(header_name, "").strip():
            return False

    client_host = (request.client.host if request.client else "").strip().lower()
    if client_host not in LOOPBACK_HOSTS:
        return False

    raw_host = request.headers.get("host", "").strip().lower()
    if raw_host:
        if raw_host.startswith("["):
            host_only = raw_host.split("]")[0] + "]"
        else:
            host_only = raw_host.split(":")[0]
        if host_only not in LOOPBACK_HOSTS:
            return False

    return True


_TRUSTED_PROXY_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


def _is_trusted_proxy_peer(peer_host: str) -> bool:
    """Return True if the immediate socket peer is loopback or an RFC1918/ULA private reverse proxy."""
    clean = peer_host.strip().lower()
    if not clean:
        return False
    if clean in LOOPBACK_HOSTS:
        return True
    try:
        addr = ipaddress.ip_address(clean.strip("[]"))
        return any(addr in net for net in _TRUSTED_PROXY_NETWORKS)
    except ValueError:
        return False


def extract_client_ip(websocket: WebSocket) -> str:
    """
    Extract client IP address from reverse proxy headers (only when connected via
    a local/private reverse proxy) or directly from the socket peer.
    """
    peer_host = (
        websocket.client.host.strip()
        if (websocket.client and websocket.client.host)
        else ""
    )
    if not peer_host or _is_trusted_proxy_peer(peer_host):
        for header in ("cf-connecting-ip", "x-real-ip"):
            val = websocket.headers.get(header, "").strip()
            if val:
                return val[:64]
        xff = websocket.headers.get("x-forwarded-for", "").strip()
        if xff:
            first_ip = xff.split(",")[0].strip()
            if first_ip:
                return first_ip[:64]
    if peer_host:
        return peer_host[:64]
    return "unknown"


def is_allowed_public_ws_origin(
    websocket: WebSocket,
    allowed_origins: list[str],
) -> bool:
    """Validate WebSocket Origin header against configured public allowed origins."""
    normalized_allowed = {
        o.strip().rstrip("/").lower() for o in allowed_origins if o.strip()
    }
    if not normalized_allowed:
        return False
    if "*" in normalized_allowed:
        return True

    origin = websocket.headers.get("origin", "").strip().rstrip("/").lower()
    if not origin:
        return False
    return origin in normalized_allowed
