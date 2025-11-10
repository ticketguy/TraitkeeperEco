from django.db import models
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
import json


class EcosystemHealth(models.Model):
    """
    Tracks overall platform-wide health metrics and ecosystem indicators.

    This model stores periodic snapshots of the entire TraitKeeper ecosystem health,
    including marketplace activity, indexer performance, user engagement, and system resources.
    """

    class HealthStatus(models.TextChoices):
        HEALTHY = 'HEALTHY', 'Healthy'
        WARNING = 'WARNING', 'Warning'
        CRITICAL = 'CRITICAL', 'Critical'
        ERROR = 'ERROR', 'Error'

    # Timestamp
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    # Overall health status
    status = models.CharField(
        max_length=20,
        choices=HealthStatus.choices,
        default=HealthStatus.HEALTHY
    )

    # System resource metrics
    cpu_percent = models.FloatField(default=0, help_text="CPU usage percentage")
    memory_percent = models.FloatField(default=0, help_text="Memory usage percentage")
    disk_percent = models.FloatField(default=0, help_text="Disk usage percentage")

    # Service status flags
    indexer_running = models.BooleanField(default=False)
    redis_connected = models.BooleanField(default=False)
    database_connected = models.BooleanField(default=True)

    # Task metrics
    active_tasks = models.IntegerField(default=0, help_text="Currently active background tasks")
    failed_tasks_24h = models.IntegerField(default=0, help_text="Failed tasks in last 24 hours")
    successful_tasks_24h = models.IntegerField(default=0, help_text="Successful tasks in last 24 hours")

    # Indexer metrics
    last_successful_index = models.DateTimeField(null=True, blank=True)
    events_indexed_24h = models.IntegerField(default=0, help_text="Events indexed in last 24 hours")
    indexing_lag_minutes = models.FloatField(default=0, help_text="Minutes behind blockchain")

    # Marketplace ecosystem metrics
    active_listings_count = models.IntegerField(default=0)
    sales_24h = models.IntegerField(default=0)
    volume_24h = models.DecimalField(max_digits=20, decimal_places=4, default=0, help_text="SOL")
    unique_traders_24h = models.IntegerField(default=0)

    # User engagement metrics
    active_users_24h = models.IntegerField(default=0, help_text="Users active in last 24 hours")
    new_users_24h = models.IntegerField(default=0, help_text="New users in last 24 hours")
    total_users = models.IntegerField(default=0)

    # NFT data metrics
    total_nfts_tracked = models.IntegerField(default=0)
    total_collections_tracked = models.IntegerField(default=0)
    collections_updated_24h = models.IntegerField(default=0)

    # Alert data
    alerts = models.JSONField(default=list, help_text="List of current alerts")
    alert_count = models.IntegerField(default=0)

    # Additional metadata
    metadata = models.JSONField(default=dict, help_text="Additional metrics and context")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ecosystem Health"
        verbose_name_plural = "Ecosystem Health Records"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['status', '-timestamp']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"Ecosystem Health - {self.status} at {self.timestamp}"

    @property
    def is_healthy(self) -> bool:
        """Quick check if ecosystem is healthy"""
        return self.status == self.HealthStatus.HEALTHY

    @property
    def has_critical_issues(self) -> bool:
        """Check if there are critical issues"""
        return self.status == self.HealthStatus.CRITICAL

    @classmethod
    def get_latest(cls):
        """Get the most recent health record"""
        return cls.objects.first()

    @classmethod
    def get_health_trend(cls, hours: int = 24):
        """Get health records for the last N hours"""
        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        return cls.objects.filter(timestamp__gte=cutoff)


class ServiceHealthCheck(models.Model):
    """
    Tracks health checks for individual services/components.
    More granular than EcosystemHealth for debugging specific issues.
    """

    class ServiceType(models.TextChoices):
        INDEXER = 'INDEXER', 'Indexer Service'
        DATABASE = 'DATABASE', 'Database'
        REDIS = 'REDIS', 'Redis Cache'
        MARKETPLACE = 'MARKETPLACE', 'Marketplace'
        NOTIFICATIONS = 'NOTIFICATIONS', 'Notifications'
        SOLANA_RPC = 'SOLANA_RPC', 'Solana RPC'
        EXTERNAL_API = 'EXTERNAL_API', 'External API'

    service_type = models.CharField(max_length=50, choices=ServiceType.choices)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    is_healthy = models.BooleanField(default=True)
    response_time_ms = models.FloatField(null=True, blank=True, help_text="Response time in milliseconds")

    error_message = models.TextField(blank=True)
    details = models.JSONField(default=dict, help_text="Additional check details")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Service Health Check"
        verbose_name_plural = "Service Health Checks"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['service_type', '-timestamp']),
            models.Index(fields=['is_healthy', '-timestamp']),
        ]

    def __str__(self):
        status = "✓" if self.is_healthy else "✗"
        return f"{status} {self.service_type} at {self.timestamp}"


class PerformanceMetric(models.Model):
    """
    Stores fine-grained performance metrics for trending and analysis.
    """

    class MetricType(models.TextChoices):
        INDEXING_SPEED = 'INDEXING_SPEED', 'Indexing Speed (events/min)'
        API_RESPONSE_TIME = 'API_RESPONSE_TIME', 'API Response Time (ms)'
        DATABASE_QUERY_TIME = 'DATABASE_QUERY_TIME', 'Database Query Time (ms)'
        CACHE_HIT_RATE = 'CACHE_HIT_RATE', 'Cache Hit Rate (%)'
        CONCURRENT_USERS = 'CONCURRENT_USERS', 'Concurrent Users'
        TASK_COMPLETION_TIME = 'TASK_COMPLETION_TIME', 'Task Completion Time (s)'

    metric_type = models.CharField(max_length=50, choices=MetricType.choices)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    value = models.FloatField(help_text="Metric value")
    unit = models.CharField(max_length=50, blank=True, help_text="Unit of measurement")

    # Context
    component = models.CharField(max_length=100, blank=True, help_text="Specific component or endpoint")
    metadata = models.JSONField(default=dict, help_text="Additional context")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Performance Metric"
        verbose_name_plural = "Performance Metrics"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['metric_type', '-timestamp']),
            models.Index(fields=['component', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.metric_type}: {self.value} {self.unit} at {self.timestamp}"


class SystemAlert(models.Model):
    """
    Tracks system alerts and their resolution.
    """

    class AlertLevel(models.TextChoices):
        INFO = 'INFO', 'Information'
        WARNING = 'WARNING', 'Warning'
        ERROR = 'ERROR', 'Error'
        CRITICAL = 'CRITICAL', 'Critical'

    class AlertCategory(models.TextChoices):
        RESOURCE = 'RESOURCE', 'Resource Usage'
        SERVICE = 'SERVICE', 'Service Status'
        DATA = 'DATA', 'Data Integrity'
        SECURITY = 'SECURITY', 'Security'
        PERFORMANCE = 'PERFORMANCE', 'Performance'

    alert_level = models.CharField(max_length=20, choices=AlertLevel.choices)
    category = models.CharField(max_length=50, choices=AlertCategory.choices)

    title = models.CharField(max_length=200)
    message = models.TextField()

    triggered_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    is_resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True)

    # Related health record
    ecosystem_health = models.ForeignKey(
        EcosystemHealth,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='system_alerts'
    )

    # Alert metadata
    source_component = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict)

    # Notification tracking
    notification_sent = models.BooleanField(default=False)
    notification_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Alert"
        verbose_name_plural = "System Alerts"
        ordering = ['-triggered_at']
        indexes = [
            models.Index(fields=['is_resolved', '-triggered_at']),
            models.Index(fields=['alert_level', '-triggered_at']),
            models.Index(fields=['category', '-triggered_at']),
        ]

    def __str__(self):
        status = "Resolved" if self.is_resolved else "Active"
        return f"[{self.alert_level}] {self.title} - {status}"

    def mark_resolved(self, notes: str = ""):
        """Mark alert as resolved"""
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        self.save(update_fields=['is_resolved', 'resolved_at', 'resolution_notes', 'updated_at'])

    @property
    def duration_seconds(self) -> float:
        """Calculate how long alert was active"""
        if not self.is_resolved:
            return (timezone.now() - self.triggered_at).total_seconds()
        return (self.resolved_at - self.triggered_at).total_seconds()


class HealthShareToken(models.Model):
    """
    Token for sharing system health stats publicly.
    Sensitive data is excluded from shared stats.
    """
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    # Share options
    include_performance = models.BooleanField(default=True, help_text="Include CPU, Memory, Disk stats")
    include_services = models.BooleanField(default=True, help_text="Include service status")
    include_marketplace = models.BooleanField(default=True, help_text="Include marketplace stats")
    include_uptime = models.BooleanField(default=True, help_text="Include system uptime")

    # Usage tracking
    view_count = models.IntegerField(default=0)
    last_accessed = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Health Share Token"
        verbose_name_plural = "Health Share Tokens"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token', 'expires_at']),
        ]

    def __str__(self):
        return f"Share Token {self.token[:8]}... (expires {self.expires_at})"

    @property
    def is_valid(self) -> bool:
        """Check if token is still valid"""
        return timezone.now() < self.expires_at

    def increment_view_count(self):
        """Increment view count and update last accessed time"""
        self.view_count += 1
        self.last_accessed = timezone.now()
        self.save(update_fields=['view_count', 'last_accessed'])
