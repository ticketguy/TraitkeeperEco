"""
Service Heartbeat Utility for TraitKeeper Background Tasks
Allows services to report their status to Redis for monitoring.
"""

import time
import logging
from datetime import datetime
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class ServiceHeartbeat:
    """
    Manages heartbeat reporting for background services.

    Usage in your management commands:
        from admin_panel.heartbeat import ServiceHeartbeat

        heartbeat = ServiceHeartbeat('indexer-live')
        heartbeat.start()

        try:
            # Your service logic here
            while True:
                # Do work...
                heartbeat.beat()  # Update heartbeat
                time.sleep(10)
        finally:
            heartbeat.stop()
    """

    def __init__(self, service_key, heartbeat_interval=30):
        """
        Initialize heartbeat for a service.

        Args:
            service_key: Unique identifier for the service (e.g., 'indexer-live')
            heartbeat_interval: Seconds between heartbeats (default: 30)
        """
        self.service_key = service_key
        self.heartbeat_interval = heartbeat_interval
        self.cache_key = f"service_heartbeat:{service_key}"
        self.start_time = None
        self.error_log = []

    def start(self):
        """Mark service as started."""
        self.start_time = time.time()
        self.beat(state='starting')
        logger.info(f"Service {self.service_key} heartbeat started")

    def beat(self, state='healthy', message=None):
        """
        Send a heartbeat to Redis.

        Args:
            state: Current state of the service ('healthy', 'degraded', 'starting', etc.)
            message: Optional status message
        """
        try:
            uptime = int(time.time() - self.start_time) if self.start_time else 0

            heartbeat_data = {
                'timestamp': timezone.now().isoformat(),
                'state': state,
                'uptime': uptime,
                'message': message,
                'errors': self.error_log[-10:],  # Keep last 10 errors
            }

            # Store heartbeat in Redis with 120 second expiry (2x interval)
            cache.set(self.cache_key, heartbeat_data, timeout=120)

        except Exception as e:
            logger.error(f"Failed to send heartbeat for {self.service_key}: {e}")

    def log_error(self, error_message):
        """
        Log an error for this service.

        Args:
            error_message: The error message to log
        """
        error_entry = {
            'message': str(error_message),
            'timestamp': datetime.now().isoformat()
        }
        self.error_log.append(error_entry)

        # Keep only last 20 errors in memory
        if len(self.error_log) > 20:
            self.error_log = self.error_log[-20:]

        # Also log to system error cache
        try:
            system_errors = cache.get('system_error_logs', [])
            system_errors.append({
                'container': self.service_key,
                'message': str(error_message),
                'timestamp': datetime.now().isoformat()
            })
            # Keep only last 50 system errors
            cache.set('system_error_logs', system_errors[-50:], timeout=3600)  # 1 hour
        except Exception as e:
            logger.error(f"Failed to log error to system cache: {e}")

    def stop(self):
        """Mark service as stopped."""
        try:
            self.beat(state='stopped', message='Service shutdown')
            logger.info(f"Service {self.service_key} heartbeat stopped")
        except Exception as e:
            logger.error(f"Error stopping heartbeat for {self.service_key}: {e}")


def report_service_heartbeat(service_key, state='healthy', errors=None):
    """
    Simplified one-time heartbeat reporting.

    Use this for simple scripts that don't need continuous heartbeat.

    Args:
        service_key: Service identifier
        state: Current state
        errors: List of error messages (optional)
    """
    try:
        cache_key = f"service_heartbeat:{service_key}"
        heartbeat_data = {
            'timestamp': timezone.now().isoformat(),
            'state': state,
            'uptime': 0,
            'message': None,
            'errors': errors or [],
        }
        cache.set(cache_key, heartbeat_data, timeout=120)
    except Exception as e:
        logger.error(f"Failed to report heartbeat for {service_key}: {e}")
