# system_health/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta
from django.db import models
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser # Use IsAdminUser for staff-only access
from rest_framework.response import Response
import logging
import secrets

from .monitoring import system_monitor
# Consolidate all imports from the background manager at the top
from .background_task_manager import (
    get_health_status,
    health_task_manager, # Used to access the new thread-safe method
    start_health_monitoring,
    stop_health_monitoring
)

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def health_check(request):
    """Get comprehensive system health status."""
    try:
        health_data = system_monitor.check_health()
        return Response(health_data)
    except Exception as e:
        logger.error(f"Health check API error: {e}", exc_info=True)
        return Response({'error': 'An unexpected error occurred.'}, status=500)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def health_metrics(request):
    """Get current system metrics like CPU, memory, etc."""
    try:
        metrics = system_monitor.get_system_metrics()
        return Response({
            'cpu_percent': metrics.cpu_percent,
            'memory_percent': metrics.memory_percent,
            'disk_usage': metrics.disk_usage,
            'active_tasks': metrics.active_tasks,
            'failed_tasks_24h': metrics.failed_tasks_24h,
            'services': {
                'indexer': metrics.indexer_status,
                'health_monitor': metrics.health_worker_status,
                'redis': 'connected' if metrics.redis_connected else 'disconnected'
            }
        })
    except Exception as e:
        logger.error(f"Health metrics API error: {e}", exc_info=True)
        return Response({'error': 'An unexpected error occurred while fetching metrics.'}, status=500)

@login_required
def health_dashboard(request):
    """Render health monitoring dashboard for admin users."""
    if not request.user.is_staff:
        return render(request, 'admin/permission_denied.html', status=403)

    # Simple template render - all data loaded via JavaScript API calls
    return render(request, 'system_health/dashboard.html')

@login_required
def error_logs_page(request):
    """Render dedicated error logs page for admin users."""
    if not request.user.is_staff:
        return render(request, 'admin/permission_denied.html', status=403)

    # Simple template render - all data loaded via JavaScript API calls
    return render(request, 'system_health/error_logs.html')

@api_view(['GET'])
@permission_classes([IsAdminUser])
def health_task_status(request):
    """Get the status of the background health task manager."""
    try:
        status_data = get_health_status()
        return Response(status_data)
    except Exception as e:
        logger.error(f"Health task status API error: {e}", exc_info=True)
        return Response({'error': 'An unexpected error occurred.'}, status=500)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def health_task_history(request):
    """Get the recent execution history of health tasks."""
    try:
        history = health_task_manager.get_task_history()
        recent_history = history[-20:]
        return Response({
            'task_history': recent_history,
            'total_recorded_tasks': len(history)
        })
    except Exception as e:
        logger.error(f"Health task history API error: {e}", exc_info=True)
        return Response({'error': 'An unexpected error occurred.'}, status=500)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def restart_health_monitoring(request):
    """Stops and starts the background health monitoring service."""
    try:
        logger.warning(f"Health monitoring restart triggered by user: {request.user.username}")
        stop_health_monitoring()
        start_health_monitoring()
        return Response({'message': 'Health monitoring service has been restarted.'})
    except Exception as e:
        logger.error(f"Health monitoring restart API error: {e}", exc_info=True)
        return Response({'error': 'Failed to restart the service.'}, status=500)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def transaction_health(request):
    """Get Solana transaction confirmation health metrics"""
    try:
        health_data = system_monitor.check_transaction_health()
        return Response(health_data)
    except Exception as e:
        logger.error(f"Transaction health API error: {e}", exc_info=True)
        return Response({
            'error': 'Failed to fetch transaction health',
            'status': 'error',
            'stuck_transactions': 0,
            'failure_rate_24h': 0,
            'avg_confirmation_time_ms': 0
        }, status=500)


# ============================================================================
# ECOSYSTEM HEALTH API ENDPOINTS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def ecosystem_health_latest(request):
    """Get the latest ecosystem health snapshot."""
    try:
        from .models import EcosystemHealth
        latest = EcosystemHealth.get_latest()

        if not latest:
            return Response({'message': 'No ecosystem health data available yet.'}, status=404)

        return Response({
            'timestamp': latest.timestamp,
            'status': latest.status,
            'system_resources': {
                'cpu_percent': latest.cpu_percent,
                'memory_percent': latest.memory_percent,
                'disk_percent': latest.disk_percent,
            },
            'services': {
                'indexer_running': latest.indexer_running,
                'redis_connected': latest.redis_connected,
                'database_connected': latest.database_connected,
            },
            'tasks': {
                'active': latest.active_tasks,
                'failed_24h': latest.failed_tasks_24h,
                'successful_24h': latest.successful_tasks_24h,
            },
            'indexer': {
                'events_indexed_24h': latest.events_indexed_24h,
                'indexing_lag_minutes': latest.indexing_lag_minutes,
                'last_successful_index': latest.last_successful_index,
            },
            'marketplace': {
                'active_listings': latest.active_listings_count,
                'sales_24h': latest.sales_24h,
                'volume_24h': float(latest.volume_24h),
                'unique_traders_24h': latest.unique_traders_24h,
            },
            'users': {
                'total': latest.total_users,
                'active_24h': latest.active_users_24h,
                'new_24h': latest.new_users_24h,
            },
            'nft_data': {
                'total_nfts': latest.total_nfts_tracked,
                'total_collections': latest.total_collections_tracked,
                'collections_updated_24h': latest.collections_updated_24h,
            },
            'alerts': latest.alerts,
            'alert_count': latest.alert_count,
        })
    except Exception as e:
        logger.error(f"Ecosystem health latest API error: {e}", exc_info=True)
        return Response({'error': 'Failed to fetch ecosystem health data.'}, status=500)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def ecosystem_health_trend(request):
    """Get ecosystem health trend for the last N hours."""
    try:
        from .models import EcosystemHealth
        hours = int(request.GET.get('hours', 24))

        health_records = EcosystemHealth.get_health_trend(hours=hours)

        trend_data = [{
            'timestamp': record.timestamp,
            'status': record.status,
            'cpu_percent': record.cpu_percent,
            'memory_percent': record.memory_percent,
            'disk_percent': record.disk_percent,
            'active_tasks': record.active_tasks,
            'failed_tasks_24h': record.failed_tasks_24h,
            'sales_24h': record.sales_24h,
            'volume_24h': float(record.volume_24h),
            'active_users_24h': record.active_users_24h,
            'alert_count': record.alert_count,
        } for record in health_records]

        return Response({
            'hours': hours,
            'data_points': len(trend_data),
            'trend': trend_data
        })
    except Exception as e:
        logger.error(f"Ecosystem health trend API error: {e}", exc_info=True)
        return Response({'error': 'Failed to fetch trend data.'}, status=500)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def ecosystem_health_summary(request):
    """Get ecosystem health summary statistics."""
    try:
        from .utils import get_ecosystem_health_summary
        hours = int(request.GET.get('hours', 24))

        summary = get_ecosystem_health_summary(hours=hours)
        return Response(summary)
    except Exception as e:
        logger.error(f"Ecosystem health summary API error: {e}", exc_info=True)
        return Response({'error': 'Failed to fetch summary data.'}, status=500)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def system_alerts_active(request):
    """Get all active system alerts."""
    try:
        from .models import SystemAlert

        active_alerts = SystemAlert.objects.filter(
            is_resolved=False
        ).order_by('-triggered_at')[:50]

        alerts_data = [{
            'id': alert.id,
            'alert_level': alert.alert_level,
            'category': alert.category,
            'title': alert.title,
            'message': alert.message,
            'triggered_at': alert.triggered_at,
            'duration_seconds': alert.duration_seconds,
            'source_component': alert.source_component,
        } for alert in active_alerts]

        return Response({
            'count': len(alerts_data),
            'alerts': alerts_data
        })
    except Exception as e:
        logger.error(f"Active alerts API error: {e}", exc_info=True)
        return Response({'error': 'Failed to fetch active alerts.'}, status=500)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def system_alert_resolve(request, alert_id):
    """Mark a system alert as resolved."""
    try:
        from .models import SystemAlert

        alert = SystemAlert.objects.get(id=alert_id)
        resolution_notes = request.data.get('notes', f'Resolved by {request.user.username}')

        alert.mark_resolved(notes=resolution_notes)

        logger.info(f"Alert {alert_id} resolved by {request.user.username}")
        return Response({
            'message': 'Alert marked as resolved.',
            'alert_id': alert_id,
            'resolved_at': alert.resolved_at
        })
    except SystemAlert.DoesNotExist:
        return Response({'error': 'Alert not found.'}, status=404)
    except Exception as e:
        logger.error(f"Alert resolve API error: {e}", exc_info=True)
        return Response({'error': 'Failed to resolve alert.'}, status=500)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def service_health_checks(request):
    """Get recent service health checks."""
    try:
        from .models import ServiceHealthCheck

        service_type = request.GET.get('service_type')
        limit = int(request.GET.get('limit', 50))

        queryset = ServiceHealthCheck.objects.all()

        if service_type:
            queryset = queryset.filter(service_type=service_type)

        checks = queryset.order_by('-timestamp')[:limit]

        checks_data = [{
            'service_type': check.service_type,
            'timestamp': check.timestamp,
            'is_healthy': check.is_healthy,
            'response_time_ms': check.response_time_ms,
            'error_message': check.error_message,
        } for check in checks]

        return Response({
            'count': len(checks_data),
            'checks': checks_data
        })
    except Exception as e:
        logger.error(f"Service health checks API error: {e}", exc_info=True)
        return Response({'error': 'Failed to fetch service health checks.'}, status=500)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def performance_metrics(request):
    """Get recent performance metrics."""
    try:
        from .models import PerformanceMetric

        metric_type = request.GET.get('metric_type')
        hours = int(request.GET.get('hours', 24))
        from datetime import timedelta
        from django.utils import timezone

        cutoff = timezone.now() - timedelta(hours=hours)
        queryset = PerformanceMetric.objects.filter(timestamp__gte=cutoff)

        if metric_type:
            queryset = queryset.filter(metric_type=metric_type)

        metrics = queryset.order_by('-timestamp')[:200]

        metrics_data = [{
            'metric_type': metric.metric_type,
            'timestamp': metric.timestamp,
            'value': metric.value,
            'unit': metric.unit,
            'component': metric.component,
        } for metric in metrics]

        return Response({
            'hours': hours,
            'count': len(metrics_data),
            'metrics': metrics_data
        })
    except Exception as e:
        logger.error(f"Performance metrics API error: {e}", exc_info=True)
        return Response({'error': 'Failed to fetch performance metrics.'}, status=500)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def docker_services_status(request):
    """Get status of all services based on Docker container health checks."""
    try:
        import docker
        from docker.errors import DockerException

        # Try to connect to Docker
        try:
            docker_client = docker.from_env()
        except DockerException:
            logger.warning("Cannot connect to Docker - falling back to internal checks")
            docker_client = None

        # Define expected services with their container name patterns
        services_config = {
            'main': {
                'description': 'Web Server (Django)',
                'check': 'self',
                'container_pattern': 'traitkeeper-main'
            },
            'indexer-live': {
                'description': 'Live WebSocket Indexer',
                'check': 'docker',
                'container_pattern': 'traitkeeper-indexer-live'
            },
            'indexer-scheduled': {
                'description': 'Scheduled Indexer',
                'check': 'docker',
                'container_pattern': 'traitkeeper-indexer-scheduled'
            },
            'vitality-analytics': {
                'description': 'Vitality Analytics Worker',
                'check': 'docker',
                'container_pattern': 'traitkeeper-vitality-analytics'
            },
            'health': {
                'description': 'Health Monitoring Worker',
                'check': 'docker',
                'container_pattern': 'traitkeeper-health'
            },
            'postgres': {
                'description': 'PostgreSQL Database',
                'check': 'database',
                'container_pattern': None
            },
            'redis': {
                'description': 'Redis Cache',
                'check': 'redis',
                'container_pattern': None
            },
        }

        services_status = []

        # Check each service
        for service_name, config in services_config.items():
            check_type = config['check']
            description = config['description']
            container_pattern = config.get('container_pattern')

            if check_type == 'self':
                # Main service is running if this code executes
                services_status.append({
                    'name': service_name,
                    'description': description,
                    'status': 'running',
                    'status_class': 'success',
                    'health': 'N/A'
                })

            elif check_type == 'docker':
                # Check Docker container status
                try:
                    if docker_client and container_pattern:
                        # Find container by name pattern
                        containers = docker_client.containers.list(
                            all=True,
                            filters={'name': container_pattern}
                        )

                        if containers:
                            container = containers[0]
                            status = container.status  # 'running', 'exited', etc.
                            state = container.attrs.get('State', {})
                            health = state.get('Health', {}).get('Status', 'N/A')

                            # Get error info if container exited
                            error_msg = None
                            if status != 'running':
                                exit_code = state.get('ExitCode', 'unknown')
                                error = state.get('Error', '')
                                if error:
                                    error_msg = f"Exit code {exit_code}: {error}"
                                elif exit_code != 0:
                                    error_msg = f"Exited with code {exit_code}"

                            is_healthy = status == 'running'
                            service_info = {
                                'name': service_name,
                                'description': description,
                                'status': status,
                                'status_class': 'success' if is_healthy else 'error',
                                'health': health if health != 'N/A' else 'N/A'
                            }
                            if error_msg:
                                service_info['error'] = error_msg

                            services_status.append(service_info)
                        else:
                            # Container not found
                            services_status.append({
                                'name': service_name,
                                'description': description,
                                'status': 'not found',
                                'status_class': 'error',
                                'health': 'N/A',
                                'error': f'Container matching pattern "{container_pattern}" not found'
                            })
                    else:
                        # Docker not available - mark as unknown
                        services_status.append({
                            'name': service_name,
                            'description': description,
                            'status': 'unknown',
                            'status_class': 'warning',
                            'health': 'Docker unavailable',
                            'error': 'Docker client unavailable - check Docker socket mount'
                        })
                except Exception as e:
                    error_detail = str(e)
                    logger.error(f"Error checking Docker container {container_pattern}: {e}", exc_info=True)
                    services_status.append({
                        'name': service_name,
                        'description': description,
                        'status': 'error',
                        'status_class': 'error',
                        'health': 'N/A',
                        'error': error_detail
                    })

            elif check_type == 'health':
                # Check health service via Docker
                try:
                    if docker_client and container_pattern:
                        containers = docker_client.containers.list(
                            all=True,
                            filters={'name': container_pattern}
                        )

                        if containers:
                            container = containers[0]
                            status = container.status
                            state = container.attrs.get('State', {})
                            health = state.get('Health', {}).get('Status', 'N/A')

                            # Get error info if container exited
                            error_msg = None
                            if status != 'running':
                                exit_code = state.get('ExitCode', 'unknown')
                                error = state.get('Error', '')
                                if error:
                                    error_msg = f"Exit code {exit_code}: {error}"
                                elif exit_code != 0:
                                    error_msg = f"Exited with code {exit_code}"

                            is_healthy = status == 'running'
                            service_info = {
                                'name': service_name,
                                'description': description,
                                'status': status,
                                'status_class': 'success' if is_healthy else 'error',
                                'health': health if health != 'N/A' else 'N/A'
                            }
                            if error_msg:
                                service_info['error'] = error_msg

                            services_status.append(service_info)
                        else:
                            services_status.append({
                                'name': service_name,
                                'description': description,
                                'status': 'not found',
                                'status_class': 'error',
                                'health': 'N/A',
                                'error': f'Container matching pattern "{container_pattern}" not found'
                            })
                    else:
                        services_status.append({
                            'name': service_name,
                            'description': description,
                            'status': 'unknown',
                            'status_class': 'warning',
                            'health': 'Docker unavailable',
                            'error': 'Docker client unavailable - check Docker socket mount'
                        })
                except Exception as e:
                    error_detail = str(e)
                    logger.error(f"Error checking health service: {e}", exc_info=True)
                    services_status.append({
                        'name': service_name,
                        'description': description,
                        'status': 'error',
                        'status_class': 'error',
                        'health': 'N/A',
                        'error': error_detail
                    })

            elif check_type == 'database':
                # Check database connection
                try:
                    from django.db import connection
                    connection.ensure_connection()
                    services_status.append({
                        'name': service_name,
                        'description': description,
                        'status': 'running',
                        'status_class': 'success',
                        'health': 'N/A'
                    })
                except Exception as e:
                    error_detail = str(e)
                    logger.error(f"Database connection error: {e}", exc_info=True)
                    services_status.append({
                        'name': service_name,
                        'description': description,
                        'status': 'not running',
                        'status_class': 'error',
                        'health': 'N/A',
                        'error': error_detail
                    })

            elif check_type == 'redis':
                # Check Redis connection
                try:
                    from django.core.cache import cache
                    cache.set('health_check', 'ok', 1)
                    is_connected = cache.get('health_check') == 'ok'

                    if is_connected:
                        services_status.append({
                            'name': service_name,
                            'description': description,
                            'status': 'running',
                            'status_class': 'success',
                            'health': 'N/A'
                        })
                    else:
                        services_status.append({
                            'name': service_name,
                            'description': description,
                            'status': 'not running',
                            'status_class': 'error',
                            'health': 'N/A',
                            'error': 'Redis health check failed - cache write/read mismatch'
                        })
                except Exception as e:
                    error_detail = str(e)
                    logger.error(f"Redis connection error: {e}", exc_info=True)
                    services_status.append({
                        'name': service_name,
                        'description': description,
                        'status': 'not running',
                        'status_class': 'error',
                        'health': 'N/A',
                        'error': error_detail
                    })

        return Response({
            'services': services_status,
            'total': len(services_status),
            'running': len([s for s in services_status if s['status'] == 'running'])
        })

    except Exception as e:
        logger.error(f"Docker services status API error: {e}", exc_info=True)
        return Response({'error': 'Failed to fetch services status.'}, status=500)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def system_error_logs(request):
    """Get recent system error logs from SystemAlert and log files."""
    try:
        from .models import SystemAlert
        from django.utils import timezone
        from datetime import timedelta

        # Get time range (default last 24 hours)
        hours = int(request.GET.get('hours', 24))
        cutoff = timezone.now() - timedelta(hours=hours)

        # Get recent alerts (errors and warnings)
        alerts = SystemAlert.objects.filter(
            triggered_at__gte=cutoff,
            alert_level__in=['ERROR', 'CRITICAL', 'WARNING']
        ).order_by('-triggered_at')[:100]

        error_logs = []

        for alert in alerts:
            error_logs.append({
                'timestamp': alert.triggered_at,
                'level': alert.alert_level,
                'category': alert.category,
                'title': alert.title,
                'message': alert.message,
                'source': alert.source_component or 'Unknown',
                'resolved': alert.is_resolved,
                'duration': alert.duration_seconds if not alert.is_resolved else None
            })

        # Try to get recent errors from ecosystem health snapshots
        try:
            from .models import EcosystemHealth
            recent_snapshots = EcosystemHealth.objects.filter(
                timestamp__gte=cutoff,
                status__in=['ERROR', 'CRITICAL']
            ).order_by('-timestamp')[:50]

            for snapshot in recent_snapshots:
                if snapshot.alerts:
                    for alert_msg in snapshot.alerts:
                        error_logs.append({
                            'timestamp': snapshot.timestamp,
                            'level': snapshot.status,
                            'category': 'SYSTEM',
                            'title': 'System Health Issue',
                            'message': alert_msg,
                            'source': 'Health Monitor',
                            'resolved': True,
                            'duration': None
                        })
        except Exception as e:
            logger.warning(f"Could not fetch ecosystem health errors: {e}")

        # Sort all logs by timestamp
        error_logs.sort(key=lambda x: x['timestamp'], reverse=True)

        # Limit to most recent 100
        error_logs = error_logs[:100]

        return Response({
            'count': len(error_logs),
            'hours': hours,
            'logs': error_logs
        })

    except Exception as e:
        logger.error(f"Error logs API error: {e}", exc_info=True)
        return Response({'error': 'Failed to fetch error logs.'}, status=500)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def vitality_metrics(request):
    """Get vitality calculation system metrics."""
    try:
        from marketplace.models import NFTVitalityHistory, CollectionVitalityHistory
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Count, Avg, Q

        # Get time range (default last 24 hours)
        cutoff = timezone.now() - timedelta(hours=24)

        # Count NFT vitality calculations in last 24h
        nft_calculations = NFTVitalityHistory.objects.filter(
            calculated_at__gte=cutoff
        ).count()

        # Count collection vitality calculations in last 24h
        collection_calculations = CollectionVitalityHistory.objects.filter(
            calculated_at__gte=cutoff
        ).count()

        # Get average calculation times (placeholder - would need timing data)
        nft_avg_time_ms = 150  # Placeholder
        collection_avg_time_ms = 250  # Placeholder

        # Calculate failed calculations (vitality_score of 0 could indicate failure)
        failed_nft = NFTVitalityHistory.objects.filter(
            calculated_at__gte=cutoff,
            vitality_score=0
        ).count()

        failed_collection = CollectionVitalityHistory.objects.filter(
            calculated_at__gte=cutoff,
            vitality_score=0
        ).count()

        failed_calculations_24h = failed_nft + failed_collection
        total_calculations = nft_calculations + collection_calculations

        # Calculate failure rate
        failure_rate_24h = (
            (failed_calculations_24h / total_calculations * 100)
            if total_calculations > 0
            else 0
        )

        # Queue size (placeholder - would need actual queue implementation)
        queue_size = 0
        queue_status = 'idle' if queue_size == 0 else 'active'

        # Get recent calculation component values (sample from latest calculations)
        recent_nft = NFTVitalityHistory.objects.order_by('-calculated_at').first()

        recent_calculations = {
            'perception_index': round(recent_nft.perception_index, 2) if recent_nft else 0,
            'trait_performance': round(recent_nft.trait_performance, 2) if recent_nft else 0,
            'market_momentum': round(recent_nft.market_momentum, 2) if recent_nft else 0,
            'collection_health': round(recent_nft.collection_health, 2) if recent_nft else 0,
        }

        return Response({
            'nft_calculations_24h': nft_calculations,
            'collection_calculations_24h': collection_calculations,
            'failed_calculations_24h': failed_calculations_24h,
            'failure_rate_24h': round(failure_rate_24h, 2),
            'nft_avg_time_ms': nft_avg_time_ms,
            'collection_avg_time_ms': collection_avg_time_ms,
            'queue_size': queue_size,
            'queue_status': queue_status,
            'recent_calculations': recent_calculations,
        })

    except Exception as e:
        logger.error(f"Vitality metrics API error: {e}", exc_info=True)
        return Response({
            'error': 'Failed to fetch vitality metrics.',
            'nft_calculations_24h': 0,
            'collection_calculations_24h': 0,
            'failed_calculations_24h': 0,
            'failure_rate_24h': 0,
            'queue_size': 0,
            'queue_status': 'error',
        }, status=500)

# ============================================================================
# HEALTH SHARING API ENDPOINTS (Public & Admin)
# ============================================================================

import secrets
from datetime import timedelta
from rest_framework.permissions import AllowAny

@api_view(['POST'])
@permission_classes([IsAdminUser])
def generate_share_token(request):
    """Generate a public share token for system health stats."""
    try:
        from .models import HealthShareToken
        
        # Generate a secure random token
        token = secrets.token_urlsafe(32)
        
        # Token expires in 24 hours
        expires_at = timezone.now() + timedelta(hours=24)
        
        # Get options from request
        include_performance = request.data.get('performance', True)
        include_services = request.data.get('services', True)
        include_marketplace = request.data.get('marketplace', True)
        include_uptime = request.data.get('uptime', True)
        
        # Create share token
        share_token = HealthShareToken.objects.create(
            token=token,
            expires_at=expires_at,
            include_performance=include_performance,
            include_services=include_services,
            include_marketplace=include_marketplace,
            include_uptime=include_uptime
        )
        
        logger.info(f"Share token {token[:8]}... created by {request.user.username}")
        
        return Response({
            'token': token,
            'expires_at': expires_at,
            'share_url': f'/system-health/share/{token}/'
        })
        
    except Exception as e:
        logger.error(f"Share token generation error: {e}", exc_info=True)
        return Response({'error': 'Failed to generate share token.'}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])  # Public endpoint
def shared_health_stats(request, token):
    """View shared system health stats (public, no auth required)."""
    try:
        from .models import HealthShareToken, EcosystemHealth
        
        # Find and validate token
        try:
            share_token = HealthShareToken.objects.get(token=token)
        except HealthShareToken.DoesNotExist:
            return Response({'error': 'Invalid or expired share link.'}, status=404)
        
        # Check if token is still valid
        if not share_token.is_valid:
            return Response({'error': 'This share link has expired.'}, status=410)
        
        # Increment view count
        share_token.increment_view_count()
        
        # Get latest ecosystem health data
        latest = EcosystemHealth.get_latest()
        
        if not latest:
            return Response({'error': 'No health data available.'}, status=404)
        
        # Build response based on share options (exclude sensitive data)
        response_data = {
            'timestamp': latest.timestamp,
            'status': latest.status,
            'share_expires_at': share_token.expires_at
        }
        
        # Include performance metrics if allowed
        if share_token.include_performance:
            response_data['system_resources'] = {
                'cpu_percent': latest.cpu_percent,
                'memory_percent': latest.memory_percent,
                'disk_percent': latest.disk_percent,
            }
        
        # Include service status if allowed
        if share_token.include_services:
            response_data['services'] = {
                'indexer_running': latest.indexer_running,
                'redis_connected': latest.redis_connected,
                'database_connected': latest.database_connected,
            }
        
        # Include marketplace stats if allowed
        if share_token.include_marketplace:
            response_data['marketplace'] = {
                'active_listings': latest.active_listings_count,
                'sales_24h': latest.sales_24h,
                'volume_24h': float(latest.volume_24h),
                'unique_traders_24h': latest.unique_traders_24h,
            }
        
        # Include uptime if allowed
        if share_token.include_uptime:
            # Calculate uptime (placeholder - would need actual deployment timestamp)
            response_data['uptime'] = {
                'message': 'System operational',
                'last_restart': latest.timestamp,
            }
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Shared health stats error: {e}", exc_info=True)
        return Response({'error': 'Failed to fetch shared health stats.'}, status=500)


def shared_health_page(request, token):
    """Render public page for shared health stats (no auth required)."""
    return render(request, 'system_health/shared_health.html', {'token': token})


# ============================================================================
# SERVICE UPTIME API ENDPOINTS (QuickNode-style dashboard)
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def service_uptime_history(request):
    """Get uptime history for all services (90-day view like QuickNode)."""
    try:
        from .models import ServiceUptime
        from datetime import timedelta

        days = int(request.GET.get('days', 90))
        cutoff_date = timezone.now().date() - timedelta(days=days)

        # Get all services
        services = ServiceUptime.ServiceName.choices

        services_data = []
        for service_value, service_label in services:
            # Get uptime history for this service
            uptime_records = ServiceUptime.objects.filter(
                service_name=service_value,
                date__gte=cutoff_date
            ).order_by('date')

            if not uptime_records:
                # No data yet - mark as operational with placeholder
                services_data.append({
                    'service_name': service_value,
                    'service_label': service_label,
                    'overall_uptime': 100.0,
                    'status': 'Operational',
                    'status_class': 'success',
                    'uptime_history': []
                })
                continue

            # Calculate overall uptime
            total_uptime = sum(float(record.uptime_percentage) for record in uptime_records)
            overall_uptime = round(total_uptime / len(uptime_records), 1)

            # Build daily uptime array
            uptime_history = [{
                'date': record.date.isoformat(),
                'uptime': float(record.uptime_percentage),
                'incidents': record.incidents_count,
                'downtime_minutes': record.downtime_minutes
            } for record in uptime_records]

            # Determine status
            if overall_uptime >= 99.9:
                status = 'Operational'
                status_class = 'success'
            elif overall_uptime >= 95.0:
                status = 'Degraded'
                status_class = 'warning'
            else:
                status = 'Issues'
                status_class = 'error'

            services_data.append({
                'service_name': service_value,
                'service_label': service_label,
                'overall_uptime': overall_uptime,
                'status': status,
                'status_class': status_class,
                'uptime_history': uptime_history
            })

        return Response({
            'days': days,
            'services': services_data,
            'generated_at': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Service uptime history API error: {e}", exc_info=True)
        return Response({'error': 'Failed to fetch uptime history.'}, status=500)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def service_uptime_summary(request):
    """Get uptime summary stats for all services."""
    try:
        from .models import ServiceUptime
        from django.db.models import Avg, Min, Max, Count
        from datetime import timedelta

        days = int(request.GET.get('days', 90))
        cutoff_date = timezone.now().date() - timedelta(days=days)

        # Aggregate stats across all services
        stats = ServiceUptime.objects.filter(
            date__gte=cutoff_date
        ).aggregate(
            avg_uptime=Avg('uptime_percentage'),
            min_uptime=Min('uptime_percentage'),
            max_uptime=Max('uptime_percentage'),
            total_incidents=Count('id', filter=models.Q(incidents_count__gt=0))
        )

        # Count services with 100% uptime
        perfect_uptime_count = ServiceUptime.objects.filter(
            date__gte=cutoff_date,
            uptime_percentage=100
        ).values('service_name').distinct().count()

        return Response({
            'avg_uptime': round(float(stats['avg_uptime'] or 0), 2),
            'min_uptime': round(float(stats['min_uptime'] or 0), 2),
            'max_uptime': round(float(stats['max_uptime'] or 0), 2),
            'total_incidents': stats['total_incidents'],
            'perfect_uptime_services': perfect_uptime_count,
            'days_analyzed': days
        })

    except Exception as e:
        logger.error(f"Service uptime summary API error: {e}", exc_info=True)
        return Response({'error': 'Failed to fetch uptime summary.'}, status=500)


@login_required
def uptime_dashboard(request):
    """Render QuickNode-style uptime dashboard page."""
    if not request.user.is_staff:
        return render(request, 'admin/permission_denied.html', status=403)

    return render(request, 'system_health/uptime_dashboard.html')
