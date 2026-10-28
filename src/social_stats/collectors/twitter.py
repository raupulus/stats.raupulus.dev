"""Twitter / X dual-tier collector (Level A Syndication API + Level B GraphQL Cookie fallback)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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

SYNDICATION_FOLLOWERS_URL = "https://cdn.syndication.twimg.com/widgets/followbutton/info.json"
SYNDICATION_TIMELINE_URL_TEMPLATE = (
    "https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}"
)
SYNDICATION_TWEET_RESULT_URL = "https://cdn.syndication.twimg.com/tweet-result"
TWITTER_GRAPHQL_USER_URL = "https://x.com/i/api/graphql/UserByScreenName"
TWITTER_GRAPHQL_TWEETS_URL = "https://x.com/i/api/graphql/UserTweets"
TWITTER_PUBLIC_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

NEXT_DATA_REGEX = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _parse_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_twitter_date(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        dt = parsedate_to_datetime(val)
        return dt.astimezone(UTC)
    except Exception:
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None


def _snowflake_sort_key(tweet: dict[str, Any]) -> int:
    raw_id = str(tweet.get("id_str") or tweet.get("id") or "0")
    try:
        return int(raw_id)
    except ValueError:
        return 0


class TwitterCollector(BaseCollector):
    """Collects Twitter/X metrics using Level B (GraphQL cookies) or Level A (Syndication API)."""

    platform = Platform.TWITTER
    default_poll_interval = 600

    def __init__(
        self,
        *,
        auth_token_cookie: str = "",
        ct0_cookie: str = "",
        snapshot_repo: SnapshotRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(snapshot_repo=snapshot_repo, http_client=http_client)
        self.auth_token_cookie = auth_token_cookie.strip()
        self.ct0_cookie = ct0_cookie.strip()

    @property
    def has_level_b_cookies(self) -> bool:
        """Return True if optional read-only session cookies are configured."""
        return bool(self.auth_token_cookie and self.ct0_cookie)

    async def _fetch_level_b_graphql(
        self, client: httpx.AsyncClient, handle: str
    ) -> AccountMetrics:
        """Query Twitter GraphQL endpoints using read-only session cookies."""
        headers = {
            "Authorization": f"Bearer {TWITTER_PUBLIC_BEARER}",
            "x-csrf-token": self.ct0_cookie,
            "Cookie": f"auth_token={self.auth_token_cookie}; ct0={self.ct0_cookie}",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        user_resp = await client.get(
            TWITTER_GRAPHQL_USER_URL,
            params={"variables": json.dumps({"screen_name": handle})},
            headers=headers,
        )
        if user_resp.status_code != 200:
            raise CollectorError(
                f"Twitter GraphQL UserByScreenName failed with HTTP {user_resp.status_code}",
                status_code=user_resp.status_code,
            )

        user_payload: dict[str, Any] = user_resp.json()
        user_result = (
            ((user_payload.get("data") or {}).get("user") or {}).get("result") or {}
        )
        legacy_user = user_result.get("legacy") or {}
        rest_id = str(user_result.get("rest_id") or "")
        if not rest_id and not legacy_user:
            raise CollectorError(f"Twitter GraphQL user '{handle}' missing result")

        followers = _parse_int(legacy_user.get("followers_count"))
        posts = _parse_int(legacy_user.get("statuses_count"))

        tweets_resp = await client.get(
            TWITTER_GRAPHQL_TWEETS_URL,
            params={"variables": json.dumps({"userId": rest_id, "count": 5})},
            headers=headers,
        )
        if tweets_resp.status_code != 200:
            raise CollectorError(
                f"Twitter GraphQL UserTweets failed with HTTP {tweets_resp.status_code}",
                status_code=tweets_resp.status_code,
            )

        tweets_payload: dict[str, Any] = tweets_resp.json()
        items: list[dict[str, Any]] = (
            tweets_payload.get("tweets")
            or ((tweets_payload.get("data") or {}).get("tweets"))
            or []
        )

        latest_post: LatestPostMetrics | None = None
        if items:
            sorted_tweets = sorted(items, key=_snowflake_sort_key, reverse=True)
            top = sorted_tweets[0]
            tid = str(top.get("id_str") or top.get("rest_id") or "")
            legacy_tweet = top.get("legacy") or top
            views_block = top.get("views") or legacy_tweet.get("ext_views") or {}
            views_val = _parse_int(views_block.get("count"))
            likes_val = _parse_int(legacy_tweet.get("favorite_count"))
            replies_val = _parse_int(legacy_tweet.get("reply_count"))
            retweets_val = _parse_int(legacy_tweet.get("retweet_count")) or 0
            quotes_val = _parse_int(legacy_tweet.get("quote_count")) or 0
            shares_val = (
                retweets_val + quotes_val
                if (
                    legacy_tweet.get("retweet_count") is not None
                    or legacy_tweet.get("quote_count") is not None
                )
                else None
            )
            if tid:
                latest_post = LatestPostMetrics(
                    post_id=tid,
                    url=f"https://x.com/{handle}/status/{tid}",
                    published_at=_parse_twitter_date(legacy_tweet.get("created_at")),
                    views=views_val,
                    likes=likes_val,
                    comments=replies_val,
                    shares=shares_val,
                )

        return AccountMetrics(
            followers_total=followers,
            posts_total=posts,
            views_total=None,
            latest_post=latest_post,
        )

    async def _fetch_syndication_followers_batch(
        self, client: httpx.AsyncClient, handles: list[str]
    ) -> dict[str, int]:
        """Query syndication followbutton/info.json for a batch of screen_names."""
        if not handles:
            return {}
        resp = await client.get(
            SYNDICATION_FOLLOWERS_URL,
            params={"screen_names": ",".join(handles)},
            headers={"User-Agent": DEFAULT_USER_AGENT},
        )
        if resp.status_code != 200:
            raise CollectorError(
                f"Twitter syndication followbutton failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        data = resp.json()
        out: dict[str, int] = {}
        if isinstance(data, list):
            for entry in data:
                sname = str(entry.get("screen_name", "")).lower()
                fcount = _parse_int(entry.get("followers_count"))
                if sname and fcount is not None:
                    out[sname] = fcount
        return out

    async def _fetch_syndication_timeline(
        self,
        client: httpx.AsyncClient,
        handle: str,
        batch_followers: int | None,
    ) -> AccountMetrics:
        """Extract posts_total and latest tweet from syndication timeline-profile __NEXT_DATA__."""
        url = SYNDICATION_TIMELINE_URL_TEMPLATE.format(handle=handle)
        resp = await client.get(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        if resp.status_code != 200:
            raise CollectorError(
                f"Twitter syndication timeline failed for '{handle}' with HTTP {resp.status_code}",
                status_code=resp.status_code,
            )

        text = resp.text
        match = NEXT_DATA_REGEX.search(text)
        if match:
            next_data: dict[str, Any] = json.loads(match.group(1))
        else:
            next_data = resp.json()

        entries: list[dict[str, Any]] = (
            ((next_data.get("props") or {}).get("pageProps") or {})
            .get("timeline", {})
            .get("entries")
            or []
        )

        followers_total = batch_followers
        posts_total: int | None = None
        own_tweets: list[dict[str, Any]] = []

        for entry in entries:
            tweet = (entry.get("content") or {}).get("tweet")
            if not isinstance(tweet, dict):
                continue
            user = tweet.get("user") or {}
            if posts_total is None and "statuses_count" in user:
                posts_total = _parse_int(user.get("statuses_count"))
            if followers_total is None:
                followers_total = _parse_int(
                    user.get("normal_followers_count") or user.get("followers_count")
                )
            if tweet.get("retweeted_status") is None:
                own_tweets.append(tweet)

        latest_post: LatestPostMetrics | None = None
        if own_tweets:
            own_tweets.sort(key=_snowflake_sort_key, reverse=True)
            newest = own_tweets[0]
            tid = str(newest.get("id_str") or newest.get("id") or "")
            views_val = _parse_int((newest.get("ext_views") or {}).get("count"))

            if views_val is None and tid:
                try:
                    tr_resp = await client.get(
                        SYNDICATION_TWEET_RESULT_URL,
                        params={"id": tid, "token": "x"},
                        headers={"User-Agent": DEFAULT_USER_AGENT},
                    )
                    if tr_resp.status_code == 200:
                        tr_data: dict[str, Any] = tr_resp.json()
                        views_val = _parse_int(
                            tr_data.get("views_count")
                            or (tr_data.get("ext_views") or {}).get("count")
                        )
                except Exception:
                    pass

            likes_val = _parse_int(newest.get("favorite_count"))
            replies_val = _parse_int(newest.get("reply_count"))
            retweets_val = _parse_int(newest.get("retweet_count")) or 0
            quotes_val = _parse_int(newest.get("quote_count")) or 0
            shares_val = (
                retweets_val + quotes_val
                if (
                    newest.get("retweet_count") is not None
                    or newest.get("quote_count") is not None
                )
                else None
            )

            if tid:
                latest_post = LatestPostMetrics(
                    post_id=tid,
                    url=f"https://x.com/{handle}/status/{tid}",
                    published_at=_parse_twitter_date(newest.get("created_at")),
                    views=views_val,
                    likes=likes_val,
                    comments=replies_val,
                    shares=shares_val,
                )

        if followers_total is None and posts_total is None:
            raise CollectorError(
                f"Twitter syndication produced no metrics for '{handle}'"
            )

        return AccountMetrics(
            followers_total=followers_total,
            posts_total=posts_total,
            views_total=None,
            latest_post=latest_post,
        )

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        accounts: list[AccountConfig],
    ) -> dict[str, AccountMetrics]:
        results: dict[str, AccountMetrics] = {}
        need_syndication: list[AccountConfig] = []

        if self.has_level_b_cookies:
            for acc in accounts:
                handle = (acc.handle or acc.account_key).lstrip("@").lower()
                try:
                    metrics = await self._fetch_level_b_graphql(client, handle)
                    enriched = await self.enrich_with_snapshots(acc.account_key, metrics)
                    results[acc.account_key] = enriched
                except Exception:
                    # Transparent fallback from Level B to Level A (Syndication)
                    need_syndication.append(acc)
        else:
            need_syndication = list(accounts)

        if not need_syndication:
            return results

        handles = [
            (acc.handle or acc.account_key).lstrip("@").lower()
            for acc in need_syndication
        ]
        try:
            followers_map = await self._fetch_syndication_followers_batch(client, handles)
        except Exception:
            followers_map = {}

        for acc in need_syndication:
            handle = (acc.handle or acc.account_key).lstrip("@").lower()
            try:
                base_metrics = await self._fetch_syndication_timeline(
                    client,
                    handle,
                    followers_map.get(handle),
                )
                enriched = await self.enrich_with_snapshots(acc.account_key, base_metrics)
                results[acc.account_key] = enriched
            except Exception as exc:
                self.record_account_error(acc.account_key, f"{type(exc).__name__}: {exc}")

        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect Twitter/X metrics for all active accounts."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
