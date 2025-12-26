#!/usr/bin/env python
"""
Quick script to check Tensor API configuration in production
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'traitkeeper.settings')
django.setup()

from admin_panel.models import MarketplaceProviderSetting

print("=" * 60)
print("TENSOR API CONFIGURATION CHECK")
print("=" * 60)

# Check environment variable
env_key = os.getenv('TENSOR_API_KEY', 'NOT SET')
print(f"\n1. Environment Variable:")
print(f"   TENSOR_API_KEY: {env_key[:20]}..." if env_key != 'NOT SET' and len(env_key) > 20 else f"   TENSOR_API_KEY: {env_key}")

# Check database configuration
print(f"\n2. Database Configuration:")
try:
    tensor_settings = MarketplaceProviderSetting.objects.filter(name__iexact='tensor')

    if tensor_settings.exists():
        for setting in tensor_settings:
            print(f"   - Found Tensor setting (ID: {setting.id})")
            print(f"     Name: {setting.name}")
            print(f"     Is Active: {setting.is_active}")
            print(f"     API Key: {setting.api_key[:20]}..." if setting.api_key and len(setting.api_key) > 20 else f"     API Key: {setting.api_key}")
            print(f"     Base URL: {setting.base_url or 'Not set'}")
    else:
        print("   ⚠️  No Tensor configuration found in database!")
        print("   You need to create one in the admin panel")
except Exception as e:
    print(f"   ❌ Error checking database: {e}")

print("\n" + "=" * 60)
print("RECOMMENDATIONS:")
print("=" * 60)

if env_key == 'YOUR_PRODUCTION_TENSOR_KEY' or env_key == 'NOT SET':
    print("⚠️  Your TENSOR_API_KEY is not configured!")
    print("\nTo fix:")
    print("1. Get a Tensor API key from: https://www.tensor.so/")
    print("2. Add it to your MarketplaceProviderSetting in Django admin")
    print("   OR update your .env file with the real key")
    print("3. Restart your Django container")
else:
    print("✅ API key appears to be set")
    print("   If still getting 403, verify:")
    print("   - The API key is valid and not expired")
    print("   - The key has correct permissions")
    print("   - Your IP is not blocked")

print("=" * 60)
