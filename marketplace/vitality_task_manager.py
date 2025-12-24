# marketplace/vitality_task_manager.py

"""
Vitality Background Task Manager

Manages periodic recalculation of NFT and collection vitality scores based on
collection priority (VIP, ACTIVE, INACTIVE).

This is a dedicated task manager for vitality calculations, separate from the
indexer task manager, now refactored to be fully asynchronous.
"""

import asyncio
import logging
import sys
import os
import time
from datetime import timedelta
from collections import deque
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from django.utils import timezone
from asgiref.sync import sync_to_async

from nft_data.models import NFTCollection
from marketplace.vitality_service import VitalityCalculationService

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class VitalityTask:
    """A task for vitality calculation"""
    id: str
    name: str
    collection_address: str
    priority: TaskPriority
    created_at: object = None
    retry_count: int = 0
    max_retries: int = 2

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = timezone.now()


class VitalityTaskManager:
    """
    Asynchronous background task manager for periodic vitality recalculation.
    """

    def __init__(self):
        """Initialize the vitality task manager."""
        self.should_run_background_tasks = os.getenv('RUN_BACKGROUND_TASKS', 'true').lower() == 'true'

        if not self.should_run_background_tasks:
            logger.info("⏸️  VitalityTaskManager disabled (RUN_BACKGROUND_TASKS=false)")
            return

        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return

        self.vitality_service = VitalityCalculationService()

        # Use asyncio.Queue for inherent async safety
        self.task_queue = asyncio.Queue()
        self.task_history = deque(maxlen=500)
        self._active_tasks = set() # To prevent duplicate scheduling

        # Use asyncio.Event for control
        self.shutdown_event = asyncio.Event()
        self._tasks = []

        logger.info("✓ VitalityTaskManager initialized for asyncio.")

    async def start(self):
        """Start the vitality task manager's async tasks."""
        if self._tasks:
            logger.warning("VitalityTaskManager is already running.")
            return

        if not self.should_run_background_tasks:
            return

        logger.info("Starting VitalityTaskManager async tasks...")
        
        # Create asyncio tasks instead of threads
        self._tasks.append(asyncio.create_task(self._run_worker()))
        self._tasks.append(asyncio.create_task(self._run_scheduler()))

        logger.info("VitalityTaskManager started successfully.")

    async def stop(self):
        """Stop the vitality task manager gracefully."""
        logger.info("Stopping VitalityTaskManager...")
        self.shutdown_event.set()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        logger.info("VitalityTaskManager stopped.")

    async def _run_worker(self):
        """Main worker loop - processes tasks from the queue."""
        logger.info("Vitality worker task started.")
        while not self.shutdown_event.is_set():
            try:
                # Safely wait for and get a task from the queue
                task = await self.task_queue.get()
                await self._execute_task(task)
                self.task_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(5)
        logger.info("Vitality worker task stopped.")

    async def _run_scheduler(self):
        """Scheduler loop - adds vitality calculation tasks based on priority."""
        logger.info("Vitality scheduler task started.")
        while not self.shutdown_event.is_set():
            try:
                await self._schedule_vitality_tasks()
                # Use asyncio.sleep to not block the event loop
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
                await asyncio.sleep(60)
        logger.info("Vitality scheduler task stopped.")

    async def _schedule_vitality_tasks(self):
        """
        Schedule vitality calculation tasks based on collection priority.

        Collection priorities and intervals:
        - VIP: Every 5 minutes
        - ACTIVE: Every 30 minutes
        - INACTIVE: Every 120 minutes (2 hours)
        """
        now = timezone.now()

        # Use sync_to_async for the database query
        collections = await sync_to_async(list)(NFTCollection.objects.filter(is_listed=True))

        for collection in collections:
            # Determine recalculation interval based on priority
            if collection.priority_tier == 'VIP':
                interval_minutes, priority = 5, TaskPriority.HIGH
            elif collection.priority_tier == 'ACTIVE':
                interval_minutes, priority = 30, TaskPriority.MEDIUM
            else:  # INACTIVE
                interval_minutes, priority = 120, TaskPriority.LOW
            
            # Use await for the async check
            if await self._should_recalculate(collection, interval_minutes):
                task = VitalityTask(
                    id=f"vitality_{collection.address}_{int(now.timestamp())}",
                    name=f"Calculate Vitality: {collection.name}",
                    collection_address=collection.address,
                    priority=priority
                )
                await self.add_task(task)

    async def _should_recalculate(self, collection: NFTCollection, interval_minutes: int) -> bool:
        """Check if a collection needs vitality recalculation."""
        from marketplace.vitality_models import CollectionVitality
        try:
            # Use sync_to_async for the database query
            vitality = await sync_to_async(CollectionVitality.objects.get)(collection=collection)
            time_since_update = timezone.now() - vitality.updated_at
            return time_since_update >= timedelta(minutes=interval_minutes)
        except CollectionVitality.DoesNotExist:
            return True

    async def _execute_task(self, task: VitalityTask):
        """Execute a vitality calculation task."""
        task_start = time.monotonic()
        logger.info(f"Executing task: {task.name}")
        try:
            collection = await sync_to_async(NFTCollection.objects.get)(address=task.collection_address)

            # Assuming vitality_service will also be refactored to be async
            vitality = await self.vitality_service.calculate_collection_vitality(
                collection=collection,
                store_history=True
            )

            if vitality:
                execution_time = time.monotonic() - task_start
                self.task_history.append({
                    'task_id': task.id,
                    'task_name': task.name,
                    'collection': collection.name,
                    'vitality_score': float(vitality.vitality_score),
                    'status': 'success',
                    'duration_seconds': round(execution_time, 2),
                    'timestamp': timezone.now().isoformat()
                })
                logger.info(
                    f"Task completed: {task.name} - "
                    f"Vitality: {vitality.vitality_score}/100 - "
                    f"Duration: {execution_time:.2f}s"
                )
            else:
                raise Exception("Vitality calculation returned None (insufficient data).")

        except NFTCollection.DoesNotExist:
            logger.error(f"Collection not found: {task.collection_address}")
            self.task_history.append({
                'task_id': task.id, 'task_name': task.name, 'status': 'failed',
                'error': 'Collection not found', 'timestamp': timezone.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Task failed: {task.name} - Error: {e}", exc_info=True)
            self.task_history.append({
                'task_id': task.id, 'task_name': task.name, 'status': 'failed',
                'error': str(e), 'timestamp': timezone.now().isoformat()
            })
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                logger.info(f"Retrying task {task.name} (attempt {task.retry_count}) after delay...")
                await asyncio.sleep(5 * task.retry_count)
                await self.add_task(task)
        finally:
            self._active_tasks.discard(task.collection_address)

    async def add_task(self, task: VitalityTask):
        """Add a task to the queue if not already present."""
        if task.collection_address in self._active_tasks:
            logger.debug(f"Task for collection {task.collection_address} already queued, skipping.")
            return

        await self.task_queue.put(task)
        self._active_tasks.add(task.collection_address)
        logger.debug(f"Task added to queue: {task.name}")

    async def trigger_immediate_calculation(self, collection_address: str):
        """Trigger an immediate vitality calculation for a specific collection."""
        try:
            collection = await sync_to_async(NFTCollection.objects.get)(address=collection_address)
            task = VitalityTask(
                id=f"manual_vitality_{collection_address}_{int(timezone.now().timestamp())}",
                name=f"Manual Vitality Calculation: {collection.name}",
                collection_address=collection_address,
                priority=TaskPriority.CRITICAL
            )
            await self.add_task(task)
            logger.info(f"Manual vitality calculation triggered for {collection.name}")
            return True
        except NFTCollection.DoesNotExist:
            logger.error(f"Collection not found for manual trigger: {collection_address}")
            return False

    async def get_status(self) -> dict:
        """Get current status of the vitality task manager."""
        return {
            'is_running': not self.shutdown_event.is_set(),
            'queue_size': self.task_queue.qsize(),
            'history_size': len(self.task_history),
            'active_tasks_count': len(self._active_tasks),
            'recent_tasks': list(self.task_history)[-10:]
        }

# Global instance
vitality_task_manager = VitalityTaskManager()

async def get_vitality_task_manager_status():
    """Async helper to get status of the vitality task manager."""
    return await vitality_task_manager.get_status()