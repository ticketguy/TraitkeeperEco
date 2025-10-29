# /app/indexer/management/commands/run_background_service.py

import asyncio
import logging
import signal
from django.core.management.base import BaseCommand
from django.conf import settings
import redis.asyncio as redis
from core.api_provider.api_providers import APIProviderManager

# Import all the async task managers you want to run
from indexer.background_task_manager import background_task_manager
from marketplace.vitality_task_manager import vitality_task_manager
from system_health.background_task_manager import health_task_manager

logger = logging.getLogger(__name__)
REDIS_CHANNEL = "config_updates"

async def redis_config_listener():
    """Asynchronously listens to Redis for config update messages."""
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe(REDIS_CHANNEL)
        logger.info(f"🎧 Listening for configuration updates on Redis channel '{REDIS_CHANNEL}'...")
        
        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=None) # Listen forever
                if message and message.get("data") == "reload":
                    logger.info("✅ 'reload' signal received from Redis. Forcing provider reload.")
                    APIProviderManager().force_reload()
            except asyncio.CancelledError:
                logger.info("Redis listener is shutting down.")
                break
            except Exception as e:
                logger.error(f"Error in Redis listener: {e}", exc_info=True)
                await asyncio.sleep(5)


class Command(BaseCommand):
    help = 'Runs all asynchronous background services for TraitKeeper.'

    def __init__(self):
        super().__init__()
        self.tasks = []
        self.shutdown_event = asyncio.Event()

    async def main(self):
        """The core async logic for starting and managing all background services."""
        logger.info("=" * 80)
        logger.info("🚀 STARTING ALL ASYNCHRONOUS BACKGROUND SERVICES")
        logger.info("=" * 80)
        
        # Create a list of all the main tasks you want to run concurrently
        self.tasks = [
            asyncio.create_task(redis_config_listener()),
            asyncio.create_task(background_task_manager.start()),
            asyncio.create_task(vitality_task_manager.start()),
            asyncio.create_task(health_task_manager.start()),
        ]
        
        logger.info("✨ ALL BACKGROUND SERVICES RUNNING")
        
        # Wait until a shutdown signal is received
        await self.shutdown_event.wait()
        
        # Gracefully cancel all running tasks
        logger.info("🛑 SHUTTING DOWN BACKGROUND SERVICES...")
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("✨ ALL BACKGROUND SERVICES STOPPED GRACEFULLY")

    def handle(self, *args, **options):
        """The synchronous entry point for the management command."""
        
        # Set up signal handlers to trigger the async shutdown event
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_shutdown)
            
        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            self.stdout.write("Background services stopped manually.")

    def _handle_shutdown(self, signum, frame):
        """Sets the async event to trigger a graceful shutdown."""
        self.shutdown_event.set()