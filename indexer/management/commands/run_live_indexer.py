# indexer/management/commands/run_live_indexer.py

import asyncio
import logging
import signal
from django.core.management.base import BaseCommand
from indexer.services import IndexerService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs the live WebSocket indexer for real-time transaction processing.'

    def __init__(self):
        super().__init__()
        self.shutdown_event = asyncio.Event()
        self.indexer_service = IndexerService()

    async def main(self):
        """Main async logic for live WebSocket processing."""
        logger.info("=" * 80)
        logger.info("🔴 STARTING LIVE WEBSOCKET INDEXER")
        logger.info("=" * 80)
        
        try:
            # Start the WebSocket subscription
            logger.info("📡 Connecting to Solana WebSocket for live transactions...")
            
            # This runs indefinitely, processing live events
            await self.indexer_service.subscribe_to_collection_activity(
                collection_address=None,  # Monitor all collections
                user_callback=self._process_live_event
            )
            
        except asyncio.CancelledError:
            logger.info("🛑 Live indexer shutting down gracefully...")
        except Exception as e:
            logger.error(f"❌ Live indexer crashed: {e}", exc_info=True)
            raise

    async def _process_live_event(self, event: dict):
        """Process a single live event from WebSocket."""
        event_id = event.get('signature') or event.get('event_id')
        if not event_id:
            return
        
        try:
            # Parse and store the event using the indexer service
            result = await self.indexer_service.parser.parse_and_store_event(event)
            if result:
                logger.debug(f"✅ Processed live event: {event_id[:16]}...")
        except Exception as e:
            logger.error(f"❌ Failed to process live event {event_id[:16]}...: {e}")

    def handle(self, *args, **options):
        """Synchronous entry point for the management command."""
        
        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_shutdown)
        
        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            self.stdout.write("Live indexer stopped manually.")

    def _handle_shutdown(self, signum, frame):
        """Trigger graceful shutdown."""
        self.shutdown_event.set()