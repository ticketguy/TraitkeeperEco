# Parallel Lines Integration - TraitKeeper's World Perception Engine

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Data Models](#data-models)
4. [Webhook Integration](#webhook-integration)
5. [Vitality System Integration](#vitality-system-integration)
6. [Configuration](#configuration)
7. [API Reference](#api-reference)
8. [Admin Interface](#admin-interface)
9. [Testing](#testing)
10. [Deployment](#deployment)

---

## Overview

**Parallel Lines** is TraitKeeper's **world perception engine** - an LLM-based sentiment analysis system that analyzes community perception, behavioral patterns, and sentiment across multiple platforms at global scale.

### Why Parallel Lines?

Traditional NFT metrics (floor price, volume) are easily manipulated through wash trading and artificial activity. Parallel Lines provides **anti-gaming perception analysis** by:

- **LLM-based analysis** that understands context, sarcasm, and genuine vs. paid sentiment
- **Multi-platform aggregation** (Twitter, Discord, Reddit, on-chain signals)
- **Behavioral pattern detection** for bot activity, coordinated shilling, wash trading
- **Subconscious signal analysis** that captures hidden market sentiment

### System Philosophy: Submind + IntuOne

Parallel Lines operates on a dual-layer architecture representing the **duality of digital awareness**:

```
┌─────────────────────────────────────────────────┐
│         PARALLEL LINES ARCHITECTURE             │
│                                                 │
│  ┌───────────────────────────────────────┐    │
│  │  Submind Layer (Silent Observer)      │    │
│  │  • Subconscious perception signals    │    │
│  │  • Hidden behavioral patterns         │    │
│  │  • Unseen social dynamics             │    │
│  │  • Raw language signals               │    │
│  └───────────────┬───────────────────────┘    │
│                  │                              │
│                  ▼                              │
│  ┌───────────────────────────────────────┐    │
│  │  IntuOne Layer (Expressive Interpreter)│    │
│  │  • Emotional resonance translation    │    │
│  │  • Language tone structuring          │    │
│  │  • Perception Graph generation        │    │
│  │  • Perception Index scoring (0-1)     │    │
│  └───────────────┬───────────────────────┘    │
│                  │                              │
└──────────────────┼──────────────────────────────┘
                   │
                   │ (Real-time Webhooks / API)
                   │
                   ▼
        ┌──────────────────────┐
        │    TRAITKEEPER       │
        │  Perception Index    │
        │  (20% of Vitality)   │
        └──────────────────────┘
```

**Submind**: The silent observer that captures raw, unstructured perception signals below the surface of awareness.

**IntuOne**: The expressive interpreter that translates raw emotional resonance into structured, actionable perception data.

Together, they create the **Perception Graph** - a dynamic topology of community awareness.

---

## Architecture

### System Components

#### 1. Data Models (`marketplace/perception_models.py`)

**Core Models:**
- `PerceptionSnapshot` - Timestamped perception data at various granularities
- `PerceptionGraphNode` - Nodes in the perception topology
- `PerceptionGraphEdge` - Relationships between perception nodes
- `PerceptionAggregation` - Pre-computed rollups for performance
- `ParallelLinesWebhookLog` - Audit trail of webhook calls

**Granularity Support:**
- **Collection-level**: "DeGods community sentiment"
- **NFT-level**: "DeGods #4321 holder perception"
- **Trait-level**: "Blue Background trait demand signals"

#### 2. Integration Service (`marketplace/perception_service.py`)

**ParallelLinesIntegrationService** provides:
- `process_webhook()` - Receive and validate Parallel Lines data
- `get_perception_index()` - Retrieve perception scores for vitality calculations
- `get_perception_trend()` - Analyze perception changes over time
- Anti-gaming logic (manipulation probability dampening)

#### 3. Webhook Endpoint (`marketplace/views.py`)

**Endpoint:** `POST /api/perception/webhook`

Receives real-time perception updates from Parallel Lines.

#### 4. Vitality Integration (`marketplace/vitality_service.py`)

The Perception Index feeds into the **20% Perception Index component** of the NFT Vitality Score.

---

## Data Models

### PerceptionSnapshot

Stores timestamped perception data from Parallel Lines.

**Key Fields:**

```python
class PerceptionSnapshot(models.Model):
    # Entity (polymorphic - one of these will be set)
    collection = ForeignKey(NFTCollection, ...)
    nft = ForeignKey(NFT, ...)
    trait_value = ForeignKey(TraitValue, ...)

    # Core Perception Metrics
    perception_index = FloatField(0-1)  # Final score from IntuOne

    # Submind Layer Outputs
    submind_raw_score = FloatField(0-1)
    submind_hidden_sentiment = CharField()  # "positive", "negative", etc.
    manipulation_probability = FloatField(0-1)  # Anti-gaming metric
    behavioral_pattern_flags = JSONField()  # Bot activity, wash trading, etc.

    # IntuOne Layer Outputs
    emotional_resonance = FloatField(0-1)
    language_tone = CharField()  # "enthusiastic", "cautious", etc.
    community_awareness_score = FloatField(0-1)

    # Perception Graph Reference
    perception_graph_id = CharField()

    # Data Quality
    confidence_score = FloatField(0-1)
    data_sources = JSONField()  # ["twitter", "discord", "reddit"]
    sample_size = IntegerField()

    # Timestamps
    timestamp = DateTimeField()  # When Parallel Lines measured this
    received_at = DateTimeField()  # When TraitKeeper received it

    # Source Tracking
    source_type = CharField()  # WEBHOOK, API_POLL, MANUAL, BACKFILL
    raw_payload = JSONField()  # Full payload for audit
```

**Properties:**
- `entity_type` - Returns "collection", "nft", or "trait"
- `entity` - Returns the actual entity object
- `is_recent` - True if within last 24 hours
- `anti_gaming_flags` - Extracts bot activity, wash trading signals

**Indexes:**
- (`collection`, `-timestamp`)
- (`nft`, `-timestamp`)
- (`trait_value`, `-timestamp`)
- (`perception_graph_id`, `-timestamp`)
- (`-timestamp`, `perception_index`)

**Constraints:**
- Exactly one of `collection`, `nft`, or `trait_value` must be set (XOR constraint)

---

### PerceptionGraphNode

Stores nodes in the Perception Graph topology.

**Key Fields:**

```python
class PerceptionGraphNode(models.Model):
    graph_id = CharField()  # ID of the perception graph
    node_id = CharField()  # Unique node identifier
    node_type = CharField()  # "user", "topic", "community", "hashtag", etc.
    label = CharField()  # Human-readable label
    influence_score = FloatField(0-1)
    sentiment = CharField()
    metadata = JSONField()
```

**Unique Together:** `['graph_id', 'node_id']`

---

### PerceptionGraphEdge

Stores relationships in the Perception Graph.

**Key Fields:**

```python
class PerceptionGraphEdge(models.Model):
    graph_id = CharField()
    source_node = ForeignKey(PerceptionGraphNode)
    target_node = ForeignKey(PerceptionGraphNode)
    edge_type = CharField()  # "mentions", "endorses", "criticizes", etc.
    weight = FloatField()
    sentiment = CharField()
    metadata = JSONField()
```

**Example:** `@NFTInfluencer --[endorses]--> DeGodsCollection`

---

### PerceptionAggregation

Pre-computed aggregated metrics for performance.

**Aggregation Periods:**
- HOURLY
- DAILY
- WEEKLY
- MONTHLY

**Metrics:**
- `avg_perception_index`
- `min_perception_index`
- `max_perception_index`
- `perception_volatility` (standard deviation)
- `avg_manipulation_probability`
- `sample_count`

**Use Cases:**
- Historical trend charts
- Volatility analysis
- Performance optimization for queries

---

### ParallelLinesWebhookLog

Audit log of all webhook calls from Parallel Lines.

**Status Values:**
- `SUCCESS` - Successfully processed
- `FAILED` - Processing failed
- `VALIDATION_ERROR` - Invalid payload
- `AUTH_ERROR` - Authentication failed
- `DUPLICATE` - Duplicate data ignored

**Metrics:**
- `processing_time_ms` - Performance monitoring
- `snapshots_created` - Number of records created
- `error_message` - Debug information

---

## Webhook Integration

### Endpoint

**URL:** `POST /api/perception/webhook`

**Authentication:** Multiple methods supported (configurable in settings)
- HMAC signature verification (recommended for production)
- API key validation
- IP whitelist
- Development mode (bypass auth - unsafe!)

### Webhook Payload Structure

```json
{
  "entity_type": "collection",  // or "nft" or "trait"
  "entity_id": "DeGods_collection_address",

  "perception_data": {
    "perception_index": 0.78,  // Final score (0-1)
    "timestamp": "2025-01-08T12:34:56Z",

    "submind": {
      "raw_score": 0.72,
      "hidden_sentiment": "positive",
      "manipulation_probability": 0.12,
      "behavioral_patterns": {
        "bot_activity": false,
        "wash_trading_influence": 0.08,
        "coordinated_shilling": false
      }
    },

    "intuone": {
      "emotional_resonance": 0.85,
      "language_tone": "enthusiastic",
      "community_awareness": 0.76
    },

    "perception_graph_id": "graph_123",
    "confidence": 0.95,
    "data_sources": ["twitter", "discord", "reddit"],
    "sample_size": 5420
  },

  "perception_graph": {  // Optional
    "nodes": [
      {
        "id": "node_1",
        "type": "influencer",
        "label": "@CryptoWhale",
        "influence": 0.92,
        "sentiment": "positive",
        "metadata": {...}
      },
      ...
    ],
    "edges": [
      {
        "source": "node_1",
        "target": "node_2",
        "type": "mentions",
        "weight": 0.8,
        "sentiment": "positive",
        "metadata": {...}
      },
      ...
    ]
  }
}
```

### Response Format

**Success (200 OK):**
```json
{
  "success": true,
  "message": "Success",
  "perception_index": 0.78,
  "entity_type": "collection"
}
```

**Error (400/401/500):**
```json
{
  "success": false,
  "error": "Error message"
}
```

### Webhook Processing Flow

```
1. Receive webhook POST request
2. Extract payload and headers
3. Authenticate request (HMAC/API key/IP whitelist)
4. Validate payload structure
5. Resolve entity (collection/NFT/trait) from entity_id
6. Create PerceptionSnapshot record
7. Process Perception Graph (if included)
8. Log webhook call to ParallelLinesWebhookLog
9. Invalidate perception cache for entity
10. Return response
```

**Processing Time:** Target < 500ms

---

## Vitality System Integration

### Perception Index Component (20% Weight)

The Perception Index is one of 8 components in the NFT Vitality Score:

```python
Vitality Score =
    (Perception Index × 0.20) +
    (Trait Performance × 0.20) +
    (Collection Health × 0.15) +
    (Collection Utility × 0.10) +
    (Market Momentum × 0.10) +
    (Rarity Score × 0.10) +
    (Holder Quality × 0.10) +
    (Market Influence × 0.05)
```

### Calculation Logic

**Location:** `marketplace/vitality_service.py:512-572`

```python
async def _calculate_perception_index(self, nft: NFT) -> float:
    # Get collection-level perception (primary signal)
    collection_perception = await perception_service.get_perception_index(
        entity=nft.collection,
        entity_type='collection'
    )

    # Get NFT-level perception (if available)
    nft_perception = await perception_service.get_perception_index(
        entity=nft,
        entity_type='nft'
    )

    # Combine: Collection (70%) + NFT-specific (30%)
    perception_index = (collection_perception * 0.7) + (nft_perception * 0.3)

    return perception_index
```

### Anti-Gaming Logic

**Manipulation Dampening:**

If a PerceptionSnapshot has `manipulation_probability > 0.7`, the score is dampened towards neutral (0.5):

```python
if manipulation_probability > 0.7:
    dampening_factor = manipulation_probability * 0.5
    perception_index = perception_index * (1 - dampening_factor) + 0.5 * dampening_factor
```

**Example:**
- Raw perception: 0.9 (very positive)
- Manipulation probability: 0.8 (suspicious!)
- Dampening factor: 0.8 * 0.5 = 0.4
- Adjusted perception: `0.9 * 0.6 + 0.5 * 0.4 = 0.74`

This prevents artificially inflated sentiment from manipulating vitality scores.

### Caching Strategy

- **Cache TTL:** 5 minutes (300 seconds)
- **Cache Key:** `perception_index:{entity_type}:{entity_id}`
- **Invalidation:** On new webhook data received

### Fallback Logic

If no Parallel Lines data exists:
- **Default:** 0.5 (neutral)
- **Behavior:** Vitality calculation continues with neutral perception
- **Impact:** 20% of vitality score = 10 points (on 0-100 scale)

---

## Configuration

### Settings Required

Add to `settings.py` or environment variables:

```python
# ==========================================
# PARALLEL LINES INTEGRATION SETTINGS
# ==========================================

# Authentication Method 1: HMAC Signature (Recommended)
PARALLEL_LINES_WEBHOOK_SECRET = 'your-secret-key-here'

# Authentication Method 2: API Key
PARALLEL_LINES_API_KEY = 'your-api-key-here'

# Development Mode (UNSAFE - bypasses auth)
PARALLEL_LINES_DEV_MODE = False  # Set to True only in development

# Perception Data Settings
PERCEPTION_CACHE_TTL_SECONDS = 300  # 5 minutes
PERCEPTION_STALENESS_THRESHOLD_HOURS = 24  # Data older than 24h is stale
DEFAULT_PERCEPTION_INDEX = 0.5  # Neutral score when no data available
```

### HMAC Authentication Setup

**Parallel Lines Side:**
```python
import hmac
import hashlib
import json

payload = {...}  # Webhook payload
secret = "your-secret-key-here"

signature = hmac.new(
    secret.encode(),
    json.dumps(payload, sort_keys=True).encode(),
    hashlib.sha256
).hexdigest()

headers = {
    'X-Parallel-Lines-Signature': signature,
    'Content-Type': 'application/json'
}

requests.post('https://traitkeeper.com/api/perception/webhook', json=payload, headers=headers)
```

**TraitKeeper Side:**
Automatically validates signature in `perception_service.py:_authenticate_webhook()`

---

## API Reference

### Webhook Endpoint

**POST /api/perception/webhook**

Receives perception data from Parallel Lines.

**Authentication:** HMAC signature or API key

**Request Body:** See [Webhook Payload Structure](#webhook-payload-structure)

**Response:** See [Response Format](#response-format)

---

### Query Endpoints (TODO)

These endpoints will be added for querying perception data:

**GET /api/perception/collection/{address}**
- Get latest perception index for a collection
- Optional: `?history=true` for 30-day trend

**GET /api/perception/nft/{mint_address}**
- Get latest perception index for an NFT
- Includes collection-level context

**GET /api/perception/trait/{trait_id}**
- Get perception data for a specific trait

**GET /api/perception/trends**
- Get perception trends across multiple collections
- Query params: `collections=addr1,addr2&period=7d`

---

## Admin Interface

### Access

Django Admin → Marketplace → Perception Models

### Available Views

**1. Perception Snapshots**
- List view with color-coded perception scores
- Filter by entity type, source, timestamp, sentiment
- Manipulation risk warnings
- Expandable raw payload for debugging

**2. Perception Graph Nodes**
- View nodes by graph ID, type, influence score
- Search by label or node ID

**3. Perception Graph Edges**
- View relationships between nodes
- Filter by edge type, sentiment

**4. Perception Aggregations**
- Pre-computed rollups (hourly, daily, weekly, monthly)
- Volatility analysis
- Sample counts for data quality

**5. Webhook Logs**
- Monitor all incoming webhooks
- Processing time metrics
- Error debugging
- Retry failed webhooks (coming soon)

### Admin Actions

- **Mark as inactive** (for perception snapshots)
- **Retry failed webhooks** (webhook logs)
- **Export to CSV** (all models)

---

## Testing

### Mock Webhook Data

Use this to test the integration before Parallel Lines is live:

```python
# test_parallel_lines_integration.py

import requests
import hmac
import hashlib
import json
from datetime import datetime

# Test payload
payload = {
    "entity_type": "collection",
    "entity_id": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # DeGods

    "perception_data": {
        "perception_index": 0.78,
        "timestamp": datetime.utcnow().isoformat() + "Z",

        "submind": {
            "raw_score": 0.72,
            "hidden_sentiment": "positive",
            "manipulation_probability": 0.12,
            "behavioral_patterns": {
                "bot_activity": False,
                "wash_trading_influence": 0.08,
                "coordinated_shilling": False
            }
        },

        "intuone": {
            "emotional_resonance": 0.85,
            "language_tone": "enthusiastic",
            "community_awareness": 0.76
        },

        "perception_graph_id": "test_graph_123",
        "confidence": 0.95,
        "data_sources": ["twitter", "discord"],
        "sample_size": 5420
    }
}

# Generate HMAC signature
secret = "your-secret-key-here"
signature = hmac.new(
    secret.encode(),
    json.dumps(payload, sort_keys=True).encode(),
    hashlib.sha256
).hexdigest()

# Send webhook
response = requests.post(
    'http://localhost:8000/api/perception/webhook',
    json=payload,
    headers={
        'X-Parallel-Lines-Signature': signature,
        'Content-Type': 'application/json'
    }
)

print(response.status_code)
print(response.json())
```

### Verification Steps

1. **Send mock webhook** → Check response is 200 OK
2. **Check Django Admin** → Perception Snapshots should show new entry
3. **Check Webhook Log** → Status should be SUCCESS
4. **Trigger vitality calculation** → Perception index should be used
5. **Check caching** → Second request should hit cache

---

## Deployment

### Pre-Deployment Checklist

- [ ] Add `PARALLEL_LINES_WEBHOOK_SECRET` to production environment
- [ ] Set `PARALLEL_LINES_DEV_MODE = False`
- [ ] Run database migrations: `python manage.py migrate marketplace`
- [ ] Test webhook endpoint with mock data
- [ ] Verify HMAC authentication works
- [ ] Check admin interface accessibility
- [ ] Monitor webhook logs for errors
- [ ] Set up alerts for failed webhooks

### Database Migrations

```bash
# Create migrations
python manage.py makemigrations marketplace --name add_perception_models

# Apply migrations
python manage.py migrate marketplace

# Verify migration
python manage.py showmigrations marketplace
```

### Monitoring

**Key Metrics to Monitor:**

1. **Webhook Success Rate**
   - Target: > 99%
   - Alert if < 95%

2. **Processing Time**
   - Target: < 500ms
   - Alert if > 2000ms

3. **Perception Data Freshness**
   - Alert if no data received for > 1 hour (for active collections)

4. **Manipulation Probability Distribution**
   - Monitor average manipulation probability
   - Alert if sudden spike

### Performance Optimization

**Indexes:**
- All perception models have optimized indexes
- Query performance: < 50ms for latest perception lookup

**Caching:**
- 5-minute TTL for perception scores
- Cache hit rate target: > 85%

**Database:**
- Partition PerceptionSnapshot by timestamp (monthly)
- Archive data older than 6 months to cold storage

---

## Appendix

### Related Documentation

- [VITALITY_SYSTEM.md](./VITALITY_SYSTEM.md) - NFT Vitality Score algorithm
- [ARCHITECTURE.md](./ARCHITECTURE.md) - TraitKeeper system architecture
- [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md) - Database schema details

### Changelog

**v1.0.0 (January 2025)**
- Initial Parallel Lines integration
- Perception Index (20% weight) in Vitality Score
- Multi-granularity support (collection, NFT, trait)
- Anti-gaming logic with manipulation dampening
- Real-time webhook integration
- Perception Graph topology storage

### Future Enhancements

- [ ] Query API endpoints for perception data
- [ ] Perception trend charts in UI
- [ ] Trait-level perception analysis UI
- [ ] Perception Graph visualization
- [ ] ML-based manipulation detection
- [ ] Historical perception playback
- [ ] Cross-collection perception correlation
- [ ] Automated perception-based alerts

---

**Last Updated:** January 2025
**Version:** 1.0.0
**Integration Status:** Ready for Parallel Lines connection
**Author:** TraitKeeper Development Team
