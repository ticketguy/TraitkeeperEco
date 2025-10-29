# indexer/background_task_manager.py
import asyncio
import sys
import threading
import logging
import time
import os
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

from nft_data.models import NFTCollection
from indexer.services import IndexerService
# Use the central, refactored cache manager from the 'core' app
from core.cache_manager import cache_manager, CacheType

logger = logging.getLogger(__name__)

class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class Task:
    """A structured data class for tasks in the processing queue."""
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

class BackgroundTaskManager:
    """
    Orchestrates all background indexing and data processing tasks. It manages a
    priority-based queue, worker threads, and coordinates between the IndexerService
    and the site-wide CacheManager.
    """
    def __init__(self):
        # Check if background tasks should run (for microservices deployment)
        self.should_run_background_tasks = os.getenv('RUN_BACKGROUND_TASKS', 'true').lower() == 'true'

        if not self.should_run_background_tasks:
            logger.info("⏸️  BackgroundTaskManager disabled (RUN_BACKGROUND_TASKS=false)")
            self.is_running = False
            return

        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            self.is_running = False
            return

        self.indexer_service = IndexerService()
        self.cache_manager = cache_manager

        # Real-time processing state
        self.real_time_enabled = False
        # Task management structures
        self.task_queues = {p: deque() for p in TaskPriority}
        self.task_history = deque(maxlen=1000)
        # Control flags and threads
        self.is_running = False
        self.shutdown_event = threading.Event()
        self.worker_threads = []
        self.max_workers = 3

        logger.info("✓ BackgroundTaskManager initialized and integrated with core.cache_manager.")

    async def start(self):
        """Starts the background task manager and its worker threads."""
        if self.is_running:
            return
        self.is_running = True
        logger.info("Starting BackgroundTaskManager.")
        
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._run_worker, args=(f"worker-{i}",), daemon=True)
            worker.start()
            self.worker_threads.append(worker)
            
        await self._schedule_periodic_tasks()
        
        # ✅ Start WebSocket in thread (no async task needed)
        await self.start_real_time()
        
        logger.info(f"Started {len(self.worker_threads)} worker threads and initiated real-time subscriptions.")

    def stop(self):
        """Stops the background task manager gracefully."""
        logger.info("Stopping BackgroundTaskManager.")
        self.is_running = False
        self.real_time_enabled = False
        self.shutdown_event.set()
        for worker in self.worker_threads:
            worker.join(timeout=10)
        logger.info("BackgroundTaskManager stopped.")

    def _run_worker(self, worker_name: str):
        """The main loop for a worker thread, processing tasks from the queue."""
        logger.info(f"Starting worker: {worker_name}")
        while self.is_running:
            try:
                task = self._get_next_task()
                if task:
                    self._execute_task(task, worker_name)
                else:
                    time.sleep(0.1)
            except Exception as e:
                logger.error(f"Worker {worker_name} error: {e}", exc_info=True)
                time.sleep(1)

    def _get_next_task(self) -> Optional[Task]:
        """Gets the next task from the queues based on priority."""
        for priority in sorted(self.task_queues.keys(), key=lambda p: p.value, reverse=True):
            if self.task_queues[priority]:
                task = self.task_queues[priority].popleft()
                if task.scheduled_for <= timezone.now():
                    return task
                else:
                    self.task_queues[priority].appendleft(task)
        return None

    def _execute_task(self, task: Task, worker_name: str):
        """Executes a single task, handling async functions and retries."""
        task_start = time.time()
        logger.info(f"Worker {worker_name} executing task: {task.name}")
        try:
            # Safely execute sync or async functions from a thread
            if asyncio.iscoroutinefunction(task.function):
                async_to_sync(task.function)(*task.args, **task.kwargs)
            else:
                task.function(*task.args, **task.kwargs)
            
            execution_time = time.time() - task_start
            self.task_history.append({'name': task.name, 'status': 'success', 'duration_s': execution_time})
            
        except Exception as e:
            logger.error(f"Task {task.name} failed: {e}", exc_info=True)
            self.task_history.append({'name': task.name, 'status': 'failed', 'error': str(e)})
            
            # Handle retry logic
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.scheduled_for = timezone.now() + timedelta(minutes=task.retry_count * 2) # Exponential backoff
                self.add_task(task)
                logger.info(f"Retrying task {task.name} (attempt {task.retry_count}).")

    def add_task(self, task: Task):
        """Adds a task to the appropriate priority queue."""
        self.task_queues[task.priority].append(task)

    async def _schedule_periodic_tasks(self):
        """Schedules the recurring jobs for the indexer."""
        self.add_task(Task(
            id="periodic_collection_indexing",
            name="Periodic Collection Indexing",
            function=self._run_collection_indexing,
            priority=TaskPriority.HIGH
        ))
        self.add_task(Task(
            id="failed_transaction_retry",
            name="Failed Transaction Retry",
            function=self._run_failed_transaction_retry,
            priority=TaskPriority.MEDIUM,
            scheduled_for=timezone.now() + timedelta(minutes=10)
        ))

    async def _run_collection_indexing(self):
        try:
            collections = await sync_to_async(list)(NFTCollection.objects.filter(is_listed=True))
            logger.info(f"Starting periodic indexing for {len(collections)} collections.")
            for collection in collections:
                logger.info(f"Processing historical events for {collection.address}")
                await self.indexer_service.process_onchain_events(collection.address)

               
                logger.info(f"Updating metrics after historical scan for {collection.address}")
                await self.indexer_service.update_collection_after_retrieval(collection.address)
                logger.info(f"Finished processing historical events for {collection.address}")

                await asyncio.sleep(2) # Stagger requests
        finally:
            # Reschedule this task
            self.add_task(Task(id="periodic_collection_indexing", name="Periodic Collection Indexing", function=self._run_collection_indexing, priority=TaskPriority.HIGH, scheduled_for=timezone.now() + timedelta(minutes=15)))

    async def _run_failed_transaction_retry(self):
        """Periodically retries a batch of previously failed transactions."""
        try:
            # Delegate the work to the IndexerService
            await self.indexer_service.retry_failed_transactions()
        finally:
            # Reschedule this task to run again in 30 minutes
            self.add_task(Task(id="failed_transaction_retry", name="Failed Transaction Retry", function=self._run_failed_transaction_retry, priority=TaskPriority.MEDIUM, scheduled_for=timezone.now() + timedelta(minutes=30)))

    async def _process_event_once(self, event: dict):
        """
        Processes a real-time event, using the central cache for deduplication
        to ensure it's processed only once across all servers and restarts.
        """
        event_id = event.get('signature') or event.get('event_id')
        if not event_id:
            return

        # Use the central CacheManager for persistent, scalable deduplication
        cache_key = self.cache_manager._get_key_with_prefix(CacheType.GLOBAL, f"processed_event:{event_id}")
        
        is_processed = await self.cache_manager.get(cache_key)
        if is_processed:
            logger.debug(f"Event {event_id} already processed (cache hit), skipping.")
            return

        # Call the public method on the specialized parser service. This respects our new architecture.
        result = await self.indexer_service.parser.parse_and_store_event(event)
        
        if result:
            # If successful, mark this event as processed in the cache with a 2-hour TTL.
            # The TTL prevents the cache from growing infinitely with old event IDs.
            await self.cache_manager.set(cache_key, True, ttl=7200)

    async def start_real_time(self):
        """Starts the real-time event subscription that feeds the processing pipeline."""
        if self.real_time_enabled:
            return
        
        try:
            self.real_time_enabled = True
            logger.info("Starting real-time event subscriptions...")
            
            # ✅ ADD ERROR HANDLING HERE
            try:
                await self.indexer_service.subscribe_to_collection_activity(
                    collection_address=None,
                    user_callback=self._process_event_once
                )
            except Exception as e:
                logger.error(f"❌ WEBSOCKET CRASHED: {e}", exc_info=True)
                raise  # Re-raise to see full traceback
                
        except Exception as e:
            logger.error(f"Failed to start real-time subscriptions: {e}", exc_info=True)
            self.real_time_enabled = False

    def get_status(self) -> dict:
        """
        Gathers and returns a snapshot of the manager's current operational status.
        This data is used to populate the admin panel dashboard.
        """
        # Calculate the total number of tasks waiting in all priority queues.
        total_pending_tasks = sum(len(queue) for queue in self.task_queues.values())
        
        return {
            'is_running': self.is_running,
            'real_time_enabled': self.real_time_enabled,
            'worker_count': len(self.worker_threads),
            'total_pending_tasks': total_pending_tasks,
            'task_history_size': len(self.task_history),
            'task_queues': {
                # Provide a count of tasks in each priority queue.
                priority.name: len(queue) 
                for priority, queue in self.task_queues.items()
            },
        }

# Global instance and control functions
task_manager = BackgroundTaskManager() if not ('migrate' in sys.argv or 'makemigrations' in sys.argv) else None


def get_task_manager_status():
    """Gets the status from the global task manager instance."""
    if task_manager:
        return task_manager.get_status()
    return {'is_running': False, 'status': 'disabled'}


background_task_manager = BackgroundTaskManager()