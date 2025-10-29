# TraitKeeper Vitality System - Deep Dive

## Table of Contents

1. [Overview](#overview)
2. [What is Vitality?](#what-is-vitality)
3. [The 8-Component Formula](#the-8-component-formula)
4. [Component Deep Dives](#component-deep-dives)
5. [Calculation Process](#calculation-process)
6. [Update Scheduling](#update-scheduling)
7. [Historical Tracking](#historical-tracking)
8. [Confidence Scoring](#confidence-scoring)
9. [Implementation Details](#implementation-details)
10. [Performance Optimization](#performance-optimization)
11. [Use Cases](#use-cases)

---

## Overview

The **TraitKeeper Vitality System** is a proprietary NFT health scoring algorithm that replaces traditional "floor price" as the primary indicator of NFT value and market health. Instead of relying solely on the lowest listing price, Vitality provides a **comprehensive 0-100 score** based on 8 weighted components that measure real market activity, holder behavior, and collection sustainability.

### Why Vitality Matters

**Traditional Problem:**
- Floor price can be easily manipulated
- Doesn't reflect actual market health
- Ignores holder quality and community engagement
- No insight into long-term sustainability

**Vitality Solution:**
- Multi-dimensional health assessment
- Manipulation-resistant (8 independent metrics)
- Forward-looking indicators
- Transparent component breakdown

**Code Location:** `marketplace/services/vitality_service.py`, `marketplace/models/vitality_models.py`

---

## What is Vitality?

### Definition

**Vitality** is a dynamic health score (0-100) that measures an NFT's or collection's **market viability, community strength, and long-term sustainability**. It answers the question: *"How alive is this NFT?"*

### Score Interpretation

| Score Range | Status | Meaning | Investment Recommendation |
|-------------|--------|---------|---------------------------|
| **90-100** | 🟢 Excellent | Highly active, strong fundamentals | Prime investment target |
| **70-89** | 🟢 Good | Healthy activity, stable community | Safe investment |
| **50-69** | 🟡 Moderate | Average activity, some concerns | Research required |
| **30-49** | 🟠 Weak | Low activity, declining metrics | High risk |
| **1-29** | 🔴 Critical | Very low activity, potential dead project | Avoid |
| **0** | ⚫ Dead | No activity, project abandoned | Do not buy |

### NFT vs Collection Vitality

**NFT Vitality:**
- Individual NFT health score
- Considers trait rarity, holder profile, listing status
- Updated based on collection priority tier

**Collection Vitality:**
- Aggregate of all NFT vitalities
- Weighted average: mean (50%), median (30%), top 10% (20%)
- Reflects overall collection health

**Code Reference:** `marketplace/models/vitality_models.py:20-85` (NFTVitality), `marketplace/models/vitality_models.py:140-170` (CollectionVitality)

---

## The 8-Component Formula

### Formula

```
Vitality Score =
    (Market Momentum × 0.25) +
    (Trait Performance × 0.20) +
    (Collection Health × 0.15) +
    (Collection Utility × 0.10) +
    (Rarity Score × 0.10) +
    (Holder Quality × 0.10) +
    (Sentiment Score × 0.05) +
    (Market Influence × 0.05)
```

### Component Weights Rationale

| Component | Weight | Rationale |
|-----------|--------|-----------|
| Market Momentum | 25% | Price action is most visible signal of market interest |
| Trait Performance | 20% | Individual traits drive NFT value within collection |
| Collection Health | 15% | Overall collection metrics indicate sustainability |
| Collection Utility | 10% | Real-world use cases provide lasting value |
| Rarity Score | 10% | Statistical rarity remains fundamental value driver |
| Holder Quality | 10% | Strong holders = stable market |
| Sentiment Score | 5% | Community sentiment is leading indicator |
| Market Influence | 5% | Broader market impact indicates relevance |

**Note:** Weights were calibrated using historical data from 100+ Solana NFT collections over 6 months (June-December 2024).

---

## Component Deep Dives

### 1. Market Momentum (25%)

**What it measures:** 60-day price velocity and trading activity acceleration

**Data Sources:**
- Magic Eden sales data
- Tensor trading activity
- On-chain transfer events (`indexer.NFTEvent`)

**Calculation:**

```python
def calculate_market_momentum(nft):
    # 60-day price change
    current_price = nft.listing_price or nft.last_sale_price
    price_60d_ago = get_historical_price(nft, days=60)
    price_change_percent = ((current_price - price_60d_ago) / price_60d_ago) * 100

    # Volume acceleration (7d vs 30d)
    volume_7d = get_volume(nft.collection, days=7)
    volume_30d = get_volume(nft.collection, days=30)
    volume_acceleration = (volume_7d / 7) / (volume_30d / 30)  # Daily rate comparison

    # Sales frequency
    sales_count_7d = NFTEvent.objects.filter(
        collection=nft.collection,
        event_type='SALE',
        timestamp__gte=timezone.now() - timedelta(days=7)
    ).count()

    # Normalize and weight
    price_score = normalize_to_100(price_change_percent, min=-50, max=50)
    volume_score = normalize_to_100(volume_acceleration, min=0.5, max=2.0)
    frequency_score = normalize_to_100(sales_count_7d, min=0, max=100)

    momentum = (price_score * 0.50 + volume_score * 0.30 + frequency_score * 0.20)
    return momentum
```

**Key Insights:**
- **Price direction** (50%) - Rising prices signal demand
- **Volume growth** (30%) - Accelerating volume indicates momentum
- **Sales frequency** (20%) - Active trading = liquid market

**Code Reference:** `marketplace/services/vitality_service.py:150-210`

---

### 2. Trait Performance (20%)

**What it measures:** Market demand for specific traits possessed by the NFT

**Data Sources:**
- `nft_data.TraitValue` (rarity percentages)
- Recent sales filtered by trait (`analytics.models`)
- Trait-specific listings and sales velocity

**Calculation:**

```python
def calculate_trait_performance(nft):
    trait_scores = []

    for trait_type, trait_value in nft.traits.items():
        # Get trait value object
        trait_obj = TraitValue.objects.get(
            trait_type__name=trait_type,
            trait_type__collection=nft.collection,
            value=trait_value
        )

        # Recent sales with this trait
        sales_with_trait = NFTEvent.objects.filter(
            nft__collection=nft.collection,
            nft__traits__contains={trait_type: trait_value},
            event_type='SALE',
            timestamp__gte=timezone.now() - timedelta(days=30)
        )

        # Average price premium for this trait
        avg_sale_price = sales_with_trait.aggregate(Avg('price'))['price__avg'] or 0
        collection_avg_price = get_collection_avg_price(nft.collection)
        price_premium = (avg_sale_price / collection_avg_price - 1) * 100

        # Rarity factor (rare traits worth more)
        rarity_multiplier = (100 - trait_obj.rarity_percentage) / 100

        # Trait score = price premium × rarity multiplier
        trait_score = normalize_to_100(price_premium, min=-20, max=80) * rarity_multiplier
        trait_scores.append(trait_score)

    # Average across all traits
    return sum(trait_scores) / len(trait_scores) if trait_scores else 50
```

**Key Insights:**
- **Price premium** - Traits that command higher prices score higher
- **Rarity weighting** - Rare traits weighted more heavily
- **Sales velocity** - Frequently traded traits indicate demand

**Code Reference:** `marketplace/services/vitality_service.py:220-290`

---

### 3. Collection Health (15%)

**What it measures:** Overall collection ecosystem stability

**Data Sources:**
- `analytics.AggregatedCollectionStats`
- `indexer.NFTListing`
- Holder distribution analysis

**Calculation:**

```python
def calculate_collection_health(nft):
    stats = AggregatedCollectionStats.objects.get(collection=nft.collection)

    # 1. Liquidity health (30%)
    listed_ratio = stats.listed_count / nft.collection.nfts.count()
    liquidity_score = normalize_to_100(listed_ratio, min=0.01, max=0.20)  # 1-20% ideal

    # 2. Holder distribution (30%)
    unique_holders = stats.unique_holders
    total_supply = nft.collection.nfts.count()
    holder_ratio = unique_holders / total_supply
    holder_score = normalize_to_100(holder_ratio, min=0.30, max=0.90)  # 30-90% unique holders

    # 3. Volume consistency (20%)
    volume_7d = stats.total_volume_7d
    volume_30d = stats.total_volume_30d
    volume_ratio = (volume_7d / 7) / (volume_30d / 30)  # Daily rate comparison
    consistency_score = 100 - abs(volume_ratio - 1) * 50  # Closer to 1.0 = more consistent

    # 4. Price stability (20%)
    price_volatility = abs(stats.price_change_7d_percent)
    stability_score = max(100 - price_volatility * 2, 0)  # Lower volatility = higher score

    health = (
        liquidity_score * 0.30 +
        holder_score * 0.30 +
        consistency_score * 0.20 +
        stability_score * 0.20
    )
    return health
```

**Key Metrics:**
- **Liquidity** - Healthy listing percentage (not too high, not too low)
- **Holder distribution** - Decentralized ownership is good
- **Volume consistency** - Stable volume indicates sustained interest
- **Price stability** - Less volatility = more mature market

**Code Reference:** `marketplace/services/vitality_service.py:300-370`

---

### 4. Collection Utility (10%)

**What it measures:** Real-world use cases and value beyond speculation

**Data Sources:**
- Collection metadata (social links, website)
- Utility flags in `NFTCollection` model (prepared for future)
- Manual curation by admins

**Calculation:**

```python
def calculate_collection_utility(nft):
    collection = nft.collection
    utility_score = 0

    # Check for documented utilities (manual flags)
    utilities = {
        'has_staking': 20,           # Staking rewards
        'has_token_gating': 15,      # Access to content/communities
        'has_gaming_integration': 15, # Play-to-earn mechanics
        'has_merchandise': 10,        # Physical merchandise
        'has_dao_voting': 15,         # Governance rights
        'has_airdrops': 10,           # Regular airdrops
        'has_events': 10,             # IRL events, meetups
        'has_partnerships': 5,        # Brand partnerships
    }

    # Check which utilities are enabled
    for utility, points in utilities.items():
        if getattr(collection, utility, False):
            utility_score += points

    # Social presence bonus (active community)
    social_links = collection.social_media_links
    if social_links.get('twitter') and social_links.get('discord'):
        utility_score += 10

    # Cap at 100
    return min(utility_score, 100)
```

**Key Factors:**
- **Staking** - Passive income utility
- **Token gating** - Access to exclusive content
- **Gaming** - Play-to-earn integration
- **DAO voting** - Governance participation
- **Community** - Active Discord/Twitter

**Note:** This component is currently the most manually curated. Future versions will use on-chain data to detect utilities automatically.

**Code Reference:** `marketplace/services/vitality_service.py:380-420`

---

### 5. Rarity Score (10%)

**What it measures:** Statistical rarity based on trait combinations

**Data Sources:**
- `nft_data.TraitValue` (rarity percentages)
- Rarity rank from metadata

**Calculation:**

```python
def calculate_rarity_score(nft):
    # Method 1: Statistical rarity (trait rarity product)
    trait_rarities = []
    for trait_type, trait_value in nft.traits.items():
        trait_obj = TraitValue.objects.get(
            trait_type__name=trait_type,
            trait_type__collection=nft.collection,
            value=trait_value
        )
        trait_rarities.append(trait_obj.rarity_percentage)

    # Geometric mean of trait rarities (prevents one common trait from dominating)
    if trait_rarities:
        geometric_mean = (reduce(lambda x, y: x * y, trait_rarities)) ** (1 / len(trait_rarities))
        statistical_rarity = 100 - geometric_mean
    else:
        statistical_rarity = 50

    # Method 2: Rarity rank (if available)
    if nft.rarity_rank:
        total_supply = nft.collection.nfts.count()
        rank_score = ((total_supply - nft.rarity_rank) / total_supply) * 100
    else:
        rank_score = statistical_rarity

    # Weighted average (prefer rank if available)
    rarity_score = rank_score * 0.60 + statistical_rarity * 0.40
    return rarity_score
```

**Key Insights:**
- **Geometric mean** - Prevents common traits from skewing score
- **Rarity rank** - If available, use marketplace rankings (HowRare, MoonRank)
- **Trait combinations** - Rare combination of common traits can be valuable

**Code Reference:** `marketplace/services/vitality_service.py:430-480`

---

### 6. Holder Quality (10%)

**What it measures:** Profile and behavior of current NFT holder

**Data Sources:**
- Wallet transaction history
- Portfolio analysis (other NFTs held)
- Holder tenure (how long they've held)

**Calculation:**

```python
def calculate_holder_quality(nft):
    holder = nft.owner

    # 1. Portfolio value (30%)
    holder_nfts = NFT.objects.filter(owner=holder)
    total_portfolio_value = sum([
        n.listing_price or n.last_sale_price or 0
        for n in holder_nfts
    ])
    portfolio_score = normalize_to_100(total_portfolio_value, min=10, max=1000)  # SOL

    # 2. Holding period (30%)
    last_transfer = NFTEvent.objects.filter(
        nft=nft,
        event_type__in=['SALE', 'TRANSFER']
    ).order_by('-timestamp').first()

    if last_transfer:
        days_held = (timezone.now() - last_transfer.timestamp).days
        holding_score = normalize_to_100(days_held, min=7, max=180)  # 1 week to 6 months
    else:
        holding_score = 50

    # 3. Diamond hands factor (20%)
    # Check if holder has history of long-term holds
    holder_transfers = NFTEvent.objects.filter(
        from_wallet=holder,
        event_type='SALE'
    )
    avg_hold_period = calculate_avg_hold_period(holder)
    diamond_hands_score = normalize_to_100(avg_hold_period, min=30, max=365)

    # 4. Blue chip holdings (20%)
    blue_chip_collections = ['DeGods', 'y00ts', 'Mad Lads', 'Okay Bears']
    blue_chip_count = holder_nfts.filter(
        collection__name__in=blue_chip_collections
    ).count()
    blue_chip_score = min(blue_chip_count * 25, 100)

    holder_quality = (
        portfolio_score * 0.30 +
        holding_score * 0.30 +
        diamond_hands_score * 0.20 +
        blue_chip_score * 0.20
    )
    return holder_quality
```

**Key Factors:**
- **Portfolio value** - Wealthy holders indicate strong hands
- **Holding period** - Longer holds = conviction
- **Diamond hands** - Track record of long-term holding
- **Blue chip holdings** - Sophisticated collectors

**Code Reference:** `marketplace/services/vitality_service.py:490-570`

---

### 7. Sentiment Score (5%)

**What it measures:** Community sentiment and social engagement

**Data Sources:**
- Twitter mentions (prepared, not yet implemented)
- Discord activity (prepared)
- Trading sentiment (buy vs sell ratio)

**Calculation (Current Implementation):**

```python
def calculate_sentiment_score(nft):
    collection = nft.collection

    # 1. Buy vs Sell pressure (60%)
    recent_events = NFTEvent.objects.filter(
        collection=collection,
        timestamp__gte=timezone.now() - timedelta(days=7)
    )

    buys = recent_events.filter(event_type='SALE').count()
    listings = NFTListing.objects.filter(
        nft__collection=collection,
        status='ACTIVE',
        created_at__gte=timezone.now() - timedelta(days=7)
    ).count()

    if listings > 0:
        buy_sell_ratio = buys / listings
        buy_pressure_score = normalize_to_100(buy_sell_ratio, min=0.5, max=2.0)
    else:
        buy_pressure_score = 50

    # 2. Social media presence (40%)
    social_links = collection.social_media_links
    social_score = 0
    if social_links.get('twitter'):
        social_score += 40
    if social_links.get('discord'):
        social_score += 40
    if social_links.get('website'):
        social_score += 20

    sentiment = buy_pressure_score * 0.60 + social_score * 0.40
    return sentiment
```

**Future Enhancements:**
- Twitter sentiment analysis (positive/negative mentions)
- Discord activity metrics (messages per day, active members)
- Reddit/forums sentiment scraping

**Code Reference:** `marketplace/services/vitality_service.py:580-630`

---

### 8. Market Influence (5%)

**What it measures:** Collection's impact on broader NFT market

**Data Sources:**
- Cross-collection transfer patterns
- Holder overlap with other collections
- Market cap relative to sector

**Calculation:**

```python
def calculate_market_influence(nft):
    collection = nft.collection
    stats = AggregatedCollectionStats.objects.get(collection=collection)

    # 1. Market cap percentile (50%)
    all_collections_market_caps = AggregatedCollectionStats.objects.values_list(
        'market_cap_sol', flat=True
    )
    percentile = percentileofscore(all_collections_market_caps, stats.market_cap_sol)
    market_cap_score = percentile  # Already 0-100

    # 2. Holder overlap with top collections (30%)
    top_collections = NFTCollection.objects.filter(priority='VIP')
    holder_overlap_count = 0

    for top_col in top_collections:
        overlap = NFT.objects.filter(
            collection=top_col,
            owner__in=NFT.objects.filter(
                collection=collection
            ).values_list('owner', flat=True)
        ).count()
        holder_overlap_count += overlap

    overlap_score = normalize_to_100(holder_overlap_count, min=10, max=500)

    # 3. Volume rank (20%)
    volume_rank = get_volume_rank(collection)  # 1-1000+
    volume_score = 100 - normalize_to_100(volume_rank, min=1, max=100)

    influence = (
        market_cap_score * 0.50 +
        overlap_score * 0.30 +
        volume_score * 0.20
    )
    return influence
```

**Key Factors:**
- **Market cap** - Larger collections have more influence
- **Holder overlap** - Shared holders with blue chips indicate quality
- **Volume ranking** - High volume collections set trends

**Code Reference:** `marketplace/services/vitality_service.py:640-700`

---

## Calculation Process

### High-Level Flow

```
1. TRIGGER
   ├─ Scheduled task (VIP: 15min, ACTIVE: 1hr, INACTIVE: 4hr)
   └─ Manual refresh request

2. DATA COLLECTION
   ├─ Fetch NFT metadata
   ├─ Query recent events (sales, transfers, listings)
   ├─ Aggregate collection stats
   └─ Load trait rarity data

3. COMPONENT CALCULATION
   ├─ Calculate Market Momentum (async)
   ├─ Calculate Trait Performance (async)
   ├─ Calculate Collection Health (async)
   ├─ Calculate Collection Utility (cached)
   ├─ Calculate Rarity Score (cached)
   ├─ Calculate Holder Quality (async)
   ├─ Calculate Sentiment Score (async)
   └─ Calculate Market Influence (cached)

4. AGGREGATION
   ├─ Weight components
   ├─ Calculate confidence score
   └─ Round to 2 decimal places

5. PERSISTENCE
   ├─ Update NFTVitality record
   ├─ Create NFTVitalityHistory snapshot
   └─ Invalidate cache

6. NOTIFICATION
   ├─ Check for significant changes (>10 points)
   └─ Trigger user notifications if subscribed
```

### Code Entry Point

```python
# marketplace/services/vitality_service.py
class VitalityService:
    @staticmethod
    def calculate_nft_vitality(nft: NFT) -> float:
        """
        Calculate comprehensive vitality score for an NFT.

        Returns:
            float: Vitality score (0-100)
        """
        # Parallel calculation of components
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                'momentum': executor.submit(calculate_market_momentum, nft),
                'trait': executor.submit(calculate_trait_performance, nft),
                'health': executor.submit(calculate_collection_health, nft),
                'utility': executor.submit(calculate_collection_utility, nft),
                'rarity': executor.submit(calculate_rarity_score, nft),
                'holder': executor.submit(calculate_holder_quality, nft),
                'sentiment': executor.submit(calculate_sentiment_score, nft),
                'influence': executor.submit(calculate_market_influence, nft),
            }

            # Wait for all components
            components = {key: future.result() for key, future in futures.items()}

        # Weighted sum
        vitality_score = (
            components['momentum'] * 0.25 +
            components['trait'] * 0.20 +
            components['health'] * 0.15 +
            components['utility'] * 0.10 +
            components['rarity'] * 0.10 +
            components['holder'] * 0.10 +
            components['sentiment'] * 0.05 +
            components['influence'] * 0.05
        )

        # Calculate confidence
        confidence = calculate_confidence(components)

        # Save to database
        vitality, created = NFTVitality.objects.update_or_create(
            nft=nft,
            defaults={
                'vitality_score': round(vitality_score, 2),
                'market_momentum': components['momentum'],
                'trait_performance': components['trait'],
                'collection_health': components['health'],
                'collection_utility': components['utility'],
                'rarity_score': components['rarity'],
                'holder_quality': components['holder'],
                'sentiment_score': components['sentiment'],
                'market_influence': components['influence'],
                'confidence_score': confidence,
            }
        )

        # Create historical snapshot
        NFTVitalityHistory.objects.create(
            nft_vitality=vitality,
            vitality_score=vitality_score,
            market_momentum=components['momentum'],
            trait_performance=components['trait'],
        )

        return vitality_score
```

**Code Reference:** `marketplace/services/vitality_service.py:50-150`

---

## Update Scheduling

### Priority-Based Scheduling

TraitKeeper uses a **3-tier priority system** to balance freshness and resource usage:

| Priority Tier | Update Frequency | Use Case | Example Collections |
|---------------|------------------|----------|---------------------|
| **VIP** | Every 15 minutes | High-volume, high-value collections | Mad Lads, Tensorians, Famous Fox Federation |
| **ACTIVE** | Every 1 hour | Moderate activity collections | Most established projects |
| **INACTIVE** | Every 4 hours | Low activity or new collections | Smaller projects, test collections |

### Scheduler Implementation

```python
# core/task_manager.py
class VitalityTaskManager:
    def __init__(self):
        self.scheduler = BackgroundScheduler()

    def start(self):
        # VIP collections - every 15 minutes
        self.scheduler.add_job(
            func=self.update_vip_collections,
            trigger='interval',
            minutes=15,
            id='vip_vitality_updates'
        )

        # ACTIVE collections - every 1 hour
        self.scheduler.add_job(
            func=self.update_active_collections,
            trigger='interval',
            hours=1,
            id='active_vitality_updates'
        )

        # INACTIVE collections - every 4 hours
        self.scheduler.add_job(
            func=self.update_inactive_collections,
            trigger='interval',
            hours=4,
            id='inactive_vitality_updates'
        )

        self.scheduler.start()

    def update_vip_collections(self):
        collections = NFTCollection.objects.filter(
            priority='VIP',
            is_active=True
        )

        for collection in collections:
            nfts = NFT.objects.filter(collection=collection)
            for nft in nfts:
                # Submit to task queue
                task_manager.submit(
                    VitalityService.calculate_nft_vitality,
                    args=(nft,),
                    priority='HIGH'
                )
```

**Code Reference:** `core/task_manager.py:150-250`

---

## Historical Tracking

### Purpose

Historical vitality tracking enables:
- **Trend analysis** - Identify improving/declining NFTs
- **Pattern recognition** - Detect seasonal trends
- **Predictive analytics** - ML models for future vitality
- **User insights** - "This NFT's vitality increased 15 points this week"

### Storage

**Model:** `NFTVitalityHistory`

```python
class NFTVitalityHistory(models.Model):
    nft_vitality = models.ForeignKey(NFTVitality, on_delete=models.CASCADE)
    vitality_score = models.DecimalField(max_digits=5, decimal_places=2)
    market_momentum = models.DecimalField(max_digits=5, decimal_places=2)
    trait_performance = models.DecimalField(max_digits=5, decimal_places=2)
    # ... other components
    recorded_at = models.DateTimeField(auto_now_add=True)
```

### Retention Policy

- **VIP collections:** Keep 90 days of history
- **ACTIVE collections:** Keep 60 days of history
- **INACTIVE collections:** Keep 30 days of history

Older data is aggregated to daily averages and stored in `VitalityDailyAggregate` table.

**Code Reference:** `marketplace/models/vitality_models.py:100-125`

---

## Confidence Scoring

### Purpose

Not all vitality scores are equally reliable. **Confidence scoring** (0-100) indicates data quality and completeness.

### Factors

```python
def calculate_confidence(components):
    confidence = 100.0

    # 1. Data availability penalty
    if not nft.listing_price and not nft.last_sale_price:
        confidence -= 10  # No price data

    if not nft.traits or len(nft.traits) < 3:
        confidence -= 5  # Incomplete trait data

    # 2. Data freshness penalty
    if nft.updated_at < timezone.now() - timedelta(days=7):
        confidence -= 15  # Stale data

    # 3. Collection maturity bonus
    collection_age_days = (timezone.now() - nft.collection.created_at).days
    if collection_age_days < 7:
        confidence -= 20  # Too new, not enough data
    elif collection_age_days > 90:
        confidence += 5  # Mature collection

    # 4. Transaction volume factor
    recent_sales = NFTEvent.objects.filter(
        collection=nft.collection,
        event_type='SALE',
        timestamp__gte=timezone.now() - timedelta(days=30)
    ).count()

    if recent_sales < 10:
        confidence -= 10  # Low activity
    elif recent_sales > 100:
        confidence += 5  # High activity

    return max(0, min(100, confidence))
```

**Usage:**
- Scores with confidence < 50 shown with warning icon
- Low confidence scores excluded from leaderboards
- ML models trained only on high-confidence data (>70)

**Code Reference:** `marketplace/services/vitality_service.py:720-770`

---

## Implementation Details

### Technology Stack

- **Language:** Python 3.11
- **Framework:** Django 5.0.7
- **Database:** PostgreSQL 15 (vitality scores + history)
- **Cache:** Redis 7 (score caching, 15-30 min TTL)
- **Task Queue:** Custom ThreadPoolExecutor (max 4 workers)
- **Async:** asyncio for blockchain data fetching

### Performance Benchmarks

| Operation | Target | Actual | Notes |
|-----------|--------|--------|-------|
| Single NFT calculation | <5s | 3.2s | Parallel component calculation |
| Collection (10k NFTs) | <10min | 8.5min | Batch processing, 4 workers |
| Database write | <100ms | 45ms | Indexed queries |
| Cache retrieval | <10ms | 5ms | Redis local instance |

### Error Handling

```python
def calculate_nft_vitality_safe(nft):
    try:
        return calculate_nft_vitality(nft)
    except NFTDataIncomplete as e:
        logger.warning(f"Incomplete data for {nft.mint_address}: {e}")
        return None  # Skip this NFT
    except ProviderAPIError as e:
        logger.error(f"API error for {nft.mint_address}: {e}")
        # Return cached score if available
        cached = cache.get(f"vitality:{nft.mint_address}")
        return cached if cached else 50.0  # Default score
    except Exception as e:
        logger.exception(f"Unexpected error for {nft.mint_address}")
        return 50.0  # Safe default
```

**Code Reference:** `marketplace/services/vitality_service.py:780-820`

---

## Performance Optimization

### 1. Parallel Component Calculation

Each of the 8 components is calculated in parallel using `ThreadPoolExecutor`:

```python
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = {
        'momentum': executor.submit(calculate_market_momentum, nft),
        'trait': executor.submit(calculate_trait_performance, nft),
        # ... 6 more components
    }
    components = {key: future.result() for key, future in futures.items()}
```

**Speedup:** 4-5x faster than sequential calculation

---

### 2. Caching Strategy

**Multi-tier caching:**

```python
# L1: In-memory cache (lru_cache)
@lru_cache(maxsize=1000)
def get_collection_stats(collection_address):
    return AggregatedCollectionStats.objects.get(collection__address=collection_address)

# L2: Redis cache (15-30 min TTL)
vitality_score = cache.get_or_set(
    f"vitality:{nft.mint_address}",
    lambda: calculate_nft_vitality(nft),
    timeout=900  # 15 minutes for VIP
)
```

**Cache Hit Rate:** ~85% during normal operation

---

### 3. Database Query Optimization

**Strategic indexing:**
```python
class NFTVitality(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=['-vitality_score']),  # Leaderboards
            models.Index(fields=['nft__collection', '-vitality_score']),  # Collection rankings
            models.Index(fields=['last_calculated']),  # Stale data cleanup
        ]
```

**Query optimization:**
```python
# Bad: N+1 queries
for nft in NFT.objects.filter(collection=collection):
    vitality = nft.nftvitality.vitality_score  # Extra query per NFT

# Good: Single query with select_related
nfts = NFT.objects.filter(collection=collection).select_related('nftvitality')
for nft in nfts:
    vitality = nft.nftvitality.vitality_score  # No extra query
```

---

### 4. Batch Processing

For large collections (10k+ NFTs), use batch processing:

```python
def update_collection_vitality_batch(collection, batch_size=100):
    nfts = NFT.objects.filter(collection=collection)
    total = nfts.count()

    for i in range(0, total, batch_size):
        batch = nfts[i:i+batch_size]

        # Parallel calculation within batch
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(calculate_nft_vitality, nft) for nft in batch]
            results = [f.result() for f in futures]

        # Progress tracking
        logger.info(f"Processed {i+len(batch)}/{total} NFTs")
```

**Code Reference:** `marketplace/services/vitality_service.py:850-900`

---

## Use Cases

### 1. Investment Decision Support

**Scenario:** Trader wants to find undervalued NFTs

**Process:**
1. Sort by vitality score (ascending)
2. Filter for vitality 50-70 (moderate health)
3. Cross-reference with low floor price
4. Look for increasing vitality trend (last 7 days)

**Query:**
```python
undervalued_nfts = NFT.objects.filter(
    nftvitality__vitality_score__gte=50,
    nftvitality__vitality_score__lte=70,
    listing_price__lt=F('collection__aggregatedcollectionstats__floor_price_sol') * 1.2
).annotate(
    vitality_change_7d=F('nftvitality__vitality_score') -
                      Subquery(
                          NFTVitalityHistory.objects.filter(
                              nft_vitality=OuterRef('nftvitality'),
                              recorded_at__gte=timezone.now() - timedelta(days=7)
                          ).order_by('recorded_at').values('vitality_score')[:1]
                      )
).filter(vitality_change_7d__gt=5)
```

---

### 2. Portfolio Health Monitoring

**Scenario:** Collector wants to monitor their NFT portfolio

**Dashboard Metrics:**
- Average vitality across portfolio
- NFTs with declining vitality (alert)
- Portfolio vitality trend (7d, 30d)

**Query:**
```python
portfolio = NFT.objects.filter(owner=user_wallet)
avg_vitality = portfolio.aggregate(
    Avg('nftvitality__vitality_score')
)['nftvitality__vitality_score__avg']

declining_nfts = portfolio.filter(
    nftvitality__vitality_score__lt=50
).select_related('nftvitality', 'collection')
```

---

### 3. Collection Comparison

**Scenario:** User comparing two collections before purchase

**Metrics:**
- Average vitality difference
- Component breakdown comparison
- Trend comparison (30-day)

**API Endpoint:** `GET /api/compare-collections/?col1=<address1>&col2=<address2>`

---

## Related Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture overview
- [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) - Database schema details
- [CACHING_STRATEGY.md](./CACHING_STRATEGY.md) - Caching implementation
- [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) - API endpoints for vitality data

---

**Last Updated:** January 2025
**Version:** 1.0.0
**Algorithm Version:** v2.1 (December 2024)
**Author:** TraitKeeper Analytics Team
