# indexer/management/commands/backfill_collection.py
"""
One-time historical backfill for a collection.

This fetches the last 1000 transactions from the blockchain for a collection.
Used when adding a new collection or doing initial data population.

Usage:
    python manage.py backfill_collection <collection_address>
    python manage.py backfill_collection --all  # All collections
"""

import asyncio
import logging
from django.core.management.base import BaseCommand
from asgiref.sync import sync_to_async
from nft_data.models import NFTCollection
from indexer.services import IndexerService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Performs one-time historical backfill for a collection'

    def add_arguments(self, parser):
        parser.add_argument(
            'collection_address',
            nargs='?',
            type=str,
            help='Collection address to backfill'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Backfill all listed collections'
        )

    async def backfill_collection(self, collection_address):
        """Backfill historical data for a single collection."""
        try:
            # Get collection
            collection = await sync_to_async(
                NFTCollection.objects.get
            )(address=collection_address)

            logger.info("=" * 80)
            logger.info(f"📚 STARTING HISTORICAL BACKFILL")
            logger.info(f"Collection: {collection.name}")
            logger.info(f"Address: {collection.address}")
            logger.info("=" * 80)

            indexer = IndexerService()

            # Fetch historical transactions (1000 limit)
            logger.info("🔍 Fetching historical transactions from blockchain...")
            await indexer.process_onchain_events(collection.address)

            # Also fetch current market stats
            logger.info("📊 Fetching current market stats...")
            await indexer.fetch_and_store_all_market_stats(collection)

            logger.info("=" * 80)
            logger.info(f"✅ BACKFILL COMPLETE: {collection.name}")
            logger.info("=" * 80)

        except NFTCollection.DoesNotExist:
            logger.error(f"❌ Collection not found: {collection_address}")
            raise
        except Exception as e:
            logger.error(f"❌ Backfill failed for {collection_address}: {e}", exc_info=True)
            raise

    async def backfill_all(self):
        """Backfill all listed collections."""
        collections = await sync_to_async(list)(
            NFTCollection.objects.filter(is_listed=True)
        )

        logger.info("=" * 80)
        logger.info(f"📚 BACKFILLING {len(collections)} COLLECTIONS")
        logger.info("=" * 80)

        for i, collection in enumerate(collections, 1):
            try:
                logger.info(f"\n[{i}/{len(collections)}] Processing {collection.name}")
                await self.backfill_collection(collection.address)

                # Long delay between collections to avoid rate limits
                if i < len(collections):
                    logger.info("⏳ Waiting 30 seconds before next collection...")
                    await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Failed to backfill {collection.name}: {e}")
                continue

        logger.info("\n" + "=" * 80)
        logger.info(f"✅ BACKFILL COMPLETE: {len(collections)} collections processed")
        logger.info("=" * 80)

    def handle(self, *args, **options):
        collection_address = options.get('collection_address')
        backfill_all = options.get('all')

        if not collection_address and not backfill_all:
            self.stdout.write(
                self.style.ERROR('Error: Provide either collection_address or --all flag')
            )
            self.stdout.write('\nUsage:')
            self.stdout.write('  python manage.py backfill_collection <address>')
            self.stdout.write('  python manage.py backfill_collection --all')
            return

        if backfill_all:
            asyncio.run(self.backfill_all())
        else:
            asyncio.run(self.backfill_collection(collection_address))
