"""Unit tests for configuration loader (profiles.yaml and Settings)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from social_stats.config.profiles import (
    ProfilesRegistry,
    load_profiles_config,
)
from social_stats.config.settings import Settings


def test_load_example_profiles_config() -> None:
    """Verify that config/profiles.example.yaml loads and validates cleanly."""
    example_path = Path(__file__).resolve().parents[2] / "config" / "profiles.example.yaml"
    registry = load_profiles_config(example_path)

    assert registry.version == "1.0"
    assert "raupulus" in registry.profiles
    assert "proyecto_secundario" in registry.profiles

    raupulus = registry.get_profile("raupulus")
    assert raupulus is not None
    assert raupulus.profile_id == "raupulus"
    assert len(raupulus.accounts["youtube"]) == 2
    assert raupulus.accounts["youtube"][0].account_key == "UCxxxxxxxxxxxxxxxxxxxxxx"
    assert raupulus.accounts["youtube"][1].account_key == "UCyyyyyyyyyyyyyyyyyyyyyy"
    assert raupulus.accounts["mastodon"][0].account_key == "raupulus@mastodon.social"
    assert raupulus.accounts["bluesky"][0].account_key == "raupulus.dev"
    assert raupulus.accounts["linkedin"][0].enabled is False

    unique = registry.get_unique_accounts_by_platform(only_enabled=True)
    assert len(unique["youtube"]) == 3
    assert "linkedin" not in unique  # Because the only linkedin account is enabled=False

    unique_all = registry.get_unique_accounts_by_platform(only_enabled=False)
    assert len(unique_all["linkedin"]) == 1


def test_deduplication_across_profiles(tmp_path: Path) -> None:
    """Verify that shared accounts across different profiles are deduplicated for collection."""
    yaml_content = """
version: "1.0"
profiles:
  profile_a:
    name: "Profile A"
    accounts:
      youtube:
        - id: "UC1111111111111111111111"
          handle: "@shared"
        - handle: "@OnlyHandleChannel"
      bluesky:
        - handle: "@Shared.Bsky.Social"
  profile_b:
    name: "Profile B"
    accounts:
      youtube:
        - id: "UC1111111111111111111111"
          handle: "@shared"
      bluesky:
        - handle: "shared.bsky.social"
"""
    cfg_file = tmp_path / "profiles.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")

    registry = load_profiles_config(cfg_file)
    unique = registry.get_unique_accounts_by_platform()

    assert [acc.account_key for acc in unique["youtube"]] == [
        "UC1111111111111111111111",
        "onlyhandlechannel",
    ]
    assert [acc.account_key for acc in unique["bluesky"]] == ["shared.bsky.social"]


def test_reject_invalid_profile_id(tmp_path: Path) -> None:
    """Verify rejection of non-slug profile_id keys."""
    yaml_content = """
version: "1.0"
profiles:
  "Invalid Profile!":
    name: "Bad ID"
    accounts: {}
"""
    cfg_file = tmp_path / "bad_id.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(ValidationError, match="Invalid profile_id"):
        load_profiles_config(cfg_file)


def test_reject_duplicate_account_within_same_profile() -> None:
    """Verify rejection when the same account appears twice in the same profile & platform."""
    data = {
        "version": "1.0",
        "profiles": {
            "raupulus": {
                "name": "Duplicate Test",
                "accounts": {
                    "twitter": [
                        {"handle": "@raupulus"},
                        {"handle": "RAUPULUS"},
                    ]
                },
            }
        },
    }
    with pytest.raises(ValidationError, match="Duplicate account 'raupulus'"):
        ProfilesRegistry.model_validate(data)


def test_reject_invalid_youtube_and_mastodon_configs() -> None:
    """Verify platform-specific account validation errors."""
    # YouTube without id or handle
    with pytest.raises(ValidationError, match="requires at least 'id' or 'handle'"):
        ProfilesRegistry.model_validate(
            {
                "profiles": {
                    "p1": {"name": "P1", "accounts": {"youtube": [{"label": "No ID"}]}}
                }
            }
        )

    # YouTube with malformed UC id
    with pytest.raises(ValidationError, match="Invalid YouTube channel id"):
        ProfilesRegistry.model_validate(
            {
                "profiles": {
                    "p1": {"name": "P1", "accounts": {"youtube": [{"id": "UC_TOO_SHORT"}]}}
                }
            }
        )

    # Mastodon without instance
    with pytest.raises(ValidationError, match="Mastodon account requires 'instance'"):
        ProfilesRegistry.model_validate(
            {
                "profiles": {
                    "p1": {"name": "P1", "accounts": {"mastodon": [{"handle": "user"}]}}
                }
            }
        )

    # Unsupported platform
    with pytest.raises(ValidationError, match="Unsupported platform"):
        ProfilesRegistry.model_validate(
            {
                "profiles": {
                    "p1": {"name": "P1", "accounts": {"myspace": [{"handle": "tom"}]}}
                }
            }
        )


def test_malformed_yaml_and_missing_file(tmp_path: Path) -> None:
    """Verify clear error messages on missing file or broken YAML syntax."""
    with pytest.raises(FileNotFoundError):
        load_profiles_config(tmp_path / "nonexistent.yaml")

    bad_yaml = tmp_path / "broken.yaml"
    bad_yaml.write_text("profiles:\n  - [unclosed", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed YAML"):
        load_profiles_config(bad_yaml)

    list_yaml = tmp_path / "list.yaml"
    list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a YAML mapping"):
        load_profiles_config(list_yaml)


def test_settings_defaults_and_credentials_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings defaults, CORS list parsing, and dynamic Instagram credentials."""
    monkeypatch.setenv("IG_PROYECTO_USER_ID", "17841400000000")
    monkeypatch.setenv("IG_PROYECTO_ACCESS_TOKEN", "secret_token_proyecto")

    settings = Settings(
        cors_allowed_origins="http://localhost:3000, http://10.8.0.5:8080",
        ig_main_user_id="main_id",
        ig_main_access_token="main_tok",
    )

    assert settings.cors_origins_list == ["http://localhost:3000", "http://10.8.0.5:8080"]
    assert settings.get_poll_interval("youtube") == 300
    assert settings.get_poll_interval("unknown_platform") == 300
    assert settings.get_instagram_credentials("MAIN") == ("main_id", "main_tok")
    assert settings.get_instagram_credentials("proyecto") == (
        "17841400000000",
        "secret_token_proyecto",
    )
    assert settings.get_instagram_credentials("nonexistent") == ("", "")
