# TraitKeeper Indexing Architecture

## Overview

TraitKeeper uses a **3-tier indexing system** to collect NFT data efficiently:

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA COLLECTION LAYER                         │
└─────────────────────────────────────────────────────────────────┘

1. LIVE INDEXER (Webhook) - Real-time              🔴 PRIMARY
   ├─ Source: QuickNode/Helius webhook
   ├─ Frequency: Real-time (milliseconds)
   ├─ Data: NFT transactions as they happen
   └─ Service: indexer-live

2. MARKET STATS UPDATER - Every 5 minutes          💹 CONTINUOUS
   ├─ Source: Magic Eden & Tensor APIs
   ├─ Frequency: Every 5 minutes
   ├─ Data: Floor price, volume, sales count
   ├─ Speed: ~10 seconds per run
   └─ Service: indexer-scheduled

3. INCREMENTAL INDEXER - Every 4 hours             🔄 BACKUP
   ├─ Source: Blockchain RPC (QuickNode)
   ├─ Frequency: Every 4 hours
   ├─ Data: Last 24 hours of transactions only
   ├─ Purpose: Catches any transactions missed by webhook
   ├─ Limit: Max 100 transactions (not 1000!)
   └─ Service: indexer-incremental
```

## When to Use Each Service

### 1. Live Indexer (Webhook)
**When:** Always running in production
**Purpose:** Primary data source for real-time NFT events
**Use Case:** Capture sales, listings, bids as they happen

### 2. Market Stats Updater
**When:** Always running in production
**Purpose:** Keep frontend market data fresh (updates every 5 minutes)
**Use Case:** Display current floor prices, volumes on website

### 3. Incremental Indexer
**When:** Always running in production
**Purpose:** Safety net for missed transactions
**Use Case:** Webhook fails, API downtime, network issues

### 4. Historical Backfill (MANUAL OR AUTO)
**When:** One-time setup or adding new collection
**Purpose:** Load ALL historical data from blockchain (collection creation to present)
**Command:** `python manage.py backfill_collection <address>`
**Auto-trigger:** Runs automatically when new collection is added via admin
**Note:** Fetches COMPLETE history using pagination, not just 1000 transactions
**Warning:** Do NOT run periodically - very expensive and time-consuming!

## Data Flow

```
┌─────────────┐
│ Blockchain  │
└──────┬──────┘
       │
       ├──────────────────┐
       │                  │
       ▼                  ▼
  ┌─────────┐      ┌──────────────┐
  │ Webhook │      │ Incremental  │
  │ (Live)  │      │ (Every 4h)   │
  └────┬────┘      └──────┬───────┘
       │                  │
       │                  │
       ▼                  ▼
  ┌────────────────────────────┐
  │   Transaction Parser       │
  │   (Multi-tier system)      │
  └─────────────┬──────────────┘
                │
                ▼
       ┌────────────────┐
       │  NFTEvent DB   │
       └────────────────┘

┌──────────────────┐
│ Marketplace APIs │
│ (ME/Tensor)      │
└────────┬─────────┘
         │
         ▼
  ┌─────────────────┐
  │  Market Stats   │
  │  (Every 15 min) │
  └────────┬────────┘
           │
           ▼
  ┌──────────────────────┐
  │ CollectionMarketStats│
  │ (DB)                 │
  └──────────────────────┘
```

## Service Configuration

### Docker Compose Services

```yaml
# Live events from webhook
indexer-live:
  command: python manage.py run_live_indexer

# Market stats updates
indexer-scheduled:
  command: python manage.py run_scheduled_indexer

# Transaction catch-up
indexer-incremental:
  command: python manage.py run_incremental_indexer
```

### Monitoring

All services include health checks:
```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f indexer-live
docker-compose logs -f indexer-scheduled
docker-compose logs -f indexer-incremental
```

## RPC Credit Usage

### Estimated Daily RPC Calls (2 collections):

| Service | Frequency | Calls/Run | Daily Total |
|---------|-----------|-----------|-------------|
| Live Indexer | Real-time | Variable | ~1,000-5,000 |
| Market Stats | 5 min (288x/day) | 4 API calls | 1,152 calls |
| Incremental | 4 hours (6x/day) | ~200 RPC | 1,200 calls |
| **TOTAL** | | | **~3,300-7,400/day** |

### Previous (Broken) Setup:
- Scheduled indexer fetching 1000 transactions every 15 minutes
- = 96 runs × 2,000 RPC calls = **192,000 calls/day** 💸💸💸
- Would burn through credits in days!

## Troubleshooting

### Market stats not updating?
```bash
# Check if scheduler is running
docker-compose logs indexer-scheduled | grep "Completed scheduled indexing"

# Manual trigger
docker-compose exec main python manage.py fetch_market_stats_now
```

### Missing recent transactions?
```bash
# Check incremental indexer
docker-compose logs indexer-incremental | grep "recent transactions"

# Check webhook
docker-compose logs indexer-live | tail -50
```

### Webhook not receiving events?
1. Check QuickNode stream status in dashboard
2. Verify webhook URL: `https://traitkeeper.xyz/indexer/webhook/`
3. Check recent webhook logs:
   ```bash
   docker-compose logs main | grep "Webhook"
   ```

## Adding New Collections

When adding a new collection:

1. Add to database (via admin or API)
2. Run ONE-TIME historical backfill (if needed):
   ```bash
   # NOT IMPLEMENTED YET - use manual script
   ```
3. Services automatically pick it up:
   - Live indexer: Starts receiving webhook events
   - Market stats: Includes in next 15-min run
   - Incremental: Includes in next 4-hour run

## Performance Optimization

### Current Settings (Optimized):
- Market stats: 5 minutes (fast API calls)
- Incremental: 4 hours, last 24h only (light RPC usage)
- Stagger delay: 2-5 seconds between collections

### If You Need to Adjust:
- **More frequent stats:** Change `asyncio.sleep(300)` in `run_scheduled_indexer.py`
- **Longer catch-up window:** Change `timedelta(hours=24)` in `run_incremental_indexer.py`
- **More aggressive catching:** Change `limit=100` to higher value (costs more RPC)

## Summary

✅ **Efficient:** Three specialized services, each doing one thing well
✅ **Reliable:** Multiple layers ensure no data is missed
✅ **Cost-effective:** Optimized RPC usage (2,500-6,500 calls/day vs 192,000)
✅ **Fast:** Market stats update every 15 minutes
✅ **Real-time:** Webhook provides instant transaction updates

---

**Last Updated:** December 20, 2025
**Version:** 2.0 (3-tier architecture)
