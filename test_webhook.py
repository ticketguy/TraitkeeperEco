#!/usr/bin/env python
"""
Test script for webhook endpoint.
Run this to test if your webhook is working locally.

Usage:
    python test_webhook.py
"""
import requests
import json

# Test webhook URL (adjust for your environment)
WEBHOOK_URL = "http://traitkeeper.xyz/indexer/webhook/"

# Sample Helius webhook payload
helius_payload = [{
    "signature": "test_signature_123",
    "type": "NFT_SALE",
    "description": "Test NFT sale event",
    "source": "MAGIC_EDEN",
    "accountData": [],
    "nativeTransfers": [],
    "tokenTransfers": [],
    "timestamp": 1234567890,
    "slot": 12345
}]

# Sample QuickNode payload
quicknode_payload = {
    "id": "test_id_123",
    "data": {
        "signature": "test_signature_456",
        "transaction": {
            "message": {},
            "signatures": []
        }
    }
}


def test_webhook(payload, name):
    """Test webhook with a payload."""
    print(f"\n{'='*60}")
    print(f"Testing {name}")
    print(f"{'='*60}")

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )

        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            print(f"✅ {name} test PASSED")
        else:
            print(f"❌ {name} test FAILED")

    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Is your Django server running?")
        print("   Start it with: python manage.py runserver")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("🧪 Webhook Endpoint Test")
    print(f"Target: {WEBHOOK_URL}")
    print("\nMake sure your Django server is running!")

    # Test Helius format
    test_webhook(helius_payload, "Helius Webhook")

    # Test QuickNode format
    test_webhook(quicknode_payload, "QuickNode Webhook")

    print(f"\n{'='*60}")
    print("Test complete!")
    print(f"{'='*60}\n")
