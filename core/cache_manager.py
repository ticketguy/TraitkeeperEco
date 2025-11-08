# core/cache_manager.py

"""
TraitKeeper Cache Management System - Production-Ready Priority-Based Caching

This module provides a unified caching strategy that coordinates between Django's
local cache and Redis for optimal performance across the TraitKeeper platform.

## Architecture

The CacheManager implements a priority-based tiered caching system where different
types of data receive different TTLs (Time-To-Live) based on collection priority:

### Collection Priority Tiers:
- **VIP**: High-activity collections (e.g., Mad Lads, Degods) - Shortest TTLs
- **ACTIVE**: Medium-activity collections - Medium TTLs
- **INACTIVE**: Low-activity collections - Longest TTLs

### Cache Types:
- **STATS**: Collection statistics (floor price, volume, etc.)
- **PROVIDER**: External API responses (Magic Eden, Tensor)
- **METRICS**: Calculated analytics (trait performance, wallet prominence)
- **GLOBAL**: Site-wide data (trending collections, featured items)
- **RATE_LIMIT**: API rate limiting counters

## Example TTL Configuration (from settings.py):

```python
VIP Collections:
- Stats: 5 minutes
- Provider data: 10 minutes
- Metrics: 15 minutes

ACTIVE Collections:
- Stats: 30 minutes
- Provider data: 1 hour
- Metrics: 2 hours

INACTIVE Collections:
- Stats: 4 hours
- Provider data: 6 hours
- Metrics: 24 hours
```

## Usage:

```python
from core.cache_manager import CacheManager

cache = CacheManager()

# Store collection stats with VIP priority
await cache.set('collection_stats', collection_address, stats_data, priority='VIP')

# Retrieve cached data
stats = await cache.get('collection_stats', collection_address)
```

## Error Handling:

The CacheManager is designed to degrade gracefully:
- If Redis is unavailable, falls back to Django's local cache
- All cache failures are logged but don't break the application
- Returns None on cache miss instead of raising exceptions

## Configuration:

All configuration is in `settings.py` under `CACHE_MANAGER` and `CACHE_MANAGER_REDIS`.
See settings.py for full configuration options.

**Author**: TraitKeeper Development Team
**Last Updated**: January 2025
**Version**: 2.0.0 (Production-Ready)
"""

import logging
import json
from typing import Optional, Any, Dict
from enum import Enum
from django.core.cache import cache
from django.conf import settings
import redis
from redis.asyncio import Redis as AsyncRedis

logger = logging.getLogger(__name__)

# This Enum should match the keys in your settings.py TTL_CONFIG
class CacheType(Enum):
    STATS = "STATS"
    PROVIDER = "PROVIDER"
    METRICS = "METRICS"
    GLOBAL = "GLOBAL"
    RATE_LIMIT = "RATE_LIMIT"

class CacheManager:
    """
    A unified, site-wide cache manager that coordinates between Django's local
    cache and a shared Redis cache. It is configured entirely via settings.py.
    """
    def __init__(self):
        # Load all configurations from settings.py
        config = getattr(settings, 'CACHE_MANAGER', {})
        redis_config = getattr(settings, 'CACHE_MANAGER_REDIS', {})
        
        self.ttl_config = config.get('TTL_CONFIG', {})
        self.key_prefixes = getattr(settings, 'CACHE_KEY_PREFIXES', {})
        self.error_handling = config.get('ERROR_HANDLING', {})
        self.monitoring = config.get('MONITORING', {})
        
        # Initialize Redis client with settings-based configuration
        self.redis_client = None
        if hasattr(settings, 'REDIS_URL'):
            try:
                # Use async version of the client
                self.redis_client = AsyncRedis.from_url(
                    settings.REDIS_URL,
                    decode_responses=redis_config.get('DECODE_RESPONSES', True),
                    socket_connect_timeout=redis_config.get('SOCKET_TIMEOUT', 5)
                )
                logger.info("CacheManager initialized with Redis and Django cache coordination.")
            except Exception as e:
                logger.error(f"Failed to initialize Redis client: {e}")
        else:
            logger.warning("CacheManager initialized with Django cache ONLY (Redis not configured).")

    def _get_key_with_prefix(self, cache_type: CacheType, base_key: str) -> str:
        """Constructs a final cache key with the correct prefix from settings."""
        prefix = self.key_prefixes.get(cache_type.name, cache_type.name.lower())
        return f"{prefix}:{base_key}"

    def get_ttl(self, cache_type: CacheType, priority_tier: str = 'ACTIVE') -> int:
        """
        Convenience helper to calculate the correct TTL based on settings.
        This can be called by other services before they use the set() method.
        """
        tier_config = self.ttl_config.get(priority_tier, {})
        # Fallback to ACTIVE tier config if the specific tier is missing a key
        active_config = self.ttl_config.get('ACTIVE', {})
        return tier_config.get(cache_type.name, active_config.get(cache_type.name, 3600))

    async def get(self, key: str) -> Optional[Any]:
        """Gets an item from the cache, checking Django cache then Redis."""
        try:
            cached_data = cache.get(key)
            if cached_data is not None:
                if self.monitoring.get('TRACK_CACHE_HITS'): self._track_hit(key)
                return cached_data
            
            if self.redis_client:
                redis_data = await self.redis_client.get(key)
                if redis_data:
                    if self.monitoring.get('TRACK_CACHE_HITS'): self._track_hit(key, source='Redis')
                    data = json.loads(redis_data)
                    cache.set(key, data, timeout=60) # Back-populate local cache
                    return data
            
            if self.monitoring.get('TRACK_CACHE_HITS'): self._track_miss(key)
            return None
        except Exception as e:
            if self.error_handling.get('LOG_CACHE_ERRORS'):
                logger.error(f"Error getting cache key '{key}': {e}")
            return None

    async def set(self, key: str, data: Any, cache_type: CacheType, collection_address: Optional[str] = None) -> bool:
        """
        Sets an item in both cache layers and associates it with a collection if an address is provided.
        """
        if data is None:
            return False
        try:
            #  Get the TTL dynamically from the cache_type
            ttl = self.get_ttl(cache_type)

            # Set the data in the local Django cache
            cache.set(key, data, timeout=ttl)

            # Set the data in Redis and handle the collection association
            if self.redis_client:
                serialized_data = json.dumps(data, default=str)
                await self.redis_client.setex(key, ttl, serialized_data)

                #  If a collection address is provided,
                # add this item's key to the collection's set of keys.
                if collection_address:
                    collection_key_set = f"collection_keys:{collection_address}"
                    await self.redis_client.sadd(collection_key_set, key)
            
            return True
        except Exception as e:
            if self.error_handling.get('LOG_CACHE_ERRORS'):
                logger.error(f"Error setting cache key '{key}': {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Deletes an item from both cache layers."""
        try:
            cache.delete(key)
            if self.redis_client:
                await self.redis_client.delete(key)
            return True
        except Exception as e:
            if self.error_handling.get('LOG_CACHE_ERRORS'):
                logger.error(f"Error deleting cache key '{key}': {e}")
            return False
        

    async def invalidate_collection_caches(self, collection_address: str) -> int:
        """
        Invalidates all cache entries for a collection using the Redis SET of keys.
        Returns the number of keys invalidated.
        """
        if not self.redis_client:
            logger.warning("Cannot invalidate Redis cache; client not configured.")
            return 0
        try:
            # Define the key for our set of keys
            collection_key_set = f"collection_keys:{collection_address}"

            #  Get all cache keys from the collection's set
            keys_to_delete = await self.redis_client.smembers(collection_key_set)

            if not keys_to_delete:
                logger.info(f"No cache keys to invalidate for collection {collection_address}.")
                return 0

            # Also delete the set's key itself
            keys_to_delete.add(collection_key_set)

            # Delete all keys from Redis in a single, efficient operation
            deleted_count = await self.redis_client.delete(*keys_to_delete)

            # Delete from local Django cache as well
            for key in keys_to_delete:
                cache.delete(key)

            # The count includes the set key itself, so subtract 1 for the log
            invalidated_count = deleted_count - 1
            logger.info(f"Successfully invalidated {invalidated_count} cache entries for collection {collection_address}.")
            return invalidated_count

        except Exception as e:
            logger.error(f"Error during cache invalidation for collection {collection_address}: {e}")
            return 0

    async def invalidate_trait_caches(self, collection_address: str, trait_type: Optional[str] = None) -> bool:
        """
        Invalidates trait-related cache entries for a collection.
        
        Args:
            collection_address: The collection's public key
            trait_type: Optional specific trait type to invalidate. If None, invalidates all traits.
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_keys_to_delete = []
            
            if trait_type:
                # Invalidate specific trait
                cache_keys_to_delete.append(
                    self._get_key_with_prefix(CacheType.METRICS, f"trait_stats:{collection_address}:{trait_type}")
                )
            else:
                # Invalidate all trait-related caches for the collection
                # Note: In production, you might want to use Redis SCAN to find all matching keys
                cache_keys_to_delete.extend([
                    self._get_key_with_prefix(CacheType.METRICS, f"trait_rarity:{collection_address}"),
                    self._get_key_with_prefix(CacheType.METRICS, f"trait_floor:{collection_address}"),
                    self._get_key_with_prefix(CacheType.GLOBAL, f"all_traits:{collection_address}"),
                ])
            
            for key in cache_keys_to_delete:
                await self.delete(key)
            
            logger.info(f"Invalidated {len(cache_keys_to_delete)} trait cache entries for {collection_address[:8]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error invalidating trait caches: {e}")
            return False

    async def invalidate_all_caches(self) -> bool:
        """
        Nuclear option: Clears the entire cache.
        Use sparingly - mainly for emergency situations or maintenance.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            cache.clear()
            
            if self.redis_client:
                await self.redis_client.flushdb()
            
            logger.warning("⚠️ ALL CACHES CLEARED - This affects the entire application!")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing all caches: {e}")
            return False
            
    # Placeholder for monitoring methods
    def _track_hit(self, key: str, source: str = 'Django'):
        # In a real implementation, this would increment a counter in Redis or a monitoring service.
        logger.debug(f"Cache hit ({source}): {key}")
        
    def _track_miss(self, key: str):
        logger.debug(f"Cache miss: {key}")

# ===================================================================
# GLOBAL INSTANCE
# ===================================================================
# This singleton instance should be imported and used by the entire site.
cache_manager = CacheManager()