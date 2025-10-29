# system_health/management/commands/run_health_service.py

import asyncio
import logging
import signal
from django.core.management.base import BaseCommand
from system_health.background_task_manager import health_task_manager

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs the system health monitoring service.'

    def __init__(self):
        super().__init__()
        self.shutdown_event = asyncio.Event()

    async def main(self):
        """Main async logic for health monitoring."""
        logger.info("=" * 80)
        logger.info("🏥 STARTING HEALTH MONITORING SERVICE")
        logger.info("=" * 80)
        
        # Start the health task manager
        await health_task_manager.start()
        
        logger.info("✅ Health monitoring started")
        logger.info("   - System metrics: Every 5 minutes")
        logger.info("   - Failed transactions: Every 10 minutes")
        logger.info("   - Data anomalies: Every 15 minutes")
        logger.info("   - Daily report: 9:00 AM UTC")
        
        # Wait for shutdown signal
        await self.shutdown_event.wait()
        
        # Gracefully stop health monitoring
        logger.info("🛑 SHUTTING DOWN HEALTH MONITORING...")
        health_task_manager.stop()
        logger.info("✅ Health monitoring stopped gracefully")

    def handle(self, *args, **options):
        """Synchronous entry point for the management command."""
        
        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_shutdown)
        
        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            self.stdout.write("Health service stopped manually.")

    def _handle_shutdown(self, signum, frame):
        """Trigger graceful shutdown."""
        self.shutdown_event.set()