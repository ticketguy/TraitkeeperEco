# indexer/management/commands/run_incremental_indexer.py
"""
Incremental transaction indexer - catches missed transactions.

This runs periodically to fetch recent blockchain transactions that may have been
missed by the live webhook. Unlike full historical backfills, this only fetches
transactions from the last 24-48 hours.

Usage:
    python manage.py run_incremental_indexer
"""

import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone as dt_timezone
from django.core.management.base import BaseCommand
from django.utils import timezone
from asgiref.sync import sync_to_async
from nft_data.models import NFTCollection
from indexer.services import IndexerService
from admin_panel.heartbeat import ServiceHeartbeat

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Runs incremental indexing to catch missed transactions'

    def __init__(self):
        super().__init__()
        self.shutdown_event = asyncio.Event()
        self.indexer_service = IndexerService()
        self.is_running = False
        self.heartbeat = ServiceHeartbeat('indexer-incremental')

    async def heartbeat_loop(self):
        """Send heartbeat every 30 seconds."""
        while self.is_running and not self.shutdown_event.is_set():
            try:
                self.heartbeat.beat()
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(30)

    async def main(self):
        """Main async logic for incremental indexing."""
        logger.info("=" * 80)
        logger.info("⏰ STARTING INCREMENTAL TRANSACTION INDEXER")
        logger.info("=" * 80)

        self.heartbeat.start()
        self.is_running = True

        try:
            # Start heartbeat loop in background
            heartbeat_task = asyncio.create_task(self.heartbeat_loop())

            # Start the main scheduler loop
            await self._run_scheduler()
        except Exception as e:
            logger.error(f"❌ Incremental indexer crashed: {e}", exc_info=True)
            self.heartbeat.log_error(str(e))
            self.heartbeat.beat(state='failed')
            raise
        finally:
            self.heartbeat.stop()

    async def _run_scheduler(self):
        """Main scheduler loop that runs incremental indexing."""
        logger.info("📅 Incremental indexer started. Will check for missed transactions every 4 hours.")

        while self.is_running and not self.shutdown_event.is_set():
            try:
                await self._run_incremental_indexing()

                # Wait 4 hours before next run
                logger.info("⏳ Next incremental run in 4 hours...")
                await asyncio.sleep(14400)  # 4 hours

            except asyncio.CancelledError:
                logger.info("🛑 Incremental indexer cancelled, shutting down...")
                break
            except Exception as e:
                logger.error(f"❌ Incremental indexer error: {e}", exc_info=True)
                await asyncio.sleep(300)  # Wait 5 minutes before retry

    async def _run_incremental_indexing(self):
        """Fetch recent transactions for all collections to catch missed events."""
        try:
            # Get all listed collections
            collections = await sync_to_async(list)(
                NFTCollection.objects.filter(is_listed=True)
            )

            logger.info(f"🔍 Starting incremental indexing for {len(collections)} collections...")

            for collection in collections:
                try:
                    logger.info(f"🔍 Checking recent transactions for {collection.name}")

                    # Fetch ONLY recent transactions (last 24 hours)
                    # This is much lighter than full historical indexing
                    await self._fetch_recent_transactions(collection)

                    # Stagger requests to avoid API rate limits
                    await asyncio.sleep(5)

                except Exception as e:
                    logger.error(f"❌ Failed incremental indexing for {collection.name}: {e}")
                    continue

            logger.info(f"✅ Completed incremental indexing for {len(collections)} collections")

        except Exception as e:
            logger.error(f"❌ Incremental indexing failed: {e}", exc_info=True)

    async def _fetch_recent_transactions(self, collection):
        """Fetch only recent transactions (last 24-48 hours) for a collection."""
        try:
            # Get provider
            provider = await self.indexer_service.provider_manager.get_rpc_provider(
                collection.address
            )
            if not provider:
                logger.warning(f"No provider available for {collection.name}")
                return

            # Fetch recent signatures (limit to ~100 for last 24 hours)
            # This is WAY lighter than the 1000 limit used for historical backfills
            logger.info(f"Fetching recent signatures for {collection.name}...")
            signatures_data = await provider.get_signatures_for_address(
                collection.address,
                limit=100  # Only recent transactions, not 1000!
            )

            if not signatures_data:
                logger.info(f"No recent transactions for {collection.name}")
                return

            # Filter to only last 24 hours
            cutoff_time = timezone.now() - timedelta(hours=24)
            recent_sigs = []

            for sig_data in signatures_data:
                # Check if transaction is within last 24 hours
                block_time = sig_data.get('blockTime')
                if block_time:
                    tx_time = datetime.fromtimestamp(block_time, tz=dt_timezone.utc)
                    if tx_time >= cutoff_time:
                        recent_sigs.append(sig_data['signature'])

            if not recent_sigs:
                logger.info(f"No transactions in last 24h for {collection.name}")
                return

            logger.info(f"Found {len(recent_sigs)} recent signatures for {collection.name}")

            # Fetch and parse the transactions
            transactions = await provider.get_transactions(recent_sigs)

            for tx in transactions:
                if tx:
                    await self.indexer_service.parser.parse_and_store_event(tx)

            logger.info(f"✅ Processed {len(recent_sigs)} recent transactions for {collection.name}")

        except Exception as e:
            logger.error(f"Failed to fetch recent transactions for {collection.name}: {e}", exc_info=True)

    def handle(self, *args, **options):
        """Synchronous entry point for the management command."""

        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_shutdown)

        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            self.stdout.write("Incremental indexer stopped manually.")

    def _handle_shutdown(self, signum, frame):
        """Trigger graceful shutdown."""
        logger.info("🛑 Shutdown signal received...")
        self.is_running = False
        self.shutdown_event.set()
