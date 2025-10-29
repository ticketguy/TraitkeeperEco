# Indexer App

## Overview

The indexer app is the **real-time blockchain data collection engine** for TraitKeeper. It monitors the Solana blockchain for NFT-related events across multiple marketplaces and stores them in a structured, queryable format.

## Purpose

- **Real-time event indexing** via WebSocket subscriptions to 7 marketplace programs
- **Multi-source data collection** from blockchain, Magic Eden API, Tensor API
- **Tiered transaction parsing** with discriminator-based classification
- **Automated collection discovery** without prior knowledge of collection addresses
- **Market statistics aggregation** from multiple external sources

## Architecture

### Data Flow

```
Solana Blockchain
    ↓
WebSocket Subscriptions (7 marketplace programs)
    ↓
TransactionParserService (Tiered parsing)
    ↓
Database (NFTEvent, NFTListing, CollectionMarketStats)
    ↓
Analytics App (for vitality calculations)
```

### 7 Monitored Marketplace Programs

1. **Magic Eden V2** - `M2mx93ekt1fmXSVkTrUL9xVFHkmME8HTUi5Cyc5aF7K`
2. **Magic Eden MMM** - `mmm3XBJg5gk8XJxEKBvdgptZz6SgK4tXvn36sodowMc`
3. **Tensor cNFT** - `TCMPhJdwDryooaGtiocG1u3xcYbRpiJzb283XfCZsDp`
4. **Tensor AMM** - `TAMM6ubQ3ij1mbetomYVBLeKYQi4UPUJQGkhjsg`
5. **TensorSwap** - `TSWAPaqyCSx2KABk68Shruf4rp7CxcNi8hAsbdwmHbN`
6. **Hyperspace** - `3o9d13qUvEuau4hFrVom1vuCzgNsJifeaBYDPquaT73Y`
7. **Hadeswap** - `hausS13jsjafwWwGqZTUQRmWyvyxn9EQpqMwV1PBBmk`

## Key Components

### 1. Real-Time Event Monitoring

**WebSocket subscriptions** to marketplace programs for immediate event detection.

**What we capture:**

- NFT sales
- Listings created/cancelled
- Bids placed/cancelled
- Transfers
- Mints
- Burns

### 2. Transaction Parsing System

**Tiered parsing** for efficient and accurate event classification.

**Tier 1: Discriminator Parsing**

- Fast classification using 8-byte instruction discriminators
- Identifies marketplace and action type instantly
- Filters out admin operations

**Tier 2: Log Pattern Analysis** (when discriminator unknown)

- Analyzes transaction logs for marketplace signatures
- Detects transfers and price patterns
- Auto-learns new discriminators

**Tier 3: Account Analysis** (fallback)

- Deep inspection of account changes
- Validates NFT/SOL transfers
- Confirms marketplace involvement

### 3. Multi-Source Data Aggregation

Collects data from **3 sources** for reliability:

| Source | Data Type | Update Frequency |
|--------|-----------|------------------|
| Blockchain | Raw on-chain events | Real-time (WebSocket) |
| Magic Eden API | Collection stats, slugs | Every 15-60 min |
| Tensor API | Collection stats, UUIDs | Every 15-60 min |

### 4. Collection Discovery

**Automatic discovery** of new NFT collections through:

- Event monitoring (Metaplex program events)
- API integrations (Magic Eden, Tensor new listings)
- User submissions (marketplace/PendingCollection)
- Marketplace method discovery (planned)

## Models

### Core Event Models

#### NFTEvent

**Immutable record** of on-chain NFT events.

**Key Fields:**

- `event_id` - Transaction signature (PK)
- `collection_address` - Collection this event belongs to
- `nft_mint` - Specific NFT involved
- `event_type` - SALE, LISTING, BID, TRANSFER, MINT, BURN
- `marketplace` - magic_eden, tensor, traitkeeper, etc.
- `amount` - Price/bid amount in SOL
- `buyer` / `seller` - Wallet addresses
- `timestamp` - On-chain timestamp
- `details` - Raw transaction data (JSON)

**Indexes:**

- `(collection_address, event_type, timestamp)` - Fast collection queries
- `(nft_mint, timestamp)` - NFT history lookups

**Used by:**

- Analytics app for vitality calculations
- Marketplace app for transaction history
- Admin panel for monitoring

#### NFTListing

**Tracks active marketplace listings**.

**Key Fields:**

- `listing_id` - Marketplace-specific ID (PK)
- `nft_mint` - NFT being listed
- `collection_address` - Collection
- `marketplace` - Source marketplace
- `price` - Listing price in SOL
- `seller_address` - Seller wallet
- `status` - ACTIVE, SOLD, CANCELLED, EXPIRED
- `listed_at` / `expires_at` - Timing
- `raw_data` - Complete API response (JSON)

**Indexes:**

- `(collection_address, status, price)` - Floor price queries
- `(marketplace, status, listed_at)` - Marketplace analytics

### Multi-Source Data Models

#### CollectionMarketStats

**Raw statistics from external sources**.

**Purpose:** Store unmodified data from each source for later aggregation.

**Key Fields:**

- `collection` - FK to NFTCollection
- `source` - magic_eden, tensor, blockchain, traitkeeper
- `floor_price` - Source's reported floor
- `volume_24h` - 24h trading volume
- `sales_count_24h` - Number of sales
- `owners_count` - Unique holders
- `listed_count` - Active listings
- `total_supply` - Total NFTs in collection
- `timestamp` - When data was collected
- `raw_data` - Complete API response (JSON)

**Indexes:**

- `(collection, source, timestamp)` - Time-series queries per source

**Used by:**

- Analytics app for aggregated statistics
- Vitality calculations (market influence component)
- Cache manager for source attribution

#### MarketplaceIdentifier

**Maps collections to marketplace-specific IDs**.

**Why:** Each marketplace uses different identifiers (slugs, UUIDs, symbols).

**Key Fields:**

- `collection` - FK to NFTCollection
- `marketplace` - magic_eden, tensor, opensea
- `identifier_value` - The slug/UUID/symbol

**Example:**

```python
# Mad Lads collection has different IDs per marketplace
MarketplaceIdentifier(collection=mad_lads, marketplace='magic_eden', identifier_value='mad_lads')
MarketplaceIdentifier(collection=mad_lads, marketplace='tensor', identifier_value='uuid-1234')
```

### Helper Models

#### BurnEvent

Specific record for NFT burns (irreversible).

#### TraitEvent

Tracks metadata updates where traits change.

#### FailedTransaction

Logs transactions that failed processing for retry/investigation.

#### UnknownDiscriminator

**Auto-learning system** for unknown instruction discriminators.

**Purpose:** Automatically detect and learn new marketplace programs.

**Key Fields:**

- `program_id` + `discriminator` - Unique identifier
- `inferred_marketplace` - Best guess of which marketplace
- `inferred_action` - Detected action type
- `has_nft_transfer` / `has_native_transfer` - Transfer detection
- `log_patterns` - Matched log signatures
- `sample_signatures` - Example transactions
- `occurrence_count` - How often seen
- `is_approved` - Manual review flag
- `should_ignore` - If it's admin operations

## Services

### IndexerService

**Main orchestrator** in `services/main.py`.

**Responsibilities:**

- Initialize WebSocket subscriptions
- Coordinate real-time event processing
- Manage background task scheduling
- Handle collection indexing

### TransactionParserService

**Tiered transaction parser** in `services/parser.py`.

**Main Method:** `parse_transaction(signature)`

**Process:**

1. Tier 1: Check discriminator → instant classification
2. Tier 2: Analyze logs → pattern matching
3. Tier 3: Check accounts → deep inspection
4. Create NFTEvent if marketplace transaction found

### MetadataService

**NFT metadata fetcher** in `services/metadata.py`.

**Fetches:**

- On-chain metadata from Metaplex
- Off-chain JSON from URI
- Image URLs
- Trait data

### TransactionFilterService

**Filters relevant transactions** in `services/transaction_filter.py`.

**Filters:**

- Marketplace transactions only
- Ignore admin operations
- Ignore failed transactions
- Prioritize by collection importance

### DiscriminatorLearner

**Auto-learning system** in `services/discriminator_learner.py`.

**Learns:**

- New marketplace programs
- New instruction types
- Transaction patterns
- Log signatures

## Background Tasks

### BackgroundTaskManager

Manages **3 types of background tasks**:

#### 1. Real-Time Event Subscriptions

- WebSocket connections to 7 marketplace programs
- Processes events as they occur
- Runs continuously

#### 2. Periodic Collection Indexing

- Fetches missing transaction history
- Updates collection statistics
- Runs every 15-60 minutes based on priority

#### 3. Marketplace API Polling

- Fetches data from Magic Eden, Tensor APIs
- Updates CollectionMarketStats
- Runs every 15-60 minutes

## Data Sources

### 1. Blockchain (Primary)

**Real-time on-chain events** via QuickNode RPC + WebSockets.

**Advantages:**

- Most accurate (source of truth)
- Real-time updates
- No rate limits (WebSocket)

**Disadvantages:**

- Complex parsing required
- No collection-level aggregates
- High data volume

### 2. Magic Eden API (Secondary)

**REST API** for collection statistics and metadata.

**Endpoints Used:**

- `/collections/{slug}/stats` - Collection statistics
- `/collections/{slug}/listings` - Active listings
- `/collections/{slug}/activities` - Recent sales

**Advantages:**

- Clean, structured data
- Collection-level aggregates
- Marketplace-specific insights

**Disadvantages:**

- Rate limits
- Delayed updates (not real-time)
- Requires slug mapping

### 3. Tensor API (Secondary)

**GraphQL API** for collection data.

**Queries Used:**

- Collection statistics
- Active listings
- Recent sales
- Floor price trends

**Advantages:**

- Powerful querying
- Good for analytics
- Popular marketplace

**Disadvantages:**

- Requires UUID mapping
- Rate limits
- Complex authentication

## Configuration

### Marketplace Program IDs

Located in `nft_constants.py`:

```python
MARKETPLACE_PROGRAMS = {
    'magic_eden_v2': 'M2mx93ekt1fmXSVkTrUL9xVFHkmME8HTUi5Cyc5aF7K',
    'magic_eden_mmm': 'mmm3XBJg5gk8XJxEKBvdgptZz6SgK4tXvn36sodowMc',
    'tensor_cnft': 'TCMPhJdwDryooaGtiocG1u3xcYbRpiJzb283XfCZsDp',
    # ... etc
}
```

### Indexer Configuration

Located in `indexer_config.py`:

```python
INDEXER_CONFIG = {
    'WEBSOCKET_ENABLED': True,
    'RETRY_FAILED_EVENTS': True,
    'MAX_RETRIES': 3,
    'BATCH_SIZE': 100,
    # ... etc
}
```

### RPC Provider

Set in settings.py or environment:

```python
QUICKNODE_ENDPOINT = "https://neat-quiet-pine.solana-mainnet.quiknode.pro/..."
```

## Quota Management

### QuotaManager

Located in `quota_manager.py`.

**Manages:**

- Daily credit allocation per provider
- Requests per second limits
- Priority-based credit distribution (VIP: 60%, ACTIVE: 30%, INACTIVE: 10%)

**Providers:**

- Helius (WebSocket, API)
- QuickNode (RPC, WebSocket)

## Integration with Other Apps

### → Analytics App

Provides raw data for analytics:

- NFTEvent → Trait performance analysis
- CollectionMarketStats → Collection health scores
- NFTListing → Floor price calculations

### → Marketplace App

Provides event data for:

- NFT transaction history
- Vitality price comparisons
- Market momentum calculations

### → Admin Panel

Provides monitoring data:

- Event processing status
- Failed transactions
- Unknown discriminators needing review

## Monitoring & Debugging

### Debug Logs

Located in `debug_session.log`:

- Real-time event processing
- Parser tier decisions
- WebSocket connection status
- Error traces

### Background Task Logs

Located in `background_tasks.log`:

- Task execution times
- Success/failure rates
- Collection processing status

### Admin Interface

Monitor via Django admin:

- Failed transactions
- Unknown discriminators
- Recent events
- Collection discovery

## Common Operations

### Start Real-Time Indexing

```python
from indexer.background_task_manager import BackgroundTaskManager

manager = BackgroundTaskManager()
manager.start()  # Starts WebSocket subscriptions + periodic tasks
```

### Index Specific Collection

```python
from indexer.services.main import IndexerService
from nft_data.models import NFTCollection

indexer = IndexerService()
collection = NFTCollection.objects.get(address="...")
indexer.index_collection(collection.address)
```

### Retry Failed Transactions

```python
from indexer.models import FailedTransaction

failed = FailedTransaction.objects.filter(retry_count__lt=3)
for ft in failed:
    # Retry parsing
    parser.parse_transaction(ft.event_id)
```

## TODOList

### High Priority

- [ ] Optimize WebSocket reconnection logic
- [ ] Implement event deduplication across sources
- [ ] Add health monitoring dashboard
- [ ] Improve discriminator auto-learning accuracy

### Medium Priority

- [ ] Add support for more marketplaces (OpenSea, Solanart)
- [ ] Implement event replay for missed transactions
- [ ] Create admin tools for manual event editing
- [ ] Add metrics/analytics for indexer performance

### Low Priority

- [ ] Optimize database indexes for large datasets
- [ ] Implement data archiving for old events
- [ ] Add support for compressed NFTs (cNFTs) across all marketplaces

## Troubleshooting

### WebSocket Disconnections

Check `debug_session.log` for:

- Connection errors
- Rate limit issues
- Invalid subscriptions

**Solution:** Background manager auto-reconnects, but manual restart may be needed.

### Missing Events

Check:

- `FailedTransaction` model for parse errors
- `UnknownDiscriminator` for new marketplace programs
- WebSocket subscription status

### High CPU Usage

- Reduce `BATCH_SIZE` in config
- Increase `POLLING_INTERVAL`
- Disable less important marketplaces

## Related Documentation

- [nft_constants.py](./nft_constants.py) - All marketplace program IDs and discriminators
- [indexer_config.py](./indexer_config.py) - Configuration options
- [background_task_manager.py](./background_task_manager.py) - Task scheduling logic
- [services/parser.py](./services/parser.py) - Transaction parsing implementation
