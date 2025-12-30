# marketplace/management/commands/run_vitality_analytics_service.py

import asyncio
import logging
import signal
from django.core.management.base import BaseCommand

# Import vitality task manager
from marketplace.vitality_task_manager import vitality_task_manager
from admin_panel.heartbeat import ServiceHeartbeat

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs the vitality analytics background service for NFT and collection vitality calculations'

    def __init__(self):
        super().__init__()
        self.shutdown_event = asyncio.Event()
        self.tasks = []
        self.heartbeat = ServiceHeartbeat('vitality-analytics')

    async def heartbeat_loop(self):
        """Send heartbeat every 30 seconds."""
        while not self.shutdown_event.is_set():
            try:
                self.heartbeat.beat()
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(30)

    async def main(self):
        """Main async logic for vitality analytics service."""
        logger.info("=" * 80)
        logger.info("📊 STARTING VITALITY ANALYTICS SERVICE")
        logger.info("=" * 80)

        self.heartbeat.start()

        try:
            # Start heartbeat loop in background
            heartbeat_task = asyncio.create_task(self.heartbeat_loop())

            # Start vitality task manager
            self.tasks = [
                asyncio.create_task(vitality_task_manager.start(), name="VitalityManager"),
                heartbeat_task,
            ]

            logger.info("✅ Vitality analytics service started")
            logger.info("   - VIP collections: Every 5 minutes")
            logger.info("   - Active collections: Every 30 minutes")
            logger.info("   - Inactive collections: Every 2 hours")

            # Wait for shutdown signal
            await self.shutdown_event.wait()

            # Gracefully stop vitality analytics
            logger.info("🛑 SHUTTING DOWN VITALITY ANALYTICS SERVICE...")

            await vitality_task_manager.stop()

            for task in self.tasks:
                task.cancel()

            await asyncio.gather(*self.tasks, return_exceptions=True)

            logger.info("✅ Vitality analytics service stopped gracefully")

        except Exception as e:
            logger.error(f"❌ Vitality analytics crashed: {e}", exc_info=True)
            self.heartbeat.log_error(str(e))
            self.heartbeat.beat(state='failed')
            raise
        finally:
            self.heartbeat.stop()

    def handle(self, *args, **options):
        """Synchronous entry point for the management command."""
        
        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_shutdown)
        
        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            self.stdout.write("Vitality analytics service stopped manually.")

    def _handle_shutdown(self, signum, frame):
        """Trigger graceful shutdown."""
        self.shutdown_event.set()