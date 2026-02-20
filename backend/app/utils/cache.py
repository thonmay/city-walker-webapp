"""In-memory LRU cache with TTL expiration.

Simple process-level cache for hot data (discover responses, food queries).
Survives across requests in the same uvicorn worker.
TTL: 24h (landmarks don't change daily). Max 100 entries (~2MB RAM).
"""

import time
from collections import OrderedDict


class LRUCache:
    """TTL-aware LRU cache for JSON-serializable responses."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 86400) -> None:
        self._cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, key: str) -> dict | None:
        if key not in self._cache:
            return None
        ts, value = self._cache[key]
        if time.time() - ts > self._ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: dict) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time(), value)
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
