"""Profile aggregator projecting unique account states into per-profile views."""

from __future__ import annotations

from datetime import UTC, datetime

from social_stats.config.profiles import (
    CRYPTO_ALIASES,
    AccountConfig,
    ProfileConfig,
    ProfilesRegistry,
)
from social_stats.models.api import (
    CollectorHealthSummary,
    CryptoAssetPrice,
    CryptoPricesResponse,
    GlobalStatsResponse,
    KeycounterAccountStats,
    KeycounterStatsResponse,
    ProfileCatalogItem,
    ProfilesCatalogResponse,
)
from social_stats.models.enums import CollectorStatus, Platform
from social_stats.models.metrics import AccountState, PlatformSummary, ProfileStats
from social_stats.storage.state_store import StateStore

KEYCOUNTER_PRIVATE_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "pulsations_today",
        "pulsations_last_1h",
        "clicks_today",
        "clicks_last_1h",
    }
)


def sanitize_account_state_for_public(state: AccountState) -> AccountState:
    """
    Redact private operational metadata and non-public metrics for /ws/public:
    - Never expose error_message or last_attempt_at.
    - For KEYCOUNTER, only expose lifetime totals (pulsations_total, clicks_total),
      setting 1h and 24h/today fields to None.
    """
    metrics = state.metrics
    if state.platform == Platform.KEYCOUNTER:
        metrics = metrics.model_copy(
            update={
                "pulsations_today": None,
                "pulsations_last_1h": None,
                "clicks_today": None,
                "clicks_last_1h": None,
                "window_1h_complete": False,
                "window_24h_complete": False,
            }
        )
    return state.model_copy(
        update={
            "error_message": None,
            "last_attempt_at": None,
            "metrics": metrics,
        }
    )


def compute_platform_status(accounts: list[AccountState]) -> CollectorStatus:
    """
    Compute aggregated CollectorStatus according to deterministic precedence rules:
    1. All accounts DISABLED (or empty) -> DISABLED
    2. All active accounts HEALTHY -> HEALTHY
    3. All active accounts ERROR -> ERROR
    4. Any active account STALE or mixed ERROR/HEALTHY -> STALE
    """
    active = [acc for acc in accounts if acc.status != CollectorStatus.DISABLED]
    if not active:
        return CollectorStatus.DISABLED

    statuses = {acc.status for acc in active}
    if statuses == {CollectorStatus.HEALTHY}:
        return CollectorStatus.HEALTHY
    if statuses == {CollectorStatus.ERROR}:
        return CollectorStatus.ERROR
    return CollectorStatus.STALE


def _sum_nullable_ints(values: list[int | None]) -> int | None:
    """Sum non-None integer values, returning None if all values are None."""
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present)


class ProfileAggregator:
    """Aggregates account states from StateStore into ProfileStats and GlobalStatsResponse."""

    def __init__(self, registry: ProfilesRegistry, state_store: StateStore) -> None:
        self.registry = registry
        self.state_store = state_store

    def _resolve_account_state(
        self, platform: Platform, acc_cfg: AccountConfig
    ) -> AccountState:
        """Fetch AccountState from StateStore or construct default state from config."""
        stored = self.state_store.get_account_state(platform, acc_cfg.account_key)
        if stored is not None:
            return stored.model_copy(
                update={
                    "handle": acc_cfg.handle or stored.handle,
                    "label": acc_cfg.label or stored.label,
                    "status": (
                        CollectorStatus.DISABLED
                        if not acc_cfg.enabled
                        else stored.status
                    ),
                }
            )
        return AccountState(
            platform=platform,
            account_key=acc_cfg.account_key,
            handle=acc_cfg.handle,
            label=acc_cfg.label,
            status=CollectorStatus.DISABLED if not acc_cfg.enabled else CollectorStatus.HEALTHY,
        )

    def build_platform_summary(
        self,
        platform: Platform,
        account_configs: list[AccountConfig],
        *,
        public_only: bool = False,
    ) -> PlatformSummary:
        """Build aggregated PlatformSummary for a list of AccountConfig in a profile."""
        filtered_configs = (
            [cfg for cfg in account_configs if cfg.enabled and cfg.public]
            if public_only
            else account_configs
        )
        account_states = [
            self._resolve_account_state(platform, cfg) for cfg in filtered_configs
        ]
        if public_only:
            account_states = [
                sanitize_account_state_for_public(st)
                for st in account_states
                if st.status != CollectorStatus.DISABLED
            ]

        active_states = [
            st for st in account_states if st.status != CollectorStatus.DISABLED
        ]
        source_states = active_states if active_states else account_states

        followers_total = sum(
            st.metrics.followers_total or 0 for st in source_states
        )
        posts_total = sum(st.metrics.posts_total or 0 for st in source_states)

        followers_last_24h = _sum_nullable_ints(
            [st.metrics.followers_last_24h for st in source_states]
        )
        views_total = _sum_nullable_ints(
            [st.metrics.views_total for st in source_states]
        )
        views_last_24h = _sum_nullable_ints(
            [st.metrics.views_last_24h for st in source_states]
        )
        views_last_1h = _sum_nullable_ints(
            [st.metrics.views_last_1h for st in source_states]
        )
        stars_total = _sum_nullable_ints(
            [st.metrics.stars_total for st in source_states]
        )
        forks_total = _sum_nullable_ints(
            [st.metrics.forks_total for st in source_states]
        )
        live_flags = [
            st.metrics.is_live for st in source_states if st.metrics.is_live is not None
        ]
        is_live: bool | None = any(live_flags) if live_flags else None
        live_viewers = _sum_nullable_ints(
            [st.metrics.live_viewers for st in source_states]
        )
        pulsations_total = _sum_nullable_ints(
            [st.metrics.pulsations_total for st in source_states]
        )
        pulsations_today = _sum_nullable_ints(
            [st.metrics.pulsations_today for st in source_states]
        )
        pulsations_last_1h = _sum_nullable_ints(
            [st.metrics.pulsations_last_1h for st in source_states]
        )
        clicks_total = _sum_nullable_ints(
            [st.metrics.clicks_total for st in source_states]
        )
        clicks_today = _sum_nullable_ints(
            [st.metrics.clicks_today for st in source_states]
        )
        clicks_last_1h = _sum_nullable_ints(
            [st.metrics.clicks_last_1h for st in source_states]
        )

        status = compute_platform_status(account_states)

        return PlatformSummary(
            platform=platform,
            accounts_count=len(account_states),
            status=status,
            followers_total=followers_total,
            followers_last_24h=followers_last_24h,
            posts_total=posts_total,
            views_total=views_total,
            views_last_24h=views_last_24h,
            views_last_1h=views_last_1h,
            stars_total=stars_total,
            forks_total=forks_total,
            is_live=is_live,
            live_viewers=live_viewers,
            pulsations_total=pulsations_total,
            pulsations_today=pulsations_today,
            pulsations_last_1h=pulsations_last_1h,
            clicks_total=clicks_total,
            clicks_today=clicks_today,
            clicks_last_1h=clicks_last_1h,
            accounts=account_states,
        )

    def get_profile_stats(
        self,
        profile_id: str,
        *,
        platform_filter: Platform | None = None,
        include_disabled_platforms: bool = False,
        public_only: bool = False,
        now: datetime | None = None,
    ) -> ProfileStats | None:
        """Build ProfileStats for a single profile_id, or return None if profile does not exist."""
        pconfig: ProfileConfig | None = self.registry.get_profile(profile_id)
        if pconfig is None:
            return None
        if public_only and (not pconfig.public or not pconfig.enable):
            return None

        ts = now if now is not None else datetime.now(UTC)
        platforms_map: dict[Platform, PlatformSummary] = {}
        latest_update: datetime | None = None

        for platform_str, acc_configs in pconfig.accounts.items():
            platform = Platform(platform_str)
            if platform_filter is not None and platform != platform_filter:
                continue

            if public_only:
                public_enabled = [
                    c for c in acc_configs if c.enabled and c.public
                ]
                if not public_enabled:
                    continue
                configs_to_use = public_enabled
            else:
                enabled_configs = [c for c in acc_configs if c.enabled]
                if not enabled_configs and not include_disabled_platforms:
                    continue
                configs_to_use = (
                    acc_configs if include_disabled_platforms else enabled_configs
                )

            summary = self.build_platform_summary(
                platform,
                configs_to_use,
                public_only=public_only,
            )
            if public_only and not summary.accounts:
                continue

            platforms_map[platform] = summary

            for acc_state in summary.accounts:
                if acc_state.last_updated_at is not None and (
                    latest_update is None or acc_state.last_updated_at > latest_update
                ):
                    latest_update = acc_state.last_updated_at

        return ProfileStats(
            profile_id=pconfig.profile_id,
            name=pconfig.name,
            description=pconfig.description,
            updated_at=latest_update if latest_update is not None else ts,
            platforms=platforms_map,
        )

    def get_global_stats(
        self,
        *,
        profile_filter: str | None = None,
        platform_filter: Platform | None = None,
        include_disabled_platforms: bool = False,
        public_only: bool = False,
        now: datetime | None = None,
    ) -> GlobalStatsResponse:
        """Build GlobalStatsResponse across all profiles (or filtered subset)."""
        ts = now if now is not None else datetime.now(UTC)
        profiles_out: dict[str, ProfileStats] = {}

        target_ids = (
            [profile_filter]
            if profile_filter is not None
            else list(self.registry.profiles.keys())
        )
        for pid in target_ids:
            pstats = self.get_profile_stats(
                pid,
                platform_filter=platform_filter,
                include_disabled_platforms=include_disabled_platforms,
                public_only=public_only,
                now=ts,
            )
            if pstats is not None:
                profiles_out[pid] = pstats

        return GlobalStatsResponse(generated_at=ts, profiles=profiles_out)

    def get_profiles_catalog(
        self,
        *,
        public_only: bool = False,
        now: datetime | None = None,
    ) -> ProfilesCatalogResponse:
        """Build ProfilesCatalogResponse for GET /api/v1/profiles."""
        ts = now if now is not None else datetime.now(UTC)
        items: list[ProfileCatalogItem] = []

        for pid, pconfig in self.registry.profiles.items():
            if public_only and (not pconfig.public or not pconfig.enable):
                continue
            active_platforms: list[Platform] = []
            total_enabled_accounts = 0
            for platform_str, acc_list in pconfig.accounts.items():
                enabled_in_platform = [
                    a
                    for a in acc_list
                    if a.enabled and (not public_only or a.public)
                ]
                if enabled_in_platform:
                    active_platforms.append(Platform(platform_str))
                    total_enabled_accounts += len(enabled_in_platform)

            items.append(
                ProfileCatalogItem(
                    profile_id=pid,
                    name=pconfig.name,
                    description=pconfig.description,
                    platforms=active_platforms,
                    accounts_count=total_enabled_accounts,
                )
            )

        return ProfilesCatalogResponse(generated_at=ts, profiles=items)

    def get_global_crypto_summary(
        self,
        *,
        public_only: bool = False,
    ) -> PlatformSummary:
        """Build global PlatformSummary for all configured crypto assets."""
        unique_crypto = self.registry.get_unique_accounts_by_platform(
            only_enabled=not public_only,
            only_public=public_only,
        ).get(Platform.CRYPTO.value, [])
        return self.build_platform_summary(
            Platform.CRYPTO,
            unique_crypto,
            public_only=public_only,
        )

    def is_account_public(
        self,
        profile_id: str,
        platform: Platform,
        account_key: str,
    ) -> bool:
        """Return True if the profile and the specific account within it are enabled and public."""
        if profile_id == "global" and platform == Platform.CRYPTO:
            for acc in self.registry.crypto:
                if acc.account_key == account_key and acc.enabled and acc.public:
                    return True
            return False
        pconfig = self.registry.get_profile(profile_id)
        if pconfig is None or not pconfig.enable or not pconfig.public:
            return False
        for acc in pconfig.accounts.get(str(platform), []):
            if acc.account_key == account_key and acc.enabled and acc.public:
                return True
        return False

    def get_profiles_referencing_account(
        self, platform: Platform, account_key: str
    ) -> list[tuple[str, AccountConfig]]:
        """Return list of (profile_id, AccountConfig) that include an enabled account."""
        matches: list[tuple[str, AccountConfig]] = []
        for pid, pconfig in self.registry.profiles.items():
            for acc in pconfig.accounts.get(str(platform), []):
                if acc.enabled and acc.account_key == account_key:
                    matches.append((pid, acc))
        if platform == Platform.CRYPTO and not matches:
            for acc in self.registry.crypto:
                if acc.enabled and acc.account_key == account_key:
                    matches.append(("global", acc))
        return matches

    def get_collectors_health(self) -> dict[Platform, CollectorHealthSummary]:
        """Build per-platform health summaries across all unique accounts."""
        summaries: dict[Platform, CollectorHealthSummary] = {}
        unique_all = self.registry.get_unique_accounts_by_platform(only_enabled=False)

        for platform_str, acc_configs in unique_all.items():
            platform = Platform(platform_str)
            states = [self._resolve_account_state(platform, cfg) for cfg in acc_configs]
            active_states = [s for s in states if s.status != CollectorStatus.DISABLED]

            healthy_cnt = sum(1 for s in active_states if s.status == CollectorStatus.HEALTHY)
            stale_cnt = sum(1 for s in active_states if s.status == CollectorStatus.STALE)
            error_cnt = sum(1 for s in active_states if s.status == CollectorStatus.ERROR)

            last_success: datetime | None = None
            for s in active_states:
                if s.last_updated_at is not None and (
                    last_success is None or s.last_updated_at > last_success
                ):
                    last_success = s.last_updated_at

            summaries[platform] = CollectorHealthSummary(
                platform=platform,
                status=compute_platform_status(states),
                accounts_total=len(active_states),
                accounts_healthy=healthy_cnt,
                accounts_stale=stale_cnt,
                accounts_error=error_cnt,
                last_success_at=last_success,
            )

        return summaries

    def get_crypto_prices(
        self,
        *,
        symbol_filter: str | None = None,
        now: datetime | None = None,
    ) -> CryptoPricesResponse:
        """Build CryptoPricesResponse across all configured crypto accounts."""
        ts = now if now is not None else datetime.now(UTC)
        unique_crypto = self.registry.get_unique_accounts_by_platform(
            only_enabled=True
        ).get(Platform.CRYPTO.value, [])

        norm_filter: str | None = None
        if symbol_filter is not None:
            raw_sym = symbol_filter.strip().lstrip("$@").lower()
            norm_filter = CRYPTO_ALIASES.get(raw_sym, raw_sym)

        assets: dict[str, CryptoAssetPrice] = {}
        for acc_cfg in unique_crypto:
            if norm_filter is not None and acc_cfg.account_key != norm_filter:
                continue
            state = self._resolve_account_state(Platform.CRYPTO, acc_cfg)
            m = state.metrics
            sym_upper = acc_cfg.account_key.upper()
            assets[sym_upper] = CryptoAssetPrice(
                symbol=sym_upper,
                account_key=acc_cfg.account_key,
                label=state.label,
                status=state.status,
                last_updated_at=state.last_updated_at,
                price_usd=m.price_usd,
                price_eur=m.price_eur,
                price_change_24h_usd=m.price_change_24h_usd,
                price_change_24h_pct=m.price_change_24h_pct,
                price_change_24h_eur=m.price_change_24h_eur,
                price_change_24h_eur_pct=m.price_change_24h_eur_pct,
                high_24h_usd=m.high_24h_usd,
                low_24h_usd=m.low_24h_usd,
                high_24h_eur=m.high_24h_eur,
                low_24h_eur=m.low_24h_eur,
            )

        return CryptoPricesResponse(generated_at=ts, assets=assets)

    def get_keycounter_stats(
        self,
        *,
        account_filter: str | None = None,
        now: datetime | None = None,
    ) -> KeycounterStatsResponse:
        """Build KeycounterStatsResponse across all configured keycounter accounts."""
        ts = now if now is not None else datetime.now(UTC)
        unique_kc = self.registry.get_unique_accounts_by_platform(
            only_enabled=True
        ).get(Platform.KEYCOUNTER.value, [])

        norm_filter = (
            account_filter.strip().lstrip("@").lower()
            if account_filter is not None
            else None
        )

        accounts_out: dict[str, KeycounterAccountStats] = {}
        for acc_cfg in unique_kc:
            if norm_filter is not None and acc_cfg.account_key != norm_filter:
                continue
            state = self._resolve_account_state(Platform.KEYCOUNTER, acc_cfg)
            m = state.metrics
            accounts_out[acc_cfg.account_key] = KeycounterAccountStats(
                account_key=acc_cfg.account_key,
                handle=state.handle,
                label=state.label,
                status=state.status,
                last_updated_at=state.last_updated_at,
                error_message=state.error_message,
                pulsations_total=m.pulsations_total,
                pulsations_today=m.pulsations_today,
                pulsations_last_1h=m.pulsations_last_1h,
                clicks_total=m.clicks_total,
                clicks_today=m.clicks_today,
                clicks_last_1h=m.clicks_last_1h,
            )

        return KeycounterStatsResponse(generated_at=ts, accounts=accounts_out)
