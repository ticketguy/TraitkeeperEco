# indexer/apps.py
from django.apps import AppConfig
from django.conf import settings
import logging
import threading
import os
import sys

logger = logging.getLogger(__name__)

class IndexerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'indexer'
    
    # A flag to ensure the startup code runs only once
    tasks_started = False

    def ready(self):
        """
        This method is called by Django when the app is ready.
        It's the ideal place to initialize background processes.
        """
        # --- Master Switch ---
        # 1. Check our setting from settings.py first. If it's False, do nothing.
        if not getattr(settings, 'RUN_INDEXER_BACKGROUND_TASKS', False):
            logger.info("Indexer background tasks are disabled in settings.py.")
            return

        # --- Environment Checks ---
        # 2. Skip initialization for management commands like migrations, shell, etc.
        skip_commands = ['migrate', 'makemigrations', 'shell', 'collectstatic', 'test']
        if any(cmd in sys.argv for cmd in skip_commands):
            return

        # 3. Ensure this code runs only once in the main process, not the reloader process.
        # This is the standard check for the Django development server.
        is_main_process = os.environ.get('RUN_MAIN') == 'true'
        if not is_main_process:
            return

        # 4. Prevent starting the tasks multiple times if ready() is called again.
        if self.tasks_started:
            return

        logger.info("Starting Indexer background tasks in a separate thread...")
        
        # Start the background tasks in a separate, non-blocking thread.
        background_thread = threading.Thread(target=self._start_tasks, daemon=True)
        background_thread.start()
        self.tasks_started = True

    def _start_tasks(self):
        """A helper method to import and run the task manager's start function."""
        try:
            from .background_task_manager import start_background_tasks
            start_background_tasks()
            logger.info("✅ Indexer background task manager started successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to start Indexer background task manager: {e}", exc_info=True)