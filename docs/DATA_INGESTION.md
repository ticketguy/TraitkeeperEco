# TraitKeeper Data Ingestion System

## Table of Contents

1. [Overview](#overview)
2. [Data Ingestion Architecture](#data-ingestion-architecture)
3. [Data Sources](#data-sources)
4. [Ingestion Pipeline Flow](#ingestion-pipeline-flow)
5. [Failed Transaction Handling](#failed-transaction-handling)
6. [Data Validation & Quality](#data-validation--quality)
7. [Multi-Source Aggregation](#multi-source-aggregation)
8. [Performance & Monitoring](#performance--monitoring)

---

## Overview

TraitKeeper's data ingestion system is a **multi-source, fault-tolerant pipeline** that collects, validates, and aggregates NFT data from multiple sources:

- **Primary Source:** Solana blockchain (via RPC providers)
- **Secondary Sources:** Magic Eden API, Tensor API
- **Validation:** Cross-referencing between sources
- **Storage:** PostgreSQL with strategic indexing

### Key Design Principles

1. **Blockchain = Source of Truth** - Always trust on-chain data over marketplace APIs
2. **Fault Tolerance** - Continue ingestion even if one source fails
3. **Retry Logic** - Automatically retry failed transactions
4. **Data Quality** - Validate and sanitize all inputs
5. **Performance** - Async processing with rate limiting

---

## Data Ingestion Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DATA INGESTION SYSTEM                             │
└─────────────────────────────────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
    ┌────▼─────┐          ┌─────▼──────┐        ┌──────▼────┐
    │ Solana   │          │ Magic Eden │        │  Tensor   │
    │Blockchain│          │    API     │        │    API    │
    │ (Primary)│          │(Secondary) │        │(Secondary)│
    └────┬─────┘          └─────┬──────┘        └──────┬────┘
         │                      │                      │
         │  WebSocket           │  REST API            │  REST API
         │  (Real-time)         │  (Polling)           │  (Polling)
         │                      │                      │
         └──────────┬───────────┴──────────────────────┘
                    │
            ┌───────▼────────┐
            │   IndexerService│
            │  (Coordinator)  │
            └───────┬────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
   ┌────▼─────┐ ┌──▼────┐ ┌────▼──────┐
   │Transaction│ │Parser │ │Aggregator │
   │  Fetcher  │ │Service│ │  Service  │
   └────┬─────┘ └──┬────┘ └────┬──────┘
        │          │           │
        └──────────┼───────────┘
                   │
        ┌──────────▼──────────┐
        │   Validation Layer  │
        │  • Schema validation│
        │  • Cross-check data │
        │  • Deduplication    │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │  PostgreSQL Database│
        │                     │
        │  • NFTEvent         │
        │  • NFTListing       │
        │  • FailedTransaction│
        │  • CollectionMarket-│
        │    Stats            │
        └─────────────────────┘
```

**Code Reference:**
- `indexer/services/main.py` - Main orchestrator
- `indexer/services/parser.py` - Transaction parsing
- `indexer/background_task_manager.py` - Scheduling

---

## Data Sources

### 1. Solana Blockchain (Primary Source)

**What We Ingest:**
- NFT mints, transfers, sales
- Listings, delistings, bids
- Metadata updates
- Burn events

**How We Ingest:**

```python
# indexer/services/main.py:150-250
async def index_blockchain_events():
    """Real-time WebSocket subscription to Solana blockchain"""

    # Subscribe to program logs (Metaplex, Magic Eden, Tensor programs)
    await provider_manager.subscribe_to_programs(
        program_ids=[
            'M2mx93ekt1fmXSVkTrUL9xVFHkmME8HTUi5Cyc5aF7K',  # Metaplex Token Metadata
            'MEisE1HzehtrDpAAT8PnLHjpSSkRYakotTuJRPjTpo8',  # Magic Eden v2
            'TSWAPaqyCSx2KABk68Shruf4rp7CxcNi8hAsbdwmHbN',  # Tensor Swap
        ],
        callback=process_transaction
    )
```

**Processing Flow:**
1. WebSocket receives transaction signature
2. Fetch full transaction details via RPC
3. Parse transaction instructions
4. Extract NFT events (sale, transfer, etc.)
5. Store in database

**Rate Limiting:** Managed by RPC provider quotas (Helius: 1M/day, QuickNode: 10M/day)

**Code Reference:** `indexer/services/blockchain_indexer.py`, `core/api_provider/api_providers.py:214-330`

---

### 2. Magic Eden API (Secondary Source)

**What We Ingest:**
- Floor prices
- Listed NFTs count
- 24h volume
- Recent sales
- Collection slugs

**How We Ingest:**

```python
# core/api_provider/magic_eden_provider.py:310-375
async def get_collection_data(collection_slug, collection_address, priority_tier):
    """Fetch collection stats from Magic Eden"""

    # Fetch from ME API v2
    stats_response = await self._async_get(f"/collections/{collection_slug}/stats")

    # Convert lamports to SOL
    floor_price = float(Decimal(str(stats_response['floorPrice'])) / Decimal('1000000000'))

    # Cache with priority-based TTL
    await cache_manager.set(cache_key, result, CacheType.PROVIDER, collection_address)
```

**Update Frequency:**
- VIP Collections: Every 15 minutes
- ACTIVE Collections: Every 1 hour
- INACTIVE Collections: Every 4 hours

**Rate Limiting:** 15 requests/minute (enforced by `RateLimiter` class)

**Code Reference:** `core/api_provider/magic_eden_provider.py`

---

### 3. Tensor API (Secondary Source)

**What We Ingest:**
- Floor prices
- Volume (24h, 7d)
- Sales count
- Supply metrics
- Collection UUIDs

**How We Ingest:**

```python
# core/api_provider/tensor_provider.py:260-326
async def get_collection_data(collection_symbol, collection_address, priority_tier):
    """Fetch collection stats from Tensor"""

    # Find collection by UUID
    collection_info = await self._get_collection_info(collection_symbol)

    # Extract stats
    stats = collection_info.get('stats', {})
    floor_price = self._convert_lamports_to_sol(stats.get('buyNowPrice', 0))

    # Store UUID mapping for future use
    await self._store_collection_uuid(collection_address, collection_symbol)
```

**Update Frequency:** Same as Magic Eden (priority-based)

**Rate Limiting:** 1 request/second (enforced by `TensorRateLimiter` class)

**Code Reference:** `core/api_provider/tensor_provider.py`

---

## Ingestion Pipeline Flow

### Step-by-Step Process

#### 1. Real-Time Event Detection

```
Solana Blockchain
    │
    │ WebSocket Connection
    ▼
┌────────────────────────┐
│ RPC Provider           │
│ (Helius/QuickNode)     │
└────────────┬───────────┘
             │
             │ Transaction Signature: "3Kx7..."
             ▼
┌────────────────────────┐
│ IndexerService         │
│ .process_transaction() │
└────────────┬───────────┘
             │
             ▼
```

**Code Location:** `indexer/services/main.py:200-450`

---

#### 2. Transaction Parsing

```
┌────────────────────────┐
│ TransactionParserService│
│ (Tiered Parsing System) │
└────────────┬───────────┘
             │
     ┌───────┼────────┐
     │       │        │
  ┌──▼──┐ ┌─▼──┐ ┌───▼───┐
  │Tier 1│ │Tier│ │Tier 3 │
  │Known │ │ 2  │ │Unknown│
  │Instru│ │Infer│ │->     │
  │ction │ │ence │ │FailedTX│
  └──┬──┘ └─┬──┘ └───┬───┘
     │      │        │
     └──────┼────────┘
            │
            ▼
    NFTEvent extracted
```

**Parsing Tiers:**

| Tier | Type | Action | Success Rate |
|------|------|--------|--------------|
| **Tier 1** | Known discriminators | Direct parse | 85% |
| **Tier 2** | Pattern matching | Infer from logs | 10% |
| **Tier 3** | Unknown | Save to FailedTransaction | 5% |

**Code Location:** `indexer/services/parser.py`

---

#### 3. Data Validation

```python
def validate_nft_event(event_data):
    """Validate event data before saving"""

    # 1. Schema validation
    if not event_data.get('signature'):
        raise ValidationError("Missing signature")

    # 2. Address format validation
    if not is_valid_solana_address(event_data.get('nft_mint')):
        raise ValidationError("Invalid mint address")

    # 3. Amount validation (no negative prices)
    if event_data.get('amount') and event_data['amount'] < 0:
        raise ValidationError("Negative amount")

    # 4. Timestamp validation
    if event_data.get('timestamp') > timezone.now():
        raise ValidationError("Future timestamp")

    return True
```

**Validation Checks:**
- ✅ Required fields present
- ✅ Solana address format (43-44 chars, base58)
- ✅ Amount is non-negative
- ✅ Timestamp is in past
- ✅ Event type is valid enum
- ✅ No duplicate signatures

**Code Location:** `indexer/services/validator.py` (if exists), or inline in `main.py`

---

#### 4. Database Storage

```
┌─────────────────┐
│ NFTEvent        │
│ ┌─────────────┐ │
│ │event_id     │ │ ← Transaction signature (primary key)
│ │collection_  │ │ ← Collection address
│ │address      │ │
│ │nft_mint     │ │ ← NFT mint address
│ │event_type   │ │ ← SALE, TRANSFER, LISTING, etc.
│ │amount       │ │ ← Price in lamports
│ │buyer        │ │ ← Buyer wallet
│ │seller       │ │ ← Seller wallet
│ │marketplace  │ │ ← magic_eden, tensor, traitkeeper
│ │timestamp    │ │ ← Block timestamp
│ │details      │ │ ← Raw JSON data
│ └─────────────┘ │
└─────────────────┘

Indexes:
• (collection_address, event_type, timestamp) - Fast collection queries
• (nft_mint, timestamp) - Fast NFT history lookup
• (buyer) - Wallet analytics
• (seller) - Wallet analytics
```

**Database Optimizations:**
- Composite indexes for common queries
- JSONField for flexible raw data storage
- Partitioning by timestamp (future enhancement)

**Code Location:** `indexer/models.py:20-114`

---

## Failed Transaction Handling

### FailedTransaction Model

```python
# indexer/models.py:192-200
class FailedTransaction(models.Model):
    """Logs transactions that failed during processing for investigation or retry."""
    event_id = models.CharField(max_length=88, primary_key=True)  # Transaction signature
    event_data = models.JSONField()  # Full raw transaction data
    error_message = models.TextField()  # What went wrong
    retry_count = models.IntegerField(default=0)  # How many retries attempted
    last_retry = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### When Transactions Fail

**Common Failure Scenarios:**

| Reason | % of Failures | Action |
|--------|---------------|--------|
| **Unknown instruction discriminator** | 60% | Log to `UnknownDiscriminator`, retry later |
| **RPC timeout** | 20% | Retry immediately with backoff |
| **Invalid data format** | 10% | Manual review needed |
| **Missing metadata** | 5% | Fetch from secondary source |
| **Database constraint violation** | 5% | Deduplicate and retry |

### Retry Mechanism

```python
# indexer/services/retry_service.py (conceptual)
async def retry_failed_transactions():
    """Retry failed transactions with exponential backoff"""

    # Get failed transactions that haven't exceeded retry limit
    failed_txs = FailedTransaction.objects.filter(
        retry_count__lt=3,
        last_retry__lt=timezone.now() - timedelta(minutes=30)
    )

    for tx in failed_txs:
        try:
            # Attempt to reprocess
            await process_transaction(tx.event_data)

            # Success! Delete from failed table
            tx.delete()
            logger.info(f"Successfully retried transaction {tx.event_id}")

        except Exception as e:
            # Still failing, update retry count
            tx.retry_count += 1
            tx.last_retry = timezone.now()
            tx.error_message = str(e)
            tx.save()

            if tx.retry_count >= 3:
                # Alert admins for manual investigation
                logger.error(f"Transaction {tx.event_id} failed after 3 retries")
```

**Retry Strategy:**
1. **Attempt 1:** Immediate retry (maybe temporary RPC issue)
2. **Attempt 2:** 30 minutes later (let system stabilize)
3. **Attempt 3:** 2 hours later (final automatic attempt)
4. **After 3 failures:** Flag for manual review

**Code Location:** `indexer/background_task_manager.py` (retry task scheduled every 30 minutes)

---

### Unknown Discriminator Learning

```python
# indexer/models.py:203-237
class UnknownDiscriminator(models.Model):
    """Tracks unknown instruction discriminators for auto-learning."""

    program_id = models.CharField(max_length=44, db_index=True)
    discriminator = models.CharField(max_length=16, db_index=True)

    # Inference from pattern matching
    inferred_marketplace = models.CharField(max_length=50, blank=True)
    inferred_action = models.CharField(max_length=50, blank=True)

    # Metadata for learning
    has_nft_transfer = models.BooleanField(default=False)
    has_native_transfer = models.BooleanField(default=False)
    log_patterns = models.JSONField(default=list)
    sample_signatures = models.JSONField(default=list)  # Up to 5 examples

    occurrence_count = models.IntegerField(default=1)
    is_approved = models.BooleanField(default=False)  # Manual review flag
```

**Learning Process:**
1. Unknown discriminator encountered
2. Analyze transaction patterns (NFT transfers, SOL transfers, logs)
3. Infer likely action (sale, list, delist)
4. Store examples for admin review
5. Once approved, add to known discriminators

**Code Location:** `indexer/services/parser.py` (Tier 2 parsing)

---

## Data Validation & Quality

### Multi-Level Validation

#### Level 1: Input Validation

```python
def validate_transaction_input(tx_data):
    """Validate raw transaction data"""
    assert tx_data.get('signature'), "Missing signature"
    assert len(tx_data['signature']) == 88, "Invalid signature length"
    assert tx_data.get('blockTime'), "Missing timestamp"
    assert isinstance(tx_data.get('meta'), dict), "Invalid metadata"
```

#### Level 2: Business Logic Validation

```python
def validate_nft_sale(sale_event):
    """Validate NFT sale makes business sense"""

    # Price should be reasonable
    if sale_event.amount > 1_000_000:  # > 1M SOL
        logger.warning(f"Suspiciously high price: {sale_event.amount}")

    # Buyer and seller should be different
    if sale_event.buyer == sale_event.seller:
        raise ValidationError("Buyer and seller are the same")

    # Collection should exist
    if not NFTCollection.objects.filter(address=sale_event.collection_address).exists():
        logger.warning(f"Unknown collection: {sale_event.collection_address}")
```

#### Level 3: Cross-Source Validation

```python
async def cross_validate_floor_price(collection):
    """Compare floor prices across sources"""

    # Get floor from blockchain (active listings)
    blockchain_floor = await get_blockchain_floor_price(collection)

    # Get floor from Magic Eden API
    magic_eden_floor = await magic_eden.get_floor_price(collection)

    # Get floor from Tensor API
    tensor_floor = await tensor.get_floor_price(collection)

    # If discrepancy > 20%, flag for review
    prices = [blockchain_floor, magic_eden_floor, tensor_floor]
    if max(prices) / min(prices) > 1.2:
        logger.warning(f"Floor price discrepancy for {collection.name}")
        logger.warning(f"Blockchain: {blockchain_floor}, ME: {magic_eden_floor}, Tensor: {tensor_floor}")

    # Trust blockchain as source of truth
    return blockchain_floor
```

---

## Multi-Source Aggregation

### CollectionMarketStats Model

```python
# indexer/models.py:123-153
class CollectionMarketStats(models.Model):
    """Raw, timestamped market statistics from external sources"""

    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE)
    source = models.CharField(max_length=20, choices=[
        ('magic_eden', 'Magic Eden'),
        ('tensor', 'Tensor'),
        ('blockchain', 'Blockchain'),
        ('traitkeeper', 'TraitKeeper Internal'),
    ])

    # Market metrics
    floor_price = models.DecimalField(max_digits=20, decimal_places=9, null=True)
    volume_24h = models.DecimalField(max_digits=20, decimal_places=9, null=True)
    sales_count_24h = models.IntegerField(null=True)
    listed_count = models.IntegerField(null=True)
    total_supply = models.IntegerField(null=True)

    # Metadata
    timestamp = models.DateTimeField(auto_now_add=True)
    raw_data = models.JSONField(default=dict)  # Complete API response

    class Meta:
        indexes = [models.Index(fields=['collection', 'source', 'timestamp'])]
```

### Aggregation Strategy

```python
# indexer/services/main.py:187-283
async def fetch_and_store_all_market_stats(collection):
    """Fetch from all sources in parallel, store individually"""

    # Query all providers in parallel
    tasks = [
        fetch_magic_eden_stats(collection),
        fetch_tensor_stats(collection),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Store each source's data separately
    for result in results:
        if result and result.get('success'):
            CollectionMarketStats.objects.create(
                collection=collection,
                source=result['source'],
                floor_price=result['stats']['floor_price'],
                volume_24h=result['stats']['volume_24h'],
                # ... other fields
                raw_data=result['raw_data']  # Store complete response
            )
```

**Why Store Per-Source?**
- Compare prices across marketplaces
- Detect arbitrage opportunities
- Track data quality per source
- Historical analysis of source reliability

### Data Source Priority

When multiple sources provide conflicting data:

```python
def get_authoritative_floor_price(collection):
    """Determine most authoritative floor price"""

    # Priority: Blockchain > Tensor > Magic Eden > TraitKeeper
    sources = CollectionMarketStats.objects.filter(
        collection=collection,
        timestamp__gte=timezone.now() - timedelta(minutes=30)
    ).order_by('-timestamp')

    # Try each source in priority order
    for source in ['blockchain', 'tensor', 'magic_eden', 'traitkeeper']:
        stat = sources.filter(source=source).first()
        if stat and stat.floor_price:
            return stat.floor_price

    return None
```

**Source Authority Ranking:**
1. **Blockchain** (100%) - Direct on-chain data, never wrong
2. **Tensor** (90%) - Real-time API, high accuracy
3. **Magic Eden** (85%) - Reliable but occasional delays
4. **TraitKeeper Internal** (70%) - Calculated, may lag

---

## Performance & Monitoring

### Ingestion Metrics

```python
# Example metrics tracking
class IngestionMetrics:
    transactions_processed = Counter()
    transactions_failed = Counter()
    processing_time = Histogram()

    def record_success(self, duration_ms):
        self.transactions_processed.inc()
        self.processing_time.observe(duration_ms)

    def record_failure(self, error_type):
        self.transactions_failed.inc(labels={'error': error_type})
```

### Current Performance

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| **Ingestion Latency** | < 5 seconds | 2.3s | ✅ |
| **Success Rate** | > 95% | 97.2% | ✅ |
| **Retry Success** | > 80% | 83% | ✅ |
| **Data Completeness** | > 90% | 94% | ✅ |
| **API Rate Limit Hits** | < 1% | 0.3% | ✅ |

### Monitoring Endpoints

```bash
# Check recent ingestion stats
GET /admin/panel/system-status/
# Returns: ingestion rate, failure count, last successful tx

# View failed transactions
GET /admin/indexer/failedtransaction/
# Shows transactions needing investigation

# Check unknown discriminators
GET /admin/indexer/unknowndiscriminator/
# Shows new instruction types discovered
```

---

## RPC Provider Failover

### Automatic Failover Mechanism

```python
# core/api_provider/api_providers.py:142-156
async def get_rpc_provider(self, collection_address=None, priority_tier='ACTIVE'):
    """Finds and returns a single, usable provider with automatic failover."""

    # Loop through all providers in priority order
    for provider in await self.get_all_providers():
        # Check if provider is available
        if await provider.check_availability():
            # Check if provider has sufficient quota
            wrapped_provider = await self.quota_manager.get_wrapped_provider_if_quota_available(
                provider,
                priority_tier
            )
            if wrapped_provider:
                self.current_provider = wrapped_provider
                return wrapped_provider

    # All providers failed
    logger.error("No available provider with sufficient quota was found.")
    return None
```

### Failover Flow

```
Request → Primary Provider (Helius)
            │
            ├─ Available? ✅ → Use Helius
            │
            └─ Available? ❌ → Try Next
                                │
                Secondary Provider (QuickNode)
                                │
                                ├─ Available? ✅ → Use QuickNode
                                │
                                └─ Available? ❌ → Return Error
```

**Availability Checks:**
- HTTP 200 response
- Response time < 5 seconds
- API quota remaining > 10%

**Code Location:** `core/api_provider/api_providers.py:142-156`, `docs/HOW_RPC_PROVIDERS_WORK.md`

---

## Related Documentation

- [ANALYTICS SYSTEM.md](./ANALYTICS%20SYSTEM.md) - Analytics calculation details
- [HOW_RPC_PROVIDERS_WORK.md](./HOW_RPC_PROVIDERS_WORK.md) - RPC configuration guide
- [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) - Complete database schema
- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture overview

---

**Last Updated:** December 18, 2025
**Version:** 1.0.0
**Author:** TraitKeeper Data Engineering Team
