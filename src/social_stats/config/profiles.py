"""Loader and validator for declarative multi-profile configuration (profiles.json / profiles.yaml)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

PROFILE_ID_REGEX = re.compile(r"^[a-z0-9_-]+$")
YOUTUBE_CHANNEL_ID_REGEX = re.compile(r"^UC[a-zA-Z0-9_-]{22}$")
CRYPTO_SYMBOL_REGEX = re.compile(r"^[a-z0-9]{2,15}$")
CRYPTO_ALIASES: dict[str, str] = {
    "bitcoin": "btc",
    "cardano": "ada",
    "ethereum": "eth",
    "solana": "sol",
    "ripple": "xrp",
}
PLATFORM_ALIASES: dict[str, str] = {
    "keystrokes": "keycounter",
}
SUPPORTED_PLATFORMS: frozenset[str] = frozenset(
    {
        "youtube",
        "twitter",
        "instagram",
        "bluesky",
        "mastodon",
        "tiktok",
        "linkedin",
        "github",
        "gitlab",
        "telegram",
        "twitch",
        "facebook",
        "crypto",
        "keycounter",
    }
)


def _normalize_enable_and_interval_fields(data: Any) -> Any:
    """Normalize 'enable' -> 'enabled' and 'poll_interval_minutes'/'interval' -> 'interval_minutes'."""
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    if "enable" in normalized:
        enable_val = normalized.pop("enable")
        if "enabled" not in normalized:
            normalized["enabled"] = enable_val
    for alias in ("poll_interval_minutes", "interval"):
        if alias in normalized:
            interval_val = normalized.pop(alias)
            if "interval_minutes" not in normalized:
                normalized["interval_minutes"] = interval_val
    return normalized


class AccountConfig(BaseModel):
    """Configuration for a single social media account, channel, crypto asset, or keycounter."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    handle: str | None = None
    instance: str | None = None
    label: str | None = None
    credentials_ref: str = "MAIN"
    account_type: Literal["personal", "organization"] = "personal"
    enabled: bool = True
    public: bool = True
    interval_minutes: float | None = Field(default=None, gt=0)
    platform: str = ""
    account_key: str = ""

    @model_validator(mode="before")
    @classmethod
    def _preprocess_aliases(cls, data: Any) -> Any:
        return _normalize_enable_and_interval_fields(data)

    @property
    def enable(self) -> bool:
        """Alias for enabled."""
        return self.enabled

    def get_poll_interval_seconds(self, default_seconds: int) -> int:
        """Return effective polling interval in seconds for this account."""
        if self.interval_minutes is not None and self.interval_minutes > 0:
            return max(5, int(round(self.interval_minutes * 60)))
        return default_seconds

    def compute_account_key(self, platform: str) -> str:
        """Validate platform-specific fields and compute deterministic account_key."""
        raw_p = platform.strip().lower()
        norm_platform = PLATFORM_ALIASES.get(raw_p, raw_p)
        if norm_platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform '{platform}'")

        clean_id = self.id.strip() if self.id else ""
        clean_handle = self.handle.strip() if self.handle else ""
        clean_instance = self.instance.strip().lower() if self.instance else ""

        if norm_platform == "youtube":
            if not clean_id and not clean_handle:
                raise ValueError("YouTube account requires at least 'id' or 'handle'")
            if clean_id:
                if not YOUTUBE_CHANNEL_ID_REGEX.match(clean_id):
                    raise ValueError(
                        f"Invalid YouTube channel id '{clean_id}'. Expected format 'UC' + 22 chars"
                    )
                return clean_id
            normalized_handle = clean_handle.lstrip("@").lower()
            if not normalized_handle:
                raise ValueError("YouTube account handle cannot be empty")
            return normalized_handle

        if norm_platform == "mastodon":
            if not clean_instance:
                raise ValueError("Mastodon account requires 'instance'")
            normalized_handle = clean_handle.lstrip("@").lower()
            if not normalized_handle:
                raise ValueError("Mastodon account requires 'handle'")
            return f"{normalized_handle}@{clean_instance}"

        if norm_platform == "gitlab":
            eff_instance = (
                clean_instance.removeprefix("https://")
                .removeprefix("http://")
                .rstrip("/")
                or "gitlab.com"
            )
            normalized_handle = clean_handle.lstrip("@").strip("/").lower()
            if not normalized_handle:
                raise ValueError("GitLab account requires 'handle'")
            return f"{normalized_handle}@{eff_instance}"

        if norm_platform == "telegram":
            raw_tg = (
                clean_handle.removeprefix("https://t.me/s/")
                .removeprefix("http://t.me/s/")
                .removeprefix("https://t.me/")
                .removeprefix("http://t.me/")
                .removeprefix("t.me/s/")
                .removeprefix("t.me/")
                .strip("/")
                .lstrip("@")
                .lower()
            )
            if not raw_tg:
                raise ValueError("Telegram channel requires a non-empty 'handle'")
            return raw_tg

        if norm_platform == "facebook":
            raw_fb = (clean_handle or clean_id).lstrip("@").strip("/").lower()
            if not raw_fb:
                raise ValueError("Facebook account requires 'handle' or 'id'")
            return raw_fb

        if norm_platform == "crypto":
            raw_symbol = (clean_handle or clean_id).lstrip("$@").lower()
            if not raw_symbol:
                raise ValueError(
                    "Crypto account requires 'handle' or 'id' (e.g. 'BTC', 'ADA')"
                )
            normalized_symbol = CRYPTO_ALIASES.get(raw_symbol, raw_symbol)
            if not CRYPTO_SYMBOL_REGEX.match(normalized_symbol):
                raise ValueError(
                    f"Invalid crypto symbol '{raw_symbol}'. Expected 2-15 alphanumeric chars"
                )
            return normalized_symbol

        if norm_platform == "keycounter":
            raw_kc = (clean_handle or clean_id or self.credentials_ref or "main").lstrip("@").lower()
            if not raw_kc:
                raise ValueError(
                    "Keycounter account requires a non-empty 'handle', 'id', or 'credentials_ref'"
                )
            return raw_kc

        normalized_handle = clean_handle.lstrip("@").lower()
        if not normalized_handle:
            raise ValueError(f"Platform '{norm_platform}' account requires a non-empty 'handle'")
        return normalized_handle


class ProfileConfig(BaseModel):
    """Configuration for a logical profile grouping multiple social accounts."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str = ""
    name: str = Field(..., min_length=1)
    description: str | None = None
    enabled: bool = True
    public: bool = True
    interval_minutes: float | None = Field(default=None, gt=0)
    accounts: dict[str, list[AccountConfig]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _preprocess_aliases(cls, data: Any) -> Any:
        return _normalize_enable_and_interval_fields(data)

    @property
    def enable(self) -> bool:
        """Alias for enabled."""
        return self.enabled

    @model_validator(mode="after")
    def validate_and_normalize_accounts(self) -> ProfileConfig:
        """Validate platforms, compute account_key for each account, and reject duplicates."""
        normalized_accounts: dict[str, list[AccountConfig]] = {}
        for raw_platform, account_list in self.accounts.items():
            raw_p = raw_platform.strip().lower()
            platform = PLATFORM_ALIASES.get(raw_p, raw_p)
            if platform not in SUPPORTED_PLATFORMS:
                raise ValueError(
                    f"Unsupported platform '{raw_platform}'. "
                    f"Allowed: {sorted(SUPPORTED_PLATFORMS)}"
                )
            seen_keys: set[str] = set()
            processed_list: list[AccountConfig] = dict.get(normalized_accounts, platform, [])
            if processed_list:
                seen_keys.update(a.account_key for a in processed_list)
            else:
                processed_list = []

            for acc in account_list:
                key = acc.compute_account_key(platform)
                if key in seen_keys:
                    raise ValueError(
                        f"Duplicate account '{key}' for platform '{platform}' in profile "
                        f"'{self.profile_id or self.name}'"
                    )
                seen_keys.add(key)
                effective_enabled = acc.enabled and self.enabled
                effective_public = acc.public and self.public
                effective_interval = (
                    acc.interval_minutes
                    if acc.interval_minutes is not None
                    else self.interval_minutes
                )
                updated_acc = acc.model_copy(
                    update={
                        "platform": platform,
                        "account_key": key,
                        "enabled": effective_enabled,
                        "public": effective_public,
                        "interval_minutes": effective_interval,
                    }
                )
                processed_list.append(updated_acc)
            normalized_accounts[platform] = processed_list
        self.accounts = normalized_accounts
        return self


class ProfilesRegistry(BaseModel):
    """Root configuration model representing config/profiles.json or config/profiles.yaml."""

    model_config = ConfigDict(extra="forbid")

    version: str = "1.0"
    profiles: dict[str, ProfileConfig]

    @model_validator(mode="after")
    def validate_profiles_map(self) -> ProfilesRegistry:
        """Ensure profile_id keys are valid slugs and propagate profile_id into ProfileConfig."""
        if not self.profiles:
            raise ValueError("At least one profile must be defined in 'profiles'")

        updated_profiles: dict[str, ProfileConfig] = {}
        for pid, pconfig in self.profiles.items():
            if not PROFILE_ID_REGEX.match(pid):
                raise ValueError(
                    f"Invalid profile_id '{pid}'. Must match ^[a-z0-9_-]+$ (lowercase slug)"
                )
            updated_profiles[pid] = pconfig.model_copy(update={"profile_id": pid})
        self.profiles = updated_profiles
        return self

    def get_profile(self, profile_id: str) -> ProfileConfig | None:
        """Return ProfileConfig by profile_id or None if not found."""
        return self.profiles.get(profile_id)

    def get_unique_accounts_by_platform(
        self,
        *,
        only_enabled: bool = True,
        only_public: bool = False,
    ) -> dict[str, list[AccountConfig]]:
        """
        Deduplicate accounts across all profiles by (platform, account_key).
        When the same account is present in multiple profiles, merges enabled/public status
        and keeps the shortest configured interval_minutes.
        """
        result: dict[str, dict[str, AccountConfig]] = {}
        for profile in self.profiles.values():
            for platform, accounts in profile.accounts.items():
                for acc in accounts:
                    if only_enabled and not acc.enabled:
                        continue
                    if only_public and not acc.public:
                        continue
                    platform_bucket = result.setdefault(platform, {})
                    if acc.account_key not in platform_bucket:
                        platform_bucket[acc.account_key] = acc
                    else:
                        existing = platform_bucket[acc.account_key]
                        merged_enabled = existing.enabled or acc.enabled
                        merged_public = existing.public or acc.public
                        if existing.interval_minutes is not None and acc.interval_minutes is not None:
                            merged_interval: float | None = min(
                                existing.interval_minutes, acc.interval_minutes
                            )
                        else:
                            merged_interval = (
                                existing.interval_minutes
                                if existing.interval_minutes is not None
                                else acc.interval_minutes
                            )
                        platform_bucket[acc.account_key] = existing.model_copy(
                            update={
                                "enabled": merged_enabled,
                                "public": merged_public,
                                "interval_minutes": merged_interval,
                            }
                        )
        return {platform: list(bucket.values()) for platform, bucket in result.items()}


def load_profiles_config(path: Path | str) -> ProfilesRegistry:
    """Load, parse, and validate profiles configuration from a JSON or YAML file."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Profiles configuration file not found: {file_path}")

    raw_text = file_path.read_text(encoding="utf-8")
    is_json = file_path.suffix.lower() == ".json"

    if is_json:
        try:
            data: Any = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON in {file_path}: {exc}") from exc
    else:
        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise ValueError(f"Malformed YAML in {file_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Invalid root structure in {file_path}: expected a JSON object / YAML mapping"
        )

    return ProfilesRegistry.model_validate(data)
