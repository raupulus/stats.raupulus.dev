"""Application services: profile aggregation, scheduler, and WebSocket management."""

from social_stats.services.aggregator import ProfileAggregator, compute_platform_status
from social_stats.services.scheduler import CollectorScheduler, calculate_backoff_delay
from social_stats.services.ws_manager import WSManager, WSSubscription

__all__ = [
    "CollectorScheduler",
    "ProfileAggregator",
    "WSManager",
    "WSSubscription",
    "calculate_backoff_delay",
    "compute_platform_status",
]
