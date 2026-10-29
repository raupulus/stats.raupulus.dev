"""Twitch dual-tier collector (Official Helix API OAuth2 App Token + Public GQL fallback)."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import httpx

from social_stats.collectors.base import (
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_USER_AGENT,
    BaseCollector,
    CollectorError,
)
from social_stats.config.profiles import AccountConfig
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics, LatestPostMetrics
from social_stats.storage.snapshot_repo import SnapshotRepository

TWITCH_OAUTH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_HELIX_BASE_URL = "https://api.twitch.tv/helix"
TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
TWITCH_PUBLIC_GQL_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

_TWITCH_GQL_QUERY = """
query($login: String!) {
  user(login: $login) {
    id
    login
    followers {
      totalCount
    }
    stream {
      id
      viewersCount
      createdAt
    }
    videos(first: 1) {
      totalCount
      edges {
        node {
          id
          viewCount
          publishedAt
        }
      }
    }
  }
}
"""


def _parse_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_iso_datetime(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return None


class TwitchCollector(BaseCollector):
    """
    Collects Twitch channel followers, VOD count, live status (is_live),
    and concurrent live viewers (live_viewers).
    Level A: Official Twitch Helix API with auto-refreshed OAuth2 client_credentials token.
    Level B: Public Twitch GraphQL endpoint fallback (zero credentials required).
    """

    platform = Platform.TWITCH
    default_poll_interval = 180

    def __init__(
        self,
        *,
        client_id: str = "",
        client_secret: str = "",
        snapshot_repo: SnapshotRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(snapshot_repo=snapshot_repo, http_client=http_client)
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self._app_token: str = ""
        self._app_token_expires_at: float = 0.0

    async def _get_helix_app_token(self, client: httpx.AsyncClient) -> str:
        now = time.monotonic()
        if self._app_token and now < self._app_token_expires_at - 60.0:
            return self._app_token

        resp = await client.post(
            TWITCH_OAUTH_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise CollectorError(
                f"Twitch OAuth2 client_credentials failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
            )

        payload: dict[str, Any] = resp.json()
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise CollectorError("Twitch OAuth2 response missing access_token")

        expires_in = int(payload.get("expires_in") or 3600)
        self._app_token = token
        self._app_token_expires_at = now + max(120, expires_in)
        return token

    async def _fetch_level_a_helix(
        self,
        client: httpx.AsyncClient,
        handle: str,
    ) -> AccountMetrics:
        token = await self._get_helix_app_token(client)
        headers = {
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        user_resp = await client.get(
            f"{TWITCH_HELIX_BASE_URL}/users",
            params={"login": handle},
            headers=headers,
        )
        if user_resp.status_code != 200:
            raise CollectorError(
                f"Twitch Helix /users failed with HTTP {user_resp.status_code}",
                status_code=user_resp.status_code,
            )
        users_data: list[dict[str, Any]] = user_resp.json().get("data") or []
        if not users_data:
            raise CollectorError(f"Twitch user '{handle}' not found on Helix", status_code=404)

        broadcaster_id = str(users_data[0]["id"])

        fol_resp = await client.get(
            f"{TWITCH_HELIX_BASE_URL}/channels/followers",
            params={"broadcaster_id": broadcaster_id, "first": 1},
            headers=headers,
        )
        if fol_resp.status_code != 200:
            raise CollectorError(
                f"Twitch Helix /channels/followers failed with HTTP {fol_resp.status_code}",
                status_code=fol_resp.status_code,
            )
        followers_total = _parse_int(fol_resp.json().get("total"))

        stream_resp = await client.get(
            f"{TWITCH_HELIX_BASE_URL}/streams",
            params={"user_id": broadcaster_id},
            headers=headers,
        )
        if stream_resp.status_code != 200:
            raise CollectorError(
                f"Twitch Helix /streams failed with HTTP {stream_resp.status_code}",
                status_code=stream_resp.status_code,
            )
        streams_data: list[dict[str, Any]] = stream_resp.json().get("data") or []
        is_live = len(streams_data) > 0
        live_viewers = _parse_int(streams_data[0].get("viewer_count")) or 0 if is_live else 0

        videos_resp = await client.get(
            f"{TWITCH_HELIX_BASE_URL}/videos",
            params={"user_id": broadcaster_id, "first": 1},
            headers=headers,
        )
        latest_post: LatestPostMetrics | None = None
        posts_total: int | None = None
        if videos_resp.status_code == 200:
            vids: list[dict[str, Any]] = videos_resp.json().get("data") or []
            if vids:
                v = vids[0]
                vid_id = v.get("id")
                latest_post = LatestPostMetrics(
                    post_id=str(vid_id) if vid_id is not None else None,
                    url=v.get("url"),
                    published_at=_parse_iso_datetime(v.get("published_at")),
                    views=_parse_int(v.get("view_count")),
                )

        if latest_post is None and is_live:
            s = streams_data[0]
            latest_post = LatestPostMetrics(
                post_id=str(s.get("id")) if s.get("id") else None,
                url=f"https://www.twitch.tv/{handle}",
                published_at=_parse_iso_datetime(s.get("started_at")),
                views=live_viewers,
            )

        return AccountMetrics(
            followers_total=followers_total,
            posts_total=posts_total,
            is_live=is_live,
            live_viewers=live_viewers,
            latest_post=latest_post,
        )

    async def _fetch_level_b_public_gql(
        self,
        client: httpx.AsyncClient,
        handle: str,
    ) -> AccountMetrics:
        resp = await client.post(
            TWITCH_GQL_URL,
            json={
                "query": _TWITCH_GQL_QUERY,
                "variables": {"login": handle},
            },
            headers={
                "Client-Id": TWITCH_PUBLIC_GQL_CLIENT_ID,
                "Content-Type": "application/json",
                "User-Agent": DEFAULT_USER_AGENT,
            },
        )
        if resp.status_code != 200:
            raise CollectorError(
                f"Twitch public GQL failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
            )

        payload: dict[str, Any] = resp.json()
        user: dict[str, Any] | None = (payload.get("data") or {}).get("user")
        if not user:
            raise CollectorError(f"Twitch user '{handle}' not found in GQL response", status_code=404)

        followers_total = _parse_int((user.get("followers") or {}).get("totalCount"))
        stream_obj = user.get("stream")
        is_live = isinstance(stream_obj, dict) and bool(stream_obj.get("id"))
        live_viewers = (
            _parse_int(stream_obj.get("viewersCount")) or 0
            if isinstance(stream_obj, dict) and is_live
            else 0
        )

        videos_obj: dict[str, Any] = user.get("videos") or {}
        posts_total = _parse_int(videos_obj.get("totalCount"))
        edges: list[dict[str, Any]] = videos_obj.get("edges") or []

        latest_post: LatestPostMetrics | None = None
        if edges:
            node: dict[str, Any] = edges[0].get("node") or {}
            vid_id = node.get("id")
            if vid_id is not None:
                latest_post = LatestPostMetrics(
                    post_id=str(vid_id),
                    url=f"https://www.twitch.tv/videos/{vid_id}",
                    published_at=_parse_iso_datetime(node.get("publishedAt")),
                    views=_parse_int(node.get("viewCount")),
                )
        elif is_live and isinstance(stream_obj, dict):
            latest_post = LatestPostMetrics(
                post_id=str(stream_obj.get("id")),
                url=f"https://www.twitch.tv/{handle}",
                published_at=_parse_iso_datetime(stream_obj.get("createdAt")),
                views=live_viewers,
            )

        return AccountMetrics(
            followers_total=followers_total,
            posts_total=posts_total,
            is_live=is_live,
            live_viewers=live_viewers,
            latest_post=latest_post,
        )

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        accounts: list[AccountConfig],
    ) -> dict[str, AccountMetrics]:
        results: dict[str, AccountMetrics] = {}
        has_helix_creds = bool(self.client_id and self.client_secret)

        for acc in accounts:
            handle = (acc.handle or acc.account_key or "").strip().lstrip("@").lower()
            if not handle:
                self.record_account_error(acc.account_key, "Twitch account missing handle")
                continue

            metrics: AccountMetrics | None = None
            if has_helix_creds:
                try:
                    metrics = await self._fetch_level_a_helix(client, handle)
                except Exception:
                    metrics = None

            if metrics is None:
                try:
                    metrics = await self._fetch_level_b_public_gql(client, handle)
                except Exception as exc:
                    self.record_account_error(acc.account_key, f"{type(exc).__name__}: {exc}")
                    continue

            results[acc.account_key] = await self.enrich_with_snapshots(acc.account_key, metrics)

        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect Twitch metrics for all configured channels."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
