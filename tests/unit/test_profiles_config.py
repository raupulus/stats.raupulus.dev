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
    assert [c.account_key for c in raupulus.accounts["crypto"]] == ["btc", "ada"]
    assert [k.account_key for k in raupulus.accounts["keycounter"]] == ["raupulus"]
    assert raupulus.accounts["keycounter"][0].interval_minutes == 1
    assert raupulus.accounts["keycounter"][0].get_poll_interval_seconds(300) == 60

    unique = registry.get_unique_accounts_by_platform(only_enabled=True)
    assert len(unique["youtube"]) == 3
    assert [c.account_key for c in unique["crypto"]] == ["btc", "ada"]
    assert [k.account_key for k in unique["keycounter"]] == ["raupulus"]
    assert "linkedin" not in unique  # Because the only linkedin account is enabled=False

    unique_all = registry.get_unique_accounts_by_platform(only_enabled=False)
    assert len(unique_all["linkedin"]) == 1


def test_load_example_json_profiles_config_and_enable_interval_features(
    tmp_path: Path,
) -> None:
    """
    Verify loading config/profiles.example.json and testing JSON configuration with
    'enable' bool (profile and account level) and 'interval_minutes' individual polling intervals.
    """
    example_json_path = (
        Path(__file__).resolve().parents[2] / "config" / "profiles.example.json"
    )
    registry = load_profiles_config(example_json_path)
    assert "raupulus" in registry.profiles
    assert "proyecto_secundario" in registry.profiles
    assert registry.profiles["raupulus"].enable is True
    assert registry.profiles["raupulus"].accounts["youtube"][0].interval_minutes == 5
    assert (
        registry.profiles["raupulus"].accounts["youtube"][0].get_poll_interval_seconds(300)
        == 300
    )
    assert registry.profiles["raupulus"].accounts["youtube"][1].interval_minutes == 10
    assert (
        registry.profiles["raupulus"].accounts["youtube"][1].get_poll_interval_seconds(300)
        == 600
    )

    # Test JSON with disabled profile, interval inheritance, and deduplication taking shortest interval
    custom_json = tmp_path / "profiles.json"
    custom_json.write_text(
        """
        {
          "version": "1.0",
          "profiles": {
            "activo": {
              "name": "Perfil Activo",
              "enable": true,
              "interval_minutes": 10,
              "accounts": {
                "twitter": [
                  {"handle": "@raupulus", "enable": true, "interval_minutes": 15}
                ],
                "keystrokes": [
                  {"handle": "raupulus", "enable": true, "interval_minutes": 1}
                ]
              }
            },
            "rapido": {
              "name": "Perfil Rápido",
              "enable": true,
              "accounts": {
                "twitter": [
                  {"handle": "raupulus", "enable": true, "interval_minutes": 3}
                ]
              }
            },
            "inactivo": {
              "name": "Perfil Inactivo",
              "enable": false,
              "accounts": {
                "bluesky": [
                  {"handle": "disabled.bsky.social", "enable": true, "interval_minutes": 2}
                ]
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    custom_reg = load_profiles_config(custom_json)
    assert custom_reg.profiles["inactivo"].enabled is False
    # Account inside disabled profile is automatically marked enabled=False
    assert custom_reg.profiles["inactivo"].accounts["bluesky"][0].enabled is False
    # Alias 'keystrokes' normalized to 'keycounter'
    assert "keycounter" in custom_reg.profiles["activo"].accounts

    unique = custom_reg.get_unique_accounts_by_platform(only_enabled=True)
    assert "bluesky" not in unique
    assert len(unique["twitter"]) == 1
    # Shortest interval_minutes between 15 and 3 is 3 minutes (180 seconds)
    assert unique["twitter"][0].interval_minutes == 3
    assert unique["twitter"][0].get_poll_interval_seconds(600) == 180

    # Malformed JSON raises clear ValueError
    broken_json = tmp_path / "broken.json"
    broken_json.write_text("{invalid json", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed JSON"):
        load_profiles_config(broken_json)


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
    with pytest.raises(ValueError, match="expected a JSON object / YAML mapping"):
        load_profiles_config(list_yaml)


def test_settings_defaults_and_credentials_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings defaults, CORS list parsing, and dynamic Instagram & Keycounter credentials."""
    monkeypatch.setenv("IG_PROYECTO_USER_ID", "17841400000000")
    monkeypatch.setenv("IG_PROYECTO_ACCESS_TOKEN", "secret_token_proyecto")
    monkeypatch.setenv("KEYCOUNTER_WORK_API_TOKEN", "work_kc_token")

    settings = Settings(
        _env_file=None,
        cors_allowed_origins="http://localhost:3000, http://10.8.0.5:8080",
        ws_public_allowed_origins="https://stats.raupulus.dev, http://localhost:8000",
        ig_main_user_id="main_id",
        ig_main_access_token="main_tok",
        keycounter_api_token="main_kc_token",
    )

    assert settings.cors_origins_list == ["http://localhost:3000", "http://10.8.0.5:8080"]
    assert settings.ws_public_origins_list == [
        "https://stats.raupulus.dev",
        "http://localhost:8000",
    ]
    assert settings.get_poll_interval("youtube") == 300
    assert settings.get_poll_interval("keycounter") == 60
    assert settings.get_poll_interval("unknown_platform") == 300
    assert settings.get_instagram_credentials("MAIN") == ("main_id", "main_tok")
    assert settings.get_instagram_credentials("proyecto") == (
        "17841400000000",
        "secret_token_proyecto",
    )
    assert settings.get_instagram_credentials("nonexistent") == ("", "")
    assert settings.get_keycounter_token("MAIN") == "main_kc_token"
    assert settings.get_keycounter_token("WORK") == "work_kc_token"


def test_public_flag_propagation_and_deduplication() -> None:
    """Verify profile/account 'public' flag defaults to True and propagates when profile is private."""
    registry = ProfilesRegistry.model_validate(
        {
            "version": "1.0",
            "profiles": {
                "public_prof": {
                    "name": "Public Profile",
                    "public": True,
                    "accounts": {
                        "bluesky": [
                            {"handle": "pub.bsky.social"},
                            {"handle": "priv.bsky.social", "public": False},
                        ]
                    },
                },
                "private_prof": {
                    "name": "Private Profile",
                    "public": False,
                    "accounts": {
                        "bluesky": [
                            {"handle": "secret.bsky.social", "public": True},
                        ]
                    },
                },
            },
        }
    )

    pub_prof = registry.get_profile("public_prof")
    assert pub_prof is not None
    assert pub_prof.public is True
    assert pub_prof.accounts["bluesky"][0].public is True
    assert pub_prof.accounts["bluesky"][1].public is False

    priv_prof = registry.get_profile("private_prof")
    assert priv_prof is not None
    assert priv_prof.public is False
    assert priv_prof.accounts["bluesky"][0].public is False

    unique_public = registry.get_unique_accounts_by_platform(only_public=True)
    assert [a.account_key for a in unique_public["bluesky"]] == ["pub.bsky.social"]
