# TraitKeeper Data Sources - Quick Reference for Data Scientists

## 🎯 Purpose
This document provides a clear understanding of TraitKeeper's data sources, helping data scientists identify:
- What data is **proprietary** (calculated by TraitKeeper)
- What data is **external** (aggregated from APIs)
- Which systems are **critical dependencies**
- How to handle data conflicts and prioritization

---

## 📊 Data Source Classification

### 1. TraitKeeper Proprietary Calculations (Your Platform = Source of Truth)

These are **calculated entirely by TraitKeeper** using our own algorithms and represent our intellectual property:

| Metric | Service | Description | Storage |
|--------|---------|-------------|---------|
| **Vitality Score** | VitalityCalculationService | 8-component health score (0-100) | `marketplace.NFTVitality` |
| **Trait Performance** | TraitAnalyticsService | Trait demand & pricing premium | `analytics.TraitPerformanceScore` |
| **Market Efficiency** | MarketAggregationService | Price discovery effectiveness | `analytics.AggregatedCollectionStats` |
| **Holder Confidence** | MarketAggregationService | Holder sentiment indicator | `analytics.AggregatedCollectionStats` |
| **Liquidity Health** | MarketAggregationService | Market liquidity quality | `analytics.AggregatedCollectionStats` |
| **Wallet Prominence** | WalletAnalyticsService | Holder quality score | `analytics.WalletBehaviorProfile` |
| **Sweep Detection** | SweepDetector | Whale activity identification | `analytics.CollectionSweepEvent` |
| **Rarity Rank** | TraitService | Statistical rarity calculation | `nft_data.TraitValue` |

**Key Point:** These metrics are NOT available from any external API. They are TraitKeeper's unique value proposition.

**Code Locations:**
- `marketplace/services/vitality_service.py` - Vitality calculations
- `analytics/services/` - All analytics services
- See [ANALYTICS SYSTEM.md](./ANALYTICS%20SYSTEM.md) for formulas

---

### 2. External Data (Aggregated from APIs)

These metrics come from **external sources** and are aggregated/validated by TraitKeeper:

| Metric | Primary Source | Backup Sources | Update Freq | Storage |
|--------|----------------|----------------|-------------|---------|
| **Floor Price** | Blockchain | Magic Eden, Tensor | Per priority tier | `indexer.CollectionMarketStats` |
| **24h Volume** | Blockchain (NFTEvent) | Magic Eden, Tensor | Real-time | `indexer.CollectionMarketStats` |
| **Listed Count** | Magic Eden, Tensor | Blockchain queries | Per priority tier | `indexer.CollectionMarketStats` |
| **Total Supply** | Blockchain | APIs (fallback) | Hourly | `nft_data.NFTCollection` |
| **Sales Count** | Blockchain (NFTEvent) | N/A | Real-time | `indexer.NFTEvent` |
| **NFT Metadata** | Blockchain | Helius API | On mint | `nft_data.NFT` |

**Key Point:** Always prefer blockchain data over API data when available.

**Code Locations:**
- `core/api_provider/magic_eden_provider.py`
- `core/api_provider/tensor_provider.py`
- `indexer/services/main.py:fetch_and_store_all_market_stats()`

---

## 🔗 System Dependencies

### Critical (Cannot function without)

```
1. Solana RPC Provider (Helius or QuickNode)
   └─ Purpose: Blockchain data ingestion
   └─ Failover: YES (automatic)
   └─ Config: Admin Panel → Primary Provider Settings

2. PostgreSQL Database
   └─ Purpose: All data storage
   └─ Failover: NO (single instance)
   └─ Backup: Daily automated backups

3. Redis Cache
   └─ Purpose: Performance optimization
   └─ Failover: NO (degrades to slower DB queries)
   └─ Impact if down: 3-5x slower responses
```

### Important (Enhances data quality)

```
4. Magic Eden API
   └─ Purpose: Marketplace floor prices & listings
   └─ Failover: YES (use Tensor or blockchain)
   └─ Rate Limit: 15 req/min

5. Tensor API
   └─ Purpose: Market analytics & UUIDs
   └─ Failover: YES (use Magic Eden or blockchain)
   └─ Rate Limit: 1 req/sec
```

### Optional (Future features)

```
6. Twitter API - Sentiment analysis (Perception Index component)
7. Discord API - Community engagement metrics
8. CoinGecko API - SOL/USD price conversions
```

---

## 🚨 RPC Failover Mechanism

**YES, RPC failover is active and working!**

### How It Works

```python
# core/api_provider/api_providers.py:142-156
async def get_rpc_provider(self, priority_tier='ACTIVE'):
    """Automatic failover to next available provider"""

    # Try each provider in priority order
    for provider in await self.get_all_providers():
        if await provider.check_availability():
            if provider.has_quota(priority_tier):
                return provider  # ✅ Use this provider

    # All providers failed
    return None  # ❌ No providers available
```

### Failover Flow

```
Request
  │
  ├─→ Try Primary (Helius)
  │     ├─ Available? → ✅ Use it
  │     └─ Failed? → ❌ Next
  │
  └─→ Try Secondary (QuickNode)
        ├─ Available? → ✅ Use it
        └─ Failed? → ❌ Error
```

**Checks Performed:**
- HTTP 200 response
- Response time < 5 seconds
- API quota remaining > 10%

**Verification:**
```bash
# Check current provider
docker-compose logs data | grep "provider"
# Should show: "Using provider: helius" or "Failover to: quicknode"
```

**Documentation:** See [HOW_RPC_PROVIDERS_WORK.md](./HOW_RPC_PROVIDERS_WORK.md)

---

## 📈 Data Priority Rules

### When multiple sources conflict:

```
Priority Order:
1. Blockchain (100% trust) - Always correct
2. Tensor (90% trust) - Real-time API
3. Magic Eden (85% trust) - Reliable but may lag
4. TraitKeeper Calculated (70% trust) - Estimate when no external data
```

### Example: Determining Floor Price

```python
def get_authoritative_floor_price(collection):
    """Priority-based floor price resolution"""

    # 1. Check blockchain (active NFTListing records)
    blockchain_floor = NFTListing.objects.filter(
        nft__collection=collection,
        status='ACTIVE'
    ).aggregate(Min('price'))['price__min']

    if blockchain_floor:
        return blockchain_floor  # ✅ Trust blockchain

    # 2. Check Tensor API (recent fetch)
    tensor_stats = CollectionMarketStats.objects.filter(
        collection=collection,
        source='tensor',
        timestamp__gte=timezone.now() - timedelta(minutes=30)
    ).first()

    if tensor_stats and tensor_stats.floor_price:
        return tensor_stats.floor_price  # ✅ Trust Tensor

    # 3. Check Magic Eden API
    magic_eden_stats = CollectionMarketStats.objects.filter(
        collection=collection,
        source='magic_eden',
        timestamp__gte=timezone.now() - timedelta(minutes=30)
    ).first()

    if magic_eden_stats and magic_eden_stats.floor_price:
        return magic_eden_stats.floor_price  # ✅ Trust Magic Eden

    # 4. Use TraitKeeper estimate (last resort)
    return calculate_estimated_floor(collection)  # ⚠️ Estimate only
```

**Code Location:** `analytics/services/aggregation_service.py`

---

## 🔄 Data Update Frequencies

### Priority-Based Updates

| Collection Tier | Vitality | Market Stats | Blockchain Events |
|----------------|----------|--------------|-------------------|
| **VIP** | Every 15 min | Every 15 min | Real-time |
| **ACTIVE** | Every 1 hour | Every 1 hour | Real-time |
| **INACTIVE** | Every 4 hours | Every 4 hours | Real-time |

**Note:** Blockchain events are ALWAYS real-time regardless of collection tier.

**Code Location:** `indexer/background_task_manager.py`

---

## 💡 Aggregated Data Indicators (Frontend)

**Implemented Enhancement:**

Visual indicators mark aggregated data (floor price, volume) across the frontend to show users that the data comes from multiple sources.

### Visual Result:

```
Before:
Floor: 2.34 SOL

After:
Floor: 2.34 SOL ⓘ
       └─ [Tooltip: Aggregated from Magic Eden, Tensor & Blockchain]

Footer:
SOL: $98.45 | TPS: 3,542 | ⓘ Aggregated Data | Support
```

### Implementation:
- ⓘ icon next to all aggregated metrics (floor, volume, listed count)
- Tooltip on hover: "Aggregated from Magic Eden, Tensor & Blockchain"
- Footer legend explains what the icon means
- Responsive (desktop + mobile)
- Dark mode support

### Files:
- CSS: `static/css/data-source-indicator.css` ✅ Created
- Component: `templates/index page/components/data_indicator.html` 🔨 To create
- Guide: [IMPLEMENTATION_AGGREGATED_DATA_INDICATORS.md](./IMPLEMENTATION_AGGREGATED_DATA_INDICATORS.md) ✅

### Status:
📝 CSS Ready | 📋 Implementation Pending (see guide above)

---

## 📖 Complete Documentation

### For Data Scientists:
1. **[DATA_INGESTION.md](./DATA_INGESTION.md)** - How data enters the system
2. **[ANALYTICS SYSTEM.md](./ANALYTICS%20SYSTEM.md)** - How analytics are calculated
3. **[DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)** - Database structure

### For Developers:
4. **[ARCHITECTURE.md](./ARCHITECTURE.md)** - System architecture
5. **[HOW_RPC_PROVIDERS_WORK.md](./HOW_RPC_PROVIDERS_WORK.md)** - RPC configuration

### For Operations:
6. **[CACHING_STRATEGY.md](./CACHING_STRATEGY.md)** - Performance optimization

---

## 🎓 Quick Answers

**Q: Is market stats data from Magic Eden or TraitKeeper?**
A: Both! Magic Eden provides raw data, TraitKeeper aggregates and validates it.

**Q: What if Magic Eden API goes down?**
A: Automatic failover to Tensor API, then blockchain data.

**Q: Can I trust the floor prices shown?**
A: Yes, floor prices are validated across 3 sources (blockchain > Tensor > Magic Eden).

**Q: What happens if RPC provider fails?**
A: Automatic failover to backup provider (Helius → QuickNode).

**Q: How do I know which data is "real-time"?**
A: Blockchain events = real-time, API data = per priority tier (15min to 4hr).

**Q: Where is failed transaction data stored?**
A: `indexer.FailedTransaction` model - includes retry logic and error messages.

---

**Last Updated:** December 18, 2025
**Version:** 1.0.0
**Author:** TraitKeeper Data Team
