"""Social media metric collectors."""

from social_stats.collectors.base import (
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_USER_AGENT,
    BaseCollector,
    CollectorError,
)

__all__ = [
    "BaseCollector",
    "CollectorError",
    "DEFAULT_HTTP_TIMEOUT",
    "DEFAULT_USER_AGENT",
]
