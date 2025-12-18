#!/bin/bash

echo "=== Market Stats Verification Script ==="
echo ""

echo "1. Checking if marketplace providers are loaded..."
docker-compose exec main python manage.py shell -c "
from core.api_provider.api_providers import APIProviderManager
manager = APIProviderManager()
providers = manager.get_rpc_providers()
print('Magic Eden:', 'LOADED' if 'magic_eden' in providers else 'NOT FOUND')
print('Tensor:', 'LOADED' if 'tensor' in providers else 'NOT FOUND')
"

echo ""
echo "2. Checking CollectionMarketStats records..."
docker-compose exec main python manage.py shell -c "
from indexer.models import CollectionMarketStats
from django.utils import timezone
from datetime import timedelta

# Total records
total = CollectionMarketStats.objects.count()
print(f'Total records: {total}')

# Recent records (last hour)
recent = CollectionMarketStats.objects.filter(
    timestamp__gte=timezone.now() - timedelta(hours=1)
).count()
print(f'Records in last hour: {recent}')

# By source
for source in ['magic_eden', 'tensor']:
    count = CollectionMarketStats.objects.filter(source=source).count()
    print(f'{source}: {count} records')
"

echo ""
echo "3. Checking listed collections with slugs..."
docker-compose exec main python manage.py shell -c "
from indexer.models import NFTCollection
listed = NFTCollection.objects.filter(is_listed=True)
print(f'Total listed collections: {listed.count()}')
with_slug = listed.exclude(slug__isnull=True).exclude(slug='')
print(f'Collections with Magic Eden slug: {with_slug.count()}')
"

echo ""
echo "4. Checking recent scheduled indexer logs..."
docker-compose logs --tail=50 indexer-scheduled | grep -i "market\|magic\|tensor"

echo ""
echo "=== Verification Complete ==="
