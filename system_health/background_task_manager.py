import asyncio
import threading
import logging
import time
import os
import sys
import django
from django.utils import timezone
from datetime import datetime, timedelta
from asgiref.sync import sync_to_async, async_to_sync
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional
from enum import Enum

# Configure Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'traitkeeper.settings')
django.setup()

# --- MODIFIED IMPORTS ---
# Centralized service is now used for all notifications
from notifications.services import NotificationService
# Direct model imports are no longer needed for notifications
# from admin_panel.models import AdminUser
# from notifications.models import AdminNotification

from indexer.models import FailedTransaction, CollectionMarketStats
from nft_data.models import NFTCollection
import psutil

logger = logging.getLogger(__name__)

class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class HealthTask:
    id: str
    name: str
    function: Callable
    args: tuple = ()
    kwargs: dict = None
    priority: TaskPriority = TaskPriority.MEDIUM
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = None
    scheduled_for: datetime = None
    
    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}
        if self.created_at is None:
            self.created_at = timezone.now()
        if self.scheduled_for is None:
            self.scheduled_for = timezone.now()

class SystemHealthTaskManager:
    """Background task manager for system health monitoring and alerts."""
    
    def __init__(self):
        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            logger.info("Migration detected, skipping background task initialization.")
            self.is_running = False
            return

        self.task_queues = {p: deque() for p in TaskPriority}
        self.task_history = deque(maxlen=500)
        self.is_running = False
        self.shutdown_event = threading.Event()
        self.worker_thread = None
        logger.info("SystemHealthTaskManager initialized.")

    async def start(self):
        """Start the system health task manager."""
        if self.is_running:
            return
            
        self.is_running = True
        logger.info("Starting SystemHealthTaskManager.")
        
        self.worker_thread = threading.Thread(target=self._run_worker, name="HealthWorker", daemon=True)
        self.worker_thread.start()
        
        await self._schedule_initial_tasks()
        logger.info("SystemHealthTaskManager started.")

    def stop(self):
        """Stop the task manager."""
        if not self.is_running:
            return
        logger.info("Stopping SystemHealthTaskManager.")
        self.is_running = False
        self.shutdown_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=5)

    def _run_worker(self):
        """Worker thread for health tasks."""
        logger.info("Health worker thread started.")
        while self.is_running:
            try:
                task = self._get_next_task()
                if task:
                    self._execute_task(task)
                else:
                    time.sleep(1) # Wait if no tasks are ready
            except Exception as e:
                logger.error(f"Health worker loop error: {e}", exc_info=True)
                time.sleep(5)

    def _get_next_task(self) -> Optional[HealthTask]:
        """Get next task by priority."""
        for priority in sorted(self.task_queues.keys(), key=lambda p: p.value, reverse=True):
            if self.task_queues[priority]:
                task = self.task_queues[priority].popleft()
                if task.scheduled_for <= timezone.now():
                    return task
                else:
                    self.task_queues[priority].appendleft(task) # Put it back if not ready
        return None

    def _execute_task(self, task: HealthTask):
        """Execute a single task with proper async/sync handling."""
        task_start = time.time()
        logger.info(f"Executing task: {task.name} (ID: {task.id})")
        
        try:
            if asyncio.iscoroutinefunction(task.function):
                sync_function = async_to_sync(task.function)
                result = sync_function(*task.args, **task.kwargs)
            else:
                result = task.function(*task.args, **task.kwargs)
            
            execution_time = time.time() - task_start
            logger.info(f"Task {task.name} completed in {execution_time:.2f}s.")
            self._record_task_history(task, 'success', execution_time)
            return result
            
        except Exception as e:
            execution_time = time.time() - task_start
            logger.error(f"Task {task.name} failed after {execution_time:.2f}s: {e}", exc_info=True)
            self._record_task_history(task, 'failed', execution_time, str(e))
            self._handle_task_failure(task)

    def _handle_task_failure(self, task: HealthTask):
        """Handle retry logic for a failed task."""
        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.scheduled_for = timezone.now() + timedelta(seconds=60 * task.retry_count) # Exponential backoff
            logger.info(f"Retrying task {task.name} (attempt {task.retry_count}/{task.max_retries}). Next run in {60 * task.retry_count}s.")
            self.add_task(task)
        else:
            logger.error(f"Task {task.name} failed permanently after {task.max_retries} retries.")
            async_to_sync(self._create_admin_notification)(
                subject=f"CRITICAL: Task Failed Permanently",
                message=f"The background task '{task.name}' failed after {task.max_retries} retries and will not be attempted again. Please investigate.",
                notification_type='system_alert',
                severity='error',
            )

    def _record_task_history(self, task: HealthTask, status: str, duration: float, error: str = None):
        """Record the outcome of a task."""
        history_entry = {
            'task_id': task.id, 'name': task.name, 'status': status,
            'execution_time': duration, 'completed_at': timezone.now().isoformat(),
        }
        if error:
            history_entry['error'] = error
        self.task_history.append(history_entry)

    def add_task(self, task: HealthTask):
        """Add task to the appropriate priority queue."""
        self.task_queues[task.priority].append(task)


    def get_task_history(self) -> list:
        """Returns a thread-safe copy of the task history."""
        # Creating a list from the deque creates a copy, preventing race conditions.
        return list(self.task_history)

    async def _schedule_initial_tasks(self):
        """Schedule all recurring health monitoring tasks."""
        now = timezone.now()

        # Ecosystem health snapshot - Every 15 minutes
        self.add_task(HealthTask(id="ecosystem_health_snapshot", name="Ecosystem Health Snapshot", function=self._capture_ecosystem_snapshot, priority=TaskPriority.HIGH))

        # System metrics check - Every 5 minutes
        self.add_task(HealthTask(id="system_metrics_check", name="System Metrics Check", function=self._check_system_metrics, priority=TaskPriority.HIGH))

        # Failed transaction monitoring - Every 10 minutes
        self.add_task(HealthTask(id="failed_transaction_monitor", name="Failed Transaction Monitor", function=self._monitor_failed_transactions, priority=TaskPriority.MEDIUM))

        # Data anomaly detection - Every 15 minutes
        self.add_task(HealthTask(id="data_anomaly_detection", name="Data Anomaly Detection", function=self._detect_data_anomalies, priority=TaskPriority.MEDIUM))

        # Daily health report - Schedules itself to run at 9 AM UTC
        self.add_task(HealthTask(id="daily_health_report", name="Daily Health Report", function=self._send_daily_health_report, priority=TaskPriority.LOW))

        # Health data cleanup - Daily at midnight
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        self.add_task(HealthTask(id="health_data_cleanup", name="Health Data Cleanup", function=self._cleanup_old_health_data, priority=TaskPriority.LOW, scheduled_for=next_midnight))

        logger.info("Initial health tasks have been scheduled.")

    async def _check_system_metrics(self):
        """Monitor system performance metrics and reschedule itself."""
        try:
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory().percent
            if cpu > 80 or mem > 85:
                await self._create_admin_notification(
                    subject="System Performance Alert",
                    message=f"One or more system metrics have exceeded thresholds. CPU: {cpu}%, Memory: {mem}%",
                    notification_type='server_load',
                    severity='warning',
                )
        finally:
            self.add_task(HealthTask(id="system_metrics_check", name="System Metrics Check", function=self._check_system_metrics, priority=TaskPriority.HIGH, scheduled_for=timezone.now() + timedelta(minutes=5)))

    async def _monitor_failed_transactions(self):
        """Monitor failed transaction accumulation and reschedule itself."""
        try:
            failures = await sync_to_async(FailedTransaction.objects.filter(created_at__gte=timezone.now() - timedelta(hours=1)).count)()
            if failures >= 10:
                await self._create_admin_notification(
                    subject="High Transaction Failure Rate",
                    message=f"The system recorded {failures} failed transactions in the last hour. Please check the indexer logs.",
                    notification_type='performance_issue',
                    severity='warning',
                )
        finally:
            self.add_task(HealthTask(id="failed_transaction_monitor", name="Failed Transaction Monitor", function=self._monitor_failed_transactions, priority=TaskPriority.MEDIUM, scheduled_for=timezone.now() + timedelta(minutes=10)))

    async def _detect_data_anomalies(self):
        """Detect data anomalies and reschedule itself."""
        try:
            zero_floor_stats = await sync_to_async(list)(
                CollectionMarketStats.objects.filter(floor_price=0, total_supply__gt=0, timestamp__gte=timezone.now() - timedelta(hours=1))
                .select_related('collection').values_list('collection__name', flat=True)
            )
            if zero_floor_stats:
                names = ", ".join(list(zero_floor_stats)[:3])
                await self._create_admin_notification(
                    subject="Data Anomaly: Zero Floor Price",
                    message=f"The following collections have a supply but report a zero floor price: {names}.",
                    notification_type='data_anomaly',
                    severity='warning',
                )
        finally:
            self.add_task(HealthTask(id="data_anomaly_detection", name="Data Anomaly Detection", function=self._detect_data_anomalies, priority=TaskPriority.MEDIUM, scheduled_for=timezone.now() + timedelta(minutes=15)))

    async def _send_daily_health_report(self):
        """Triggers the daily health report and reschedules for the next day."""
        try:
            await sync_to_async(NotificationService.send_daily_system_health_report)()
        finally:
            now = timezone.now()
            next_run = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            self.add_task(HealthTask(id="daily_health_report", name="Daily Health Report", function=self._send_daily_health_report, priority=TaskPriority.LOW, scheduled_for=next_run))

    async def _capture_ecosystem_snapshot(self):
        """Capture ecosystem health snapshot and reschedule itself."""
        try:
            from .utils import capture_ecosystem_health_snapshot
            snapshot = await sync_to_async(capture_ecosystem_health_snapshot)()
            logger.info(f"Ecosystem health snapshot captured: {snapshot.status}")

            # Send critical alerts if status is critical
            if snapshot.status == 'CRITICAL':
                await self._create_admin_notification(
                    subject="CRITICAL: Ecosystem Health Alert",
                    message=f"Ecosystem health is CRITICAL. Active alerts: {snapshot.alert_count}. Check admin dashboard immediately.",
                    notification_type='system_alert',
                    severity='critical',
                )
        except Exception as e:
            logger.error(f"Failed to capture ecosystem health snapshot: {e}", exc_info=True)
        finally:
            # Reschedule for 15 minutes from now
            self.add_task(HealthTask(
                id="ecosystem_health_snapshot",
                name="Ecosystem Health Snapshot",
                function=self._capture_ecosystem_snapshot,
                priority=TaskPriority.HIGH,
                scheduled_for=timezone.now() + timedelta(minutes=15)
            ))

    async def _cleanup_old_health_data(self):
        """Clean up old health data and reschedule for next day."""
        try:
            from .utils import cleanup_old_health_records
            deleted_count = await sync_to_async(cleanup_old_health_records)(days=30)
            logger.info(f"Cleaned up {deleted_count} old health records.")
        except Exception as e:
            logger.error(f"Failed to cleanup old health data: {e}", exc_info=True)
        finally:
            # Reschedule for next midnight
            now = timezone.now()
            next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            self.add_task(HealthTask(
                id="health_data_cleanup",
                name="Health Data Cleanup",
                function=self._cleanup_old_health_data,
                priority=TaskPriority.LOW,
                scheduled_for=next_midnight
            ))

    async def _create_admin_notification(self, subject: str, message: str, notification_type: str, severity: str = 'info'):
        """Creates an admin notification by calling the centralized NotificationService."""
        try:
            await sync_to_async(NotificationService.create_admin_notification)(
                subject=subject,
                message=message,
                notification_type=notification_type,
                severity=severity,
            )
            logger.info(f"Dispatched admin notification via service: '{subject}'")
        except Exception as e:
            logger.error(f"Failed to dispatch admin notification via service: {e}")

# Global instance and control functions
health_task_manager = SystemHealthTaskManager() if not ('migrate' in sys.argv or 'makemigrations' in sys.argv) else None

def start_health_monitoring():
    if health_task_manager:
        async_to_sync(health_task_manager.start)()

def stop_health_monitoring():
    if health_task_manager:
        health_task_manager.stop()

def get_health_status():
    """Gets the status from the global task manager instance."""
    if health_task_manager:
        return health_task_manager.get_status()
    return {'is_running': False, 'status': 'disabled'}


health_task_manager = SystemHealthTaskManager()