# Parallel Lines → TraitKeeper Webhook Specification

## Overview

This document specifies the exact format for sending perception data from Parallel Lines (your LLM world perception engine) to TraitKeeper's vitality system.

**Endpoint:** `POST https://traitkeeper.com/api/perception/webhook`

**Authentication:** HMAC-SHA256 signature (recommended) or API key

**Content-Type:** `application/json`

---

## Quick Reference

### Minimal Required Payload

```json
{
  "entity_type": "collection",
  "entity_id": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
  "perception_data": {
    "perception_index": 0.78,
    "timestamp": "2025-01-08T12:34:56Z"
  }
}
```

### Full Payload with All Fields

```json
{
  "entity_type": "collection",
  "entity_id": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",

  "perception_data": {
    "perception_index": 0.78,
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

  "perception_graph": {
    "nodes": [...],
    "edges": [...]
  }
}
```

---

## Field Specifications

### Root Level Fields

| Field | Type | Required | Values | Description |
|-------|------|----------|--------|-------------|
| `entity_type` | string | **Yes** | `"collection"`, `"nft"`, `"trait"` | What type of entity this perception is for |
| `entity_id` | string | **Yes** | Solana address or ID | Identifier for the entity |
| `perception_data` | object | **Yes** | - | Container for all perception metrics |
| `perception_graph` | object | No | - | Optional graph topology data |

---

### perception_data Object

#### Required Fields

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `perception_index` | float | 0.0 - 1.0 | **Final perception score from IntuOne layer** |
| `timestamp` | string | ISO 8601 | When Parallel Lines measured this (UTC) |

**Example:**
```json
"perception_data": {
  "perception_index": 0.82,
  "timestamp": "2025-01-08T14:23:11Z"
}
```

#### Optional: Submind Layer Fields

Submind is the "silent observer" that captures subconscious perception signals.

| Field | Type | Range/Format | Description |
|-------|------|--------------|-------------|
| `submind.raw_score` | float | 0.0 - 1.0 | Raw behavioral score (unfiltered) |
| `submind.hidden_sentiment` | string | `"positive"`, `"negative"`, `"neutral"`, `"mixed"` | Detected sentiment below surface |
| `submind.manipulation_probability` | float | 0.0 - 1.0 | **Anti-gaming metric** (higher = more suspicious) |
| `submind.behavioral_patterns` | object | JSON | Detected gaming patterns |

**behavioral_patterns Structure:**
```json
"behavioral_patterns": {
  "bot_activity": true/false,
  "wash_trading_influence": 0.0-1.0,  // Any value > 0 triggers flag
  "coordinated_shilling": true/false
  // Add any other patterns your model detects
}
```

**Example:**
```json
"submind": {
  "raw_score": 0.79,
  "hidden_sentiment": "positive",
  "manipulation_probability": 0.08,
  "behavioral_patterns": {
    "bot_activity": false,
    "wash_trading_influence": 0.05,
    "coordinated_shilling": false
  }
}
```

#### Optional: IntuOne Layer Fields

IntuOne is the "expressive interpreter" that translates raw signals into structured data.

| Field | Type | Range/Format | Description |
|-------|------|--------------|-------------|
| `intuone.emotional_resonance` | float | 0.0 - 1.0 | How strongly the community feels |
| `intuone.language_tone` | string | Free text | Analyzed tone (e.g., `"enthusiastic"`, `"cautious"`) |
| `intuone.community_awareness` | float | 0.0 - 1.0 | Community engagement level |

**Common language_tone values:**
- `"enthusiastic"`
- `"cautious"`
- `"fearful"`
- `"euphoric"`
- `"skeptical"`
- `"neutral"`
- `"highly enthusiastic"`
- `"extremely cautious"`

**Example:**
```json
"intuone": {
  "emotional_resonance": 0.88,
  "language_tone": "enthusiastic",
  "community_awareness": 0.91
}
```

#### Optional: Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `perception_graph_id` | string | ID linking to graph topology (if you're sending `perception_graph`) |
| `confidence` | float (0-1) | Your model's confidence in this measurement |
| `data_sources` | array of strings | Sources used (e.g., `["twitter", "discord", "reddit"]`) |
| `sample_size` | integer | Number of data points analyzed |

**Example:**
```json
"perception_graph_id": "degods_graph_20250108_142311",
"confidence": 0.96,
"data_sources": ["twitter", "discord", "reddit", "on-chain"],
"sample_size": 15420
```

---

### perception_graph Object (Optional)

Only include this if you want to store the perception topology.

#### Nodes Array

Each node represents an entity in the perception network (user, topic, community, hashtag, influencer).

**Node Structure:**
```json
{
  "id": "unique_node_id",
  "type": "influencer",  // or "user", "topic", "community", "hashtag"
  "label": "Human-readable name",
  "influence": 0.95,  // 0-1 score
  "sentiment": "positive",  // or "negative", "neutral"
  "metadata": {
    // Any additional data you want to store
    "followers": 150000,
    "engagement_rate": 0.08
  }
}
```

**Example nodes:**
```json
"nodes": [
  {
    "id": "influencer_cryptowhale",
    "type": "influencer",
    "label": "@CryptoWhale",
    "influence": 0.95,
    "sentiment": "positive",
    "metadata": {
      "followers": 150000,
      "engagement_rate": 0.08,
      "verified": true
    }
  },
  {
    "id": "topic_floor_price",
    "type": "topic",
    "label": "DeGods Floor Price Discussion",
    "influence": 0.72,
    "sentiment": "neutral",
    "metadata": {
      "mention_count": 542,
      "trending": true
    }
  }
]
```

#### Edges Array

Each edge represents a relationship between nodes.

**Edge Structure:**
```json
{
  "source": "source_node_id",
  "target": "target_node_id",
  "type": "mentions",  // or "endorses", "criticizes", "discusses"
  "weight": 0.85,  // Relationship strength (0-1)
  "sentiment": "positive",  // or "negative", "neutral"
  "metadata": {
    // Any additional data
  }
}
```

**Example edges:**
```json
"edges": [
  {
    "source": "influencer_cryptowhale",
    "target": "topic_floor_price",
    "type": "mentions",
    "weight": 0.85,
    "sentiment": "positive",
    "metadata": {
      "tweet_count": 5,
      "timestamp": "2025-01-08T12:00:00Z"
    }
  },
  {
    "source": "influencer_cryptowhale",
    "target": "community_degods_discord",
    "type": "endorses",
    "weight": 0.92,
    "sentiment": "positive",
    "metadata": {
      "endorsement_strength": "strong"
    }
  }
]
```

---

## Entity ID Reference

### Collection (entity_type: "collection")

**Format:** Solana collection address

```json
{
  "entity_type": "collection",
  "entity_id": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
}
```

**Popular Collections:**
- DeGods: `DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263`
- Mad Lads: `J1S9H3QjnRtBbbuD4HjPV6RpRhwuk4zKbxsnCHuTgh9w`
- SMB Gen2: `SMBtHCCC6RYRutFEPb4gZqeBLUZbMNhRKaMKZZLHi7W`

### NFT (entity_type: "nft")

**Format:** Solana NFT mint address

```json
{
  "entity_type": "nft",
  "entity_id": "7XYZabc123defGHI456jklMNO789pqrSTU012vwxYZA"
}
```

### Trait (entity_type: "trait")

**Format:** TraitKeeper TraitValue database ID (integer as string)

```json
{
  "entity_type": "trait",
  "entity_id": "12345"
}
```

**Note:** To get trait IDs, you'll need to query TraitKeeper's database or API. The ID corresponds to the `nft_data.TraitValue` model primary key.

---

## Authentication

### Method 1: HMAC Signature (Recommended)

**Header:** `X-Parallel-Lines-Signature`

**Algorithm:** HMAC-SHA256

**Process:**
1. Serialize payload to JSON with **sorted keys**
2. Compute HMAC-SHA256 using shared secret
3. Send hex digest in header

**Secret Storage:**
Your shared secret must be added to TraitKeeper's `admin_secure.EncryptedSecret`:
- Secret name: `parallel_lines_webhook_secret`
- Secret type: Webhook Secret

**Example (see template file for implementation):**
```
Signature = HMAC-SHA256(secret, JSON.stringify(payload, sort_keys=True))
```

### Method 2: API Key (Alternative)

**Header:** `X-API-Key`

**Process:**
1. Send API key in header
2. TraitKeeper verifies against stored key

**Secret Storage:**
Your API key must be added to TraitKeeper's `admin_secure.EncryptedSecret`:
- Secret name: `parallel_lines_api_key`
- Secret type: API Token

---

## Response Format

### Success (200 OK)

```json
{
  "success": true,
  "message": "Success",
  "perception_index": 0.82,
  "entity_type": "collection"
}
```

### Authentication Failed (401 Unauthorized)

```json
{
  "success": false,
  "error": "Authentication failed"
}
```

### Validation Error (400 Bad Request)

```json
{
  "success": false,
  "error": "Missing required field: perception_index"
}
```

**Common validation errors:**
- Missing `entity_type`
- Missing `entity_id`
- Missing `perception_data.perception_index`
- Invalid `entity_type` (not "collection", "nft", or "trait")
- `perception_index` out of range (must be 0.0-1.0)

### Entity Not Found (400 Bad Request)

```json
{
  "success": false,
  "error": "Entity not found: collection DezXAZ..."
}
```

This means the collection/NFT/trait doesn't exist in TraitKeeper's database.

### Server Error (500 Internal Server Error)

```json
{
  "success": false,
  "error": "Internal server error"
}
```

---

## Complete Examples

### Example 1: Minimal Collection Perception

```json
{
  "entity_type": "collection",
  "entity_id": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",

  "perception_data": {
    "perception_index": 0.82,
    "timestamp": "2025-01-08T14:23:11Z"
  }
}
```

### Example 2: Full Collection Perception with Submind & IntuOne

```json
{
  "entity_type": "collection",
  "entity_id": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",

  "perception_data": {
    "perception_index": 0.82,
    "timestamp": "2025-01-08T14:23:11Z",

    "submind": {
      "raw_score": 0.79,
      "hidden_sentiment": "positive",
      "manipulation_probability": 0.08,
      "behavioral_patterns": {
        "bot_activity": false,
        "wash_trading_influence": 0.05,
        "coordinated_shilling": false
      }
    },

    "intuone": {
      "emotional_resonance": 0.88,
      "language_tone": "enthusiastic",
      "community_awareness": 0.91
    },

    "perception_graph_id": "degods_graph_20250108",
    "confidence": 0.96,
    "data_sources": ["twitter", "discord", "reddit"],
    "sample_size": 15420
  }
}
```

### Example 3: NFT-Level Perception

```json
{
  "entity_type": "nft",
  "entity_id": "7XYZabc123defGHI456jklMNO789pqrSTU012vwxYZA",

  "perception_data": {
    "perception_index": 0.75,
    "timestamp": "2025-01-08T14:25:00Z",

    "submind": {
      "raw_score": 0.71,
      "hidden_sentiment": "positive",
      "manipulation_probability": 0.15
    },

    "intuone": {
      "emotional_resonance": 0.78,
      "language_tone": "excited",
      "community_awareness": 0.68
    },

    "confidence": 0.85,
    "data_sources": ["twitter"],
    "sample_size": 342
  }
}
```

### Example 4: Trait-Level Perception

```json
{
  "entity_type": "trait",
  "entity_id": "12345",

  "perception_data": {
    "perception_index": 0.89,
    "timestamp": "2025-01-08T14:30:00Z",

    "submind": {
      "raw_score": 0.87,
      "hidden_sentiment": "positive",
      "manipulation_probability": 0.05,
      "behavioral_patterns": {
        "bot_activity": false,
        "wash_trading_influence": 0.02,
        "coordinated_shilling": false
      }
    },

    "intuone": {
      "emotional_resonance": 0.92,
      "language_tone": "highly enthusiastic",
      "community_awareness": 0.85
    },

    "confidence": 0.91,
    "data_sources": ["twitter", "discord"],
    "sample_size": 2840
  }
}
```

### Example 5: With Perception Graph

```json
{
  "entity_type": "collection",
  "entity_id": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",

  "perception_data": {
    "perception_index": 0.82,
    "timestamp": "2025-01-08T14:23:11Z",
    "perception_graph_id": "degods_graph_20250108",

    "submind": {
      "raw_score": 0.79,
      "hidden_sentiment": "positive",
      "manipulation_probability": 0.08
    },

    "intuone": {
      "emotional_resonance": 0.88,
      "language_tone": "enthusiastic",
      "community_awareness": 0.91
    },

    "confidence": 0.96,
    "data_sources": ["twitter", "discord"],
    "sample_size": 15420
  },

  "perception_graph": {
    "nodes": [
      {
        "id": "influencer_cryptowhale",
        "type": "influencer",
        "label": "@CryptoWhale",
        "influence": 0.95,
        "sentiment": "positive",
        "metadata": {
          "followers": 150000,
          "engagement_rate": 0.08,
          "verified": true
        }
      },
      {
        "id": "topic_floor_price",
        "type": "topic",
        "label": "DeGods Floor Price",
        "influence": 0.72,
        "sentiment": "neutral",
        "metadata": {
          "mention_count": 542
        }
      },
      {
        "id": "community_degods_discord",
        "type": "community",
        "label": "DeGods Discord",
        "influence": 0.88,
        "sentiment": "positive",
        "metadata": {
          "member_count": 45000,
          "active_members": 12000
        }
      }
    ],

    "edges": [
      {
        "source": "influencer_cryptowhale",
        "target": "topic_floor_price",
        "type": "mentions",
        "weight": 0.85,
        "sentiment": "positive",
        "metadata": {
          "tweet_count": 5,
          "timestamp": "2025-01-08T12:00:00Z"
        }
      },
      {
        "source": "influencer_cryptowhale",
        "target": "community_degods_discord",
        "type": "endorses",
        "weight": 0.92,
        "sentiment": "positive",
        "metadata": {
          "endorsement_strength": "strong"
        }
      },
      {
        "source": "community_degods_discord",
        "target": "topic_floor_price",
        "type": "discusses",
        "weight": 0.78,
        "sentiment": "neutral",
        "metadata": {
          "discussion_volume": "high"
        }
      }
    ]
  }
}
```

---

## Data Processing Flow

When you send data to TraitKeeper, here's what happens:

1. **Authentication** - HMAC signature or API key verified
2. **Validation** - Payload structure checked
3. **Entity Resolution** - Collection/NFT/trait found in database
4. **PerceptionSnapshot Created** - Data stored
5. **Perception Graph Processed** - Nodes/edges stored (if included)
6. **Audit Logging** - Full webhook logged to `ParallelLinesWebhookLog`
7. **Cache Invalidation** - Old perception data cleared
8. **Response Sent** - Success/error returned

**Processing Time Target:** < 500ms

---

## What TraitKeeper Does With Your Data

### Immediate Use

**Vitality Score Calculation:**
- Your `perception_index` becomes **20% of the NFT Vitality Score**
- Collection-level perception weighted 70%
- NFT-level perception weighted 30%

**Anti-Gaming:**
- If `manipulation_probability > 0.7`, score is dampened toward neutral (0.5)
- Prevents artificially inflated perception from affecting vitality

### Storage

**PerceptionSnapshot Table:**
- Every webhook creates a timestamped snapshot
- Full audit trail with all Submind + IntuOne data
- Indexed by entity and timestamp for fast queries

**PerceptionGraph Tables:**
- Nodes stored in `PerceptionGraphNode`
- Edges stored in `PerceptionGraphEdge`
- Linked by `perception_graph_id`

**Webhook Audit:**
- Every call logged to `ParallelLinesWebhookLog`
- Processing time tracked
- Errors recorded for debugging

### Caching

- Perception scores cached for 5 minutes
- Reduces database load
- Automatic invalidation on new data

---

## Best Practices

### 1. Update Frequency

**Recommended:**
- **Collection-level:** Every 5-15 minutes
- **NFT-level:** Every 30-60 minutes (only for high-value NFTs)
- **Trait-level:** Every 1-4 hours

**Why:** TraitKeeper caches perception for 5 minutes, so sending more frequently doesn't improve freshness.

### 2. Confidence Scoring

Always include `confidence` if your model can calculate it:
- High confidence (> 0.9): Large sample, clear signal
- Medium confidence (0.7-0.9): Decent sample, some noise
- Low confidence (< 0.7): Small sample or unclear signal

TraitKeeper may use this in the future to weight perception data.

### 3. Manipulation Probability

**Critical for anti-gaming:**
- `< 0.3`: Clean signal, no dampening
- `0.3 - 0.7`: Moderate suspicion, slight dampening
- `> 0.7`: High suspicion, **significant dampening** applied

Be conservative - only flag clear manipulation.

### 4. Behavioral Patterns

Structure should be consistent:
```json
"behavioral_patterns": {
  "bot_activity": true/false,
  "wash_trading_influence": 0.0-1.0,
  "coordinated_shilling": true/false
}
```

You can add additional patterns, but keep these three for consistency.

### 5. Data Sources

Be specific about sources:
```json
"data_sources": ["twitter", "discord", "reddit", "on-chain", "telegram"]
```

This helps TraitKeeper understand data quality and coverage.

### 6. Timestamp Format

**Always use UTC ISO 8601:**
```python
from datetime import datetime
timestamp = datetime.utcnow().isoformat() + "Z"
# "2025-01-08T14:23:11Z"
```

### 7. Perception Graph

Only include if you have meaningful topology data:
- Minimum 3 nodes
- At least 2 edges
- Include `perception_graph_id` in `perception_data`

---

## Error Handling

### Retry Logic

**Recommended approach:**
```python
import time
import requests

def send_with_retry(payload, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = send_perception_to_traitkeeper(payload)
            if response.status_code == 200:
                return response
            elif response.status_code in [400, 401]:
                # Don't retry validation/auth errors
                return response
            else:
                # Server error - retry with backoff
                time.sleep(2 ** attempt)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
```

### Common Issues

**401 Unauthorized:**
- Check HMAC signature calculation
- Verify secret is configured in admin_secure
- Ensure payload JSON is sorted when computing signature

**400 Bad Request - Missing field:**
- Ensure `perception_index` is present
- Check `entity_type` is valid
- Verify `timestamp` is ISO 8601 format

**400 Bad Request - Entity not found:**
- Collection/NFT/trait doesn't exist in TraitKeeper
- Check entity ID is correct
- For traits, ensure you're using database ID not trait name

---

## Next Steps

1. **Review the template file** (`parallel_lines_webhook_template.py`)
2. **Set up authentication** in TraitKeeper's admin_secure
3. **Test with minimal payload** first
4. **Add Submind/IntuOne data** gradually
5. **Monitor webhook logs** in Django Admin

---

## Related Documentation

- [PARALLEL_LINES_AUTH_SETUP.md](./PARALLEL_LINES_AUTH_SETUP.md) - Authentication configuration
- [PARALLEL_LINES_INTEGRATION.md](./PARALLEL_LINES_INTEGRATION.md) - Full integration architecture
- [VITALITY_SYSTEM.md](./VITALITY_SYSTEM.md) - How perception affects vitality scores

---

**Last Updated:** January 2025
**Webhook Version:** 1.0
**Endpoint:** `/api/perception/webhook`
**Implementation:** `marketplace/views.py:346-438`, `marketplace/perception_service.py`
