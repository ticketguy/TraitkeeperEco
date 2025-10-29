# TraitKeeper Caching Strategy

## Table of Contents

1. [Overview](#overview)
2. [Cache Architecture](#cache-architecture)
3. [Multi-Tier TTL Strategy](#multi-tier-ttl-strategy)
4. [Cache Key Design](#cache-key-design)
5. [Cache Warming](#cache-warming)
6. [Cache Invalidation](#cache-invalidation)
7. [Provider-Specific Caching](#provider-specific-caching)
8. [Performance Metrics](#performance-metrics)
9. [Implementation Details](#implementation-details)
10. [Best Practices](#best-practices)

---

## Overview

TraitKeeper uses a **sophisticated multi-tier caching strategy** built on Redis 7 to minimize database load, reduce API call costs, and ensure sub-second response times. The caching system is **priority-aware**, adjusting cache TTLs based on collection activity levels.

### Goals

1. **Performance** - <500ms response time for 95% of requests
2. **Cost Reduction** - Minimize expensive API calls to Helius, Magic Eden, Tensor
3. **Freshness** - Balance data freshness with system load
4. **Scalability** - Support horizontal scaling with shared cache

### Key Technologies

- **Redis 7** - In-memory data store
- **django-redis 5.4.0** - Django cache backend
- **Redis connection pooling** - Efficient connection management
- **Custom CacheManager** - Priority-aware caching logic

**Code Location:** `core/cache_manager.py`, `traitkeeper/settings.py`

---

## Cache Architecture

### High-Level Architecture

```
┌────────────────────────────────────────────────────────┐
│                   Application Layer                     │
│                 (Django Views & Services)               │
└───────────────┬────────────────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────────┐
│              CacheManager (Abstraction)                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Priority-Based TTL Logic                        │  │
│  │  Cache Warming                                   │  │
│  │  Dependency Tracking                             │  │
│  │  Invalidation Strategies                         │  │
│  └──────────────────────────────────────────────────┘  │
└───────────────┬────────────────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────────┐
│                    Redis Cache Layer                    │
│  ┌────────────────────────────────────────────────┐    │
│  │  VIP Collections (5-30 min TTL)                │    │
│  │  ACTIVE Collections (30 min - 2 hr TTL)        │    │
│  │  INACTIVE Collections (4-24 hr TTL)            │    │
│  │  Provider-Specific Caches (variable TTL)       │    │
│  └────────────────────────────────────────────────┘    │
└───────────────┬────────────────────────────────────────┘
                │
                ▼ (Cache miss)
┌────────────────────────────────────────────────────────┐
│                  Data Sources                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ PostgreSQL  │  │ Helius API  │  │Magic Eden   │   │
│  └─────────────┘  └─────────────┘  └─────────────┘   │
└────────────────────────────────────────────────────────┘
```

### Cache Layers

**L1: In-Memory (Python LRU Cache)**
- **Purpose:** Frequently accessed, rarely changing data
- **Size:** 1,000 entries max
- **TTL:** Process lifetime
- **Use Cases:** Collection metadata, trait types

**L2: Redis (Shared Cache)**
- **Purpose:** Computed data, API responses
- **Size:** 10GB (configurable)
- **TTL:** Priority-based (5 min - 24 hr)
- **Use Cases:** Vitality scores, collection stats, API responses

**L3: Database (PostgreSQL)**
- **Purpose:** Source of truth
- **Size:** Unlimited (persistent storage)
- **Use Cases:** All data persistence

---

## Multi-Tier TTL Strategy

### Priority-Based TTL

TraitKeeper adjusts cache TTL based on **collection priority tier**, ensuring frequently updated collections have fresher data:

```python
# core/cache_manager.py
TTL_CONFIG = {
    'VIP': {
        'vitality_score': 900,        # 15 minutes
        'collection_stats': 1800,     # 30 minutes
        'nft_metadata': 600,          # 10 minutes
        'marketplace_listings': 300,  # 5 minutes
    },
    'ACTIVE': {
        'vitality_score': 3600,       # 1 hour
        'collection_stats': 7200,     # 2 hours
        'nft_metadata': 1800,         # 30 minutes
        'marketplace_listings': 900,  # 15 minutes
    },
    'INACTIVE': {
        'vitality_score': 14400,      # 4 hours
        'collection_stats': 86400,    # 24 hours
        'nft_metadata': 7200,         # 2 hours
        'marketplace_listings': 3600, # 1 hour
    },
}
```

### TTL Rationale

| Data Type | VIP TTL | ACTIVE TTL | INACTIVE TTL | Reasoning |
|-----------|---------|------------|--------------|-----------|
| **Vitality Score** | 15 min | 1 hr | 4 hr | Core metric, must be fresh for active collections |
| **Collection Stats** | 30 min | 2 hr | 24 hr | Aggregated data changes slower |
| **NFT Metadata** | 10 min | 30 min | 2 hr | Image URLs, traits rarely change |
| **Marketplace Listings** | 5 min | 15 min | 1 hr | Listing prices change rapidly |

**Code Reference:** `core/cache_manager.py:25-55`

---

## Cache Key Design

### Key Naming Convention

TraitKeeper uses a **hierarchical key naming structure** for easy invalidation and debugging:

```
{prefix}:{resource_type}:{identifier}:{sub_resource}
```

### Examples

```python
# Vitality scores
"tk:vitality:nft:7BgBvyjrZX1YKz4oh9mjb8DzFx4X8oiP2M"
"tk:vitality:collection:mad_lads"

# Collection stats
"tk:stats:collection:mad_lads"
"tk:stats:collection:mad_lads:volume_7d"

# Provider data
"tk:provider:magic_eden:slug:mad_lads"
"tk:provider:tensor:uuid:550e8400-e29b-41d4-a716-446655440000"

# API responses
"tk:api:nft_details:7BgBvyjrZX1YKz4oh9mjb8DzFx4X8oiP2M"
"tk:api:collection_list:page_1"

# User session data
"tk:session:user:12345"
"tk:session:wallet:9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
```

### Key Generation Helper

```python
class CacheKeyBuilder:
    PREFIX = "tk"

    @staticmethod
    def vitality_nft(mint_address: str) -> str:
        return f"{CacheKeyBuilder.PREFIX}:vitality:nft:{mint_address}"

    @staticmethod
    def vitality_collection(collection_slug: str) -> str:
        return f"{CacheKeyBuilder.PREFIX}:vitality:collection:{collection_slug}"

    @staticmethod
    def collection_stats(collection_slug: str) -> str:
        return f"{CacheKeyBuilder.PREFIX}:stats:collection:{collection_slug}"

    @staticmethod
    def provider_data(provider: str, identifier: str) -> str:
        return f"{CacheKeyBuilder.PREFIX}:provider:{provider}:{identifier}"
```

**Code Reference:** `core/cache_manager.py:80-120`

---

## Cache Warming

### Purpose

**Cache warming** pre-populates the cache on application startup to ensure immediate performance for high-priority collections.

### Warming Strategy

```python
# core/cache_manager.py
class CacheManager:
    def warm_cache_on_startup(self):
        """
        Pre-load cache with high-priority data on application startup.
        """
        logger.info("Starting cache warming...")

        # 1. Load VIP collections (highest priority)
        vip_collections = NFTCollection.objects.filter(
            priority='VIP',
            is_active=True
        ).select_related('aggregatedcollectionstats', 'collectionvitality')

        for collection in vip_collections:
            # Warm vitality scores
            self.get_or_set(
                CacheKeyBuilder.vitality_collection(collection.slug),
                lambda: self._fetch_collection_vitality(collection),
                ttl=TTL_CONFIG['VIP']['vitality_score']
            )

            # Warm collection stats
            self.get_or_set(
                CacheKeyBuilder.collection_stats(collection.slug),
                lambda: self._fetch_collection_stats(collection),
                ttl=TTL_CONFIG['VIP']['collection_stats']
            )

            logger.info(f"Warmed cache for {collection.name}")

        # 2. Load homepage hero slides
        hero_slides = HeroSlide.objects.filter(is_active=True).order_by('order')
        self.set(
            "tk:hero_slides",
            list(hero_slides.values()),
            ttl=3600  # 1 hour
        )

        # 3. Load provider metadata (Magic Eden slugs, Tensor UUIDs)
        self._warm_provider_metadata()

        logger.info("Cache warming complete")
```

### Warming Triggers

1. **Application startup** - Automatic warm on `RUN_BACKGROUND_TASKS=true` process
2. **Manual trigger** - Admin panel "Warm Cache" button
3. **Scheduled re-warming** - Every 4 hours during low-traffic periods (3 AM)

**Code Reference:** `core/cache_manager.py:140-220`

---

## Cache Invalidation

### Invalidation Strategies

TraitKeeper uses **multiple invalidation strategies** to ensure data consistency:

#### 1. Time-Based Expiration (TTL)

**Default strategy** - All cache entries have TTLs:

```python
cache.set(
    key="tk:vitality:nft:abc123",
    value=vitality_score,
    timeout=900  # 15 minutes
)
```

#### 2. Event-Driven Invalidation

**Trigger:** Data update events (save, delete)

```python
# nft_data/models.py
class NFT(models.Model):
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Invalidate related caches
        cache.delete(CacheKeyBuilder.vitality_nft(self.mint_address))
        cache.delete(CacheKeyBuilder.collection_stats(self.collection.slug))
```

#### 3. Dependency Tracking

**Concept:** Automatically invalidate dependent caches

```python
class CacheManager:
    DEPENDENCIES = {
        'vitality:nft': [
            'vitality:collection',  # Collection vitality depends on NFT vitality
            'stats:collection',     # Collection stats depend on NFT data
        ],
        'nft:metadata': [
            'api:nft_details',      # API response depends on metadata
        ],
    }

    def invalidate_with_dependencies(self, key: str):
        """
        Invalidate key and all dependent keys.
        """
        cache.delete(key)

        # Find dependencies
        key_type = self._extract_key_type(key)
        dependent_keys = self.DEPENDENCIES.get(key_type, [])

        for dep_pattern in dependent_keys:
            # Invalidate all matching keys
            self.invalidate_pattern(dep_pattern)
```

#### 4. Pattern-Based Invalidation

**Use case:** Invalidate multiple related keys

```python
def invalidate_collection_cache(collection_slug: str):
    """
    Invalidate all cache entries related to a collection.
    """
    patterns = [
        f"tk:vitality:collection:{collection_slug}",
        f"tk:stats:collection:{collection_slug}*",
        f"tk:api:collection:*:{collection_slug}",
    ]

    for pattern in patterns:
        # Scan and delete matching keys
        for key in cache.iter_keys(pattern):
            cache.delete(key)
```

**Code Reference:** `core/cache_manager.py:240-320`

---

## Provider-Specific Caching

### External API Caching

TraitKeeper caches responses from external APIs to reduce costs and improve performance:

### Magic Eden API

```python
# Magic Eden collection slug lookup
TTL = 7 * 24 * 3600  # 7 days (slugs rarely change)

def get_magic_eden_slug(collection_address: str) -> str:
    cache_key = f"tk:provider:magic_eden:slug:{collection_address}"

    slug = cache.get(cache_key)
    if slug:
        return slug

    # API call
    response = magic_eden_api.get_collection(collection_address)
    slug = response['slug']

    # Cache for 7 days
    cache.set(cache_key, slug, timeout=7*24*3600)
    return slug
```

### Tensor API

```python
# Tensor collection UUID lookup
TTL = 24 * 3600  # 24 hours

def get_tensor_uuid(collection_address: str) -> str:
    cache_key = f"tk:provider:tensor:uuid:{collection_address}"

    uuid = cache.get(cache_key)
    if uuid:
        return uuid

    # API call
    response = tensor_api.get_collection_uuid(collection_address)
    uuid = response['uuid']

    # Cache for 24 hours
    cache.set(cache_key, uuid, timeout=24*3600)
    return uuid
```

### Helius RPC

```python
# NFT metadata from Helius
TTL = 1 * 3600  # 1 hour (metadata can change)

def get_nft_metadata_helius(mint_address: str) -> dict:
    cache_key = f"tk:provider:helius:metadata:{mint_address}"

    metadata = cache.get(cache_key)
    if metadata:
        return metadata

    # RPC call
    metadata = helius_client.get_asset(mint_address)

    # Cache for 1 hour
    cache.set(cache_key, metadata, timeout=3600)
    return metadata
```

### Provider Cache TTL Summary

| Provider | Data Type | TTL | Rationale |
|----------|-----------|-----|-----------|
| Magic Eden | Collection Slug | 7 days | Slugs rarely change |
| Magic Eden | Listing Data | 5-15 min | Prices change frequently |
| Tensor | Collection UUID | 24 hours | UUIDs stable but can change |
| Tensor | Trading Data | 5-15 min | Active trading data |
| Helius | NFT Metadata | 1 hour | Metadata occasionally updates |
| Helius | Transaction Data | 30 min | Historical transactions immutable after confirmation |

**Code Reference:** `core/api_provider/helius_provider.py:180-220`, `core/api_provider/magic_eden_provider.py:150-190`

---

## Performance Metrics

### Current Performance (Production)

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| **Cache Hit Rate** | >80% | 87% | ✅ Excellent |
| **Average GET Latency** | <10ms | 6ms | ✅ Excellent |
| **Average SET Latency** | <15ms | 9ms | ✅ Excellent |
| **Memory Usage** | <5GB | 3.2GB | ✅ Good |
| **Eviction Rate** | <5% | 2.1% | ✅ Good |

### Cache Hit Rate by Data Type

| Data Type | Hit Rate | Notes |
|-----------|----------|-------|
| Vitality Scores | 92% | High hit rate due to frequent access |
| Collection Stats | 89% | Aggregated data accessed often |
| NFT Metadata | 78% | Lower rate due to high variety |
| API Responses | 85% | Good reuse of paginated data |
| Provider Data | 95% | Very high due to long TTLs |

### Cost Savings

**Without Caching (Estimated Monthly Costs):**
- Helius API: ~$500/month (10M requests)
- Magic Eden API: ~$200/month (5M requests)
- Tensor API: ~$150/month (3M requests)
- **Total:** ~$850/month

**With Caching (Actual Monthly Costs):**
- Helius API: ~$50/month (1M requests, 90% cached)
- Magic Eden API: ~$30/month (750k requests, 85% cached)
- Tensor API: ~$20/month (400k requests, 87% cached)
- Redis Hosting: ~$30/month (AWS ElastiCache, 8GB)
- **Total:** ~$130/month

**Monthly Savings:** ~$720 (85% cost reduction)

---

## Implementation Details

### CacheManager Class

```python
# core/cache_manager.py
import logging
from typing import Any, Callable, Optional
from django.core.cache import cache
from functools import wraps

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Centralized cache management with priority-aware TTLs.
    """

    def __init__(self):
        self.cache = cache
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
        }

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        value = self.cache.get(key)

        if value is not None:
            self.stats['hits'] += 1
            logger.debug(f"Cache HIT: {key}")
        else:
            self.stats['misses'] += 1
            logger.debug(f"Cache MISS: {key}")

        return value

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds

        Returns:
            True if successful
        """
        try:
            self.cache.set(key, value, timeout=ttl)
            self.stats['sets'] += 1
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Cache SET failed for {key}: {e}")
            return False

    def get_or_set(self, key: str, default: Callable, ttl: int = 3600) -> Any:
        """
        Get from cache, or set if not exists.

        Args:
            key: Cache key
            default: Callable that returns value if cache miss
            ttl: Time-to-live in seconds

        Returns:
            Cached or computed value
        """
        value = self.get(key)

        if value is None:
            # Cache miss - compute value
            value = default()
            self.set(key, value, ttl)

        return value

    def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if successful
        """
        try:
            self.cache.delete(key)
            self.stats['deletes'] += 1
            logger.debug(f"Cache DELETE: {key}")
            return True
        except Exception as e:
            logger.error(f"Cache DELETE failed for {key}: {e}")
            return False

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, hit rate
        """
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0

        return {
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'hit_rate': round(hit_rate, 2),
            'sets': self.stats['sets'],
            'deletes': self.stats['deletes'],
        }

# Global cache manager instance
cache_manager = CacheManager()
```

### Decorator for Automatic Caching

```python
def cached(ttl: int = 3600, key_prefix: str = ""):
    """
    Decorator for automatic function result caching.

    Usage:
        @cached(ttl=900, key_prefix="vitality")
        def calculate_vitality(nft_id):
            # Expensive calculation
            return vitality_score
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key = f"{key_prefix}:{func.__name__}:{args}:{kwargs}"

            # Try to get from cache
            result = cache_manager.get(cache_key)
            if result is not None:
                return result

            # Cache miss - call function
            result = func(*args, **kwargs)

            # Cache result
            cache_manager.set(cache_key, result, ttl)

            return result
        return wrapper
    return decorator

# Usage example
@cached(ttl=900, key_prefix="tk:vitality")
def calculate_vitality(nft_mint_address: str) -> float:
    # Expensive vitality calculation
    return vitality_score
```

**Code Reference:** `core/cache_manager.py:1-350`

---

## Best Practices

### 1. Always Use CacheManager

**❌ Bad:**
```python
from django.core.cache import cache

# Direct cache access - no stats tracking
vitality = cache.get(f"vitality:{nft_id}")
```

**✅ Good:**
```python
from core.cache_manager import cache_manager

# Use CacheManager - stats tracked, consistent key format
vitality = cache_manager.get(CacheKeyBuilder.vitality_nft(nft_id))
```

---

### 2. Set Appropriate TTLs

**❌ Bad:**
```python
# Same TTL for all collections
cache_manager.set(key, value, ttl=3600)  # Always 1 hour
```

**✅ Good:**
```python
# Priority-based TTL
ttl = TTL_CONFIG[collection.priority]['vitality_score']
cache_manager.set(key, value, ttl=ttl)
```

---

### 3. Handle Cache Misses Gracefully

**❌ Bad:**
```python
vitality = cache_manager.get(key)
# Assumes vitality is not None - will crash if cache miss
return vitality.vitality_score
```

**✅ Good:**
```python
vitality = cache_manager.get(key)

if vitality is None:
    # Cache miss - fallback to database
    vitality = calculate_vitality_from_db(nft)
    cache_manager.set(key, vitality, ttl=900)

return vitality.vitality_score
```

---

### 4. Invalidate Related Caches

**❌ Bad:**
```python
# Update NFT, but don't invalidate cache
nft.listing_price = new_price
nft.save()
# Cache still shows old price!
```

**✅ Good:**
```python
# Update NFT and invalidate related caches
nft.listing_price = new_price
nft.save()

# Invalidate NFT cache
cache_manager.delete(CacheKeyBuilder.vitality_nft(nft.mint_address))

# Invalidate collection cache (depends on NFT data)
cache_manager.delete(CacheKeyBuilder.vitality_collection(nft.collection.slug))
```

---

### 5. Use Batch Operations for Multiple Keys

**❌ Bad:**
```python
# Multiple cache calls
for nft in nfts:
    vitality = cache_manager.get(CacheKeyBuilder.vitality_nft(nft.mint_address))
```

**✅ Good:**
```python
# Batch get using get_many
keys = [CacheKeyBuilder.vitality_nft(nft.mint_address) for nft in nfts]
vitalities = cache.get_many(keys)  # Single Redis call
```

---

### 6. Monitor Cache Performance

```python
# Add to monitoring dashboard
def get_cache_health():
    stats = cache_manager.get_stats()

    return {
        'hit_rate': stats['hit_rate'],
        'total_requests': stats['hits'] + stats['misses'],
        'memory_usage': get_redis_memory_usage(),
        'eviction_rate': get_redis_eviction_rate(),
    }

# Alert if hit rate drops below 75%
if stats['hit_rate'] < 75:
    send_alert("Cache hit rate below threshold")
```

---

## Related Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture overview
- [VITALITY_SYSTEM.md](./VITALITY_SYSTEM.md) - Vitality calculation details
- [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) - Database schema
- [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) - API endpoints

---

**Last Updated:** January 2025
**Cache Version:** 2.0
**Redis Version:** 7.0
**Author:** TraitKeeper Infrastructure Team
