# indexer/management/commands/run_scheduled_indexer.py

import asyncio
import logging
import signal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from asgiref.sync import sync_to_async
from nft_data.models import NFTCollection
from indexer.services import IndexerService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs scheduled/periodic indexing tasks for historical data.'

    def __init__(self):
        super().__init__()
        self.shutdown_event = asyncio.Event()
        self.indexer_service = None  # Initialize later to avoid DB access during app init
        self.is_running = False

    async def main(self):
        """Main async logic for scheduled indexing."""
        # Initialize IndexerService here (after Django is fully loaded)
        self.indexer_service = IndexerService()

        logger.info("=" * 80)
        logger.info("⏰ STARTING SCHEDULED INDEXER")
        logger.info("=" * 80)

        self.is_running = True
        
        # Start the main scheduler loop
        await self._run_scheduler()

    async def _run_scheduler(self):
        """Main scheduler loop that runs periodic indexing tasks."""
        logger.info("📅 Scheduler started. Will check collections every 5 minutes.")
        
        while self.is_running and not self.shutdown_event.is_set():
            try:
                await self._run_collection_indexing()

                # Wait 5 minutes before next run
                logger.info("⏳ Next scheduled run in 5 minutes...")
                await asyncio.sleep(300)  # 5 minutes
                
            except asyncio.CancelledError:
                logger.info("🛑 Scheduler cancelled, shutting down...")
                break
            except Exception as e:
                logger.error(f"❌ Scheduler error: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait 1 minute before retry

    async def _run_collection_indexing(self):
        """Index historical data and calculate comprehensive analytics for all listed collections."""
        try:
            # Get all listed collections
            collections = await sync_to_async(list)(
                NFTCollection.objects.filter(is_listed=True)
            )

            logger.info(f"📊 Starting scheduled indexing for {len(collections)} collections...")

            # Step 1: Fetch market stats from APIs + calculate blockchain volume for all collections
            for collection in collections:
                try:
                    logger.info(f"📊 Fetching market stats for {collection.name} ({collection.address[:16]}...)")

                    # Fetch API stats from Tensor/Magic Eden (marketplace-specific volumes)
                    # NOTE: Historical on-chain indexing (process_onchain_events) should NOT run periodically
                    # as it's expensive and meant for one-time backfills only
                    await self.indexer_service.fetch_and_store_all_market_stats(collection)

                    # Calculate cross-marketplace volume from our own NFTEvent data (90-95% accurate)
                    await self.indexer_service.calculate_and_store_blockchain_volume(collection)

                    # Stagger requests to avoid API rate limits
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"❌ Failed to fetch market stats for {collection.name}: {e}")
                    continue

            logger.info(f"✅ Completed fetching market stats + blockchain volume for {len(collections)} collections")

            # Step 2: Calculate comprehensive analytics (market + trait + wallet + trending/top traits)
            # This uses MetricsCalculationService.calculate_comprehensive_metrics() which:
            # - Updates market metrics (AggregatedCollectionStats)
            # - Updates trait analytics (TraitPerformanceScore) with activity-based skipping
            # - Calculates wallet prominence (WalletProminence, WalletBehaviorProfile)
            # - Calculates trending traits (TrendingTrait)
            # - Calculates top traits (TopTrait)
            logger.info("📊 Running comprehensive analytics calculation...")
            collection_addresses = [c.address for c in collections]

            result = await self.indexer_service.metrics_service.calculate_comprehensive_metrics(
                collection_addresses=collection_addresses
            )

            if result.get('success'):
                logger.info("✅ Comprehensive analytics calculation completed successfully")
                logger.info(f"   Summary: {result.get('message', 'No message')}")
            else:
                logger.error(f"❌ Comprehensive analytics calculation failed: {result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"❌ Collection indexing failed: {e}", exc_info=True)

    def handle(self, *args, **options):
        """Synchronous entry point for the management command."""
        
        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_shutdown)
        
        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            self.stdout.write("Scheduled indexer stopped manually.")

    def _handle_shutdown(self, signum, frame):
        """Trigger graceful shutdown."""
        logger.info("🛑 Shutdown signal received...")
        self.is_running = False
        self.shutdown_event.set()