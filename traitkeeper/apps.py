# In /app/traitkeeper/apps.py

from django.apps import AppConfig
import logging
import os
import threading
import asyncio # Make sure this is imported

logger = logging.getLogger(__name__)


class TraitkeeperConfig(AppConfig):
    name = 'traitkeeper'
    verbose_name = 'TraitKeeper Core'

    def ready(self):
        """
        Called when Django is fully loaded. Start background tasks here.
        """
        run_background_tasks = os.getenv('RUN_BACKGROUND_TASKS', 'false').lower() == 'true'

        if run_background_tasks:
            logger.info("🔧 Starting background task managers...")
            self.start_vitality_manager()
        else:
            logger.info("⏭️  Background tasks disabled (RUN_BACKGROUND_TASKS=false)")

    def start_vitality_manager(self):
        """Start the vitality background task manager in a separate thread."""
        from marketplace.vitality_task_manager import vitality_task_manager

        def _run_async_tasks():
            """This function will be the target for our new thread."""
            try:
                # ✅ Use asyncio.run() to start the event loop and run the async start() method
                asyncio.run(vitality_task_manager.start())
                logger.info("✅ Vitality Task Manager started successfully")
            except Exception as e:
                logger.error(f"❌ Failed to start Vitality Task Manager: {e}", exc_info=True)

        # The thread will run our new target function
        thread = threading.Thread(target=_run_async_tasks, daemon=True, name="vitality-startup")
        thread.start()