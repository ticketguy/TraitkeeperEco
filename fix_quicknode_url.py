#!/usr/bin/env python
"""
Quick script to fix QuickNode URLs in the database.
Run with: docker exec traitkeeper-main python fix_quicknode_url.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'traitkeeper.settings')
django.setup()

from admin_panel.models import PrimaryProviderSetting

# Correct URLs from QuickNode dashboard
CORRECT_RPC_URL = "https://thrumming-newest-orb.solana-mainnet.quiknode.pro/1af8fa5f6208ae3d2692408618436930ed1c8071/"
CORRECT_WS_URL = "wss://thrumming-newest-orb.solana-mainnet.quiknode.pro/1af8fa5f6208ae3d2692408618436930ed1c8071/"

try:
    quicknode = PrimaryProviderSetting.objects.get(name='quicknode')

    print(f"Current RPC URL: {quicknode.rpc_url}")
    print(f"Current WS URL:  {quicknode.ws_url}")
    print()

    quicknode.rpc_url = CORRECT_RPC_URL
    quicknode.ws_url = CORRECT_WS_URL
    quicknode.save()

    print("✅ Updated to:")
    print(f"New RPC URL: {quicknode.rpc_url}")
    print(f"New WS URL:  {quicknode.ws_url}")
    print()
    print("🔄 Now restart indexers: docker compose restart indexer-live indexer-scheduled")

except PrimaryProviderSetting.DoesNotExist:
    print("❌ QuickNode provider not found in database")
except Exception as e:
    print(f"❌ Error: {e}")
