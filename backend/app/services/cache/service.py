"""Cache service implementation.

This module provides an abstract cache service interface and a concrete
Redis implementation for caching POI data and other responses.

Requirements: 2.5, 7.5, 7.6
- 2.5: Cache API responses using city and place_id as cache keys
- 7.5: Implement response caching at the backend level
- 7.6: Use city and place_id as cache keys

Property 6: Cache Key Consistency
- For any POI cached by the system, retrieving it using the same city
  and placeId combination SHALL return an equivalent POI object.
"""

import json
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import redis.asyncio as redis

T = TypeVar("T")


class CacheService(ABC):
    """Abstract base class for cache services.

    Defines the interface for caching operations including get, set,
    and invalidation. Also provides a static method for building
    consistent POI cache keys.
    """

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Retrieve cached value by key.

        Args:
            key: The cache key to look up.

        Returns:
            The cached value if found, None otherwise.
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Store value in cache with optional TTL.

        Args:
            key: The cache key to store under.
            value: The value to cache (must be JSON serializable).
            ttl_seconds: Time-to-live in seconds. Defaults to 3600 (1 hour).
        """
        pass

    @abstractmethod
    async def invalidate(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern.

        Args:
            pattern: Glob-style pattern to match keys (e.g., "poi:paris:*").

        Returns:
            Number of keys invalidated.
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: The cache key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a specific key from the cache.

        Args:
            key: The cache key to delete.

        Returns:
            True if the key was deleted, False if it didn't exist.
        """
        pass

    @staticmethod
    def build_poi_key(city: str, place_id: str) -> str:
        """Generate cache key for a POI.

        Creates a consistent cache key format using city and place_id.
        The key format is: ``poi:{city_lowercase}:{place_id}``

        Args:
            city: The city name (will be lowercased for consistency).
            place_id: The OSM-based place identifier (e.g. ``osm_node_12345``).

        Returns:
            A formatted cache key string.

        Example:
            >>> CacheService.build_poi_key("Paris", "osm_node_12345")
            'poi:paris:osm_node_12345'
        """
        return f"poi:{city.lower()}:{place_id}"


class RedisCacheService(CacheService):
    """Redis-based implementation of the cache service.

    Uses Redis for storing cached values with support for TTL,
    pattern-based invalidation, and JSON serialization.

    Attributes:
        _client: The Redis async client instance.
        _default_ttl: Default TTL in seconds for cached values.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        default_ttl: int = 3600,
    ) -> None:
        """Initialize the Redis cache service.

        Args:
            redis_url: Redis connection URL. Defaults to localhost:6379.
            default_ttl: Default TTL in seconds. Defaults to 3600 (1 hour).
        """
        self._redis_url = redis_url
        self._default_ttl = default_ttl
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """Establish connection to Redis.

        Should be called before using the cache service.
        """
        if self._client is None:
            self._client = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )

    async def disconnect(self) -> None:
        """Close the Redis connection.

        Should be called when shutting down the application.
        """
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def _ensure_connected(self) -> redis.Redis:
        """Ensure Redis client is connected.

        Returns:
            The connected Redis client.

        Raises:
            RuntimeError: If not connected and connection fails.
        """
        if self._client is None:
            await self.connect()
        return self._client  # type: ignore

    async def get(self, key: str) -> Any | None:
        """Retrieve cached value by key.

        Args:
            key: The cache key to look up.

        Returns:
            The deserialized cached value if found, None otherwise.
        """
        client = await self._ensure_connected()
        value = await client.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Return raw value if not JSON
            return value

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Store value in cache with optional TTL.

        Args:
            key: The cache key to store under.
            value: The value to cache (will be JSON serialized).
            ttl_seconds: Time-to-live in seconds. Uses default if not specified.
        """
        client = await self._ensure_connected()
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        # Serialize value to JSON
        if isinstance(value, str):
            serialized = value
        else:
            serialized = json.dumps(value)

        await client.set(key, serialized, ex=ttl)

    async def invalidate(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern.

        Uses Redis SCAN to find matching keys and deletes them.
        This is more efficient than KEYS for large datasets.

        Args:
            pattern: Glob-style pattern to match keys (e.g., "poi:paris:*").

        Returns:
            Number of keys invalidated.
        """
        client = await self._ensure_connected()
        deleted_count = 0

        # Use SCAN to find matching keys (safer than KEYS for large datasets)
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                deleted_count += await client.delete(*keys)
            if cursor == 0:
                break

        return deleted_count

    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: The cache key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        client = await self._ensure_connected()
        return bool(await client.exists(key))

    async def delete(self, key: str) -> bool:
        """Delete a specific key from the cache.

        Args:
            key: The cache key to delete.

        Returns:
            True if the key was deleted, False if it didn't exist.
        """
        client = await self._ensure_connected()
        result = await client.delete(key)
        return result > 0

    @property
    def default_ttl(self) -> int:
        """Get the default TTL in seconds."""
        return self._default_ttl
