"""Loader and validator for declarative multi-profile configuration (profiles.yaml)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

PROFILE_ID_REGEX = re.compile(r"^[a-z0-9_-]+$")
YOUTUBE_CHANNEL_ID_REGEX = re.compile(r"^UC[a-zA-Z0-9_-]{22}$")
SUPPORTED_PLATFORMS: frozenset[str] = frozenset(
    {
        "youtube",
        "twitter",
        "instagram",
        "bluesky",
        "mastodon",
        "tiktok",
        "linkedin",
    }
)


class AccountConfig(BaseModel):
    """Configuration for a single social media account or channel."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    handle: str | None = None
    instance: str | None = None
    label: str | None = None
    credentials_ref: str = "MAIN"
    account_type: Literal["personal", "organization"] = "personal"
    enabled: bool = True
    platform: str = ""
    account_key: str = ""

    def compute_account_key(self, platform: str) -> str:
        """Validate platform-specific fields and compute deterministic account_key."""
        norm_platform = platform.strip().lower()
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
    accounts: dict[str, list[AccountConfig]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_and_normalize_accounts(self) -> ProfileConfig:
        """Validate platforms, compute account_key for each account, and reject duplicates."""
        normalized_accounts: dict[str, list[AccountConfig]] = {}
        for raw_platform, account_list in self.accounts.items():
            platform = raw_platform.strip().lower()
            if platform not in SUPPORTED_PLATFORMS:
                raise ValueError(
                    f"Unsupported platform '{raw_platform}'. "
                    f"Allowed: {sorted(SUPPORTED_PLATFORMS)}"
                )
            seen_keys: set[str] = set()
            processed_list: list[AccountConfig] = []
            for acc in account_list:
                key = acc.compute_account_key(platform)
                if key in seen_keys:
                    raise ValueError(
                        f"Duplicate account '{key}' for platform '{platform}' in profile "
                        f"'{self.profile_id or self.name}'"
                    )
                seen_keys.add(key)
                updated_acc = acc.model_copy(update={"platform": platform, "account_key": key})
                processed_list.append(updated_acc)
            normalized_accounts[platform] = processed_list
        self.accounts = normalized_accounts
        return self


class ProfilesRegistry(BaseModel):
    """Root configuration model representing config/profiles.yaml."""

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
        self, *, only_enabled: bool = True
    ) -> dict[str, list[AccountConfig]]:
        """Deduplicate accounts across all profiles by (platform, account_key)."""
        result: dict[str, dict[str, AccountConfig]] = {}
        for profile in self.profiles.values():
            for platform, accounts in profile.accounts.items():
                for acc in accounts:
                    if only_enabled and not acc.enabled:
                        continue
                    platform_bucket = result.setdefault(platform, {})
                    if acc.account_key not in platform_bucket:
                        platform_bucket[acc.account_key] = acc
        return {platform: list(bucket.values()) for platform, bucket in result.items()}


def load_profiles_config(path: Path | str) -> ProfilesRegistry:
    """Load, parse, and validate profiles configuration from a YAML file."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Profiles configuration file not found: {file_path}")

    raw_text = file_path.read_text(encoding="utf-8")
    try:
        data: Any = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Malformed YAML in {file_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Invalid root structure in {file_path}: expected a YAML mapping")

    return ProfilesRegistry.model_validate(data)
