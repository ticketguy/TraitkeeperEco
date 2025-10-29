# nft_data/services/cache_service.py

import logging
import json
import redis
from django.conf import settings
from django.core.cache import cache
from asgiref.sync import sync_to_async

try:
    from core.cache_manager import cache_manager, CacheType
    CACHE_MANAGER_AVAILABLE = True
except ImportError:
    cache_manager = None
    CACHE_MANAGER_AVAILABLE = False
    logging.warning("Cache manager not available, using fallback caching.")
    from enum import Enum
    class CacheType(Enum):
        STATS = "stats"
        PROVIDER = "provider"
        METRICS = "metrics"

logger = logging.getLogger(__name__)

class CacheService:
    """Handles all get/set operations for caching with multiple fallbacks."""
    def __init__(self):
        self.redis_client = None
        if hasattr(settings, 'REDIS_URL') and settings.REDIS_URL:
            try:
                self.redis_client = redis.from_url(settings.REDIS_URL)
                logger.info("CacheService: Redis client initialized.")
            except Exception as e:
                logger.warning(f"CacheService: Failed to initialize Redis client: {e}")
        
        self.cache_manager = cache_manager if CACHE_MANAGER_AVAILABLE else None

    async def get_cache_key(self, prefix: str, identifier: str) -> str:
        """Generate a consistent cache key."""
        return f"{prefix}:{identifier}"

    async def get_from_cache(self, prefix: str, identifier: str):
        """Retrieve data from the cache, trying the primary manager first, then fallbacks."""
        cache_key = await self.get_cache_key(prefix, identifier)
        
        # 1. Try primary cache manager
        if self.cache_manager:
            try:
                cached_data = await self.cache_manager.get(cache_key)
                if cached_data is not None:
                    logger.info(f"Cache hit (Manager): {cache_key}")
                    return cached_data
            except Exception as e:
                logger.warning(f"Cache Manager 'get' error for {cache_key}: {e}")
        
        # 2. Fallback to Django cache
        try:
            cached_data = await sync_to_async(cache.get)(cache_key)
            if cached_data:
                logger.info(f"Cache hit (Django): {cache_key}")
                return cached_data
        except Exception as e:
            logger.warning(f"Django cache 'get' error for {cache_key}: {e}")
        
        # 3. Fallback to Redis
        if self.redis_client:
            try:
                redis_data = await sync_to_async(self.redis_client.get)(cache_key)
                if redis_data:
                    logger.info(f"Cache hit (Redis): {cache_key}")
                    return json.loads(redis_data)
            except Exception as e:
                logger.warning(f"Redis 'get' error for {cache_key}: {e}")
        
        return None

    async def save_to_cache(self, prefix: str, identifier: str, data, timeout: int = 3600, collection_address: str = None):
        """Save data to the cache using the primary manager with fallbacks."""
        if not data:
            return False
        
        cache_key = await self.get_cache_key(prefix, identifier)
        cache_type = self._determine_cache_type(prefix)
        
        # 1. Try primary cache manager
        if self.cache_manager:
            try:
                success = await self.cache_manager.set(cache_key, data, cache_type, collection_address)
                if success:
                    logger.info(f"Cached data via manager: {cache_key}")
                    return True
            except Exception as e:
                logger.warning(f"Cache Manager 'set' error for {cache_key}: {e}")
        
        # 2. Fallback to Django cache and Redis
        try:
            await sync_to_async(cache.set)(cache_key, data, timeout)
            if self.redis_client:
                await sync_to_async(self.redis_client.setex)(cache_key, timeout, json.dumps(data, default=str))
            logger.info(f"Cached data via fallback: {cache_key}")
            return True
        except Exception as e:
            logger.error(f"Error saving to fallback cache for {cache_key}: {e}")
            return False

    def _determine_cache_type(self, prefix: str) -> CacheType:
        """Determine the cache category based on the key prefix."""
        prefix_mapping = {
            'metadata': CacheType.STATS,
            'collection': CacheType.PROVIDER,
            'traits': CacheType.METRICS,
            'nft': CacheType.STATS,
            'rarity': CacheType.METRICS,
            'retrieval': CacheType.PROVIDER,
            'validation': CacheType.PROVIDER,
            'uri_metadata': CacheType.STATS,
            'ipfs': CacheType.PROVIDER,
        }
        
        if prefix in prefix_mapping:
            return prefix_mapping[prefix]
        
        for key, cache_type in prefix_mapping.items():
            if key in prefix.lower():
                return cache_type
        
        return CacheType.PROVIDER

    async def invalidate_collection_cache(self, collection_address: str) -> int:
        """Invalidate all caches associated with a specific collection."""
        if not self.cache_manager:
            logger.warning("Cannot invalidate collection cache: Cache manager not available.")
            return 0
        
        try:
            count = await self.cache_manager.invalidate_collection_caches(collection_address)
            logger.info(f"Invalidated {count} cache keys for collection {collection_address}")
            return count
        except Exception as e:
            logger.error(f"Error invalidating collection cache for {collection_address}: {e}")
            return 0