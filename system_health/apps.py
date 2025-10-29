# system_health/apps.py
from django.apps import AppConfig
import threading
import logging

logger = logging.getLogger(__name__)

class SystemHealthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'system_health'
    
    def ready(self):
        """Start health monitoring when Django starts"""
        import os
        import sys
        
        skip_commands = ['migrate', 'makemigrations', 'shell', 'shell_plus', 'collectstatic', 'test']
        if any(cmd in sys.argv for cmd in skip_commands):
            return
            
        if (not getattr(self, '_health_started', False) and 
            (os.environ.get('RUN_MAIN') == 'true' or 'waitress-serve' in ' '.join(sys.argv))):
            
            self._health_started = True
            
            def start_health_monitoring():
                try:
                    from .background_task_manager import start_health_monitoring
                    start_health_monitoring()
                    logger.info("System health monitoring started")
                except Exception as e:
                    logger.error(f"Failed to start health monitoring: {e}")
            
            health_thread = threading.Thread(target=start_health_monitoring, daemon=True)
            health_thread.start()