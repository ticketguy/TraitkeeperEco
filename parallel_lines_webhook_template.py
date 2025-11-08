"""
Parallel Lines → TraitKeeper Webhook Template

This template provides ready-to-use code for sending perception data from
Parallel Lines to TraitKeeper's vitality system.

SETUP:
1. Install dependencies: pip install requests
2. Configure your shared secret or API key
3. Implement your perception calculation logic
4. Call send_perception_to_traitkeeper() with your data

DOCUMENTATION:
See docs/PARALLEL_LINES_WEBHOOK_SPEC.md for complete field specifications
"""

import hmac
import hashlib
import json
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any


# ============================================================================
# CONFIGURATION
# ============================================================================

# TraitKeeper webhook endpoint
TRAITKEEPER_WEBHOOK_URL = "https://traitkeeper.com/api/perception/webhook"

# Authentication (choose one method)
WEBHOOK_SECRET = "your-shared-secret-here"  # For HMAC authentication (recommended)
API_KEY = "your-api-key-here"  # For API key authentication (alternative)

# Which authentication method to use
AUTH_METHOD = "HMAC"  # or "API_KEY"


# ============================================================================
# AUTHENTICATION FUNCTIONS
# ============================================================================

def generate_hmac_signature(payload: Dict[str, Any], secret: str) -> str:
    """
    Generate HMAC-SHA256 signature for webhook authentication.

    Args:
        payload: The JSON payload to sign
        secret: Shared secret key

    Returns:
        Hex digest of HMAC signature
    """
    # IMPORTANT: Payload must be JSON-serialized with SORTED KEYS
    # This ensures consistent hashing on both sides
    payload_json = json.dumps(payload, sort_keys=True)

    # Compute HMAC-SHA256
    signature = hmac.new(
        secret.encode('utf-8'),
        payload_json.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return signature


# ============================================================================
# WEBHOOK SENDER
# ============================================================================

def send_perception_to_traitkeeper(
    payload: Dict[str, Any],
    auth_method: str = AUTH_METHOD,
    webhook_secret: str = WEBHOOK_SECRET,
    api_key: str = API_KEY,
    webhook_url: str = TRAITKEEPER_WEBHOOK_URL
) -> requests.Response:
    """
    Send perception data to TraitKeeper via webhook.

    Args:
        payload: Perception data payload (see examples below)
        auth_method: "HMAC" or "API_KEY"
        webhook_secret: Shared secret for HMAC
        api_key: API key for API_KEY auth
        webhook_url: TraitKeeper webhook endpoint

    Returns:
        Response object from requests

    Raises:
        requests.RequestException: If request fails
    """
    headers = {
        'Content-Type': 'application/json'
    }

    # Add authentication header
    if auth_method == "HMAC":
        signature = generate_hmac_signature(payload, webhook_secret)
        headers['X-Parallel-Lines-Signature'] = signature
    elif auth_method == "API_KEY":
        headers['X-API-Key'] = api_key
    else:
        raise ValueError(f"Invalid auth_method: {auth_method}")

    # Send POST request
    response = requests.post(
        webhook_url,
        json=payload,
        headers=headers,
        timeout=10  # 10 second timeout
    )

    return response


def send_with_retry(
    payload: Dict[str, Any],
    max_retries: int = 3,
    **kwargs
) -> requests.Response:
    """
    Send perception data with automatic retry on server errors.

    Args:
        payload: Perception data payload
        max_retries: Maximum number of retry attempts
        **kwargs: Additional arguments passed to send_perception_to_traitkeeper()

    Returns:
        Response object from requests
    """
    import time

    last_exception = None

    for attempt in range(max_retries):
        try:
            response = send_perception_to_traitkeeper(payload, **kwargs)

            # Success or client error (don't retry 4xx)
            if response.status_code < 500:
                return response

            # Server error (5xx) - retry with exponential backoff
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                print(f"Server error {response.status_code}. Retrying in {wait_time}s...")
                time.sleep(wait_time)

        except requests.RequestException as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"Request failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)

    # All retries failed
    if last_exception:
        raise last_exception
    return response


# ============================================================================
# PAYLOAD BUILDER FUNCTIONS
# ============================================================================

def build_perception_payload(
    entity_type: str,
    entity_id: str,
    perception_index: float,
    submind_data: Optional[Dict] = None,
    intuone_data: Optional[Dict] = None,
    perception_graph: Optional[Dict] = None,
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Build a complete perception webhook payload.

    Args:
        entity_type: "collection", "nft", or "trait"
        entity_id: Collection address, NFT mint, or trait ID
        perception_index: Final perception score (0.0-1.0)
        submind_data: Optional Submind layer outputs
        intuone_data: Optional IntuOne layer outputs
        perception_graph: Optional graph topology
        metadata: Optional metadata (confidence, data_sources, sample_size)

    Returns:
        Complete webhook payload ready to send
    """
    # Validate inputs
    assert entity_type in ["collection", "nft", "trait"], "Invalid entity_type"
    assert 0.0 <= perception_index <= 1.0, "perception_index must be 0.0-1.0"

    # Build perception_data
    perception_data = {
        "perception_index": perception_index,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    # Add Submind data if provided
    if submind_data:
        perception_data["submind"] = submind_data

    # Add IntuOne data if provided
    if intuone_data:
        perception_data["intuone"] = intuone_data

    # Add metadata if provided
    if metadata:
        if "perception_graph_id" in metadata:
            perception_data["perception_graph_id"] = metadata["perception_graph_id"]
        if "confidence" in metadata:
            perception_data["confidence"] = metadata["confidence"]
        if "data_sources" in metadata:
            perception_data["data_sources"] = metadata["data_sources"]
        if "sample_size" in metadata:
            perception_data["sample_size"] = metadata["sample_size"]

    # Build final payload
    payload = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "perception_data": perception_data
    }

    # Add perception graph if provided
    if perception_graph:
        payload["perception_graph"] = perception_graph

    return payload


def build_submind_data(
    raw_score: Optional[float] = None,
    hidden_sentiment: Optional[str] = None,
    manipulation_probability: Optional[float] = None,
    bot_activity: Optional[bool] = None,
    wash_trading_influence: Optional[float] = None,
    coordinated_shilling: Optional[bool] = None,
    **additional_patterns
) -> Dict[str, Any]:
    """
    Build Submind layer data structure.

    Args:
        raw_score: Raw behavioral score (0.0-1.0)
        hidden_sentiment: "positive", "negative", "neutral", "mixed"
        manipulation_probability: Anti-gaming score (0.0-1.0)
        bot_activity: Boolean flag for bot detection
        wash_trading_influence: Wash trading score (0.0-1.0)
        coordinated_shilling: Boolean flag for coordinated campaigns
        **additional_patterns: Any additional behavioral patterns

    Returns:
        Submind data dictionary
    """
    submind = {}

    if raw_score is not None:
        assert 0.0 <= raw_score <= 1.0, "raw_score must be 0.0-1.0"
        submind["raw_score"] = raw_score

    if hidden_sentiment is not None:
        assert hidden_sentiment in ["positive", "negative", "neutral", "mixed"]
        submind["hidden_sentiment"] = hidden_sentiment

    if manipulation_probability is not None:
        assert 0.0 <= manipulation_probability <= 1.0, "manipulation_probability must be 0.0-1.0"
        submind["manipulation_probability"] = manipulation_probability

    # Build behavioral patterns
    behavioral_patterns = {}

    if bot_activity is not None:
        behavioral_patterns["bot_activity"] = bot_activity

    if wash_trading_influence is not None:
        assert 0.0 <= wash_trading_influence <= 1.0, "wash_trading_influence must be 0.0-1.0"
        behavioral_patterns["wash_trading_influence"] = wash_trading_influence

    if coordinated_shilling is not None:
        behavioral_patterns["coordinated_shilling"] = coordinated_shilling

    # Add any additional patterns
    behavioral_patterns.update(additional_patterns)

    if behavioral_patterns:
        submind["behavioral_patterns"] = behavioral_patterns

    return submind


def build_intuone_data(
    emotional_resonance: Optional[float] = None,
    language_tone: Optional[str] = None,
    community_awareness: Optional[float] = None
) -> Dict[str, Any]:
    """
    Build IntuOne layer data structure.

    Args:
        emotional_resonance: How strongly community feels (0.0-1.0)
        language_tone: Analyzed tone (e.g., "enthusiastic", "cautious")
        community_awareness: Community engagement level (0.0-1.0)

    Returns:
        IntuOne data dictionary
    """
    intuone = {}

    if emotional_resonance is not None:
        assert 0.0 <= emotional_resonance <= 1.0, "emotional_resonance must be 0.0-1.0"
        intuone["emotional_resonance"] = emotional_resonance

    if language_tone is not None:
        intuone["language_tone"] = language_tone

    if community_awareness is not None:
        assert 0.0 <= community_awareness <= 1.0, "community_awareness must be 0.0-1.0"
        intuone["community_awareness"] = community_awareness

    return intuone


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

def example_minimal_collection_perception():
    """
    Example 1: Send minimal collection-level perception.

    This is the absolute minimum required - just perception_index and timestamp.
    """
    payload = build_perception_payload(
        entity_type="collection",
        entity_id="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # DeGods
        perception_index=0.82
    )

    response = send_with_retry(payload)

    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

    return response


def example_full_collection_perception():
    """
    Example 2: Send complete collection perception with Submind + IntuOne.

    This includes all optional fields for maximum insight.
    """
    # Build Submind layer data
    submind = build_submind_data(
        raw_score=0.79,
        hidden_sentiment="positive",
        manipulation_probability=0.08,
        bot_activity=False,
        wash_trading_influence=0.05,
        coordinated_shilling=False
    )

    # Build IntuOne layer data
    intuone = build_intuone_data(
        emotional_resonance=0.88,
        language_tone="enthusiastic",
        community_awareness=0.91
    )

    # Build metadata
    metadata = {
        "confidence": 0.96,
        "data_sources": ["twitter", "discord", "reddit"],
        "sample_size": 15420
    }

    # Build complete payload
    payload = build_perception_payload(
        entity_type="collection",
        entity_id="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        perception_index=0.82,
        submind_data=submind,
        intuone_data=intuone,
        metadata=metadata
    )

    response = send_with_retry(payload)

    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

    return response


def example_nft_perception():
    """
    Example 3: Send NFT-level perception.
    """
    submind = build_submind_data(
        raw_score=0.71,
        hidden_sentiment="positive",
        manipulation_probability=0.15
    )

    intuone = build_intuone_data(
        emotional_resonance=0.78,
        language_tone="excited",
        community_awareness=0.68
    )

    metadata = {
        "confidence": 0.85,
        "data_sources": ["twitter"],
        "sample_size": 342
    }

    payload = build_perception_payload(
        entity_type="nft",
        entity_id="7XYZabc123defGHI456jklMNO789pqrSTU012vwxYZA",  # Example NFT mint
        perception_index=0.75,
        submind_data=submind,
        intuone_data=intuone,
        metadata=metadata
    )

    response = send_with_retry(payload)

    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

    return response


def example_with_perception_graph():
    """
    Example 4: Send perception with graph topology.
    """
    submind = build_submind_data(
        raw_score=0.79,
        hidden_sentiment="positive",
        manipulation_probability=0.08
    )

    intuone = build_intuone_data(
        emotional_resonance=0.88,
        language_tone="enthusiastic",
        community_awareness=0.91
    )

    # Build perception graph
    perception_graph = {
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
                    "verified": True
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
            }
        ]
    }

    metadata = {
        "perception_graph_id": "degods_graph_20250108",
        "confidence": 0.96,
        "data_sources": ["twitter", "discord"],
        "sample_size": 15420
    }

    payload = build_perception_payload(
        entity_type="collection",
        entity_id="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        perception_index=0.82,
        submind_data=submind,
        intuone_data=intuone,
        perception_graph=perception_graph,
        metadata=metadata
    )

    response = send_with_retry(payload)

    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

    return response


# ============================================================================
# INTEGRATION WITH YOUR PARALLEL LINES MODEL
# ============================================================================

def send_parallel_lines_output_to_traitkeeper(
    entity_type: str,
    entity_id: str,
    parallel_lines_output: Dict[str, Any]
):
    """
    Template function to integrate your Parallel Lines model output.

    Replace the placeholder logic with your actual model outputs.

    Args:
        entity_type: "collection", "nft", or "trait"
        entity_id: Entity identifier
        parallel_lines_output: Your model's output dictionary

    Expected parallel_lines_output structure:
    {
        "perception_index": 0.82,  # Final score from IntuOne
        "submind": {
            "raw_score": 0.79,
            "hidden_sentiment": "positive",
            "manipulation_probability": 0.08,
            "behavioral_patterns": {...}
        },
        "intuone": {
            "emotional_resonance": 0.88,
            "language_tone": "enthusiastic",
            "community_awareness": 0.91
        },
        "confidence": 0.96,
        "data_sources": ["twitter", "discord"],
        "sample_size": 15420,
        "perception_graph": {...}  # Optional
    }
    """
    # Extract data from your model output
    perception_index = parallel_lines_output["perception_index"]

    # Extract Submind data
    submind_data = parallel_lines_output.get("submind")

    # Extract IntuOne data
    intuone_data = parallel_lines_output.get("intuone")

    # Extract perception graph
    perception_graph = parallel_lines_output.get("perception_graph")

    # Extract metadata
    metadata = {
        "confidence": parallel_lines_output.get("confidence"),
        "data_sources": parallel_lines_output.get("data_sources"),
        "sample_size": parallel_lines_output.get("sample_size"),
        "perception_graph_id": parallel_lines_output.get("perception_graph_id")
    }

    # Build payload
    payload = build_perception_payload(
        entity_type=entity_type,
        entity_id=entity_id,
        perception_index=perception_index,
        submind_data=submind_data,
        intuone_data=intuone_data,
        perception_graph=perception_graph,
        metadata=metadata
    )

    # Send with retry
    response = send_with_retry(payload)

    # Log result
    if response.status_code == 200:
        print(f"✅ Perception sent successfully for {entity_type} {entity_id}")
        print(f"   Perception Index: {perception_index}")
    else:
        print(f"❌ Failed to send perception for {entity_type} {entity_id}")
        print(f"   Status: {response.status_code}")
        print(f"   Error: {response.json().get('error', 'Unknown error')}")

    return response


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    """
    Run examples to test the webhook integration.

    BEFORE RUNNING:
    1. Set WEBHOOK_SECRET or API_KEY at the top of this file
    2. Choose AUTH_METHOD ("HMAC" or "API_KEY")
    3. Ensure TraitKeeper has your secret configured in admin_secure

    Then run: python parallel_lines_webhook_template.py
    """
    print("=" * 80)
    print("Parallel Lines → TraitKeeper Webhook Test")
    print("=" * 80)

    # Example 1: Minimal payload
    print("\n[1] Testing minimal collection perception...")
    try:
        response = example_minimal_collection_perception()
        print("✅ Success!" if response.status_code == 200 else "❌ Failed!")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Example 2: Full payload with Submind + IntuOne
    print("\n[2] Testing full collection perception...")
    try:
        response = example_full_collection_perception()
        print("✅ Success!" if response.status_code == 200 else "❌ Failed!")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Example 3: NFT-level perception
    print("\n[3] Testing NFT perception...")
    try:
        response = example_nft_perception()
        print("✅ Success!" if response.status_code == 200 else "❌ Failed!")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Example 4: With perception graph
    print("\n[4] Testing perception with graph...")
    try:
        response = example_with_perception_graph()
        print("✅ Success!" if response.status_code == 200 else "❌ Failed!")
    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n" + "=" * 80)
    print("Testing complete!")
    print("=" * 80)
