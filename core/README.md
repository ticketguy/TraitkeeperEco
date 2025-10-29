# Core App

## Overview

Shared utilities and core services used across all apps. Contains the cache management system and common helper functions.

## Purpose

- **Cache management** - Priority-based caching with TTLs
- **Shared utilities** - Common functions for all apps
- **Configuration** - Centralized settings

## Key Components

### CacheManager

**Priority-based caching system** with intelligent TTLs.

**Features:**

- **Priority tiers**: VIP, ACTIVE, INACTIVE
- **Dynamic TTLs**: Different cache durations per priority
- **Source attribution**: Track which data source was cached
- **Dependency invalidation**: Cascade cache invalidation
- **Cache warming**: Preload important data

**TTL Configuration (from settings):**

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

**Usage:**

```python
from core.cache_manager import CacheManager

cache = CacheManager()

# Store with priority-based TTL
cache.set_stats('collection_address', stats_data, priority='VIP')

# Get cached data
stats = cache.get_stats('collection_address')
```

## Integration

All apps use core for:

- Caching API responses
- Storing calculated metrics
- Managing update schedules

## TODO

- [ ] Add distributed caching (Redis Cluster)
- [ ] Implement cache metrics/monitoring
- [ ] Add cache invalidation API
