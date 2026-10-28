"""Shared pytest fixtures for database, configuration, and state store."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from social_stats.config.profiles import ProfilesRegistry
from social_stats.services.aggregator import ProfileAggregator
from social_stats.storage.database import Database
from social_stats.storage.snapshot_repo import SnapshotRepository
from social_stats.storage.state_store import StateStore


@pytest.fixture
async def memory_db() -> AsyncIterator[Database]:
    """Provide an initialized in-memory SQLite Database instance."""
    db = Database(":memory:")
    await db.connect()
    yield db
    await db.close()


@pytest.fixture
def snapshot_repo(memory_db: Database) -> SnapshotRepository:
    """Provide a SnapshotRepository bound to the in-memory database."""
    return SnapshotRepository(memory_db)


@pytest.fixture
def sample_registry() -> ProfilesRegistry:
    """Provide a multi-profile, multi-channel ProfilesRegistry for testing."""
    return ProfilesRegistry.model_validate(
        {
            "version": "1.0",
            "profiles": {
                "raupulus": {
                    "name": "Perfil Personal (raupulus)",
                    "description": "Redes principales",
                    "accounts": {
                        "youtube": [
                            {
                                "id": "UC1111111111111111111111",
                                "handle": "@raupulus",
                                "label": "Canal Principal",
                                "enabled": True,
                            },
                            {
                                "id": "UC2222222222222222222222",
                                "handle": "@raupulus_live",
                                "label": "Canal Directos",
                                "enabled": True,
                            },
                            {
                                "id": "UC3333333333333333333333",
                                "handle": "@raupulus_clips",
                                "label": "Canal Clips",
                                "enabled": True,
                            },
                        ],
                        "twitter": [
                            {
                                "handle": "raupulus",
                                "label": "Twitter Personal",
                                "enabled": True,
                            }
                        ],
                        "bluesky": [
                            {
                                "handle": "raupulus.dev",
                                "label": "Bluesky Personal",
                                "enabled": True,
                            }
                        ],
                        "mastodon": [
                            {
                                "instance": "mastodon.social",
                                "handle": "raupulus",
                                "label": "Mastodon Personal",
                                "enabled": True,
                            }
                        ],
                        "linkedin": [
                            {
                                "handle": "raupulus",
                                "account_type": "personal",
                                "label": "LinkedIn Personal",
                                "enabled": False,
                            }
                        ],
                    },
                },
                "proyecto_secundario": {
                    "name": "Proyecto Secundario",
                    "description": "Métricas del proyecto secundario",
                    "accounts": {
                        "youtube": [
                            {
                                "id": "UC4444444444444444444444",
                                "handle": "@proyecto_sec",
                                "label": "Canal Proyecto",
                                "enabled": True,
                            }
                        ],
                        "bluesky": [
                            {
                                "handle": "proyecto.bsky.social",
                                "label": "Bluesky Proyecto",
                                "enabled": True,
                            }
                        ],
                    },
                },
            },
        }
    )


@pytest.fixture
async def state_store(
    memory_db: Database, sample_registry: ProfilesRegistry
) -> StateStore:
    """Provide an initialized StateStore seeded with sample_registry."""
    store = StateStore(memory_db)
    await store.initialize_from_config_and_db(sample_registry)
    return store


@pytest.fixture
def aggregator(
    sample_registry: ProfilesRegistry, state_store: StateStore
) -> ProfileAggregator:
    """Provide a ProfileAggregator bound to sample_registry and state_store."""
    return ProfileAggregator(sample_registry, state_store)
