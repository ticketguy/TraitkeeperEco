# Heartbeat System Integration Guide

The heartbeat system allows your background services to report their status to the Task Manager dashboard via Redis.

## Overview

Each background service reports a "heartbeat" every 30 seconds to Redis. The Task Manager dashboard reads these heartbeats to display service health.

**Benefits:**
- No Docker socket access required
- Works in containerized environments
- Real-time service monitoring
- Automatic error tracking
- Simple integration

---

## Quick Start

### 1. Basic Integration Pattern

```python
from django.core.management.base import BaseCommand
from admin_panel.heartbeat import ServiceHeartbeat
import time

class Command(BaseCommand):
    help = 'Your service description'

    def handle(self, *args, **options):
        # Create heartbeat with your service key
        heartbeat = ServiceHeartbeat('your-service-key')
        heartbeat.start()

        try:
            self.stdout.write('Service starting...')

            while True:
                # Do your work here
                self.do_work()

                # Report heartbeat every iteration
                heartbeat.beat()
                time.sleep(30)

        except KeyboardInterrupt:
            self.stdout.write('Shutting down...')
        except Exception as e:
            self.stderr.write(f'Error: {e}')
            heartbeat.log_error(str(e))
            heartbeat.beat(state='degraded')
        finally:
            heartbeat.stop()

    def do_work(self):
        # Your service logic
        pass
```

---

## Service Keys (Must Match Docker Container Names)

| Service | Key | Container Name |
|---------|-----|----------------|
| Live Indexer | `indexer-live` | traitkeeper-indexer-live |
| Scheduled Indexer | `indexer-scheduled` | traitkeeper-indexer-scheduled |
| Incremental Indexer | `indexer-incremental` | traitkeeper-indexer-incremental |
| Vitality Analytics | `vitality-analytics` | vitality-analytics |
| Health Monitor | `traitkeeper-health` | traitkeeper-health |
| Config Listener | `config-listener` | traitkeeper-config-listener |
| Web Server | `traitkeeper-web` | traitkeeper-web |

---

## Integration Examples

### Async Service (run_live_indexer.py)

```python
import asyncio
from django.core.management.base import BaseCommand
from admin_panel.heartbeat import ServiceHeartbeat
from indexer.services import IndexerService

class Command(BaseCommand):
    help = 'Runs the live WebSocket indexer'

    def __init__(self):
        super().__init__()
        self.heartbeat = ServiceHeartbeat('indexer-live')
        self.shutdown_event = asyncio.Event()

    async def main(self):
        """Main async logic"""
        self.heartbeat.start()

        try:
            # Create background task for heartbeat
            heartbeat_task = asyncio.create_task(self.heartbeat_loop())

            # Your main service logic
            await self.indexer_service.subscribe_to_collection_activity()

        except asyncio.CancelledError:
            self.stdout.write('Shutting down...')
        except Exception as e:
            self.heartbeat.log_error(str(e))
            self.heartbeat.beat(state='degraded')
        finally:
            self.heartbeat.stop()

    async def heartbeat_loop(self):
        """Send heartbeat every 30 seconds"""
        while not self.shutdown_event.is_set():
            self.heartbeat.beat()
            await asyncio.sleep(30)

    def handle(self, *args, **options):
        asyncio.run(self.main())
```

### Sync Service with Loop (run_scheduled_indexer.py)

```python
import time
from django.core.management.base import BaseCommand
from admin_panel.heartbeat import ServiceHeartbeat

class Command(BaseCommand):
    help = 'Runs the scheduled indexer'

    def handle(self, *args, **options):
        heartbeat = ServiceHeartbeat('indexer-scheduled')
        heartbeat.start()

        try:
            while True:
                self.stdout.write('Running scheduled task...')

                try:
                    # Your task logic
                    self.run_indexing_task()
                    heartbeat.beat(state='healthy')

                except Exception as e:
                    self.stderr.write(f'Task error: {e}')
                    heartbeat.log_error(str(e))
                    heartbeat.beat(state='degraded')

                # Wait before next run
                time.sleep(300)  # 5 minutes

        except KeyboardInterrupt:
            self.stdout.write('Stopping...')
        finally:
            heartbeat.stop()
```

### One-Time Task Service (calculate_vitality.py)

```python
from django.core.management.base import BaseCommand
from admin_panel.heartbeat import ServiceHeartbeat

class Command(BaseCommand):
    help = 'Calculate vitality scores'

    def handle(self, *args, **options):
        heartbeat = ServiceHeartbeat('vitality-analytics')
        heartbeat.start()

        try:
            collections = NFTCollection.objects.filter(is_listed=True)
            total = collections.count()

            for i, collection in enumerate(collections):
                try:
                    # Process collection
                    self.calculate_vitality(collection)

                    # Update heartbeat with progress
                    progress = f"Processing {i+1}/{total}"
                    heartbeat.beat(state='healthy', message=progress)

                except Exception as e:
                    heartbeat.log_error(f'Error on {collection.name}: {e}')

            self.stdout.write(self.style.SUCCESS('Completed!'))
            heartbeat.beat(state='healthy', message='Completed')

        except Exception as e:
            self.stderr.write(f'Fatal error: {e}')
            heartbeat.log_error(str(e))
            heartbeat.beat(state='failed')
        finally:
            heartbeat.stop()
```

---

## Heartbeat States

| State | Description | Dashboard Color |
|-------|-------------|-----------------|
| `healthy` | Service running normally | Green ✓ |
| `degraded` | Service running with errors | Yellow ⚠ |
| `starting` | Service initializing | Blue |
| `stopped` | Service shut down | Gray |
| `failed` | Service crashed | Red ✗ |

---

## Error Logging

```python
try:
    risky_operation()
except Exception as e:
    # Logs error to service and system-wide cache
    heartbeat.log_error(str(e))

    # Update state to degraded
    heartbeat.beat(state='degraded')
```

Errors appear in the "Container Error Logs" section of the Task Manager dashboard.

---

## Heartbeat API

### `ServiceHeartbeat(service_key, heartbeat_interval=30)`
Create a new heartbeat instance.

**Parameters:**
- `service_key` (str): Unique identifier matching your service name
- `heartbeat_interval` (int): Seconds between heartbeats (default: 30)

### Methods:

#### `start()`
Initialize and send first heartbeat. Call this when your service starts.

#### `beat(state='healthy', message=None)`
Send a heartbeat update.

**Parameters:**
- `state` (str): Current service state ('healthy', 'degraded', 'starting', 'stopped', 'failed')
- `message` (str): Optional status message

#### `log_error(error_message)`
Log an error for this service. Automatically adds to system error cache.

**Parameters:**
- `error_message` (str): Error description

#### `stop()`
Mark service as stopped. Call this in `finally` block.

---

## Simple One-Shot Heartbeat

For scripts that don't need continuous heartbeat:

```python
from admin_panel.heartbeat import report_service_heartbeat

# Quick status report
report_service_heartbeat(
    service_key='my-script',
    state='healthy',
    errors=[]
)
```

---

## Troubleshooting

### Dashboard shows "Not reporting"
- Service hasn't integrated heartbeat yet
- Service crashed before sending heartbeat
- Redis connection issue

### Dashboard shows "Last seen Xs ago" (stale)
- Service stopped sending heartbeats (crashed/hung)
- Heartbeat timeout is 90 seconds
- Check service logs for errors

### Errors not appearing
- Use `heartbeat.log_error(msg)` not `logger.error()`
- Check Redis is running
- Verify service key matches dashboard

---

## Next Steps

1. Add heartbeat to each service in `management/commands/`
2. Restart Docker containers
3. Visit `/admin-panel/task-dashboard/` to see live status
4. Monitor "Container Error Logs" section for issues

---

## Files Modified

- `admin_panel/heartbeat.py` - Heartbeat utility class
- `admin_panel/views.py` - Dashboard reads from Redis
- `templates/admin_panel/task_dashboard.html` - Dashboard UI

---

Need help? Check service logs:
```bash
docker logs traitkeeper-indexer-live
docker logs vitality-analytics
```
