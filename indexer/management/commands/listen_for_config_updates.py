# /app/indexer/management/commands/listen_for_config_updates.py

import asyncio
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
import redis.asyncio as redis

# Import the manager that has the force_reload() method
from core.api_provider.api_providers import APIProviderManager
from admin_panel.heartbeat import ServiceHeartbeat

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Listens to a Redis channel for configuration update signals and reloads providers."

    def __init__(self):
        super().__init__()
        self.heartbeat = ServiceHeartbeat('config-listener')
        self.heartbeat_counter = 0

    async def main(self):
        """The core async logic for the listener."""
        # The channel name must match the one in your signals.py
        channel_name = "config_updates"

        logger.info("🎧 STARTING CONFIG UPDATE LISTENER")
        self.heartbeat.start()

        try:
            # Connect to Redis using the async client
            redis_client = redis.from_url(settings.REDIS_URL)

            async with redis_client.pubsub() as pubsub:
                # Subscribe to the channel
                await pubsub.subscribe(channel_name)
                logger.info(f"📡 Subscribed to Redis channel '{channel_name}'. Waiting for reload signals...")

                # Start an infinite loop to listen for messages
                while True:
                    try:
                        # Wait for a message to be published on the channel
                        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

                        if message and message["data"] == b"reload":
                            logger.info("✅ 'reload' signal received from Redis.")

                            # Get the APIProviderManager instance and call force_reload()
                            manager = APIProviderManager()
                            manager.force_reload()

                            logger.info("✅ Provider cache has been successfully reloaded.")

                        # Send heartbeat every 30 iterations (30 seconds)
                        self.heartbeat_counter += 1
                        if self.heartbeat_counter >= 30:
                            self.heartbeat.beat()
                            self.heartbeat_counter = 0

                    except asyncio.TimeoutError:
                        # This is expected if no message is received within the timeout
                        continue
                    except Exception as e:
                        logger.error(f"Error in Redis listener: {e}", exc_info=True)
                        self.heartbeat.log_error(str(e))
                        self.heartbeat.beat(state='degraded')
                        # Wait a bit before retrying to prevent rapid-fire errors
                        await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"❌ Config listener crashed: {e}", exc_info=True)
            self.heartbeat.log_error(str(e))
            self.heartbeat.beat(state='failed')
            raise
        finally:
            self.heartbeat.stop()

    def handle(self, *args, **options):
        """The entry point for the management command."""
        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            self.stdout.write("Listener stopped manually.")