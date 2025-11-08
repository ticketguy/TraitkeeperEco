# TraitKeeper Database Schema Documentation

## Table of Contents

1. [Overview](#overview)
2. [Schema Diagram](#schema-diagram)
3. [Core Data Models](#core-data-models)
4. [Analytics Models](#analytics-models)
5. [Marketplace Models](#marketplace-models)
6. [Advanced Analytics Models](#advanced-analytics-models)
7. [User & Authentication Models](#user--authentication-models)
8. [Administrative Models](#administrative-models)
9. [Support Models](#support-models)
10. [Indexes & Performance](#indexes--performance)
11. [Data Integrity](#data-integrity)

---

## Overview

TraitKeeper's database schema consists of **80+ models** across 13 Django apps, designed using PostgreSQL 15. The schema follows these principles:

- **Domain-Driven Design** - Models grouped by business domain
- **Normalization with Denormalization** - Balance between data integrity and query performance
- **Strategic Indexing** - Multi-column indexes for common query patterns
- **JSON Flexibility** - JSON fields for semi-structured data (traits, metadata)
- **Soft Deletes** - Preserve historical data with `is_active` flags
- **Audit Trails** - Timestamps and user tracking for critical operations

**Database:** PostgreSQL 15
**ORM:** Django 5.0.7
**Total Models:** 80+
**Total Tables:** ~85 (including many-to-many)

---

## Schema Diagram

### High-Level Entity Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                        Core Data Layer                       │
└─────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
            ▼                 ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │NFTCollection │  │    Creator   │  │ CustomUser   │
    └──────┬───────┘  └──────────────┘  └──────┬───────┘
           │                                    │
           ├────────────┐                       │
           │            │                       │
           ▼            ▼                       ▼
    ┌──────────┐ ┌──────────┐         ┌──────────────┐
    │   NFT    │ │TraitType │         │WalletProfile │
    └────┬─────┘ └────┬─────┘         └──────────────┘
         │            │
         │            ▼
         │      ┌──────────┐
         │      │TraitValue│
         │      └──────────┘
         │
         ├────────────┬─────────────┬─────────────┐
         │            │             │             │
         ▼            ▼             ▼             ▼
  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
  │NFTVitality│ │NFTEvent  │ │NFTListing│ │AuctionEvent│
  └──────────┘ └──────────┘ └──────────┘ └──────────┘

┌─────────────────────────────────────────────────────────────┐
│                     Analytics Layer                          │
└─────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
            ▼                 ▼                 ▼
 ┌──────────────────┐  ┌──────────────┐  ┌──────────────┐
 │Aggregated        │  │Collection    │  │HighProfile   │
 │CollectionStats   │  │SweepEvent    │  │Transfer      │
 └──────────────────┘  └──────────────┘  └──────────────┘
```

---

## Core Data Models

### 1. NFTCollection (`nft_data.models`)

**Purpose:** Represents a Solana NFT collection

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `address` | CharField(255) | PRIMARY KEY | Collection mint address (Solana) |
| `name` | CharField(255) | | Raw collection name from blockchain |
| `display_name` | CharField(255) | | Cleaned, user-friendly name |
| `slug` | SlugField(255) | UNIQUE | URL-friendly identifier (auto-generated) |
| `image` | URLField | Nullable | Collection thumbnail |
| `description` | TextField | | Collection description |
| `creator_address` | CharField(255) | FK to Creator | Creator wallet |
| `social_media_links` | JSONField | Default: {} | Social links (Twitter, Discord, etc.) |
| `is_featured` | BooleanField | Default: False | Homepage featured flag |
| `is_active` | BooleanField | Default: True | Soft delete flag |
| `priority` | CharField(20) | Choices: VIP/ACTIVE/INACTIVE | Update frequency tier |
| `update_frequency_minutes` | IntegerField | Default: 60 | How often to refresh data |
| `last_fetched` | DateTimeField | Nullable | Last successful data fetch |
| `created_at` | DateTimeField | Auto-now-add | Creation timestamp |
| `updated_at` | DateTimeField | Auto-now | Last update timestamp |

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['priority', 'is_active']),
        models.Index(fields=['slug']),
        models.Index(fields=['-created_at']),
    ]
```

**Relationships:**
- **Has Many:** NFT (1:N)
- **Has Many:** TraitType (1:N)
- **Has One:** CollectionVitality (1:1)
- **Has One:** AggregatedCollectionStats (1:1)

**Code Reference:** `nft_data/models.py:15-70`

---

### 2. NFT (`nft_data.models`)

**Purpose:** Represents an individual NFT

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `mint_address` | CharField(255) | PRIMARY KEY | NFT mint address (Solana) |
| `collection` | ForeignKey | CASCADE, indexed | Parent collection |
| `name` | CharField(255) | | NFT name |
| `image` | URLField | Nullable | NFT image URL |
| `owner` | CharField(255) | Indexed | Current owner wallet |
| `traits` | JSONField | Default: {} | Trait attributes as JSON |
| `metadata_uri` | URLField | Nullable | Arweave/IPFS metadata URI |
| `listing_price` | DecimalField(20,9) | Nullable | Current listing price (SOL) |
| `last_sale_price` | DecimalField(20,9) | Nullable | Most recent sale price |
| `price_magic_eden` | DecimalField(20,9) | Nullable | Magic Eden listing price |
| `price_tensor` | DecimalField(20,9) | Nullable | Tensor listing price |
| `rarity_rank` | IntegerField | Nullable, indexed | Rarity ranking within collection |
| `is_listed` | BooleanField | Default: False | Currently listed for sale |
| `is_burned` | BooleanField | Default: False | NFT has been burned |
| `created_at` | DateTimeField | Auto-now-add | Creation timestamp |
| `updated_at` | DateTimeField | Auto-now | Last update timestamp |

**Traits JSON Example:**
```json
{
  "Background": "Blue",
  "Hat": "Crown",
  "Eyes": "Laser",
  "Outfit": "Suit",
  "Accessory": "Gold Chain"
}
```

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['collection', 'rarity_rank']),
        models.Index(fields=['collection', 'is_listed']),
        models.Index(fields=['owner']),
        models.Index(fields=['-last_sale_price']),
    ]
```

**Relationships:**
- **Belongs To:** NFTCollection (N:1)
- **Has Many:** TraitValue (M:N through trait_values)
- **Has One:** NFTVitality (1:1)
- **Has Many:** NFTEvent (1:N)
- **Has Many:** NFTListing (1:N)

**Code Reference:** `nft_data/models.py:80-150`

---

### 3. TraitType (`nft_data.models`)

**Purpose:** Defines trait categories for a collection (e.g., "Hat", "Background")

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `collection` | ForeignKey | CASCADE, indexed | Parent collection |
| `trait_name` | CharField(255) | | Trait category name |
| `trait_count` | IntegerField | Default: 0 | Number of unique values |

**Unique Constraint:** `(collection, trait_name)` - Each collection has unique trait types

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['collection', 'trait_name']),
    ]
    unique_together = [['collection', 'trait_name']]
```

**Relationships:**
- **Belongs To:** NFTCollection (N:1)
- **Has Many:** TraitValue (1:N)

**Code Reference:** `nft_data/models.py:165-185`

---

### 4. TraitValue (`nft_data.models`)

**Purpose:** Stores specific trait values with rarity calculations

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `trait_type` | ForeignKey | CASCADE, indexed | Parent trait type |
| `value` | CharField(255) | | Specific trait value (e.g., "Crown") |
| `rarity_percentage` | DecimalField(5,2) | | Rarity (0-100%) |
| `nft_count` | IntegerField | Default: 0 | Number of NFTs with this trait |

**Rarity Calculation:**
```python
rarity_percentage = (nft_count / total_collection_supply) * 100
```

**Unique Constraint:** `(trait_type, value)` - Each value is unique per trait type

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['trait_type', 'rarity_percentage']),
        models.Index(fields=['trait_type', '-nft_count']),
    ]
    unique_together = [['trait_type', 'value']]
```

**Relationships:**
- **Belongs To:** TraitType (N:1)
- **Has Many:** NFT (M:N through NFT.trait_values)

**Code Reference:** `nft_data/models.py:200-230`

---

### 5. Creator (`nft_data.models`)

**Purpose:** Tracks NFT creator wallet information

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `address` | CharField(255) | PRIMARY KEY | Creator's Solana wallet address |
| `name` | CharField(255) | Nullable | Creator name (optional) |
| `verified` | BooleanField | Default: False | Verified on marketplaces |
| `share` | DecimalField(5,2) | Default: 0.00 | Royalty share percentage |

**Code Reference:** `nft_data/models.py:245-260`

---

### 6. PendingCollection (`nft_data.models`)

**Purpose:** User-submitted collections awaiting admin approval

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `submitted_by` | ForeignKey | CASCADE | User who submitted (CustomUser) |
| `collection_address` | CharField(255) | UNIQUE | Proposed collection address |
| `collection_name` | CharField(255) | | Proposed name |
| `description` | TextField | | Collection description |
| `image_url` | URLField | Nullable | Collection image |
| `social_media_links` | JSONField | Default: {} | Social links |
| `reason` | TextField | | Why user wants this collection |
| `status` | CharField(20) | Choices: PENDING/APPROVED/REJECTED | Review status |
| `validation_error` | TextField | Nullable | Error message if validation failed |
| `submitted_at` | DateTimeField | Auto-now-add | Submission timestamp |
| `reviewed_by` | ForeignKey | Nullable, SET_NULL | Admin who reviewed (AdminUser) |
| `reviewed_at` | DateTimeField | Nullable | Review timestamp |

**Workflow:**
1. User submits → `status='PENDING'`
2. Admin reviews → `status='APPROVED'` or `'REJECTED'`
3. If approved → Admin creates NFTCollection

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['status', '-submitted_at']),
    ]
```

**Code Reference:** `nft_data/models.py:275-320`

---

## Analytics Models

### 7. AggregatedCollectionStats (`analytics.models`)

**Purpose:** Pre-computed analytics metrics for collections

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `collection` | OneToOneField | CASCADE, PRIMARY KEY | Parent collection |
| `vitality_score` | DecimalField(5,2) | Default: 0.00 | Overall vitality (0-100) |
| `holder_quality_score` | DecimalField(5,2) | Default: 0.00 | Holder profile quality |
| `sentiment_score` | DecimalField(5,2) | Default: 0.00 | Community sentiment |
| `market_influence_score` | DecimalField(5,2) | Default: 0.00 | Market impact |
| `liquidity_health_score` | DecimalField(5,2) | Default: 0.00 | Market liquidity |
| `liquidity_efficiency_score` | DecimalField(5,2) | Default: 0.00 | Liquidity vs volume |
| `market_cap_sol` | DecimalField(20,9) | Default: 0.00 | Market cap in SOL |
| `market_cap_usd` | DecimalField(20,2) | Default: 0.00 | Market cap in USD |
| `floor_price_sol` | DecimalField(20,9) | Nullable | Floor price |
| `average_price_sol` | DecimalField(20,9) | Nullable | Average sale price |
| `total_volume_24h` | DecimalField(20,9) | Default: 0.00 | 24h trading volume |
| `total_volume_7d` | DecimalField(20,9) | Default: 0.00 | 7d trading volume |
| `price_change_24h_percent` | DecimalField(6,2) | Default: 0.00 | 24h price change |
| `price_change_7d_percent` | DecimalField(6,2) | Default: 0.00 | 7d price change |
| `listed_count` | IntegerField | Default: 0 | Number of listed NFTs |
| `unique_holders` | IntegerField | Default: 0 | Unique wallet count |
| `last_calculated` | DateTimeField | Auto-now | Last calculation timestamp |

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['-vitality_score']),
        models.Index(fields=['-market_cap_sol']),
        models.Index(fields=['-total_volume_24h']),
    ]
```

**Relationships:**
- **Belongs To:** NFTCollection (1:1)

**Code Reference:** `analytics/models.py:20-85`

---

### 8. CollectionSweepEvent (`analytics.models`)

**Purpose:** Tracks rapid buying patterns (whale activity)

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `collection` | ForeignKey | CASCADE, indexed | Target collection |
| `buyer_wallet` | CharField(255) | Indexed | Buyer's wallet address |
| `nft_count` | IntegerField | | Number of NFTs purchased |
| `total_value_sol` | DecimalField(20,9) | | Total purchase value |
| `average_price_sol` | DecimalField(20,9) | | Average price per NFT |
| `time_window_seconds` | IntegerField | | Time window for sweep |
| `significance_score` | DecimalField(5,2) | Default: 0.00 | Sweep importance (0-100) |
| `detected_at` | DateTimeField | Auto-now-add | Detection timestamp |

**Significance Calculation:**
```python
# Based on: NFT count, total value, speed of purchase
significance_score = (
    (nft_count / collection.supply) * 40 +  # % of supply
    (total_value_sol / collection.market_cap) * 40 +  # % of market cap
    (3600 / time_window_seconds) * 20  # Speed factor
)
```

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['collection', '-detected_at']),
        models.Index(fields=['buyer_wallet', '-detected_at']),
        models.Index(fields=['-significance_score']),
    ]
```

**Code Reference:** `analytics/models.py:100-140`

---

### 9. HighProfileTransfer (`analytics.models`)

**Purpose:** Tracks notable NFT movements between wallets

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `nft` | ForeignKey | CASCADE, indexed | Transferred NFT |
| `from_wallet` | CharField(255) | Indexed | Sender wallet |
| `to_wallet` | CharField(255) | Indexed | Receiver wallet |
| `transaction_signature` | CharField(255) | UNIQUE | Solana tx signature |
| `transfer_value_sol` | DecimalField(20,9) | Nullable | Transfer value (if sale) |
| `significance_score` | DecimalField(5,2) | Default: 0.00 | Transfer importance (0-100) |
| `transfer_type` | CharField(20) | Choices: SALE/TRANSFER/GIFT | Transfer category |
| `detected_at` | DateTimeField | Auto-now-add | Detection timestamp |

**Significance Factors:**
- Wallet prominence (known whales, influencers)
- Transfer value vs floor price
- NFT rarity rank
- Historical transfer patterns

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['nft', '-detected_at']),
        models.Index(fields=['from_wallet', '-detected_at']),
        models.Index(fields=['to_wallet', '-detected_at']),
        models.Index(fields=['-significance_score']),
    ]
```

**Code Reference:** `analytics/models.py:155-200`

---

## Marketplace Models

### 10. NFTVitality (`marketplace.models.vitality_models`)

**Purpose:** Individual NFT health score (0-100) using Anti-Gaming Architecture

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `nft` | OneToOneField | CASCADE, PRIMARY KEY | Parent NFT |
| `vitality_score` | DecimalField(5,2) | Default: 50.00 | Overall vitality (0-100) |
| `market_momentum` | FloatField | Default: 0.5 | 60-day price velocity (10%) - reduced to prevent gaming |
| `trait_performance` | FloatField | Default: 0.5 | Trait market demand (20%) |
| `collection_health` | FloatField | Default: 0.5 | Collection metrics (15%) |
| `collection_utility` | FloatField | Default: 0.5 | Real-world value (10%) |
| `rarity_score` | FloatField | Default: 0.5 | Statistical rarity (10%) |
| `holder_quality` | FloatField | Default: 0.5 | Holder profile (10%) |
| `perception_index` | FloatField | Default: 0.5 | Community perception (20%) - anti-gaming focus |
| `market_influence` | FloatField | Default: 0.5 | Market impact (5%) |
| `suggested_price` | DecimalField(20,9) | Nullable | Suggested SOL price (not yet implemented) |
| `last_calculated` | DateTimeField | Auto-now | Last calculation timestamp |
| `calculation_source` | CharField(50) | Default: 'system' | What triggered calculation |
| `has_sufficient_data` | BooleanField | Default: False | True if collection has ≥1 transaction |
| `updated_at` | DateTimeField | Auto-now | Last update timestamp |

**Component Scores:** All component fields (market_momentum, trait_performance, etc.) use FloatField with 0-1 range for precise calculations. The final vitality_score is DecimalField scaled to 0-100.

**Vitality Formula (Anti-Gaming Architecture v3.0):**
```python
vitality_score = (
    perception_index * 0.20 +      # 20% - Anti-gaming focus
    trait_performance * 0.20 +     # 20%
    collection_health * 0.15 +     # 15%
    collection_utility * 0.10 +    # 10%
    market_momentum * 0.10 +       # 10% - Reduced from 25%
    rarity_score * 0.10 +          # 10%
    holder_quality * 0.10 +        # 10%
    market_influence * 0.05        # 5%
) * 100  # Scale to 0-100
```

**Weight Changes:** Market Momentum reduced from 25% to 10%, and Perception Index (formerly Sentiment Score) increased from 5% to 20% to prioritize difficult-to-manipulate metrics.

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['vitality_score', '-last_calculated']),
        models.Index(fields=['has_sufficient_data', 'vitality_score']),
    ]
```

**Relationships:**
- **Belongs To:** NFT (1:1)
- **Has Many:** NFTVitalityHistory (1:N)

**Code Reference:** `marketplace/vitality_models.py:19-128`

---

### 11. NFTVitalityHistory (`marketplace.models.vitality_models`)

**Purpose:** Historical vitality tracking for trend analysis

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `nft` | ForeignKey | CASCADE, indexed | Parent NFT |
| `vitality_score` | DecimalField(5,2) | | Snapshot vitality score (0-100) |
| `market_momentum` | FloatField | | Snapshot market momentum (0-1) |
| `trait_performance` | FloatField | | Snapshot trait performance (0-1) |
| `collection_health` | FloatField | | Snapshot collection health (0-1) |
| `collection_utility` | FloatField | | Snapshot collection utility (0-1) |
| `rarity_score` | FloatField | | Snapshot rarity score (0-1) |
| `holder_quality` | FloatField | | Snapshot holder quality (0-1) |
| `perception_index` | FloatField | | Snapshot perception index (0-1) |
| `market_influence` | FloatField | | Snapshot market influence (0-1) |
| `suggested_price` | DecimalField(20,9) | Nullable | Snapshot suggested price |
| `calculated_at` | DateTimeField | Auto-now-add, indexed | When snapshot was created |
| `recorded_at` | DateTimeField | Auto-now-add | Snapshot timestamp |

**Retention Policy:** Keep last 90 days for VIP collections, 60 days for ACTIVE, 30 days for INACTIVE

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['nft', '-calculated_at']),
        models.Index(fields=['calculated_at', 'vitality_score']),
    ]
    ordering = ['-calculated_at']
```

**Code Reference:** `marketplace/vitality_models.py:130-183`

---

### 12. CollectionVitality (`marketplace.models.vitality_models`)

**Purpose:** Collection-level vitality score (aggregated from NFT vitalities)

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `collection` | OneToOneField | CASCADE, PRIMARY KEY | Parent collection |
| `vitality_score` | DecimalField(5,2) | Default: 50.00 | Aggregate vitality (0-100) |
| `market_momentum` | FloatField | Default: 0.5 | Collection price/volume momentum (0-1) |
| `avg_trait_performance` | FloatField | Default: 0.5 | Average trait performance across collection (0-1) |
| `collection_health` | FloatField | Default: 0.5 | Overall market health (0-1) |
| `collection_utility` | FloatField | Default: 0.5 | Collection utility/use-case value (0-1) |
| `avg_rarity_score` | FloatField | Default: 0.5 | Average rarity across collection (0-1) |
| `holder_quality_avg` | FloatField | Default: 0.5 | Average holder quality (0-1) |
| `perception_index` | FloatField | Default: 0.5 | Collection perception (0-1) |
| `market_influence` | FloatField | Default: 0.5 | Collection market influence (0-1) |
| `last_calculated` | DateTimeField | Auto-now | Last calculation timestamp |
| `has_sufficient_data` | BooleanField | Default: False | True if collection has ≥1 transaction |
| `updated_at` | DateTimeField | Auto-now | Last update timestamp |

**Calculation:**
Collection vitality is calculated by:
1. Aggregating component scores from all NFT vitalities in the collection (using Avg)
2. For collections without NFT vitalities, using collection-level metrics directly
3. Applying the same Anti-Gaming Architecture weights as NFT vitality

```python
# Aggregate from NFT vitalities
aggregates = NFTVitality.objects.filter(
    nft__collection=collection,
    has_sufficient_data=True
).aggregate(
    avg_trait_perf=Avg('trait_performance'),
    avg_rarity=Avg('rarity_score'),
    avg_holder_quality=Avg('holder_quality')
)

# Apply same weights as NFT vitality
vitality_score = (
    perception_index * 0.20 +
    avg_trait_performance * 0.20 +
    collection_health * 0.15 +
    collection_utility * 0.10 +
    market_momentum * 0.10 +
    avg_rarity_score * 0.10 +
    holder_quality_avg * 0.10 +
    market_influence * 0.05
) * 100
```

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['vitality_score', '-last_calculated']),
    ]
```

**Code Reference:** `marketplace/vitality_models.py:186-265`

---

### 13. CollectionVitalityHistory (`marketplace.models.vitality_models`)

**Purpose:** Historical collection vitality tracking for trend analysis

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `collection` | ForeignKey | CASCADE, indexed | Parent collection |
| `vitality_score` | DecimalField(5,2) | | Snapshot collection vitality (0-100) |
| `market_momentum` | FloatField | | Snapshot market momentum (0-1) |
| `avg_trait_performance` | FloatField | | Snapshot average trait performance (0-1) |
| `collection_health` | FloatField | | Snapshot collection health (0-1) |
| `collection_utility` | FloatField | | Snapshot collection utility (0-1) |
| `avg_rarity_score` | FloatField | | Snapshot average rarity score (0-1) |
| `holder_quality_avg` | FloatField | | Snapshot average holder quality (0-1) |
| `perception_index` | FloatField | | Snapshot perception index (0-1) |
| `market_influence` | FloatField | | Snapshot market influence (0-1) |
| `calculated_at` | DateTimeField | Auto-now-add, indexed | When snapshot was created |
| `recorded_at` | DateTimeField | Auto-now-add | Snapshot timestamp |

**Retention Policy:** Same as NFT vitality history (90/60/30 days based on collection priority)

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['collection', '-calculated_at']),
    ]
    ordering = ['-calculated_at']
```

**Code Reference:** `marketplace/vitality_models.py:306-348`

---

### 15. AuctionEvent (`marketplace.models`)

**Purpose:** Platform auction management

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `nft` | ForeignKey | CASCADE, indexed | Auctioned NFT |
| `seller` | ForeignKey | CASCADE | Seller (CustomUser) |
| `starting_price` | DecimalField(20,9) | | Auction starting price |
| `current_bid` | DecimalField(20,9) | Nullable | Current highest bid |
| `reserve_price` | DecimalField(20,9) | Nullable | Minimum acceptable price |
| `highest_bidder` | ForeignKey | Nullable, SET_NULL | Current highest bidder |
| `status` | CharField(20) | Choices: ACTIVE/SOLD/CANCELLED | Auction status |
| `start_time` | DateTimeField | | Auction start time |
| `end_time` | DateTimeField | | Auction end time |
| `created_at` | DateTimeField | Auto-now-add | Creation timestamp |

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['status', 'end_time']),
        models.Index(fields=['nft', '-created_at']),
    ]
```

**Code Reference:** `marketplace/models/auction_models.py:15-60`

---

## Advanced Analytics Models (axplorer app)

### 16. MarketRegime (`axplorer.models`)

**Purpose:** Classifies current market conditions

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `collection` | ForeignKey | Nullable, CASCADE | Collection (null = global) |
| `regime_type` | CharField(20) | Choices: BULL/BEAR/CONSOLIDATION/VOLATILE | Market classification |
| `confidence` | DecimalField(5,2) | | Classification confidence |
| `metrics` | JSONField | | Supporting metrics |
| `start_time` | DateTimeField | | Regime start time |
| `end_time` | DateTimeField | Nullable | Regime end time (null = ongoing) |

**Regime Classification Logic:**
```python
if price_change_7d > 20% and volume_increase > 50%:
    regime_type = 'BULL'
elif price_change_7d < -20% and volume_increase > 30%:
    regime_type = 'BEAR'
elif abs(price_change_7d) < 5% and volume_stable:
    regime_type = 'CONSOLIDATION'
else:
    regime_type = 'VOLATILE'
```

**Code Reference:** `axplorer/models.py:50-90`

---

### 17. AdvancedCrossMarketplaceAnalysis (`axplorer.models`)

**Purpose:** Multi-platform price and volume analysis

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `collection` | ForeignKey | CASCADE, indexed | Analyzed collection |
| `magic_eden_floor` | DecimalField(20,9) | Nullable | Magic Eden floor price |
| `tensor_floor` | DecimalField(20,9) | Nullable | Tensor floor price |
| `price_discrepancy_percent` | DecimalField(6,2) | | Cross-platform price difference |
| `arbitrage_opportunity_score` | DecimalField(5,2) | | Arbitrage potential (0-100) |
| `magic_eden_volume_24h` | DecimalField(20,9) | | Magic Eden 24h volume |
| `tensor_volume_24h` | DecimalField(20,9) | | Tensor 24h volume |
| `liquidity_imbalance_score` | DecimalField(5,2) | | Liquidity distribution score |
| `analyzed_at` | DateTimeField | Auto-now-add | Analysis timestamp |

**Arbitrage Calculation:**
```python
price_diff = abs(magic_eden_floor - tensor_floor)
arbitrage_opportunity_score = min(
    (price_diff / min(magic_eden_floor, tensor_floor)) * 100,
    100
)
```

**Code Reference:** `axplorer/models.py:120-170`

---

### 18. PredictionRecord (`axplorer.models`)

**Purpose:** ML prediction tracking and validation

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `collection` | ForeignKey | CASCADE, indexed | Predicted collection |
| `prediction_type` | CharField(50) | Choices: PRICE/VOLUME/VITALITY | Prediction category |
| `predicted_value` | DecimalField(20,9) | | Predicted value |
| `actual_value` | DecimalField(20,9) | Nullable | Actual observed value |
| `prediction_horizon_hours` | IntegerField | | Prediction timeframe |
| `confidence` | DecimalField(5,2) | | Model confidence (0-100) |
| `model_version` | CharField(50) | | ML model version |
| `features_used` | JSONField | | Input features |
| `predicted_at` | DateTimeField | Auto-now-add | Prediction timestamp |
| `validated_at` | DateTimeField | Nullable | Validation timestamp |
| `accuracy_score` | DecimalField(5,2) | Nullable | Prediction accuracy (0-100) |

**Accuracy Calculation:**
```python
error = abs(predicted_value - actual_value)
accuracy_score = max(100 - (error / actual_value * 100), 0)
```

**Code Reference:** `axplorer/models.py:200-250`

---

## User & Authentication Models

### 19. CustomUser (`wallet.models`)

**Purpose:** Custom user model extending Django's AbstractUser

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `username` | CharField(150) | UNIQUE | Username (optional for wallet-only users) |
| `email` | EmailField(254) | UNIQUE | User email |
| `password` | CharField(128) | | Hashed password |
| `secondary_identifier` | CharField(255) | Nullable | Multi-factor identifier |
| `last_login_ip` | GenericIPAddressField | Nullable | Last login IP address |
| `password_expires_at` | DateTimeField | Nullable | Password expiration |
| `two_factor_enabled` | BooleanField | Default: False | 2FA enabled flag |
| `two_factor_secret` | CharField(100) | Nullable | TOTP secret key |
| `is_active` | BooleanField | Default: True | Account active flag |
| `is_staff` | BooleanField | Default: False | Staff access flag |
| `is_superuser` | BooleanField | Default: False | Superuser flag |
| `date_joined` | DateTimeField | Auto-now-add | Account creation date |

**Indexes:**
```python
class Meta:
    indexes = [
        models.Index(fields=['email']),
        models.Index(fields=['username']),
    ]
```

**Relationships:**
- **Has Many:** WalletProfile (1:N)
- **Has Many:** Notification (1:N)
- **Has Many:** PendingCollection (1:N)

**Code Reference:** `wallet/models.py:20-70`

---

### 20. WalletProfile (`wallet.models`)

**Purpose:** Links Solana wallets to CustomUser accounts

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `user` | ForeignKey | CASCADE, indexed | Parent CustomUser |
| `public_key` | CharField(255) | UNIQUE | Solana wallet public key (Base58) |
| `is_primary` | BooleanField | Default: False | Primary wallet flag |
| `verified_at` | DateTimeField | Nullable | Wallet verification timestamp |
| `created_at` | DateTimeField | Auto-now-add | Link creation timestamp |

**Validation:**
```python
# Solana public key must be valid Base58 format
import re
SOLANA_ADDRESS_REGEX = r'^[1-9A-HJ-NP-Za-km-z]{32,44}$'

def clean_public_key(self):
    if not re.match(SOLANA_ADDRESS_REGEX, self.public_key):
        raise ValidationError("Invalid Solana address format")
```

**Code Reference:** `wallet/models.py:85-115`

---

### 21. PasswordResetCode (`wallet.models`)

**Purpose:** Temporary password reset tokens

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `user` | ForeignKey | CASCADE | Target user |
| `code` | CharField(100) | UNIQUE | Reset token (UUID4) |
| `expires_at` | DateTimeField | | Token expiration (24 hours) |
| `used` | BooleanField | Default: False | Token used flag |
| `created_at` | DateTimeField | Auto-now-add | Creation timestamp |

**Token Generation:**
```python
import uuid
from datetime import timedelta
from django.utils import timezone

code = uuid.uuid4().hex
expires_at = timezone.now() + timedelta(hours=24)
```

**Code Reference:** `wallet/models.py:130-155`

---

## Administrative Models

### 22. AdminUser (`admin_panel.models`)

**Purpose:** Separate admin authentication (not using Django's built-in User)

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `username` | CharField(150) | UNIQUE | Admin username |
| `email` | EmailField(254) | UNIQUE | Admin email |
| `password` | CharField(128) | | Hashed password |
| `full_name` | CharField(255) | Nullable | Admin full name |
| `is_active` | BooleanField | Default: True | Account active flag |
| `is_superadmin` | BooleanField | Default: False | Super admin flag |
| `permissions` | JSONField | Default: [] | Custom permissions list |
| `last_login` | DateTimeField | Nullable | Last login timestamp |
| `last_login_ip` | GenericIPAddressField | Nullable | Last login IP |
| `two_factor_enabled` | BooleanField | Default: False | 2FA enabled flag |
| `two_factor_secret` | CharField(100) | Nullable | TOTP secret |
| `created_at` | DateTimeField | Auto-now-add | Account creation |

**Why Separate from CustomUser?**
- Enhanced security (separate auth backend)
- Different permission model
- Independent audit trail
- No overlap with user authentication

**Code Reference:** `admin_panel/models.py:20-75`

---

### 23. AdminLoginAttempt (`admin_panel.models`)

**Purpose:** Admin login audit trail

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `admin_user` | ForeignKey | Nullable, CASCADE | Attempted admin (null if invalid username) |
| `username_attempted` | CharField(150) | | Username used in attempt |
| `ip_address` | GenericIPAddressField | | Source IP address |
| `user_agent` | TextField | | Browser user agent |
| `success` | BooleanField | | Login success flag |
| `failure_reason` | CharField(255) | Nullable | Failure reason if unsuccessful |
| `attempted_at` | DateTimeField | Auto-now-add | Attempt timestamp |

**Security Features:**
- Track failed login attempts
- IP-based rate limiting
- Brute force detection

**Code Reference:** `admin_panel/models.py:90-120`

---

### 24. PrimaryProviderSetting (`admin_panel.models`)

**Purpose:** RPC provider configuration

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `provider_name` | CharField(50) | UNIQUE | Provider name (Helius, QuickNode) |
| `is_primary` | BooleanField | Default: False | Primary provider flag |
| `api_key` | CharField(255) | | API key (encrypted) |
| `rpc_url` | URLField | | RPC endpoint URL |
| `websocket_url` | URLField | Nullable | WebSocket URL for subscriptions |
| `quota_daily` | BigIntegerField | | Daily request quota |
| `quota_used` | BigIntegerField | Default: 0 | Requests used today |
| `priority_allocation` | JSONField | | Priority-based quota allocation |
| `is_active` | BooleanField | Default: True | Provider active flag |
| `last_reset` | DateTimeField | | Last quota reset timestamp |

**Priority Allocation Example:**
```json
{
  "VIP": 60,
  "ACTIVE": 30,
  "INACTIVE": 10
}
```

**Code Reference:** `admin_panel/models.py:140-190`

---

## Support Models

### 25. Notification (`notifications.models`)

**Purpose:** User notification system

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `user` | ForeignKey | CASCADE, indexed | Target user |
| `notification_type` | CharField(50) | | Type (TRANSACTION/SWEEP/TRAIT_CHANGE/etc.) |
| `title` | CharField(255) | | Notification title |
| `message` | TextField | | Notification message |
| `link` | URLField | Nullable | Associated link (NFT detail, collection page) |
| `is_read` | BooleanField | Default: False | Read status |
| `created_at` | DateTimeField | Auto-now-add | Creation timestamp |

**Notification Types:**
- `TRANSACTION` - NFT sales/purchases
- `COLLECTION_SWEEP` - Collection sweep detected
- `TRAIT_PERFORMANCE` - Trait value changes
- `HIGH_PROFILE_TRANSFER` - Notable NFT movements
- `WALLET_ACTIVITY` - Monitored wallet activity
- `COLLECTION_APPROVED` - Pending collection approved

**Code Reference:** `notifications/models.py:20-60`

---

### 26. HeroSlide (`advertisement.models`)

**Purpose:** Homepage hero carousel management

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `title` | CharField(255) | | Slide title |
| `description` | TextField | | Slide description |
| `image` | ImageField | | Background image |
| `button_text` | CharField(100) | Nullable | CTA button text |
| `button_link` | URLField | Nullable | CTA button URL |
| `order` | IntegerField | Default: 0 | Display order |
| `is_active` | BooleanField | Default: True | Active flag |
| `created_at` | DateTimeField | Auto-now-add | Creation timestamp |

**Code Reference:** `advertisement/models.py:15-45`

---

### 27. Course (`learn.models`)

**Purpose:** Educational course management

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `title` | CharField(255) | | Course title |
| `slug` | SlugField(255) | UNIQUE | URL-friendly identifier |
| `description` | TextField | | Course description |
| `difficulty` | CharField(20) | Choices: BEGINNER/INTERMEDIATE/ADVANCED | Difficulty level |
| `is_featured` | BooleanField | Default: False | Featured flag |
| `created_at` | DateTimeField | Auto-now-add | Creation timestamp |

**Code Reference:** `learn/models.py:15-40`

---

### 28. NFTBurn (`nftmemories.models`)

**Purpose:** NFT burn history with community commentary

**Fields:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | AutoField | PRIMARY KEY | Auto-incrementing ID |
| `nft` | ForeignKey | CASCADE | Burned NFT |
| `collection` | ForeignKey | CASCADE | Parent collection |
| `burned_by` | CharField(255) | | Burner's wallet address |
| `burn_reason` | TextField | | User-submitted burn reason |
| `community_commentary` | TextField | Nullable | Community comments |
| `significance` | CharField(20) | Choices: LOW/MEDIUM/HIGH/LEGENDARY | Burn significance |
| `transaction_signature` | CharField(255) | UNIQUE | Solana tx signature |
| `burned_at` | DateTimeField | | Burn timestamp |
| `created_at` | DateTimeField | Auto-now-add | Record creation |

**Code Reference:** `nftmemories/models.py:20-65`

---

## Indexes & Performance

### Index Strategy

**Primary Indexes:**
- All primary keys (auto-indexed)
- All foreign keys (auto-indexed in PostgreSQL)
- All unique constraints (auto-indexed)

**Custom Composite Indexes:**

```python
# High-traffic query patterns
models.Index(fields=['collection', 'rarity_rank'])  # NFT rarity queries
models.Index(fields=['collection', '-vitality_score'])  # Vitality leaderboards
models.Index(fields=['status', '-submitted_at'])  # Admin review queue
models.Index(fields=['-detected_at', 'collection'])  # Recent events
```

**Index Maintenance:**
```sql
-- Analyze table statistics (run weekly)
ANALYZE nft_data_nft;
ANALYZE marketplace_nftvitality;
ANALYZE analytics_aggregatedcollectionstats;

-- Rebuild indexes (if fragmented)
REINDEX TABLE nft_data_nft;
```

---

## Data Integrity

### Foreign Key Constraints

**CASCADE Deletes:**
- `NFT.collection` → `NFTCollection` (cascade)
- `TraitValue.trait_type` → `TraitType` (cascade)
- `NFTVitality.nft` → `NFT` (cascade)

**SET_NULL on Delete:**
- `HighProfileTransfer.nft` → `NFT` (set null to preserve history)
- `PendingCollection.reviewed_by` → `AdminUser` (set null)

### Data Validation

**Model-Level Validation:**
```python
class NFT(models.Model):
    def clean(self):
        # Validate Solana address format
        if not re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', self.mint_address):
            raise ValidationError("Invalid mint address")

        # Validate price is positive
        if self.listing_price and self.listing_price < 0:
            raise ValidationError("Price must be positive")
```

**Database Constraints:**
```python
class Meta:
    constraints = [
        models.CheckConstraint(
            check=models.Q(vitality_score__gte=0) & models.Q(vitality_score__lte=100),
            name='vitality_score_range'
        ),
    ]
```

---

## Related Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture overview
- [VITALITY_SYSTEM.md](./VITALITY_SYSTEM.md) - Vitality calculation details
- [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) - API endpoints reference
- [CACHING_STRATEGY.md](./CACHING_STRATEGY.md) - Cache layer documentation

---

**Last Updated:** January 2025
**Database Version:** PostgreSQL 15
**Schema Version:** 2.0.0
**Vitality Algorithm Version:** v3.0 (Anti-Gaming Architecture)
