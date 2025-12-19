#!/bin/bash
# Verify marketplace API providers and market stats

echo "🔍 MARKETPLACE & WEBHOOK DIAGNOSTICS"
echo "======================================"
echo ""

echo "1. Testing Marketplace API Providers..."
docker-compose exec main python manage.py diagnose_market_stats

echo ""
echo "2. Checking Recent Webhook Activity..."
docker-compose exec main python manage.py shell -c "
from indexer.models import NFTEvent
from django.utils import timezone
from datetime import timedelta

recent = timezone.now() - timedelta(hours=1)
count = NFTEvent.objects.filter(created_at__gte=recent).count()

print(f'Events in last hour: {count}')

if count > 0:
    latest = NFTEvent.objects.latest('created_at')
    print(f'Latest event: {latest.event_type} at {latest.created_at}')
    print(f'Collection: {latest.collection.name if latest.collection else \"N/A\"}')
else:
    print('⚠️  No recent events - webhook may not be working')
"

echo ""
echo "3. Checking Django Logs for Webhook Activity..."
docker-compose logs main --tail 50 | grep -i "webhook\|📨" || echo "No webhook activity in recent logs"

echo ""
echo "4. Checking Market Stats Update Status..."
docker-compose exec main python manage.py shell -c "
from nft_data.models import NFTCollection
from django.utils import timezone
from datetime import timedelta

recent = timezone.now() - timedelta(hours=24)
collections = NFTCollection.objects.filter(is_listed=True)

total = collections.count()
updated_recently = collections.filter(last_stats_update__gte=recent).count()

print(f'Total listed collections: {total}')
print(f'Updated in last 24h: {updated_recently}')

if updated_recently == 0:
    print('⚠️  No collections updated recently - stats fetching may not be working')
else:
    latest = collections.filter(last_stats_update__isnull=False).order_by('-last_stats_update').first()
    if latest:
        print(f'Most recent update: {latest.name} at {latest.last_stats_update}')
        print(f'Floor: {latest.floor_price} SOL')
"

echo ""
echo "======================================"
echo "✅ DIAGNOSTICS COMPLETE"
echo "======================================"
