# TraitKeeper Analytics System - Complete Overview

## Table of Contents

1. [Overview](#overview)
2. [Analytics Architecture](#analytics-architecture)
3. [Data Collection Pipeline](#data-collection-pipeline)
4. [Calculation Engines](#calculation-engines)
5. [Analytics Components](#analytics-components)
6. [Update & Scheduling](#update--scheduling)
7. [Performance & Caching](#performance--caching)
8. [Data Flow Diagram](#data-flow-diagram)

---

## Overview

**TraitKeeper Analytics** is a comprehensive NFT intelligence system that transforms raw blockchain data into actionable insights. The system processes data from multiple sources (Solana blockchain, Magic Eden, Tensor) and applies sophisticated algorithms to calculate metrics across three major domains:

### Core Analytics Domains

1. **Vitality Scoring** - Multi-dimensional health assessment for NFTs and collections
2. **Market Intelligence** - Trading patterns, sweeps, anomaly detection
3. **Predictive Analytics** - ML-powered market regime prediction and price forecasting

### Why TraitKeeper Analytics?

**Traditional NFT Platforms:**
- Rely solely on floor price and volume
- No real-time market health indicators
- Limited historical analysis
- No predictive capabilities

**TraitKeeper Solution:**
- 8-component vitality scoring replacing floor price
- Real-time sweep detection and whale tracking
- 90-day historical trend analysis
- ML-powered predictions (regime detection, price forecasting)
- Cross-marketplace aggregation (Magic Eden, Tensor, TraitKeeper)

---

## Analytics Architecture

### Three-Layer Processing System

```
┌──────────────────────────────────────────────────────────┐
│                  DATA INGESTION LAYER                     │
│  (Blockchain Indexer, API Scrapers, Event Listeners)    │
└────────────────┬─────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────┐
│              RAW DATA STORAGE (PostgreSQL)                │
│  • NFTEvent (sales, transfers, listings)                 │
│  • NFT metadata & traits                                 │
│  • Collection data                                        │
│  • User wallet profiles                                  │
└────────────────┬─────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────┐
│            ANALYTICS PROCESSING LAYER                     │
│  ┌───────────────┬──────────────┬────────────────────┐  │
│  │   Vitality    │   Market     │    Predictive      │  │
│  │   Engine      │   Analytics  │    ML Engine       │  │
│  │  (8 metrics)  │  (sweeps,    │  (regime, price)   │  │
│  │               │   anomalies) │                    │  │
│  └───────────────┴──────────────┴────────────────────┘  │
└────────────────┬─────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────┐
│         COMPUTED ANALYTICS STORAGE (PostgreSQL)           │
│  • NFTVitality & NFTVitalityHistory                      │
│  • AggregatedCollectionStats                             │
│  • CollectionSweepEvent                                  │
│  • MarketRegime, PredictionRecord                        │
└──────────────────────────────────────────────────────────┘
```

### Processing Modes

| Mode | Purpose | Frequency | Load |
|------|---------|-----------|------|
| **Real-Time** | Critical events (sweeps, high-value sales) | < 5 seconds | High priority |
| **Scheduled** | Vitality updates, stats aggregation | 15min - 4hr (tier-based) | Normal priority |
| **Batch** | Historical analysis, ML training | Daily/Weekly | Low priority |
| **On-Demand** | User-triggered recalculations | As requested | Normal priority |

**Code Reference:** `indexer/background_task_manager.py`, `marketplace/services/vitality_service.py`, `axplorer/prediction_engine.py`

---

## Data Collection Pipeline

### 1. Blockchain Indexing

**Process Flow:**

```
Solana RPC → NFT Events → Database Storage → Analytics Trigger
```

**What We Index:**

| Event Type | Frequency | Data Captured | Processing |
|-----------|-----------|---------------|------------|
| **SALE** | ~500/hour | Price, buyer, seller, timestamp, marketplace | Real-time analytics update |
| **TRANSFER** | ~200/hour | From/to wallets, timestamp | Holder quality recalc |
| **LISTING** | ~300/hour | List price, marketplace, expiry | Liquidity metrics update |
| **MINT** | ~50/hour | Minter, collection, metadata | Collection stats update |
| **BURN** | ~5/hour | Burner, collection | Supply metrics update |

**Code Reference:** `indexer/services/solana_service.py:150-450`, `indexer/models.py:20-75`

### 2. Marketplace API Integration

**Magic Eden & Tensor Data:**

```python
# Every 5 minutes for VIP collections
fetch_collection_stats()  # Floor, volume, listed count
fetch_recent_sales()      # Last 100 sales
fetch_active_listings()   # Current listings
```

**Data Validated & Merged:**
- Cross-check on-chain data vs marketplace API
- Resolve discrepancies (on-chain = source of truth)
- Fill gaps in historical data

**Code Reference:** `marketplace/services/marketplace_api.py:50-200`

### 3. Trait Rarity Calculation

**One-Time Processing** (on collection import):

```python
def calculate_trait_rarity(collection):
    # For each trait type (Background, Hat, Eyes, etc.)
    for trait_type in collection.trait_types.all():
        trait_values = TraitValue.objects.filter(trait_type=trait_type)
        total_nfts = collection.nfts.count()

        for trait_value in trait_values:
            # Count NFTs with this trait
            count = collection.nfts.filter(
                traits__contains={trait_type.name: trait_value.value}
            ).count()

            # Calculate rarity percentage
            rarity = (count / total_nfts) * 100
            trait_value.rarity_percentage = rarity
            trait_value.nft_count = count
            trait_value.save()
```

**Result:** Trait rarity percentages stored in `TraitValue` model for fast lookups

**Code Reference:** `nft_data/services/trait_service.py:100-180`

---

## Calculation Engines

### 1. Vitality Scoring Engine

**Purpose:** Calculate comprehensive health scores (0-100) for NFTs and collections

**Formula (8 Components):**

```
Vitality Score =
    (Perception Index × 20%) +      ← Community perception (anti-gaming)
    (Trait Performance × 20%) +     ← Trait demand & pricing
    (Collection Health × 15%) +     ← Ecosystem stability
    (Collection Utility × 10%) +    ← Real-world use cases
    (Market Momentum × 10%) +       ← Price velocity (reduced to prevent gaming)
    (Rarity Score × 10%) +          ← Statistical rarity
    (Holder Quality × 10%) +        ← Holder profile & behavior
    (Market Influence × 5%)         ← Broader market impact
```

**Calculation Process:**

```
1. Fetch NFT Data
   ├─ Metadata (traits, rarity rank)
   ├─ Recent events (sales, transfers)
   ├─ Listing status & price
   └─ Collection stats

2. Parallel Component Calculation (ThreadPoolExecutor)
   ├─ Thread 1: Market Momentum
   ├─ Thread 2: Trait Performance
   ├─ Thread 3: Collection Health
   ├─ Thread 4: Collection Utility
   ├─ Thread 5: Rarity Score
   ├─ Thread 6: Holder Quality
   ├─ Thread 7: Perception Index
   └─ Thread 8: Market Influence

3. Weighted Aggregation
   └─ Sum (component × weight)

4. Confidence Scoring
   └─ Data quality assessment (0-100)

5. Persistence
   ├─ Update NFTVitality record
   ├─ Create NFTVitalityHistory snapshot
   └─ Invalidate cache
```

**Performance:** 3.2 seconds per NFT (8 parallel calculations)

**For detailed vitality documentation, see:** [VITALITY_SYSTEM.md](./VITALITY_SYSTEM.md)

**Code Reference:** `marketplace/services/vitality_service.py:50-820`

---

### 2. Collection Stats Aggregation Engine

**Purpose:** Pre-compute expensive collection-level metrics

**Metrics Calculated:**

| Category | Metrics | Update Frequency |
|----------|---------|------------------|
| **Volume** | 24h, 7d, 30d volume in SOL | Every 30 min |
| **Price** | Floor, ceiling, avg sale price | Every 15 min (VIP) |
| **Liquidity** | Listed count, listed ratio | Every 15 min |
| **Holders** | Unique holders, top holder % | Every 1 hour |
| **Activity** | Sales count (24h, 7d, 30d) | Every 30 min |
| **Market Cap** | Total value estimate | Every 1 hour |
| **Trends** | 7d/30d price change % | Every 1 hour |

**Calculation Example:**

```python
def aggregate_collection_stats(collection):
    now = timezone.now()

    # Volume calculations
    sales_24h = NFTEvent.objects.filter(
        collection=collection,
        event_type='SALE',
        timestamp__gte=now - timedelta(hours=24)
    )

    volume_24h = sales_24h.aggregate(Sum('price'))['price__sum'] or 0
    sales_count_24h = sales_24h.count()

    # Repeat for 7d, 30d windows
    # ... (similar queries for 7d and 30d)

    # Floor price (lowest current listing)
    floor_price = NFTListing.objects.filter(
        nft__collection=collection,
        status='ACTIVE'
    ).aggregate(Min('price'))['price__min']

    # Unique holders
    unique_holders = NFT.objects.filter(
        collection=collection
    ).values('owner').distinct().count()

    # Price changes
    price_7d_ago = get_historical_floor_price(collection, days=7)
    price_change_7d = ((floor_price - price_7d_ago) / price_7d_ago) * 100

    # Save to AggregatedCollectionStats
    stats, created = AggregatedCollectionStats.objects.update_or_create(
        collection=collection,
        defaults={
            'total_volume_24h': volume_24h,
            'sales_count_24h': sales_count_24h,
            'floor_price_sol': floor_price,
            'unique_holders': unique_holders,
            'price_change_7d_percent': price_change_7d,
            # ... 20+ more fields
        }
    )
```

**Why Pre-Compute?**
- Collection pages load in < 500ms (vs 5+ seconds with live queries)
- Reduces database load by 90%
- Enables fast API responses

**Code Reference:** `analytics/services/aggregation_service.py:50-300`

---

### 3. Sweep Detection Engine

**Purpose:** Identify bulk purchases (whale activity) in real-time

**Detection Algorithm:**

```python
def detect_sweep(event: NFTEvent):
    # Sweep criteria
    SWEEP_THRESHOLDS = {
        'min_nfts': 3,        # At least 3 NFTs
        'time_window': 300,   # Within 5 minutes
        'min_value': 5.0,     # Total value > 5 SOL
    }

    # Find recent purchases by same buyer
    recent_purchases = NFTEvent.objects.filter(
        collection=event.collection,
        event_type='SALE',
        to_wallet=event.to_wallet,
        timestamp__gte=event.timestamp - timedelta(
            seconds=SWEEP_THRESHOLDS['time_window']
        )
    )

    nft_count = recent_purchases.count()
    total_value = recent_purchases.aggregate(Sum('price'))['price__sum']

    # Is it a sweep?
    if (nft_count >= SWEEP_THRESHOLDS['min_nfts'] and
        total_value >= SWEEP_THRESHOLDS['min_value']):

        # Create sweep event
        sweep = CollectionSweepEvent.objects.create(
            collection=event.collection,
            buyer=event.to_wallet,
            nft_count=nft_count,
            total_value_sol=total_value,
            avg_price_sol=total_value / nft_count,
            sweep_duration_seconds=calculate_duration(recent_purchases),
            sweep_type='FLOOR' if is_floor_sweep(recent_purchases) else 'MIXED'
        )

        # Trigger notifications
        notify_sweep_subscribers(sweep)

    return sweep
```

**Sweep Types:**

| Type | Definition | Example |
|------|------------|---------|
| **FLOOR** | All purchases within 5% of floor | Buyer scoops 10 NFTs at 2.1-2.2 SOL (floor: 2.0) |
| **TRAIT** | Focused on specific traits | Buyer purchases all "Gold Crown" NFTs |
| **MIXED** | Mix of floor and rare traits | Strategic accumulation |
| **PANIC** | During rapid price decline | Buying the dip |

**Code Reference:** `analytics/services/sweep_detector.py:20-180`

---

### 4. Predictive Analytics Engine (ML-Powered)

**Purpose:** Forecast market trends and price movements

**ML Models Deployed:**

1. **Market Regime Detection**
   - **Model:** XGBoost Classifier
   - **Input Features:** 15 market indicators (volume velocity, price volatility, social metrics)
   - **Output:** BULL / BEAR / SIDEWAYS / VOLATILE
   - **Accuracy:** 73% on test set
   - **Update:** Every 1 hour

2. **Collection Price Prediction**
   - **Model:** LSTM Neural Network
   - **Input:** 90-day price/volume history
   - **Output:** 7-day price forecast (floor, avg, ceiling)
   - **MAE:** 12% (mean absolute error)
   - **Update:** Daily

3. **Vitality Trend Prediction**
   - **Model:** Random Forest Regressor
   - **Input:** 30-day vitality history + market features
   - **Output:** Expected vitality change (7d, 30d)
   - **R²:** 0.68
   - **Update:** Daily

**Prediction Flow:**

```
1. Feature Engineering
   ├─ Extract 30-90 days of historical data
   ├─ Calculate technical indicators (RSI, MACD, Bollinger Bands)
   ├─ Add social metrics (Twitter mentions, Discord activity)
   └─ Normalize features

2. Model Inference
   ├─ Load trained model from disk
   ├─ Run prediction
   └─ Calculate confidence intervals

3. Post-Processing
   ├─ Smooth predictions (moving average)
   ├─ Apply constraints (price can't go negative)
   └─ Add confidence scores

4. Storage
   └─ Save to PredictionRecord table
```

**Code Reference:** `axplorer/prediction_engine.py:50-500`, `axplorer/models.py:20-150`

---

## Analytics Components

### Component Breakdown

#### 1. Market Momentum (10% of Vitality)

**What:** 60-day price velocity + trading activity acceleration

**Calculation:**

```python
# Price change (current vs 60 days ago)
price_change_60d = ((current_price - price_60d_ago) / price_60d_ago) * 100

# Volume acceleration (7d vs 30d daily rates)
daily_vol_7d = volume_7d / 7
daily_vol_30d = volume_30d / 30
volume_acceleration = daily_vol_7d / daily_vol_30d

# Sales frequency (recent activity)
sales_7d = get_sales_count(collection, days=7)

# Weighted score
momentum = (
    normalize(price_change_60d, -50, 50) * 0.50 +
    normalize(volume_acceleration, 0.5, 2.0) * 0.30 +
    normalize(sales_7d, 0, 100) * 0.20
)
```

**Why 10%?** Reduced from 25% to prevent wash trading manipulation.

---

#### 2. Trait Performance (20% of Vitality)

**What:** Market demand for NFT's specific traits

**Calculation:**

```python
trait_scores = []

for trait_type, trait_value in nft.traits.items():
    # Get recent sales with this trait
    sales_with_trait = get_sales_by_trait(
        collection, trait_type, trait_value, days=30
    )

    # Calculate price premium
    avg_with_trait = sales_with_trait.avg_price()
    collection_avg = collection.avg_sale_price()
    premium = (avg_with_trait / collection_avg - 1) * 100

    # Get trait rarity
    trait_obj = TraitValue.objects.get(...)
    rarity_multiplier = (100 - trait_obj.rarity_percentage) / 100

    # Score this trait
    trait_score = normalize(premium, -20, 80) * rarity_multiplier
    trait_scores.append(trait_score)

# Average across all traits
return sum(trait_scores) / len(trait_scores)
```

**Key Insight:** Rare traits with high price premiums score best.

---

#### 3. Collection Health (15% of Vitality)

**What:** Overall collection ecosystem stability

**Sub-Metrics:**

| Sub-Metric | Weight | Ideal Range | What It Measures |
|------------|--------|-------------|------------------|
| Liquidity | 30% | 5-15% listed | Healthy listing ratio |
| Holder Distribution | 30% | 40-80% unique | Decentralization |
| Volume Consistency | 20% | Ratio near 1.0 | Stable trading activity |
| Price Stability | 20% | Low volatility | Mature market |

**Calculation:**

```python
# Liquidity score
listed_ratio = listed_count / total_supply
liquidity = normalize(listed_ratio, 0.05, 0.15)  # 5-15% ideal

# Holder distribution
holder_ratio = unique_holders / total_supply
holder_dist = normalize(holder_ratio, 0.40, 0.80)

# Volume consistency (7d vs 30d)
vol_consistency = 100 - abs((vol_7d/7) / (vol_30d/30) - 1) * 50

# Price stability
stability = max(100 - abs(price_volatility) * 2, 0)

# Weighted sum
health = (
    liquidity * 0.30 +
    holder_dist * 0.30 +
    vol_consistency * 0.20 +
    stability * 0.20
)
```

---

#### 4. Perception Index (20% of Vitality)

**What:** Community perception & genuine engagement (anti-gaming metric)

**Future Implementation:**
- Twitter sentiment analysis (positive/negative mentions)
- Discord activity metrics (messages, unique users)
- TraitKeeper user reviews/ratings
- Buy vs sell pressure ratios
- Anti-bot detection heuristics

**Current State:** Returns neutral (50) until full implementation

**Why 20%?** Increased from 5% to prioritize genuine community engagement over easily manipulated metrics.

---

## Update & Scheduling

### Priority-Based Update System

TraitKeeper uses a **3-tier priority system** to optimize resource usage:

| Tier | Collections | Update Frequency | Use Case |
|------|-------------|------------------|----------|
| **VIP** | Top 50 by volume | Every 15 minutes | Mad Lads, Famous Fox, Tensorians |
| **ACTIVE** | 500+ collections | Every 1 hour | Established projects with regular activity |
| **INACTIVE** | 2000+ collections | Every 4 hours | Smaller or declining projects |

### Scheduled Tasks

```python
# VIP Collection Updates - Every 15 minutes
scheduler.add_job(
    update_vip_vitality,
    'interval',
    minutes=15
)

# Collection Stats Aggregation - Every 30 minutes
scheduler.add_job(
    aggregate_collection_stats,
    'interval',
    minutes=30
)

# ML Predictions - Daily at 2 AM
scheduler.add_job(
    run_prediction_engine,
    'cron',
    hour=2
)

# Sweep Detection - Real-time (event-driven)
@receiver(post_save, sender=NFTEvent)
def check_for_sweep(sender, instance, **kwargs):
    if instance.event_type == 'SALE':
        detect_sweep(instance)
```

**Code Reference:** `indexer/background_task_manager.py:200-400`

---

## Performance & Caching

### Multi-Tier Caching Strategy

```
┌─────────────────────────────────────────────────────────┐
│ L1: In-Memory Cache (lru_cache)                         │
│ • Trait rarity lookups                                  │
│ • Collection metadata                                   │
│ • TTL: Session-based                                    │
└───────────────────┬─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│ L2: Redis Cache                                          │
│ • Vitality scores (15-30 min TTL)                       │
│ • Aggregated stats (30 min TTL)                         │
│ • API responses (5 min TTL)                             │
└───────────────────┬─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│ L3: PostgreSQL (Source of Truth)                        │
│ • All raw & computed data                               │
│ • Strategic indexes for fast queries                    │
└─────────────────────────────────────────────────────────┘
```

### Performance Benchmarks

| Operation | Target | Actual | Optimization |
|-----------|--------|--------|--------------|
| Single NFT Vitality Calc | < 5s | 3.2s | Parallel threads |
| Collection (10k NFTs) | < 10min | 8.5min | Batch processing |
| Stats Aggregation | < 30s | 12s | Indexed queries |
| Sweep Detection | < 1s | 0.3s | Real-time trigger |
| API Response (cached) | < 50ms | 15ms | Redis caching |

**Cache Hit Rates:**
- Vitality scores: 85%
- Collection stats: 90%
- Trait rarity: 95%

---

## Data Flow Diagram

### End-to-End Analytics Pipeline

```
┌─────────────┐
│   Solana    │
│ Blockchain  │◄──── Indexer polls every 30s
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  NFTEvent   │──┐
│   Table     │  │
└─────────────┘  │
                 │
       ┌─────────┴────────┐
       │                  │
       ▼                  ▼
┌─────────────┐    ┌─────────────┐
│   Sweep     │    │  Vitality   │
│  Detection  │    │   Engine    │
└──────┬──────┘    └──────┬──────┘
       │                  │
       │                  ▼
       │           ┌─────────────┐
       │           │ NFTVitality │
       │           │   Table     │
       │           └──────┬──────┘
       │                  │
       │                  ▼
       │           ┌─────────────┐
       │           │  Vitality   │
       │           │  History    │
       │           └──────┬──────┘
       │                  │
       ▼                  ▼
┌──────────────────────────────┐
│    Collection Stats          │
│    Aggregation Engine        │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ AggregatedCollectionStats    │
│         Table                │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│   Predictive ML Engine       │
│   (Daily Updates)            │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│    PredictionRecord          │
│         Table                │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│   API / Frontend             │
│   (User-Facing)              │
└──────────────────────────────┘
```

---

## Related Documentation

- **[VITALITY_SYSTEM.md](./VITALITY_SYSTEM.md)** - Deep dive into vitality scoring algorithm
- **[DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)** - Complete database schema
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - System architecture overview
- **[CACHING_STRATEGY.md](./CACHING_STRATEGY.md)** - Caching implementation details

---

**Last Updated:** January 2025
**Version:** 2.0.0
**Author:** TraitKeeper Analytics Team

**Changelog:**
- **v2.0 (January 2025):** Anti-Gaming Architecture
  - Perception Index weight increased to 20%
  - Market Momentum reduced to 10%
  - Enhanced sweep detection algorithm
  - Added ML-powered predictions

