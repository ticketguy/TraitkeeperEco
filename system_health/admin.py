from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Count, Avg
from datetime import timedelta

from .models import (
    EcosystemHealth,
    ServiceHealthCheck,
    PerformanceMetric,
    SystemAlert
)


@admin.register(EcosystemHealth)
class EcosystemHealthAdmin(admin.ModelAdmin):
    """Admin interface for EcosystemHealth model"""

    list_display = [
        'timestamp',
        'status_display',
        'system_resources',
        'services_status',
        'marketplace_summary',
        'alert_count',
    ]
    list_filter = ['status', 'indexer_running', 'redis_connected', 'timestamp']
    search_fields = ['alerts']
    readonly_fields = [
        'timestamp',
        'created_at',
        'detailed_metrics_display',
        'alerts_display',
        'services_display',
    ]
    ordering = ['-timestamp']

    fieldsets = (
        ('Status', {
            'fields': ('timestamp', 'status', 'alert_count', 'alerts_display')
        }),
        ('System Resources', {
            'fields': ('cpu_percent', 'memory_percent', 'disk_percent')
        }),
        ('Services', {
            'fields': ('services_display', 'indexer_running', 'redis_connected', 'database_connected')
        }),
        ('Tasks', {
            'fields': ('active_tasks', 'failed_tasks_24h', 'successful_tasks_24h')
        }),
        ('Indexer', {
            'fields': ('last_successful_index', 'events_indexed_24h', 'indexing_lag_minutes')
        }),
        ('Marketplace', {
            'fields': ('active_listings_count', 'sales_24h', 'volume_24h', 'unique_traders_24h')
        }),
        ('Users', {
            'fields': ('total_users', 'active_users_24h', 'new_users_24h')
        }),
        ('NFT Data', {
            'fields': ('total_nfts_tracked', 'total_collections_tracked', 'collections_updated_24h')
        }),
        ('Metadata', {
            'fields': ('metadata', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def status_display(self, obj):
        """Display status with color coding"""
        colors = {
            'HEALTHY': '#28a745',
            'WARNING': '#ffc107',
            'CRITICAL': '#dc3545',
            'ERROR': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'

    def system_resources(self, obj):
        """Display system resource usage"""
        cpu_color = '#dc3545' if obj.cpu_percent > 80 else '#28a745'
        mem_color = '#dc3545' if obj.memory_percent > 85 else '#28a745'
        disk_color = '#dc3545' if obj.disk_percent > 90 else '#28a745'

        return format_html(
            'CPU: <span style="color: {};">{:.1f}%</span> | '
            'MEM: <span style="color: {};">{:.1f}%</span> | '
            'DISK: <span style="color: {};">{:.1f}%</span>',
            cpu_color, obj.cpu_percent,
            mem_color, obj.memory_percent,
            disk_color, obj.disk_percent
        )
    system_resources.short_description = 'Resources'

    def services_status(self, obj):
        """Display services status"""
        indexer_icon = '✓' if obj.indexer_running else '✗'
        redis_icon = '✓' if obj.redis_connected else '✗'
        db_icon = '✓' if obj.database_connected else '✗'

        indexer_color = '#28a745' if obj.indexer_running else '#dc3545'
        redis_color = '#28a745' if obj.redis_connected else '#dc3545'
        db_color = '#28a745' if obj.database_connected else '#dc3545'

        return format_html(
            '<span style="color: {};">{} Indexer</span> | '
            '<span style="color: {};">{} Redis</span> | '
            '<span style="color: {};">{} DB</span>',
            indexer_color, indexer_icon,
            redis_color, redis_icon,
            db_color, db_icon
        )
    services_status.short_description = 'Services'

    def marketplace_summary(self, obj):
        """Display marketplace metrics summary"""
        return format_html(
            '{} sales | {:.2f} SOL | {} listings',
            obj.sales_24h,
            obj.volume_24h,
            obj.active_listings_count
        )
    marketplace_summary.short_description = 'Marketplace (24h)'

    def detailed_metrics_display(self, obj):
        """Display all metrics in formatted view"""
        output = []

        output.append("<h3>System Resources</h3>")
        output.append(f"CPU: {obj.cpu_percent:.1f}%")
        output.append(f"Memory: {obj.memory_percent:.1f}%")
        output.append(f"Disk: {obj.disk_percent:.1f}%")

        output.append("<h3>Services</h3>")
        output.append(f"Indexer: {'Running' if obj.indexer_running else 'Stopped'}")
        output.append(f"Redis: {'Connected' if obj.redis_connected else 'Disconnected'}")
        output.append(f"Database: {'Connected' if obj.database_connected else 'Disconnected'}")

        output.append("<h3>Tasks</h3>")
        output.append(f"Active: {obj.active_tasks}")
        output.append(f"Failed (24h): {obj.failed_tasks_24h}")
        output.append(f"Successful (24h): {obj.successful_tasks_24h}")

        output.append("<h3>Marketplace (24h)</h3>")
        output.append(f"Sales: {obj.sales_24h}")
        output.append(f"Volume: {obj.volume_24h:.4f} SOL")
        output.append(f"Active Listings: {obj.active_listings_count}")
        output.append(f"Unique Traders: {obj.unique_traders_24h}")

        output.append("<h3>Users</h3>")
        output.append(f"Total: {obj.total_users}")
        output.append(f"Active (24h): {obj.active_users_24h}")
        output.append(f"New (24h): {obj.new_users_24h}")

        output.append("<h3>NFT Data</h3>")
        output.append(f"NFTs Tracked: {obj.total_nfts_tracked:,}")
        output.append(f"Collections: {obj.total_collections_tracked}")
        output.append(f"Updated (24h): {obj.collections_updated_24h}")

        return format_html('<pre>{}</pre>', '\n'.join(output))
    detailed_metrics_display.short_description = 'Detailed Metrics'

    def alerts_display(self, obj):
        """Display alerts in formatted view"""
        if not obj.alerts:
            return format_html('<span style="color: #28a745;">No alerts</span>')

        output = [f"<strong>{len(obj.alerts)} Alerts:</strong>"]
        for alert in obj.alerts:
            output.append(f"⚠ {alert}")

        return format_html('<pre>{}</pre>', '\n'.join(output))
    alerts_display.short_description = 'Alerts'

    def services_display(self, obj):
        """Display services in formatted view"""
        metadata = obj.metadata.get('services', {})
        output = []

        for service, status in metadata.items():
            icon = '✓' if status == 'running' or status == 'connected' else '✗'
            color = '#28a745' if status == 'running' or status == 'connected' else '#dc3545'
            output.append(f'<span style="color: {color};">{icon} {service}: {status}</span>')

        return format_html('<br>'.join(output) if output else 'No service data')
    services_display.short_description = 'Service Details'


@admin.register(ServiceHealthCheck)
class ServiceHealthCheckAdmin(admin.ModelAdmin):
    """Admin interface for ServiceHealthCheck model"""

    list_display = [
        'timestamp',
        'service_type',
        'health_status',
        'response_time_display',
        'error_summary',
    ]
    list_filter = ['service_type', 'is_healthy', 'timestamp']
    search_fields = ['error_message', 'service_type']
    readonly_fields = ['timestamp', 'created_at', 'details_display']
    ordering = ['-timestamp']

    fieldsets = (
        ('Check Info', {
            'fields': ('service_type', 'timestamp', 'is_healthy')
        }),
        ('Performance', {
            'fields': ('response_time_ms',)
        }),
        ('Error Details', {
            'fields': ('error_message',)
        }),
        ('Additional Details', {
            'fields': ('details', 'details_display'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )

    def health_status(self, obj):
        """Display health status with icon"""
        if obj.is_healthy:
            return format_html('<span style="color: #28a745;">✓ Healthy</span>')
        else:
            return format_html('<span style="color: #dc3545;">✗ Unhealthy</span>')
    health_status.short_description = 'Status'

    def response_time_display(self, obj):
        """Display response time with color coding"""
        if obj.response_time_ms is None:
            return '-'

        if obj.response_time_ms < 100:
            color = '#28a745'
        elif obj.response_time_ms < 500:
            color = '#ffc107'
        else:
            color = '#dc3545'

        return format_html(
            '<span style="color: {};">{:.0f} ms</span>',
            color,
            obj.response_time_ms
        )
    response_time_display.short_description = 'Response Time'

    def error_summary(self, obj):
        """Display error message summary"""
        if not obj.error_message:
            return '-'
        return obj.error_message[:100] + ('...' if len(obj.error_message) > 100 else '')
    error_summary.short_description = 'Error'

    def details_display(self, obj):
        """Display details in formatted view"""
        if not obj.details:
            return 'No details'

        output = []
        for key, value in obj.details.items():
            output.append(f"{key}: {value}")

        return format_html('<pre>{}</pre>', '\n'.join(output))
    details_display.short_description = 'Details'


@admin.register(PerformanceMetric)
class PerformanceMetricAdmin(admin.ModelAdmin):
    """Admin interface for PerformanceMetric model"""

    list_display = [
        'timestamp',
        'metric_type',
        'value_display',
        'component',
    ]
    list_filter = ['metric_type', 'component', 'timestamp']
    search_fields = ['metric_type', 'component']
    readonly_fields = ['timestamp', 'created_at', 'metadata_display']
    ordering = ['-timestamp']

    fieldsets = (
        ('Metric Info', {
            'fields': ('metric_type', 'timestamp', 'component')
        }),
        ('Value', {
            'fields': ('value', 'unit')
        }),
        ('Additional Data', {
            'fields': ('metadata', 'metadata_display'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )

    def value_display(self, obj):
        """Display value with unit"""
        return f"{obj.value:.2f} {obj.unit}".strip()
    value_display.short_description = 'Value'

    def metadata_display(self, obj):
        """Display metadata in formatted view"""
        if not obj.metadata:
            return 'No metadata'

        output = []
        for key, value in obj.metadata.items():
            output.append(f"{key}: {value}")

        return format_html('<pre>{}</pre>', '\n'.join(output))
    metadata_display.short_description = 'Metadata'


@admin.register(SystemAlert)
class SystemAlertAdmin(admin.ModelAdmin):
    """Admin interface for SystemAlert model"""

    list_display = [
        'triggered_at',
        'alert_level_display',
        'category',
        'title',
        'resolution_status',
        'duration_display',
    ]
    list_filter = ['alert_level', 'category', 'is_resolved', 'triggered_at']
    search_fields = ['title', 'message', 'source_component']
    readonly_fields = [
        'triggered_at',
        'created_at',
        'updated_at',
        'duration_display',
        'ecosystem_health',
    ]
    list_editable = []
    ordering = ['-triggered_at']

    fieldsets = (
        ('Alert Info', {
            'fields': ('alert_level', 'category', 'title', 'message')
        }),
        ('Status', {
            'fields': ('triggered_at', 'is_resolved', 'resolved_at', 'resolution_notes')
        }),
        ('Context', {
            'fields': ('source_component', 'ecosystem_health', 'metadata')
        }),
        ('Notification', {
            'fields': ('notification_sent', 'notification_sent_at')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'duration_display')
        }),
    )

    actions = ['mark_as_resolved', 'send_notifications']

    def alert_level_display(self, obj):
        """Display alert level with color"""
        colors = {
            'INFO': '#17a2b8',
            'WARNING': '#ffc107',
            'ERROR': '#fd7e14',
            'CRITICAL': '#dc3545',
        }
        color = colors.get(obj.alert_level, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_alert_level_display()
        )
    alert_level_display.short_description = 'Level'

    def resolution_status(self, obj):
        """Display resolution status"""
        if obj.is_resolved:
            return format_html('<span style="color: #28a745;">✓ Resolved</span>')
        else:
            return format_html('<span style="color: #ffc107;">⏳ Active</span>')
    resolution_status.short_description = 'Status'

    def duration_display(self, obj):
        """Display alert duration"""
        seconds = obj.duration_seconds
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds / 60)}m"
        else:
            return f"{int(seconds / 3600)}h"
    duration_display.short_description = 'Duration'

    def mark_as_resolved(self, request, queryset):
        """Mark selected alerts as resolved"""
        updated = queryset.filter(is_resolved=False).update(
            is_resolved=True,
            resolved_at=timezone.now()
        )
        self.message_user(request, f'{updated} alert(s) marked as resolved.')
    mark_as_resolved.short_description = 'Mark as resolved'

    def send_notifications(self, request, queryset):
        """Send notifications for selected alerts"""
        # TODO: Implement notification sending
        self.message_user(request, 'Notification sending not yet implemented.')
    send_notifications.short_description = 'Send notifications'
