# system_health/utils.py
"""
Utilities for tracking and persisting ecosystem health metrics.
"""

import logging
from typing import Dict, List
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Avg
from django.contrib.auth import get_user_model

from .models import (
    EcosystemHealth,
    ServiceHealthCheck,
    PerformanceMetric,
    SystemAlert
)

User = get_user_model()
logger = logging.getLogger(__name__)


def capture_ecosystem_health_snapshot() -> EcosystemHealth:
    """
    Capture a complete ecosystem health snapshot and save to database.

    This combines data from:
    - System monitoring (CPU, memory, disk)
    - Service health checks (indexer, redis, database)
    - Marketplace metrics (listings, sales, volume)
    - User engagement (active users, new signups)
    - NFT data (collections, NFTs tracked)

    Returns:
        EcosystemHealth: The created health record
    """
    from .monitoring import system_monitor
    from indexer.models import NFTEvent
    from nft_data.models import NFT, NFTCollection
    from marketplace.models import NFTListing
    from django.contrib.sessions.models import Session

    try:
        # Get current system metrics
        health_check = system_monitor.check_health()
        metrics = health_check.get('metrics')

        # Calculate marketplace metrics (last 24h)
        cutoff_24h = timezone.now() - timedelta(hours=24)

        sales_24h = NFTEvent.objects.filter(
            event_type='SALE',
            timestamp__gte=cutoff_24h
        ).count()

        volume_24h = NFTEvent.objects.filter(
            event_type='SALE',
            timestamp__gte=cutoff_24h
        ).aggregate(total=Sum('amount'))['total'] or 0

        unique_traders_24h = NFTEvent.objects.filter(
            event_type__in=['SALE', 'BID', 'LIST'],
            timestamp__gte=cutoff_24h
        ).values('seller', 'buyer').distinct().count()

        active_listings = NFTListing.objects.filter(is_active=True).count()

        # Calculate user engagement metrics
        active_users_24h = Session.objects.filter(
            expire_date__gte=timezone.now()
        ).count()

        new_users_24h = User.objects.filter(
            date_joined__gte=cutoff_24h
        ).count()

        total_users = User.objects.count()

        # Calculate NFT data metrics
        total_nfts = NFT.objects.count()
        total_collections = NFTCollection.objects.count()

        collections_updated_24h = NFTCollection.objects.filter(
            updated_at__gte=cutoff_24h
        ).count()

        events_indexed_24h = NFTEvent.objects.filter(
            created_at__gte=cutoff_24h
        ).count()

        # Determine overall status
        status_map = {
            'healthy': EcosystemHealth.HealthStatus.HEALTHY,
            'warning': EcosystemHealth.HealthStatus.WARNING,
            'critical': EcosystemHealth.HealthStatus.CRITICAL,
            'error': EcosystemHealth.HealthStatus.ERROR,
        }
        overall_status = status_map.get(
            health_check.get('status', 'error'),
            EcosystemHealth.HealthStatus.ERROR
        )

        # Extract alerts
        alerts = health_check.get('alerts', [])
        alert_count = len(alerts)

        # Create health snapshot
        health_snapshot = EcosystemHealth.objects.create(
            status=overall_status,
            # System metrics
            cpu_percent=metrics.cpu_percent if metrics else 0,
            memory_percent=metrics.memory_percent if metrics else 0,
            disk_percent=metrics.disk_usage if metrics else 0,
            # Service status
            indexer_running=(metrics.indexer_status == 'running') if metrics else False,
            redis_connected=metrics.redis_connected if metrics else False,
            database_connected=True,  # If we got here, DB is connected
            # Task metrics
            active_tasks=metrics.active_tasks if metrics else 0,
            failed_tasks_24h=metrics.failed_tasks_24h if metrics else 0,
            successful_tasks_24h=0,  # TODO: Calculate from task history
            # Indexer metrics
            last_successful_index=None,  # TODO: Parse from metrics
            events_indexed_24h=events_indexed_24h,
            indexing_lag_minutes=0,  # TODO: Calculate from blockchain
            # Marketplace metrics
            active_listings_count=active_listings,
            sales_24h=sales_24h,
            volume_24h=volume_24h,
            unique_traders_24h=unique_traders_24h,
            # User engagement
            active_users_24h=active_users_24h,
            new_users_24h=new_users_24h,
            total_users=total_users,
            # NFT data
            total_nfts_tracked=total_nfts,
            total_collections_tracked=total_collections,
            collections_updated_24h=collections_updated_24h,
            # Alerts
            alerts=alerts,
            alert_count=alert_count,
            # Metadata
            metadata={
                'services': health_check.get('services', {}),
                'capture_timestamp': timezone.now().isoformat(),
            }
        )

        # Create SystemAlert records for active alerts
        for alert_msg in alerts:
            create_system_alert_from_message(alert_msg, health_snapshot)

        logger.info(f"Captured ecosystem health snapshot: {overall_status}")
        return health_snapshot

    except Exception as e:
        logger.error(f"Error capturing ecosystem health snapshot: {e}", exc_info=True)
        # Create error health record
        return EcosystemHealth.objects.create(
            status=EcosystemHealth.HealthStatus.ERROR,
            alerts=[f"Error capturing health: {str(e)}"],
            alert_count=1,
            metadata={'error': str(e)}
        )


def create_system_alert_from_message(
    message: str,
    ecosystem_health: EcosystemHealth = None
) -> SystemAlert:
    """
    Create a SystemAlert from a health check alert message.

    Args:
        message: Alert message string
        ecosystem_health: Optional related EcosystemHealth record

    Returns:
        SystemAlert: The created alert
    """
    # Determine alert level and category from message content
    message_lower = message.lower()

    if 'critical' in message_lower or 'failed' in message_lower:
        alert_level = SystemAlert.AlertLevel.CRITICAL
    elif 'warning' in message_lower or 'high' in message_lower:
        alert_level = SystemAlert.AlertLevel.WARNING
    else:
        alert_level = SystemAlert.AlertLevel.INFO

    # Determine category
    if 'cpu' in message_lower or 'memory' in message_lower or 'disk' in message_lower:
        category = SystemAlert.AlertCategory.RESOURCE
    elif 'redis' in message_lower or 'indexer' in message_lower or 'service' in message_lower:
        category = SystemAlert.AlertCategory.SERVICE
    elif 'performance' in message_lower or 'slow' in message_lower:
        category = SystemAlert.AlertCategory.PERFORMANCE
    else:
        category = SystemAlert.AlertCategory.DATA

    # Check if similar alert exists and is unresolved
    existing_alert = SystemAlert.objects.filter(
        title=message[:200],
        is_resolved=False
    ).first()

    if existing_alert:
        # Update timestamp to show it's still active
        existing_alert.save(update_fields=['updated_at'])
        return existing_alert

    # Create new alert
    alert = SystemAlert.objects.create(
        alert_level=alert_level,
        category=category,
        title=message[:200],
        message=message,
        ecosystem_health=ecosystem_health,
        metadata={'auto_generated': True}
    )

    logger.info(f"Created system alert: [{alert_level}] {message[:100]}")
    return alert


def record_service_health_check(
    service_type: str,
    is_healthy: bool,
    response_time_ms: float = None,
    error_message: str = "",
    details: Dict = None
) -> ServiceHealthCheck:
    """
    Record a health check for a specific service.

    Args:
        service_type: Type of service (from ServiceHealthCheck.ServiceType)
        is_healthy: Whether the service is healthy
        response_time_ms: Optional response time in milliseconds
        error_message: Error message if unhealthy
        details: Additional details dict

    Returns:
        ServiceHealthCheck: The created record
    """
    try:
        check = ServiceHealthCheck.objects.create(
            service_type=service_type,
            is_healthy=is_healthy,
            response_time_ms=response_time_ms,
            error_message=error_message,
            details=details or {}
        )

        if not is_healthy:
            logger.warning(f"Service unhealthy: {service_type} - {error_message}")

        return check

    except Exception as e:
        logger.error(f"Error recording service health check: {e}", exc_info=True)
        raise


def record_performance_metric(
    metric_type: str,
    value: float,
    unit: str = "",
    component: str = "",
    metadata: Dict = None
) -> PerformanceMetric:
    """
    Record a performance metric.

    Args:
        metric_type: Type of metric (from PerformanceMetric.MetricType)
        value: Metric value
        unit: Unit of measurement
        component: Specific component or endpoint
        metadata: Additional metadata

    Returns:
        PerformanceMetric: The created record
    """
    try:
        metric = PerformanceMetric.objects.create(
            metric_type=metric_type,
            value=value,
            unit=unit,
            component=component,
            metadata=metadata or {}
        )

        return metric

    except Exception as e:
        logger.error(f"Error recording performance metric: {e}", exc_info=True)
        raise


def get_ecosystem_health_summary(hours: int = 24) -> Dict:
    """
    Get a summary of ecosystem health for the last N hours.

    Args:
        hours: Number of hours to look back

    Returns:
        Dict with health summary statistics
    """
    cutoff = timezone.now() - timedelta(hours=hours)
    health_records = EcosystemHealth.objects.filter(timestamp__gte=cutoff)

    if not health_records.exists():
        return {
            'status': 'no_data',
            'message': f'No health records in last {hours} hours'
        }

    latest = health_records.first()

    # Calculate uptime percentage
    total_records = health_records.count()
    healthy_records = health_records.filter(
        status=EcosystemHealth.HealthStatus.HEALTHY
    ).count()
    uptime_percent = (healthy_records / total_records * 100) if total_records > 0 else 0

    # Get average metrics
    avg_metrics = health_records.aggregate(
        avg_cpu=Avg('cpu_percent'),
        avg_memory=Avg('memory_percent'),
        avg_disk=Avg('disk_percent'),
        total_sales=Sum('sales_24h'),
        total_volume=Sum('volume_24h'),
    )

    # Count critical periods
    critical_count = health_records.filter(
        status=EcosystemHealth.HealthStatus.CRITICAL
    ).count()

    # Get active alerts
    active_alerts = SystemAlert.objects.filter(
        is_resolved=False
    ).order_by('-triggered_at')[:10]

    return {
        'status': latest.status,
        'latest_timestamp': latest.timestamp,
        'uptime_percent': round(uptime_percent, 2),
        'total_snapshots': total_records,
        'critical_periods': critical_count,
        'averages': {
            'cpu_percent': round(avg_metrics['avg_cpu'] or 0, 2),
            'memory_percent': round(avg_metrics['avg_memory'] or 0, 2),
            'disk_percent': round(avg_metrics['avg_disk'] or 0, 2),
        },
        'marketplace': {
            'total_sales': avg_metrics['total_sales'] or 0,
            'total_volume': float(avg_metrics['total_volume'] or 0),
            'active_listings': latest.active_listings_count,
        },
        'users': {
            'total': latest.total_users,
            'active_24h': latest.active_users_24h,
            'new_24h': latest.new_users_24h,
        },
        'active_alerts': [
            {
                'level': alert.alert_level,
                'title': alert.title,
                'triggered_at': alert.triggered_at,
            }
            for alert in active_alerts
        ]
    }


def auto_resolve_stale_alerts():
    """
    Automatically resolve alerts whose conditions are no longer true.

    This function re-validates all unresolved alerts and auto-resolves
    them if the underlying issue has been fixed.

    Returns:
        int: Number of alerts auto-resolved
    """
    from .monitoring import system_monitor

    try:
        # Get current system health
        health_check = system_monitor.check_health()
        current_services = health_check.get('services', {})
        current_alerts = set(health_check.get('alerts', []))

        # Get all unresolved alerts
        unresolved_alerts = SystemAlert.objects.filter(is_resolved=False)
        resolved_count = 0

        for alert in unresolved_alerts:
            should_resolve = False
            resolution_reason = "Issue no longer detected"

            # Check service-related alerts
            if alert.category == SystemAlert.AlertCategory.SERVICE:
                alert_msg_lower = alert.message.lower()

                # Check if indexer service alert
                if 'indexer' in alert_msg_lower and 'not running' in alert_msg_lower:
                    # Check if indexers are now running
                    docker_services = current_services.get('docker_services', {})
                    indexer_running = any(
                        service.get('status') == 'running'
                        for name, service in docker_services.items()
                        if 'indexer' in name.lower()
                    )
                    if indexer_running:
                        should_resolve = True
                        resolution_reason = "Indexer services are now running"

                # Check if redis alert
                elif 'redis' in alert_msg_lower:
                    if current_services.get('redis', {}).get('status') == 'connected':
                        should_resolve = True
                        resolution_reason = "Redis connection restored"

                # Check if database alert
                elif 'database' in alert_msg_lower or 'postgres' in alert_msg_lower:
                    if current_services.get('database', {}).get('status') == 'connected':
                        should_resolve = True
                        resolution_reason = "Database connection restored"

            # Check resource-related alerts
            elif alert.category == SystemAlert.AlertCategory.RESOURCE:
                alert_msg_lower = alert.message.lower()
                metrics = health_check.get('metrics')

                if metrics:
                    # Check CPU alerts
                    if 'cpu' in alert_msg_lower and 'high' in alert_msg_lower:
                        if metrics.cpu_percent < 80:  # Below critical threshold
                            should_resolve = True
                            resolution_reason = f"CPU usage normalized to {metrics.cpu_percent}%"

                    # Check memory alerts
                    elif 'memory' in alert_msg_lower and 'high' in alert_msg_lower:
                        if metrics.memory_percent < 85:  # Below critical threshold
                            should_resolve = True
                            resolution_reason = f"Memory usage normalized to {metrics.memory_percent}%"

                    # Check disk alerts
                    elif 'disk' in alert_msg_lower and ('full' in alert_msg_lower or 'high' in alert_msg_lower):
                        if metrics.disk_usage < 90:  # Below critical threshold
                            should_resolve = True
                            resolution_reason = f"Disk usage normalized to {metrics.disk_usage}%"

            # Check if alert message no longer appears in current alerts
            if not should_resolve and alert.message not in current_alerts:
                # Alert message not in current health check = issue likely resolved
                should_resolve = True
                resolution_reason = "Alert condition no longer present in health checks"

            # Auto-resolve if condition met
            if should_resolve:
                alert.mark_resolved(notes=f"Auto-resolved: {resolution_reason}")
                resolved_count += 1
                logger.info(f"Auto-resolved alert: {alert.title} - {resolution_reason}")

        if resolved_count > 0:
            logger.info(f"Auto-resolved {resolved_count} stale alerts")

        return resolved_count

    except Exception as e:
        logger.error(f"Error in auto_resolve_stale_alerts: {e}", exc_info=True)
        return 0


def cleanup_old_health_records(days: int = 30):
    """
    Clean up health records older than N days to prevent database bloat.

    Args:
        days: Number of days to retain

    Returns:
        int: Number of records deleted
    """
    cutoff = timezone.now() - timedelta(days=days)

    # Delete old ecosystem health records
    deleted_health, _ = EcosystemHealth.objects.filter(
        created_at__lt=cutoff
    ).delete()

    # Delete old service health checks
    deleted_checks, _ = ServiceHealthCheck.objects.filter(
        created_at__lt=cutoff
    ).delete()

    # Delete old performance metrics
    deleted_metrics, _ = PerformanceMetric.objects.filter(
        created_at__lt=cutoff
    ).delete()

    # Keep resolved alerts for 90 days, unresolved indefinitely
    alert_cutoff = timezone.now() - timedelta(days=90)
    deleted_alerts, _ = SystemAlert.objects.filter(
        is_resolved=True,
        resolved_at__lt=alert_cutoff
    ).delete()

    total_deleted = deleted_health + deleted_checks + deleted_metrics + deleted_alerts

    logger.info(
        f"Cleaned up {total_deleted} old health records "
        f"(health: {deleted_health}, checks: {deleted_checks}, "
        f"metrics: {deleted_metrics}, alerts: {deleted_alerts})"
    )

    return total_deleted
