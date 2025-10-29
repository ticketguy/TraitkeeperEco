# notifications/services.py

from datetime import timedelta
import logging
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

# Import the models this service will interact with.
from .models import AdminNotification, Notification
from admin_panel.models import AdminUser
from django.db.models import Count
from indexer.models import FailedTransaction, CollectionMarketStats
from nft_data.models import NFTCollection, PendingCollection

logger = logging.getLogger(__name__)


class NotificationService:
    """
    A centralized service for handling all notification logic.

    This service is responsible for sending emails, creating in-app notifications,
    and eventually handling push notifications for both regular users and admins.
    """
    
    @staticmethod
    def send_admin_welcome_email(user: AdminUser):
        """Sends a welcome email to a new admin user."""
        subject = 'Welcome to the TraitKeeper Admin Panel'
        message = f"""
Hello {user.username},

Welcome to the TraitKeeper Admin Panel! Your account has been created.

Important security information:
- Your password will expire in 90 days.
- Please enable two-factor authentication.

Best regards,
The TraitKeeper Team
"""
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
            logger.info(f"Sent welcome email to new admin: {user.email}")
        except Exception as e:
            logger.error(f"Failed to send welcome email to {user.email}: {e}")
    
    # You would continue to move your other email functions here as static methods...
    @staticmethod
    def send_admin_deactivation_email(user):
        """Send notification email when admin account is deactivated"""
        subject = 'Admin Account Deactivated'
        message = f"""
        Hello {user.username},
        
        Your admin account has been deactivated. If this was not expected, please contact the system administrator.
        
        Best regards,
        TraitKeeper Admin Team
        """
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True,
        )
        
    @staticmethod
    def send_admin_reactivation_email(user):
        """Send notification email when admin account is reactivated"""
        subject = 'Admin Account Reactivated'
        message = f"""
        Hello {user.username},
        
        Your admin account has been reactivated. You can now access the admin panel.
        
        Best regards,
        TraitKeeper Admin Team
        """
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True,
        )
        
    @staticmethod
    def notify_admins_of_deletion(deleted_user):
        """Notify other admins when an admin user is deleted"""
        subject = 'Admin User Deleted'
        message = f"""
        Attention Admins,
        
        The admin user {deleted_user.username} has been deleted from the system.
        
        Best regards,
        TraitKeeper Admin Team
        """
        admins = AdminUser.objects.filter(is_staff=True, is_active=True).exclude(pk=deleted_user.pk)
        admin_emails = [admin.email for admin in admins if admin.email]
        
        if admin_emails:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                admin_emails,
                fail_silently=True,
            )
        
    @staticmethod
    def create_admin_notification(subject: str, message: str, notification_type: str, severity: str = 'info'):
        """Creates an in-app notification for all active administrators."""
        admin_users = AdminUser.objects.filter(is_active=True, is_staff=True)
        for admin_user in admin_users:
            AdminNotification.objects.create(
                type=notification_type,
                message=f"<strong>{subject}</strong><br>{message}",
                severity=severity,
                admin_user=admin_user,
                details={'subject': subject, 'message': message}
            )

    @staticmethod
    def send_daily_system_health_report():
        """Generates and sends a daily summary of system health metrics to all admins."""
        try:
            total_collections = NFTCollection.objects.filter(is_listed=True).count()
            pending_collections = PendingCollection.objects.filter(status='pending').count()
            failed_txns_24h = FailedTransaction.objects.filter(
                created_at__gte=timezone.now() - timedelta(days=1)
            ).count()
            stale_collections = CollectionMarketStats.objects.filter(
                timestamp__lt=timezone.now() - timedelta(hours=6)
            ).count()
            
            # Combine subject and message for the service
            subject = "Daily System Health Report"
            message = f"""
**SYSTEM METRICS:**
- **Active Collections:** {total_collections}
- **Pending Submissions:** {pending_collections}
- **Failed Transactions (24h):** {failed_txns_24h}
- **Stale Collections (>6h old):** {stale_collections}

**RECOMMENDATIONS:**
- Review {pending_collections} pending submissions.
- Investigate the cause of {failed_txns_24h} failed transactions.
- Check indexer health; {stale_collections} collections have stale stats.
"""
            # Use the existing service method to create the in-app notification
            NotificationService.create_admin_notification(
                subject=subject,
                message=message,
                notification_type='system_alert',
                severity='info'
            )
            logger.info("Successfully sent daily system health report.")
        except Exception as e:
            logger.error(f"Failed to generate and send daily health report: {e}")
            # Optionally, send a failure alert
            NotificationService.create_admin_notification(
                subject="CRITICAL: Health Report Failed",
                message=f"Failed to generate daily health report: {str(e)}",
                notification_type='system_alert',
                severity='error'
            )