# indexer/management/commands/fetch_market_stats_now.py
"""
Manually fetch and store market stats for all listed collections.

Usage:
    python manage.py fetch_market_stats_now
"""
import asyncio
import logging
from django.core.management.base import BaseCommand
from asgiref.sync import sync_to_async
from nft_data.models import NFTCollection
from indexer.services import IndexerService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Manually fetch and store market stats for all listed collections'

    async def fetch_all_stats(self):
        """Fetch stats for all collections."""
        indexer = IndexerService()

        # Get all listed collections
        collections = await sync_to_async(list)(
            NFTCollection.objects.filter(is_listed=True)
        )

        self.stdout.write("=" * 80)
        self.stdout.write(f"📊 Fetching market stats for {len(collections)} collections...")
        self.stdout.write("=" * 80)

        success_count = 0
        failed_count = 0

        for collection in collections:
            try:
                self.stdout.write(f"\n🔍 {collection.name} ({collection.address[:16]}...)")

                await indexer.fetch_and_store_all_market_stats(collection)

                self.stdout.write(self.style.SUCCESS(f"  ✅ Success"))
                success_count += 1

                # Stagger requests to avoid rate limits
                await asyncio.sleep(2)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ Failed: {str(e)}"))
                failed_count += 1

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(f"✅ Success: {success_count}")
        self.stdout.write(f"❌ Failed: {failed_count}")
        self.stdout.write("=" * 80)

    def handle(self, *args, **options):
        asyncio.run(self.fetch_all_stats())
