# system_health/monitoring.py - Complete system monitoring implementation
import psutil
import asyncio
import logging
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional
import json
import docker
from docker.errors import DockerException

logger = logging.getLogger(__name__)

@dataclass
class HealthMetrics:
    cpu_percent: float
    memory_percent: float
    disk_usage: float
    active_tasks: int
    failed_tasks_24h: int
    last_successful_index: Optional[str]
    database_connections: int
    redis_connected: bool
    indexer_status: str
    health_worker_status: str

class SystemMonitor:
    """Monitor system health and performance"""
    
    def __init__(self):
        self.alert_thresholds = {
            'cpu_percent': 80.0,
            'memory_percent': 85.0,
            'disk_usage': 90.0,
            'failed_tasks_rate': 10.0
        }
    
    def get_system_metrics(self) -> HealthMetrics:
        """Get current system metrics"""
        try:
            # System metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Task metrics from both managers
            indexer_status = self._get_indexer_status()
            health_status = self._get_health_worker_status()
            
            # Database connections
            from django.db import connections
            db_connections = len(connections.all())
            
            # Redis connection
            redis_connected = self._check_redis_connection()
            
            # Failed tasks in last 24h
            failed_tasks_24h = self._count_failed_tasks_24h()
            
            return HealthMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                disk_usage=(disk.used / disk.total) * 100,
                active_tasks=indexer_status.get('total_pending_tasks', 0),
                failed_tasks_24h=failed_tasks_24h,
                last_successful_index=self._get_last_successful_index(),
                database_connections=db_connections,
                redis_connected=redis_connected,
                indexer_status='running' if indexer_status.get('is_running') else 'stopped',
                health_worker_status='running' if health_status.get('is_running') else 'stopped'
            )
            
        except Exception as e:
            logger.error(f"Error getting system metrics: {str(e)}")
            raise
    
    def _get_indexer_status(self) -> Dict:
        """Get indexer Docker container status"""
        try:
            docker_client = docker.from_env()

            # Check for indexer containers
            indexer_containers = docker_client.containers.list(
                all=True,
                filters={'name': 'indexer'}
            )

            running_indexers = [c for c in indexer_containers if c.status == 'running']

            if running_indexers:
                return {
                    'is_running': True,
                    'total_pending_tasks': 0,
                    'container_count': len(running_indexers),
                    'status_detail': 'running'
                }
            else:
                return {
                    'is_running': False,
                    'total_pending_tasks': 0,
                    'container_count': len(indexer_containers),
                    'status_detail': 'stopped'
                }
        except DockerException as e:
            logger.error(f"Docker error getting indexer status: {str(e)}")
            return {'is_running': False, 'total_pending_tasks': 0, 'error': str(e)}
        except Exception as e:
            logger.error(f"Error getting indexer status: {str(e)}")
            return {'is_running': False, 'total_pending_tasks': 0, 'error': str(e)}
    
    def _get_health_worker_status(self) -> Dict:
        """Get health worker status"""
        try:
            from .background_task_manager import get_health_status
            return get_health_status()
        except Exception as e:
            logger.error(f"Error getting health worker status: {str(e)}")
            return {'is_running': False}
    
    def _check_redis_connection(self) -> bool:
        """Check if Redis is accessible"""
        try:
            cache.set('health_check', 'ok', 60)
            return cache.get('health_check') == 'ok'
        except Exception:
            return False
    
    def _count_failed_tasks_24h(self) -> int:
        """Count failed tasks in the last 24 hours"""
        try:
            # Check both indexer and health task histories
            failed_count = 0
            cutoff_time = timezone.now() - timedelta(hours=24)
            
            # Indexer tasks
            try:
                from indexer.background_task_manager import task_manager
                for task in task_manager.task_history:
                    if (task.get('status') == 'failed' and 
                        task.get('completed_at', timezone.now()) > cutoff_time):
                        failed_count += 1
            except Exception:
                pass
            
            # Health tasks
            try:
                from .background_task_manager import health_task_manager
                for task in health_task_manager.task_history:
                    if (task.get('status') == 'failed' and 
                        task.get('completed_at', timezone.now()) > cutoff_time):
                        failed_count += 1
            except Exception:
                pass
            
            return failed_count
        except Exception:
            return 0
    
    def _get_last_successful_index(self) -> Optional[str]:
        """Get timestamp of last successful indexing"""
        try:
            from indexer.background_task_manager import task_manager

            for task in reversed(list(task_manager.task_history)):
                if (task.get('status') == 'success' and
                    'index' in task.get('name', '').lower()):
                    return str(task.get('completed_at'))

            return None
        except Exception:
            return None

    def _get_docker_services_status(self) -> Dict:
        """Get status of all Docker services"""
        try:
            docker_client = docker.from_env()

            # Define services we're monitoring
            service_patterns = {
                'indexer-live': 'indexer-live',
                'indexer-historical': 'indexer-historical',
                'web': 'web',
                'postgres': 'postgres',
                'redis': 'redis',
                'nginx': 'nginx',
                'celery': 'celery'
            }

            services_status = {}

            for service_name, pattern in service_patterns.items():
                try:
                    containers = docker_client.containers.list(
                        all=True,
                        filters={'name': pattern}
                    )

                    if containers:
                        container = containers[0]
                        services_status[service_name] = {
                            'status': container.status,
                            'name': container.name,
                            'id': container.short_id
                        }
                    else:
                        services_status[service_name] = {
                            'status': 'not_found',
                            'name': None,
                            'id': None
                        }
                except Exception as e:
                    services_status[service_name] = {
                        'status': 'error',
                        'error': str(e)
                    }

            return services_status

        except DockerException as e:
            logger.error(f"Docker error getting services status: {str(e)}")
            return {'error': f'Docker connection failed: {str(e)}'}
        except Exception as e:
            logger.error(f"Error getting Docker services status: {str(e)}")
            return {'error': str(e)}
    
    def check_health(self) -> Dict[str, any]:
        """Perform comprehensive health check"""
        try:
            metrics = self.get_system_metrics()
            alerts = []
            status = 'healthy'

            # Get Docker services status
            docker_services = self._get_docker_services_status()

            # Check thresholds
            if metrics.cpu_percent > self.alert_thresholds['cpu_percent']:
                alerts.append(f"High CPU usage: {metrics.cpu_percent:.1f}%")
                status = 'warning'

            if metrics.memory_percent > self.alert_thresholds['memory_percent']:
                alerts.append(f"High memory usage: {metrics.memory_percent:.1f}%")
                status = 'warning'

            if metrics.disk_usage > self.alert_thresholds['disk_usage']:
                alerts.append(f"Low disk space: {metrics.disk_usage:.1f}% used")
                status = 'critical'

            if not metrics.redis_connected:
                alerts.append("Redis connection failed")
                status = 'critical'

            if metrics.indexer_status != 'running':
                alerts.append("Indexer service not running")
                status = 'critical'

            if metrics.health_worker_status != 'running':
                alerts.append("Health monitoring not running")
                status = 'warning'

            if metrics.failed_tasks_24h > 10:
                alerts.append(f"High failure rate: {metrics.failed_tasks_24h} failed tasks in 24h")
                if metrics.failed_tasks_24h > 50:
                    status = 'critical'
                else:
                    status = 'warning'

            return {
                'status': status,
                'metrics': metrics,
                'alerts': alerts,
                'timestamp': timezone.now().isoformat(),
                'services': {
                    'indexer': metrics.indexer_status,
                    'health_monitor': metrics.health_worker_status,
                    'redis': 'connected' if metrics.redis_connected else 'disconnected',
                    'database': 'connected',
                    'docker_services': docker_services
                }
            }

        except Exception as e:
            logger.error(f"Error performing health check: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': timezone.now().isoformat(),
                'alerts': [f"Health check error: {str(e)}"]
            }
    
    def get_service_status(self) -> Dict[str, str]:
        """Get status of all services"""
        try:
            indexer_status = self._get_indexer_status()
            health_status = self._get_health_worker_status()
            
            return {
                'indexer': 'running' if indexer_status.get('is_running') else 'stopped',
                'health_monitor': 'running' if health_status.get('is_running') else 'stopped',
                'redis': 'connected' if self._check_redis_connection() else 'disconnected',
                'database': 'connected'  # Assume connected if no exception
            }
        except Exception as e:
            logger.error(f"Error getting service status: {str(e)}")
            return {'error': str(e)}
    
    def get_performance_metrics(self) -> Dict[str, float]:
        """Get current performance metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': (disk.used / disk.total) * 100,
                'memory_available_gb': memory.available / (1024**3),
                'disk_free_gb': disk.free / (1024**3)
            }
        except Exception as e:
            logger.error(f"Error getting performance metrics: {str(e)}")
            return {}

    def check_transaction_health(self) -> Dict:
        """Check Solana transaction confirmation health"""
        try:
            from marketplace.models import TransactionMonitoring

            stuck_txs = TransactionMonitoring.get_stuck_transactions(minutes=5)
            failure_rate = TransactionMonitoring.get_failure_rate_24h()
            avg_time = TransactionMonitoring.get_avg_confirmation_time(hours=1)

            status = 'healthy'
            alerts = []

            if stuck_txs.count() > 0:
                alerts.append(f"{stuck_txs.count()} transactions stuck for >5min")
                status = 'warning'

            if failure_rate > 10:
                alerts.append(f"High failure rate: {failure_rate:.1f}%")
                status = 'critical' if failure_rate > 25 else 'warning'

            if avg_time > 30000:  # 30 seconds
                alerts.append(f"Slow confirmations: {avg_time/1000:.1f}s avg")
                status = 'warning'

            return {
                'status': status,
                'stuck_transactions': stuck_txs.count(),
                'failure_rate_24h': failure_rate,
                'avg_confirmation_time_ms': avg_time,
                'alerts': alerts,
                'health': 'healthy' if len(alerts) == 0 else status
            }
        except Exception as e:
            logger.error(f"Error checking transaction health: {str(e)}")
            return {
                'status': 'error',
                'error': str(e),
                'health': 'unknown'
            }

# Global monitor instance
system_monitor = SystemMonitor()