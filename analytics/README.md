# Analytics App

## Overview

The analytics app is the **intelligence layer** of TraitKeeper, transforming raw blockchain data into actionable insights. It calculates trait performance, collection health metrics, wallet behavior patterns, and provides the data foundation for the NFT Vitality system.

## Purpose

- **Aggregate multi-source data** from indexer into unified statistics
- **Calculate trait performance scores** for individual traits
- **Analyze wallet behavior** and prominence
- **Detect market events** like sweeps and high-profile transfers
- **Provide data for Vitality calculations** in marketplace app

## Key Components

### 1. Collection-Level Analytics

**Unified view of collection health** combining all data sources.

**Models:**

- `AggregatedCollectionStats` - Single source of truth for collection metrics
- `CollectionSweepEvent` - Rapid buy events (whale activity)
- `HighProfileTransfer` - Significant sales/transfers

### 2. Trait-Level Analytics

**Performance scoring for individual traits**.

**Models:**

- `TraitPerformanceScore` - How well each trait performs in sales
- `TrendingTrait` - Traits with recent momentum
- `TopTrait` - Highest overall performance

### 3. Wallet Analytics

**Behavioral analysis of market participants**.

**Models:**

- `WalletProminence` - Overall market influence score
- `WalletBehaviorProfile` - Advanced classification (whale, scalper, holder, etc.)

## Models

### AggregatedCollectionStats

**The main analytics output model**.

**Purpose:** Combines data from blockchain, Magic Eden, Tensor into one unified record per collection.

**Key Fields:**

**Base Metrics (Aggregated):**

- `floor_price` - Intelligently aggregated from multiple sources
- `volume_24h` - 24-hour trading volume
- `listed_count` - Active listings across marketplaces
- `total_supply` - Total NFTs in collection
- `number_of_holders` - Unique wallet count

**Calculated Analytics:**

- `vitality_score` - Collection health score (0-100)
- `holder_quality_score` - Average holder influence
- `sentiment_score` - Legacy field (deprecated - see perception_index in marketplace)
- `market_influence_score` - Broader market impact
- `performance_score` - Overall performance metric
- `market_cap` - floor_price × total_supply
- `price_change_24h` - 24-hour price change %
- `price_change_7d` - 7-day price change %
- `percent_listed` - % of supply currently listed
- `velocity_24h` - Sales per hour
- `market_efficiency_score` - Price stability metric
- `holder_confidence_index` - Holder behavior indicator
- `liquidity_health_score` - How liquid the market is

**Source Attribution:**

- `source_attribution` - JSON tracking which source provided each metric

  ```json
  {
    "floor_price": "tensor",
    "volume_24h": "magic_eden",
    "total_supply": "blockchain"
  }
  ```

**Relationship:**

- One-to-one with `NFTCollection`

**Used by:**

- Marketplace app for vitality calculation (collection_health component)
- Admin panel for collection overview
- Public API for collection pages

### TraitPerformanceScore

**Individual trait value performance**.

**Purpose:** Tracks how well NFTs with specific traits perform in the market.

**Key Fields:**

- `trait_type` - FK to TraitType (e.g., "Hat")
- `trait_value` - FK to TraitValue (e.g., "Crown")
- `collection` - FK to NFTCollection
- `rarity_score` - Rarity percentage (0-100)
- `avg_sale_price` - Average price for NFTs with this trait
- `premium_score` - Price premium over floor
- `velocity_score` - How quickly these sell
- `momentum_score` - Recent price trend
- `performance_score` - **Final combined score (0-100)**

**Calculation:**

```python
performance_score = (
    premium_score * 0.4 +
    velocity_score * 0.3 +
    momentum_score * 0.2 +
    (1 - rarity_score) * 0.1  # Rarer = small bonus
)
```

**Used by:**

- Marketplace app for vitality calculation (trait_performance component - 20% weight)
- Trait search/filtering
- Collection analytics pages

**Indexes:**

- `(collection, -performance_score)` - Fast sorted queries
- `(trait_value, -performance_score)` - Cross-collection trait comparison

### WalletProminence

**Overall wallet market influence**.

**Key Fields:**

- `address` - Wallet address (unique)
- `transaction_count` - Total transactions
- `transaction_volume` - Total SOL volume
- `collections_count` - Number of collections traded
- `prominence_score` - **Overall influence (0-100)**
- `last_updated` - When last calculated

**Calculation:**

```python
prominence_score = (
    log(transaction_volume) * 0.5 +
    log(transaction_count) * 0.3 +
    collections_count / 100 * 0.2
) * 10  # Scaled to 0-100
```

**Used by:**

- Marketplace app for vitality calculation (holder_quality component - 10% weight)
- Wallet leaderboards
- High-profile transfer detection

### WalletBehaviorProfile

**Advanced wallet classification and behavioral analysis**.

**Purpose:** Deep dive into trading patterns, risk tolerance, and market influence.

**Behavior Types:**

- `whale` - Large volume traders
- `scalper` - Quick flips for small profits
- `holder` - Long-term holders
- `flipper` - Medium-term flips
- `collector` - Diversified portfolio builders
- `arbitrageur` - Cross-marketplace traders
- `market_maker` - Provides liquidity
- `institutional` - Large organized entities
- `bot` - Automated trading
- `casual` - Infrequent traders

**Key Fields:**

**Trading Behavior:**

- `avg_hold_time_hours` - Average NFT holding period
- `trade_frequency_per_day` - Trades per day
- `avg_profit_margin` - % profit per flip
- `success_rate` - % profitable trades

**Risk Profile:**

- `risk_tolerance` - very_low, low, medium, high, very_high
- `max_single_purchase` - Largest single buy
- `diversification_score` - Portfolio diversity (0-1)

**Influence Metrics:**

- `influence_score` - Market movement impact (0-1)
- `trendsetting_ability` - How often actions predict trends (0-1)
- `copy_trader_count` - Estimated followers
- `network_centrality` - Position in trading network (0-1)

**Activity Patterns:**

- `most_active_hours` - JSON array of hours (0-23)
- `seasonal_patterns` - JSON of seasonal preferences
- `preferred_collections` - M2M relationship
- `collection_loyalty_score` - How loyal to specific collections (0-1)

**Advanced Analytics:**

- `fomo_susceptibility` - FOMO buying tendency (0-1)
- `contrarian_indicator` - Trades against trend (0-1)
- `market_timing_ability` - Entry/exit timing skill (0-1)

**ML Preparation:**

- `behavior_features` - JSON feature vector for ML
- `clustering_assignment` - Cluster ID from unsupervised learning

**Used by:**

- Marketplace app for vitality (holder_quality component)
- Advanced analytics dashboards
- ML model training (future)

### CollectionSweepEvent

**Rapid bulk purchase detection**.

**Purpose:** Detect when wallets buy multiple NFTs quickly (whale activity indicator).

**Key Fields:**

- `collection` - Collection being swept
- `buyer_address` - Wallet doing the sweep
- `start_time` / `end_time` - Sweep duration
- `duration_minutes` - How long the sweep lasted
- `num_items` - NFTs purchased
- `total_volume` - SOL spent
- `significance_score` - Impact score (0-100)
- `nft_mints` - JSON array of purchased NFT addresses

**Detection Criteria:**

- 3+ NFTs purchased within 30 minutes
- By same wallet
- From same collection

**Used by:**

- High-profile event notifications
- Market momentum indicators
- Analytics dashboards

### HighProfileTransfer

**Significant sale/transfer tracking**.

**Purpose:** Track unusually important transactions.

**Key Fields:**

- `event` - FK to indexer.NFTEvent
- `collection` / `nft` - Involved assets
- `high_profile_score` - Significance (0-100)
- `value_factor` - Price significance
- `wallet_factor` - Wallet prominence significance
- `timing_factor` - Market timing significance
- `rank` - Ranking among recent transfers

**Scoring:**

```python
high_profile_score = (
    value_factor * 0.5 +        # High price
    wallet_factor * 0.3 +        # Known wallet
    timing_factor * 0.2          # Strategic timing
)
```

**Used by:**

- Featured transactions on homepage
- Notifications to users
- Market trend analysis

### TrendingTrait & TopTrait

**Trait leaderboards**.

**TrendingTrait:**

- Short-term momentum
- Recent velocity + price increases
- Updated frequently

**TopTrait:**

- All-time best performers
- Overall premium + volume + rarity
- More stable rankings

## Services

### MetricsCalculationService

**Main analytics calculation service** (location: `services.py`).

**Key Methods:**

#### `calculate_aggregated_stats(collection)`

Aggregates multi-source data into `AggregatedCollectionStats`.

**Process:**

1. Fetch latest data from all sources (blockchain, Magic Eden, Tensor)
2. Apply intelligent aggregation rules
3. Calculate derived metrics
4. Store in Aggregated CollectionStats
5. Track source attribution

#### `calculate_trait_performance_scores(collection)`

Analyzes trait performance for all traits in collection.

**Process:**

1. For each trait value:
   - Get all NFTs with this trait
   - Calculate average sale price
   - Compare to floor (premium)
   - Measure sale velocity
   - Detect price momentum
2. Combine into final performance score
3. Store in TraitPerformanceScore

#### `detect_collection_sweeps(collection, time_window)`

Detects rapid bulk purchases.

**Process:**

1. Get recent sales (last time_window)
2. Group by buyer
3. Find buyers with 3+ purchases within 30 min
4. Calculate significance score
5. Create CollectionSweepEvent

#### `calculate_wallet_prominence(wallet_address)`

Calculates overall wallet influence.

**Process:**

1. Count total transactions
2. Sum total volume
3. Count unique collections
4. Apply logarithmic scaling
5. Store in WalletProminence

## Data Flow

```
Indexer App
    ↓
(NFTEvent, NFTListing, CollectionMarketStats)
    ↓
MetricsCalculationService
    ↓
┌─────────────────────────────────┐
│  AggregatedCollectionStats      │ → Marketplace (Vitality)
│  TraitPerformanceScore          │ → Marketplace (Vitality)
│  WalletProminence               │ → Marketplace (Vitality)
│  CollectionSweepEvent           │ → Notifications
│  HighProfileTransfer            │ → Featured Content
└─────────────────────────────────┘
```

## Background Tasks

### Periodic Calculations

**Scheduled via Celery Beat:**

**Every 15 minutes (VIP collections):**

- Update AggregatedCollectionStats
- Recalculate trait performance
- Detect new sweeps

**Every hour (ACTIVE collections):**

- Same as above but for active collections

**Every 4 hours (INACTIVE collections):**

- Minimal updates for low-activity collections

**Daily:**

- Recalculate all WalletProminence scores
- Update WalletBehaviorProfile classifications
- Generate trending/top trait rankings

## Integration with Other Apps

### → Marketplace App

**Primary consumer of analytics data**.

**Provides for Vitality (Anti-Gaming Architecture v3.0):**

- TraitPerformanceScore → trait_performance component (20%)
- AggregatedCollectionStats → collection_health component (15%)
- WalletProminence → holder_quality component (10%)
- AggregatedCollectionStats → market_influence component (5%)
- **TODO**: Social/community data → perception_index component (20% - not yet implemented)

### ← Indexer App

**Primary data source**.

**Receives:**

- NFTEvent - All sales, listings, transfers
- CollectionMarketStats - Multi-source collection data
- NFTListing - Active marketplace listings

### → Admin Panel

**Monitoring and insights**.

**Provides:**

- Collection performance dashboards
- Trait analytics
- Wallet leaderboards
- Sweep/high-profile event feeds

## Configuration

### Calculation Thresholds

```python
# In services.py or config
SWEEP_DETECTION = {
    'MIN_ITEMS': 3,
    'TIME_WINDOW_MINUTES': 30,
    'MIN_SIGNIFICANCE': 50  # 0-100
}

HIGH_PROFILE_THRESHOLDS = {
    'MIN_VALUE_SOL': 10,
    'MIN_WALLET_PROMINENCE': 50,
    'TOP_N_RANKINGS': 100
}
```

### Update Frequencies

Tied to collection priority (from `core.cache_manager`):

- VIP: Every 15 minutes
- ACTIVE: Every hour
- INACTIVE: Every 4 hours

## TODO List

### High Priority

- [ ] Implement WalletBehaviorProfile calculation service
- [ ] Implement perception index calculation (Twitter, Discord, anti-gaming heuristics)
- [ ] Optimize trait performance calculations for large collections
- [ ] Add collection utility detection/scoring

### Medium Priority

- [ ] ML model for wallet behavior classification
- [ ] Cross-collection trait performance comparison
- [ ] Advanced sweep detection (coordinated multi-wallet)
- [ ] Social network analysis for wallet influence

### Low Priority

- [ ] Historical trend analysis
- [ ] Predictive analytics (price forecasting)
- [ ] Anomaly detection for unusual market behavior

## Common Operations

### Calculate Collection Analytics

```python
from analytics.services import MetricsCalculationService
from nft_data.models import NFTCollection

service = MetricsCalculationService()
collection = NFTCollection.objects.get(address="...")

# Full analytics update
stats = service.calculate_aggregated_stats(collection)
traits = service.calculate_trait_performance_scores(collection)
sweeps = service.detect_collection_sweeps(collection)
```

### Query Top Performing Traits

```python
from analytics.models import TraitPerformanceScore

# Top 10 traits in a collection
top_traits = TraitPerformanceScore.objects.filter(
    collection=collection
).order_by('-performance_score')[:10]

for trait in top_traits:
    print(f"{trait.trait_value.value}: {trait.performance_score}/100")
```

### Find Wallet Information

```python
from analytics.models import WalletProminence

prominence = WalletProminence.objects.get(address="wallet_address")
print(f"Prominence: {prominence.prominence_score}/100")
print(f"Volume: {prominence.transaction_volume} SOL")
```

## Related Documentation

- [../marketplace/README.md](../marketplace/README.md) - How vitality uses analytics data
- [../indexer/README.md](../indexer/README.md) - Data source for analytics
- [services.py](./services.py) - Analytics calculation implementation
