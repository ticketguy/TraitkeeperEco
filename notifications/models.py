from django.db import models
from django.conf import settings
from django.utils import timezone
from admin_panel.models import AdminUser 


class NotificationManager(models.Manager):
    def unread(self):
        return self.filter(is_read=False)


class AdminNotification(models.Model):
    TYPE_CHOICES = (
        ('server_load', 'High Server Load'),
        ('failed_login', 'Failed Login Attempt'),
        ('collection_populated', 'Collections Populated'),
        ('collection_refreshed', 'Collections Refreshed'),
        ('collection_submitted', 'Collection Submitted'),
        ('collection_action', 'Collection Action'),
        # Enhanced monitoring types
        ('system_alert', 'System Alert'),
        ('magic_eden_issue', 'Magic Eden Issue'),
        ('data_anomaly', 'Data Anomaly'),
        ('performance_issue', 'Performance Issue'),
        ('collection_issue', 'Collection Issue'),
    )
    SEVERITY_CHOICES = (
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    )
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='info')
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    admin_user = models.ForeignKey(
        AdminUser, 
        on_delete=models.CASCADE, 
        related_name='notifications', 
        null=True, 
        blank=True
    )
    objects = NotificationManager()

    class Meta:
        verbose_name = "Admin Notification"
        verbose_name_plural = "Admin Notifications"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_display()}: {self.message[:50]}..."



class Notification(models.Model):
    EVENT_TYPES = (
        ('transaction', 'Transaction'),
        ('sweep', 'Collection Sweep'),
        ('trait_performance', 'Trait Performance Change'),
        ('high_profile_transfer', 'High Profile Transfer'),
        ('wallet_activity', 'Wallet Activity'),
        # NFT-specific events
        ('nft_listed', 'NFT Listed'),
        ('nft_sold', 'NFT Sold'),
        ('nft_delisted', 'NFT Delisted'),
        ('bid_received', 'Bid Received'),
        ('bid_accepted', 'Bid Accepted'),
        ('bid_rejected', 'Bid Rejected'),
        ('bid_outbid', 'Outbid on NFT'),
        ('watchlist_listed', 'Watchlist Item Listed'),
        ('watchlist_price_change', 'Watchlist Price Change'),
        ('achievement_earned', 'Achievement Earned'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    message = models.TextField()
    data = models.JSONField(default=dict)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    # Optional foreign keys for easy querying
    related_nft = models.ForeignKey(
        'nft_data.NFT',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    related_listing = models.ForeignKey(
        'marketplace.NFTListing',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    related_bid = models.ForeignKey(
        'marketplace.Bid',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
            models.Index(fields=['user', 'event_type']),
        ]

    def __str__(self):
        return f"{self.event_type} notification for {self.user.username} at {self.created_at}"

class NotificationPreference(models.Model):
    NOTIFICATION_TYPES = (
        ('transaction', 'Transactions'),
        ('sweep', 'Collection Sweeps'),
        ('trait_performance', 'Trait Performance Changes'),
        ('high_profile_transfer', 'High Profile Transfers'),
        ('wallet_activity', 'Wallet Activity'),
        # NFT-specific notification preferences
        ('nft_listed', 'NFT Listings'),
        ('nft_sold', 'NFT Sales'),
        ('bid_received', 'Bids Received'),
        ('bid_accepted', 'Bids Accepted'),
        ('bid_outbid', 'Outbid Alerts'),
        ('watchlist_alerts', 'Watchlist Alerts'),
        ('achievement_earned', 'Achievement Notifications'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preferences')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    enabled = models.BooleanField(default=True)
    # Email and Push notification preferences
    notify_via_email = models.BooleanField(default=False)
    notify_via_push = models.BooleanField(default=False)
    # For transaction alerts, allow filtering by value
    transaction_min_value = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True, help_text="Minimum transaction value for notification (SOL)")
    # Specific filters
    specific_collections = models.JSONField(default=list, blank=True, help_text="List of collection IDs to notify about")
    specific_traits = models.JSONField(default=list, blank=True, help_text="List of trait type IDs to notify about")
    specific_wallets = models.JSONField(default=list, blank=True, help_text="List of wallet addresses to notify about")

    class Meta:
        unique_together = ('user', 'notification_type')

    def __str__(self):
        return f"{self.notification_type} preference for {self.user.username}: {'Enabled' if self.enabled else 'Disabled'}"