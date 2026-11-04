"""A tiny in-process TTL cache.

Keys map to (expires_at, value) pairs, where expires_at is a
time.monotonic() deadline: a single dict lookup answers "is this valid?"
with no second structure to keep in sync. The clock is injected as a
callable so tests can run expiry deterministically without sleeping.

Deliberately dependency-free: a cache that imports the app cannot
outlive the app, so this module knows nothing about FastAPI, psycopg
or the knowledge base.
"""

import time
from collections.abc import Callable


class TtlCache:
    def __init__(self, now: Callable[[], float] = time.monotonic, ttl: float = 30):
        self._now = now
        self._ttl = ttl
        self._entries: dict[object, tuple[float, object]] = {}

    def set(self, key, value) -> None:
        self._entries[key] = (self._now() + self._ttl, value)

    def get(self, key, default=None):
        entry = self._entries.get(key)
        if entry is None:
            return default
        expires_at, value = entry
        if self._now() >= expires_at:
            del self._entries[key]
            return default

        return value

    def delete(self, key) -> None:
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()
