# TraitKeeper System Architecture

## Table of Contents

1. [Overview](#overview)
2. [System Design Philosophy](#system-design-philosophy)
3. [Two-Process Architecture](#two-process-architecture)
4. [Application Layer](#application-layer)
5. [Data Flow](#data-flow)
6. [Caching Strategy](#caching-strategy)
7. [Background Task System](#background-task-system)
8. [API Provider Architecture](#api-provider-architecture)
9. [Real-Time Updates](#real-time-updates)
10. [Database Architecture](#database-architecture)
11. [Security Architecture](#security-architecture)
12. [Deployment Architecture](#deployment-architecture)

---

## Overview

TraitKeeper is a **Django-based Solana NFT analytics platform** built using a **dual-process architecture** that separates user-facing operations from intensive background computations. The system aggregates data from multiple sources (Solana blockchain, Magic Eden, Tensor) to provide comprehensive NFT vitality scoring, advanced analytics, and marketplace functionality.

### Key Architectural Principles

1. **Separation of Concerns** - User interface isolated from background processing
2. **Scalability** - Independent scaling of frontend and data processing
3. **Performance** - Multi-tier caching with priority-based TTL
4. **Reliability** - Fault-tolerant data aggregation with fallback mechanisms
5. **Modularity** - 13+ specialized Django apps with clear boundaries

---

## System Design Philosophy

### Why Two Processes?

**Problem:** In a single-process architecture, heavy background tasks (blockchain indexing, analytics calculations) block user requests, causing 2-5 second response times and 80%+ CPU usage.

**Solution:** Split into two independent processes sharing the same database and cache:

| Aspect | Single Process (Before) | Two Process (After) |
|--------|------------------------|---------------------|
| **Response Time** | 2-5 seconds | 200-500ms |
| **CPU Usage** | 80%+ (all tasks competing) | Main: 20-30%, Data: 60-70% |
| **Debugging** | Mixed logs (hard to trace) | Separate logs per service |
| **Scalability** | Vertical only | Horizontal + vertical |
| **Reliability** | One crash = full outage | Isolated failure domains |

---

## Two-Process Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      TraitKeeper Platform                        │
└─────────────────────────────────────────────────────────────────┘
                               │
             ┌─────────────────┴──────────────────┐
             │                                    │
   ┌─────────▼─────────┐              ┌──────────▼────────┐
   │  PROCESS 1:       │              │  PROCESS 2:        │
   │  MAIN APP         │              │  DATA SERVICE      │
   │  (Port 8000)      │              │  (Background)      │
   ├───────────────────┤              ├────────────────────┤
   │ ENV:              │              │ ENV:               │
   │ RUN_BACKGROUND_   │              │ RUN_BACKGROUND_    │
   │ TASKS=false       │              │ TASKS=true         │
   │                   │              │                    │
   │ ✓ Django views    │              │ ✓ Blockchain       │
   │ ✓ SSE streams     │              │   indexing         │
   │ ✓ REST APIs       │              │ ✓ Vitality         │
   │ ✓ User auth       │              │   calculation      │
   │ ✓ Admin panel     │              │ ✓ Analytics        │
   │ ✓ Template render │              │   engine           │
   │ ✓ Static files    │              │ ✓ Sweep detection  │
   │                   │              │ ✓ WebSocket subs   │
   │ ✗ NO background   │              │ ✓ Data aggregation │
   │   tasks           │              │                    │
   └─────────┬─────────┘              └──────────┬─────────┘
             │                                   │
             └──────────┬────────────────────────┘
                        │
             ┌──────────▼──────────┐
             │  Shared Resources:  │
             │                     │
             │  • PostgreSQL 15    │
             │  • Redis 7          │
             │  • Static Files     │
             │  • Media Uploads    │
             └─────────────────────┘
```

### Process 1: Main App (User-Facing)

**Purpose:** Handle all user interactions and API requests with minimal latency

**Responsibilities:**
- HTTP request handling (Django views)
- REST API endpoints (`/api/*`)
- Server-Sent Events (SSE) streaming (`/stream-*`)
- User authentication and sessions
- Admin panel interface
- Template rendering (Jinja2/Django templates)
- Static file serving (via Gunicorn/Nginx)

**Configuration:**
```bash
export RUN_BACKGROUND_TASKS=false
python manage.py runserver 8000
```

**Performance Targets:**
- Response time: <500ms (p95)
- CPU usage: 20-30%
- Memory: Moderate (mostly request handling)

**Code Reference:** `traitkeeper/settings.py:45`
```python
RUN_BACKGROUND_TASKS = os.getenv('RUN_BACKGROUND_TASKS', 'false').lower() == 'true'

if not RUN_BACKGROUND_TASKS:
    # Main app: only handle user requests
    INSTALLED_APPS.remove('background_tasks_module')
```

---

### Process 2: Data Service (Background Processing)

**Purpose:** Perform intensive data processing without affecting user experience

**Responsibilities:**
- **Blockchain indexing** - WebSocket subscriptions to Solana (async)
- **Vitality calculation** - NFT and collection health scores (threaded)
- **Analytics engine** - Sweep detection, anomaly detection, predictions
- **Data aggregation** - Multi-source data fetching (Helius, Magic Eden, Tensor)
- **Cache warming** - Pre-populate cache on startup
- **Database maintenance** - Cleanup, archival, optimization

**Configuration:**
```bash
export RUN_BACKGROUND_TASKS=true
python manage.py runserver 8001 --noreload
```

**Performance Targets:**
- CPU usage: 60-70% (intentionally high for processing)
- Update frequency: VIP (15min), ACTIVE (1hr), INACTIVE (4hr)
- Task queue latency: <5 seconds

**Code Reference:** `traitkeeper/settings.py:50`
```python
if RUN_BACKGROUND_TASKS:
    # Data service: start background task manager
    from core.task_manager import TaskManager
    task_manager = TaskManager(max_workers=4)
    task_manager.start()
```

---

## Application Layer

TraitKeeper consists of **13 specialized Django apps**, each with a specific domain responsibility:

### Core Data Management

| App | Purpose | Key Models | Lines of Code |
|-----|---------|------------|---------------|
| **nft_data** | NFT catalog & collections | NFTCollection, NFT, TraitType, TraitValue, PendingCollection | ~800 |
| **wallet** | User authentication | CustomUser, WalletProfile, PasswordResetCode | ~400 |
| **indexer** | Blockchain event tracking | NFTListing, NFTEvent | ~600 |

**Architecture Pattern:** Domain-Driven Design (DDD) with clear entity boundaries

**Code Reference:** `nft_data/models.py`, `wallet/models.py`, `indexer/models.py`

---

### Analytics & Intelligence

| App | Purpose | Key Models | Lines of Code |
|-----|---------|------------|---------------|
| **analytics** | Collection & trait analytics | AggregatedCollectionStats, CollectionSweepEvent, HighProfileTransfer | ~900 |
| **marketplace** | Vitality scoring & auctions | NFTVitality, CollectionVitality, AuctionEvent, VitalityPriceComparison | ~1200 |
| **axplorer** | Advanced ML analytics | MarketRegime, AdvancedCrossMarketplaceAnalysis, PredictionRecord (50+ models) | ~3000+ |

**Architecture Pattern:** Event-driven analytics with background processing

**Code Reference:** `analytics/models.py`, `marketplace/models/vitality_models.py`, `axplorer/models.py`

---

### User Interface & Admin

| App | Purpose | Key Models | Lines of Code |
|-----|---------|------------|---------------|
| **admin_panel** | Admin dashboard | AdminUser, AdminLoginAttempt, AdminLogEntry, PrimaryProviderSetting | ~500 |
| **notifications** | Alerts & notifications | AdminNotification, Notification, NotificationPreference | ~400 |
| **advertisement** | Hero carousel | HeroSlide | ~200 |
| **learn** | Educational content | Course, Lesson | ~300 |
| **nftmemories** | Community & gamification | CollectionEvent, NFTBurn, UserAchievement, CollectionRaritySnapshot | ~700 |

**Architecture Pattern:** MVC (Model-View-Controller) with Django templates

---

### Infrastructure

| App | Purpose | Key Components | Lines of Code |
|-----|---------|----------------|---------------|
| **core** | Shared services | API providers, cache manager, utilities | ~1500 |
| **system_health** | Health monitoring | (prepared for metrics) | ~100 |
| **traitkeeper** | Project config | Settings, URL routing, ASGI/WSGI | ~700 |

---

## Data Flow

### 1. NFT Data Ingestion Flow

```
┌──────────────┐
│ Solana       │
│ Blockchain   │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Helius API   │────▶│ IndexerService│────▶│ NFTCollection│
│ (RPC calls)  │     │ (async)       │     │ & NFT models │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
       ┌────────────────────┴────────────────────┐
       ▼                                         ▼
┌──────────────┐                         ┌──────────────┐
│ Magic Eden   │                         │ Tensor API   │
│ API          │                         │              │
└──────┬───────┘                         └──────┬───────┘
       │                                        │
       └────────────────┬───────────────────────┘
                        │
                        ▼
                ┌──────────────┐
                │ Data Service │
                │ (Process 2)  │
                └──────┬───────┘
                       │
                       ▼
                ┌──────────────┐
                │ PostgreSQL   │
                │ Database     │
                └──────────────┘
```

**Steps:**
1. **Data Service** subscribes to Solana blockchain via WebSocket (`indexer/services/blockchain_indexer.py`)
2. **IndexerService** detects new NFT events (mints, transfers, sales)
3. **Helius API** fetches detailed NFT metadata
4. **Magic Eden + Tensor APIs** provide marketplace listings and pricing
5. **Data aggregation** combines all sources with confidence scoring
6. **Database write** creates/updates NFT and NFTEvent records
7. **Cache invalidation** clears affected cache entries
8. **Analytics trigger** queues vitality recalculation

**Code Reference:** `indexer/services/blockchain_indexer.py:150-250`

---

### 2. Vitality Calculation Flow

```
┌──────────────┐
│ Task Manager │
│ (Scheduler)  │
└──────┬───────┘
       │ (Every 15min/1hr/4hr based on priority)
       ▼
┌──────────────────────────────────────┐
│ VitalityService.calculate_vitality() │
│ (Anti-Gaming Architecture v3.0)      │
└──────┬───────────────────────────────┘
       │
       ├─▶ Perception Index (20%) - Anti-gaming focus
       ├─▶ Trait Performance (20%)
       ├─▶ Collection Health (15%)
       ├─▶ Collection Utility (10%)
       ├─▶ Market Momentum (10%) - Reduced to prevent gaming
       ├─▶ Rarity Score (10%)
       ├─▶ Holder Quality (10%)
       └─▶ Market Influence (5%)
               │
               ▼
       ┌──────────────┐
       │ NFTVitality  │
       │ (0-100)      │
       └──────┬───────┘
              │
              ▼
       ┌──────────────┐
       │ Redis Cache  │
       │ (5-30 min)   │
       └──────────────┘
```

**Priority-Based Scheduling:**
- **VIP:** Every 15 minutes (high-activity collections)
- **ACTIVE:** Every 1 hour (normal activity)
- **INACTIVE:** Every 4 hours (low activity)

**Code Reference:** `marketplace/services/vitality_service.py:50-300`

---

### 3. Real-Time SSE Stream Flow

```
User Browser
    │
    │ (GET /stream-highest-vitality-collections/)
    ▼
┌──────────────┐
│ Django View  │
│ (Process 1)  │
└──────┬───────┘
       │
       │ (Every 5 seconds in loop)
       ▼
┌──────────────┐
│ Redis Cache  │
│ (check TTL)  │
└──────┬───────┘
       │
       │ (Cache miss or expired)
       ▼
┌──────────────┐
│ PostgreSQL   │
│ (query DB)   │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ JSON encode  │
│ & stream SSE │
└──────┬───────┘
       │
       ▼
User Browser (updates UI without reload)
```

**Code Reference:** `traitkeeper/views.py:200-250` (SSE stream endpoints)

---

## Caching Strategy

### Multi-Tier Cache Architecture

TraitKeeper uses a **priority-based caching strategy** with different TTLs based on collection activity:

```
┌────────────────────────────────────────────────────┐
│              Redis Cache Layer                      │
├────────────────────────────────────────────────────┤
│                                                     │
│  VIP Collections (5-30 min TTL)                    │
│  ├─ Vitality scores                                │
│  ├─ Collection stats                               │
│  └─ Marketplace data                               │
│                                                     │
│  ACTIVE Collections (30 min - 2 hr TTL)            │
│  ├─ Vitality scores                                │
│  ├─ Collection stats                               │
│  └─ Marketplace data                               │
│                                                     │
│  INACTIVE Collections (4-24 hr TTL)                │
│  ├─ Vitality scores                                │
│  ├─ Collection stats                               │
│  └─ Marketplace data                               │
│                                                     │
│  Provider-Specific Caches                          │
│  ├─ Magic Eden slugs (7 days)                      │
│  ├─ Tensor UUIDs (24 hours)                        │
│  ├─ Blockchain transactions (30 minutes)           │
│  └─ NFT metadata (1 hour)                          │
│                                                     │
└────────────────────────────────────────────────────┘
```

### Cache Warming Strategy

**On Application Startup:**
1. Load all VIP collections
2. Pre-fetch vitality scores
3. Load homepage hero slides
4. Cache provider metadata (Magic Eden slugs, Tensor UUIDs)

**Code Reference:** `core/cache_manager.py:100-200`

```python
class CacheManager:
    def warm_cache_on_startup(self):
        # VIP collections get priority
        vip_collections = NFTCollection.objects.filter(
            priority='VIP',
            is_active=True
        )

        for collection in vip_collections:
            # Pre-fetch and cache vitality
            vitality = self.get_or_set(
                f"vitality:{collection.address}",
                lambda: VitalityService.calculate(collection),
                ttl=900  # 15 minutes
            )
```

### Cache Invalidation

**Strategies:**
1. **Time-based expiration** - TTL based on priority tier
2. **Event-driven invalidation** - Clear cache on data updates
3. **Dependency tracking** - Cascade invalidation for related data

**Code Reference:** `core/cache_manager.py:250-300`

---

## Background Task System

### Custom Task Manager

TraitKeeper uses a **custom threading-based task manager** instead of Celery for simpler deployment:

```python
# core/task_manager.py
class TaskManager:
    def __init__(self, max_workers=4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.task_queue = PriorityQueue()
        self.retry_limit = 3
        self.retry_delay = 120  # seconds

    def submit_task(self, task_func, priority='NORMAL'):
        """Submit task with priority: VIP > ACTIVE > INACTIVE"""
        self.task_queue.put((priority, task_func))
```

### Task Types & Priorities

| Task Type | Priority | Frequency | Timeout |
|-----------|----------|-----------|---------|
| VIP Vitality Calculation | HIGH | 15 min | 60s |
| ACTIVE Vitality Calculation | NORMAL | 1 hr | 120s |
| INACTIVE Vitality Calculation | LOW | 4 hr | 180s |
| Blockchain Indexing | HIGH | Real-time | N/A (async) |
| Analytics Aggregation | NORMAL | 30 min | 300s |
| Sweep Detection | HIGH | 5 min | 60s |
| Anomaly Detection | NORMAL | 1 hr | 180s |

**Code Reference:** `core/task_manager.py:1-200`

---

## API Provider Architecture

### Provider Abstraction Layer

TraitKeeper supports multiple RPC and marketplace providers through a **unified interface**:

```python
# core/api_provider/base.py
class BaseProvider(ABC):
    @abstractmethod
    async def fetch_nft_metadata(self, mint_address: str) -> dict:
        pass

    @abstractmethod
    async def fetch_collection_stats(self, collection_address: str) -> dict:
        pass
```

### Implemented Providers

```
┌────────────────────────────────────────────────┐
│          API Provider Orchestration            │
├────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────┐  ┌──────────────┐           │
│  │ Helius RPC   │  │ QuickNode    │           │
│  │ Provider     │  │ RPC Provider │           │
│  └──────┬───────┘  └──────┬───────┘           │
│         │                 │                     │
│         └────────┬────────┘                     │
│                  │                              │
│          ┌───────▼───────┐                      │
│          │ RPC Provider  │                      │
│          │ Selector      │                      │
│          │ (Primary/     │                      │
│          │  Fallback)    │                      │
│          └───────────────┘                      │
│                                                 │
│  ┌──────────────┐  ┌──────────────┐           │
│  │ Magic Eden   │  │ Tensor API   │           │
│  │ Provider     │  │ Provider     │           │
│  └──────────────┘  └──────────────┘           │
│                                                 │
└────────────────────────────────────────────────┘
```

**Quota Management:**
- Helius: Free (1M/day), Developer (10M/day)
- QuickNode: Free (10M/day), Build (80M/day)
- Priority allocation: VIP (60%), ACTIVE (30%), INACTIVE (10%)

**Code Reference:** `core/api_provider/` directory

---

## Real-Time Updates

### Server-Sent Events (SSE)

**Why SSE over WebSockets?**
- Simpler implementation (HTTP/2)
- Automatic reconnection
- Browser compatibility
- Lower server overhead

**SSE Endpoints:**
- `/stream-site-updates/` - General site updates
- `/stream-hero-slides/` - Homepage carousel
- `/stream-highest-vitality-collections/` - Top collections

**Code Reference:** `traitkeeper/views.py:200-300`

```python
def stream_highest_vitality_collections(request):
    def event_stream():
        while True:
            # Query top collections
            collections = CollectionVitality.objects.order_by('-vitality_score')[:10]

            # Format as SSE
            data = json.dumps([...])
            yield f"data: {data}\n\n"

            time.sleep(5)  # Update every 5 seconds

    return StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
```

---

## Database Architecture

### Schema Design Principles

1. **Denormalization for performance** - Pre-compute common queries
2. **Strategic indexing** - Multi-column indexes for common filters
3. **JSON fields for flexibility** - Traits stored as JSON
4. **Foreign key constraints** - Data integrity enforcement
5. **Soft deletes** - Preserve historical data

### Key Relationships

```
NFTCollection (1) ──┬─── (*) NFT
                    ├─── (*) TraitType ──── (*) TraitValue
                    ├─── (1) CollectionVitality
                    └─── (1) AggregatedCollectionStats

NFT (1) ──┬─── (1) NFTVitality
          ├─── (*) NFTEvent
          └─── (*) NFTListing

CustomUser (1) ──┬─── (*) WalletProfile
                 ├─── (*) Notification
                 └─── (*) PendingCollection
```

**See:** `docs/DATABASE_SCHEMA.md` for comprehensive schema documentation

---

## Security Architecture

### Authentication

**Dual Authentication System:**
1. **CustomUser** - Regular users (email + password, Google OAuth)
2. **AdminUser** - Separate admin authentication (not Django's built-in)

**Code Reference:** `traitkeeper/settings.py:150-180`

```python
AUTHENTICATION_BACKENDS = [
    'wallet.backends.CustomUserBackend',
    'admin_panel.backends.AdminUserBackend',
    'django.contrib.auth.backends.ModelBackend',
]
```

### Authorization

- **Django permissions** - Model-level permissions
- **Custom decorators** - View-level access control
- **Admin audit logging** - All admin actions logged

### Rate Limiting

```python
# traitkeeper/settings.py:200
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '500/hour',
        'admin': '1000/hour',
    }
}
```

---

## Deployment Architecture

### Docker Compose Services

```yaml
services:
  main:
    # Main app (user-facing)
    environment:
      - RUN_BACKGROUND_TASKS=false
    ports:
      - "8000:8000"

  data:
    # Data service (background tasks)
    environment:
      - RUN_BACKGROUND_TASKS=true
    # No exposed ports

  postgres:
    image: postgres:15

  redis:
    image: redis:7
```

### Production Deployment (systemd)

```bash
# /etc/systemd/system/traitkeeper-main.service
[Unit]
Description=TraitKeeper Main App
After=network.target postgresql.service redis.service

[Service]
Environment="RUN_BACKGROUND_TASKS=false"
ExecStart=/usr/bin/gunicorn traitkeeper.wsgi:application

# /etc/systemd/system/traitkeeper-data.service
[Unit]
Description=TraitKeeper Data Service
After=network.target postgresql.service redis.service

[Service]
Environment="RUN_BACKGROUND_TASKS=true"
ExecStart=/usr/bin/python manage.py run_data_service
```

---

## Performance Metrics

### Current Performance (Production)

| Metric | Main App | Data Service |
|--------|----------|--------------|
| **Response Time (p95)** | 450ms | N/A |
| **CPU Usage** | 25% | 65% |
| **Memory Usage** | 800MB | 1.2GB |
| **Requests/sec** | 50-100 | N/A |
| **Cache Hit Rate** | 85% | N/A |

### Scalability Targets

- **Horizontal scaling** - Deploy multiple Main App instances behind load balancer
- **Vertical scaling** - Increase Data Service resources for faster processing
- **Database scaling** - Read replicas for analytics queries

---

## Monitoring & Observability

### Health Checks

```bash
# Main app health
GET /admin/panel/system-status/
# Returns: {"status": "healthy", "background_tasks": false}

# Data service health
docker logs traitkeeper-data | grep "VitalityTaskManager"
# Should show regular task execution
```

### Logging

- **Main App:** `logs/main.log` - User requests, API calls
- **Data Service:** `logs/data.log` - Task execution, blockchain events
- **Django:** Standard Django logging (DEBUG/INFO/WARNING/ERROR)

---

## Future Architecture Enhancements

### Phase 1 (Q2 2025)
- [ ] Kubernetes deployment
- [ ] Prometheus + Grafana monitoring
- [ ] Distributed tracing (OpenTelemetry)
- [ ] Read replicas for analytics

### Phase 2 (Q3 2025)
- [ ] GraphQL API
- [ ] Multi-region deployment
- [ ] Event sourcing for audit trail
- [ ] ML model serving (TensorFlow Serving)

### Phase 3 (Q4 2025)
- [ ] Microservices migration (separate services for indexer, vitality, analytics)
- [ ] Apache Kafka for event streaming
- [ ] Elasticsearch for advanced search
- [ ] Redis Cluster for high availability

---

## Related Documentation

- [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) - Comprehensive database documentation
- [VITALITY_SYSTEM.md](./VITALITY_SYSTEM.md) - Vitality calculation details
- [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) - API reference
- [CACHING_STRATEGY.md](./CACHING_STRATEGY.md) - Detailed caching guide
- [HOW_RPC_PROVIDERS_WORK.md](./HOW_RPC_PROVIDERS_WORK.md) - RPC provider configuration

---

**Last Updated:** January 2025
**Version:** 1.0.0
**Author:** TraitKeeper Architecture Team
