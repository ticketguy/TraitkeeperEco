# nft_data/signals.py - Refactored to use NotificationService
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from .models import PendingCollection, NFTCollection
from indexer.models import FailedTransaction, CollectionMarketStats
import logging
from asgiref.sync import async_to_sync
from indexer.services import IndexerService
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count
# Import the new centralized notification service
from notifications.services import NotificationService
from django_redis import get_redis_connection
from admin_panel.models import PrimaryProviderSetting


logger = logging.getLogger(__name__)

def send_unified_admin_notification(subject, message, notification_type='system_alert', severity='info'):
    """
    Sends a unified notification to administrators via email and in-app notification.
    
    This function now uses the NotificationService to handle the creation of 
    in-app notifications, centralizing that logic.
    """
    try:
        # 1. Send email notification to admins
        formatted_message = f"""
TraitKeeper Admin Alert - {severity.upper()}
Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

{message}

---
TraitKeeper Monitoring System
"""
        from_email = '0xticketguy@gmail.com'
        recipient_list = ['samuelokwu85@gmail.com']
        send_mail(
            subject=f"[TraitKeeper-{severity.upper()}] {subject}",
            message=formatted_message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=True
        )
        
        # 2. Create in-app notification using the NotificationService
        NotificationService.create_admin_notification(
            subject=subject,
            message=message,
            notification_type=notification_type,
            severity=severity
        )
        
        logger.info(f"Successfully dispatched unified admin notification: {subject}")
        
    except Exception as e:
        logger.error(f"Failed to send unified admin notification '{subject}': {str(e)}")



@receiver(post_save, sender=PendingCollection)
def notify_admins_of_new_submission(sender, instance, created, **kwargs):
    if created and instance.status == 'pending':
        send_unified_admin_notification(
            subject=f"New Collection Submission: {instance.name}",
            message=f"""
Collection Details:
- Name: {instance.name}
- Mint Address: {instance.mint_address}
- Submitted By: {instance.submitted_by}
- Submitted At: {instance.submitted_at}

Action Required: Please review in admin panel.
""",
            notification_type='collection_submitted',
            severity='info'
        )

@receiver(post_save, sender=PendingCollection)
def run_metrics_on_collection_approval(sender, instance, **kwargs):
    if instance.status == 'approved':
        try:
            # Using django-model-utils FieldTracker to check if 'status' changed
            if kwargs.get('created', False) or (hasattr(instance, 'tracker') and instance.tracker.has_changed('status')):
                indexer_service = IndexerService()
                async_to_sync(indexer_service.update_collection_after_retrieval)(instance.mint_address)
                
                send_unified_admin_notification(
                    subject=f"Collection Approved: {instance.name}",
                    message=f"Collection '{instance.name}' approved and processing completed successfully.",
                    notification_type='collection_action',
                    severity='info'
                )
        except Exception as e:
            send_unified_admin_notification(
                subject=f"CRITICAL: Collection Processing Failed",
                message=f"""
Processing Error Details:
- Collection: {instance.name}
- Mint Address: {instance.mint_address}
- Error: {str(e)}

Immediate Action Required: Manual intervention needed.
""",
                notification_type='collection_issue',
                severity='error'
            )

@receiver(post_save, sender=FailedTransaction)
def notify_failed_transaction_threshold(sender, instance, created, **kwargs):
    if created:
        one_hour_ago = timezone.now() - timedelta(hours=1)
        recent_failures_count = FailedTransaction.objects.filter(created_at__gte=one_hour_ago).count()
        
        # Check if the threshold is met
        if recent_failures_count >= 10:
            collection_failures = FailedTransaction.objects.filter(
                created_at__gte=one_hour_ago
            ).values('collection_address').annotate(count=Count('id')).order_by('-count')[:5]
            
            failure_details = "\n".join([
                f"  - {item['collection_address']}: {item['count']} failures"
                for item in collection_failures
            ])
            
            send_unified_admin_notification(
                subject=f"High Failure Rate: {recent_failures_count} Failed Transactions",
                message=f"""
System Health Alert:
- Total Failures (last hour): {recent_failures_count}
- Latest Error: {instance.error_message}
- Provider: {instance.provider_name}

Top Failed Collections:
{failure_details}

Possible Causes:
- API provider issues
- Network connectivity problems
- Data parsing errors

Action Required: Check indexer service status and logs.
""",
                notification_type='performance_issue',
                severity='warning'
            )

@receiver(post_save, sender=CollectionMarketStats)
def monitor_stats_anomalies(sender, instance, created, **kwargs):
    if not created: # Only check on updates
        try:
            collection = NFTCollection.objects.filter(address=instance.collection_address).first()
            if not collection:
                return # Can't report on a collection that doesn't exist in our DB

            # Zero floor price alert
            if instance.floor_price == 0 and instance.total_supply > 0:
                send_unified_admin_notification(
                    subject=f"Zero Floor Price Alert: {collection.name}",
                    message=f"""
Data Anomaly Detected:
- Collection: {collection.name}
- Address: {instance.collection_address}
- Floor Price: Now 0
- Listed Count: {instance.listed_count}

Possible Issues:
- Magic Eden API problems
- All listings may have expired or been sold

Action Required: Manually verify the collection's status on Magic Eden.
""",
                    notification_type='data_anomaly',
                    severity='warning'
                )
            
            # Volume spike detection
            if instance.volume_24h > 0:
                prev_stats = CollectionMarketStats.objects.filter(
                    collection_address=instance.collection_address,
                    timestamp__lt=instance.timestamp
                ).order_by('-timestamp').first()
                
                if prev_stats and prev_stats.volume_24h > 0:
                    volume_change = (instance.volume_24h - prev_stats.volume_24h) / prev_stats.volume_24h
                    if volume_change > 10:  # >1000% increase
                        send_unified_admin_notification(
                            subject=f"Significant Volume Spike: {collection.name}",
                            message=f"""
Unusual Market Activity Detected:
- Collection: {collection.name}
- Previous 24h Volume: {prev_stats.volume_24h:.2f} SOL
- Current 24h Volume: {instance.volume_24h:.2f} SOL
- Increase: {volume_change:.1%}

Action Required: Review recent activity for this collection.
""",
                            notification_type='data_anomaly',
                            severity='info'
                        )
        except Exception as e:
            logger.error(f"Error in monitor_stats_anomalies for {instance.collection_address}: {str(e)}")

@receiver(post_delete, sender=NFTCollection)
def notify_collection_deletion(sender, instance, **kwargs):
    send_unified_admin_notification(
        subject=f"Collection Deleted: {instance.name}",
        message=f"""
A collection was deleted from the database.
- Name: {instance.name}
- Address: {instance.address}
- Symbol: {instance.symbol}
- Deletion Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

Warning: If this action was unintentional, a database restore from a backup may be required.
""",
        notification_type='collection_action',
        severity='warning'
    )

def send_daily_system_health_report():
    """Generates and sends a daily summary of system health metrics."""
    try:
        total_collections = NFTCollection.objects.filter(is_listed=True).count()
        pending_collections = PendingCollection.objects.filter(status='pending').count()
        failed_txns_24h = FailedTransaction.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=1)
        ).count()
        
        stale_collections = CollectionMarketStats.objects.filter(
            timestamp__lt=timezone.now() - timedelta(hours=6)
        ).count()
        
        collections_with_symbols = NFTCollection.objects.exclude(symbol='').exclude(symbol__isnull=True).count()
        me_coverage = (collections_with_symbols / total_collections * 100) if total_collections > 0 else 0
        
        recommendations = []
        if pending_collections > 5:
            recommendations.append(f"Review {pending_collections} pending submissions in the admin panel.")
        if failed_txns_24h > 50:
            recommendations.append(f"Investigate the cause of {failed_txns_24h} failed transactions.")
        if stale_collections > 10:
            recommendations.append(f"Check indexer health; {stale_collections} collections have stale stats.")
        if me_coverage < 70:
            recommendations.append(f"Improve Magic Eden coverage, currently at {me_coverage:.1f}%.")
        
        if not recommendations:
            recommendations.append("System is operating within normal parameters.")
        
        send_unified_admin_notification(
            subject="Daily System Health Report",
            message=f"""
SYSTEM METRICS:
- Active Collections: {total_collections}
- Pending Submissions: {pending_collections}
- Magic Eden Coverage: {me_coverage:.1f}%
- Failed Transactions (24h): {failed_txns_24h}
- Stale Collection Stats (>6h old): {stale_collections}

RECOMMENDATIONS:
{chr(10).join(f'• {rec}' for rec in recommendations)}
""",
            notification_type='system_alert',
            severity='info'
        )
        
    except Exception as e:
        send_unified_admin_notification(
            subject="CRITICAL: Health Report Generation Failed",
            message=f"The automated daily health report failed to generate. Error: {str(e)}",
            notification_type='system_alert',
            severity='error'
        )

REDIS_CHANNEL = "config_updates"

@receiver([post_save, post_delete], sender=PrimaryProviderSetting)
def handle_provider_change(sender, instance, **kwargs):
    """
    Fires when a PrimaryProviderSetting is saved or deleted.
    Publishes a message to a Redis channel to notify other services.
    """
    try:
        redis_conn = get_redis_connection("default")
        redis_conn.publish(REDIS_CHANNEL, "reload")
        logger.info(f"📡 Published 'reload' signal to Redis channel '{REDIS_CHANNEL}' due to change in provider settings.")
    except Exception as e:
        logger.error(f"Failed to publish provider change signal to Redis: {e}")