# nft_data/signals.py
"""
Signals for NFT data models.

Handles automatic tasks when collections are added/updated.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.utils import timezone
from nft_data.models import NFTCollection, PendingCollection
# Import the centralized service for notifications
from notifications.services import NotificationService

logger = logging.getLogger(__name__)


def send_unified_admin_notification(subject, message, notification_type, severity='info'):
    """
    Acts as a bridge to send both email and in-app notifications.
    - Uses NotificationService for standardized in-app alerts.
    - Uses Django's send_mail for system-level email alerts.
    """
    try:
        # 1. Create the in-app notification via the service
        NotificationService.create_admin_notification(
            subject=subject,
            message=message,
            notification_type=notification_type,
            severity=severity
        )

        # 2. Send the corresponding email alert
        email_subject = f"[TraitKeeper Alert - {severity.upper()}] {subject}"
        email_message = f"""
Hello Admin,

This is a system alert from TraitKeeper.

{message}

---
Notification generated at {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        # NOTE: You should configure these in your settings.py
        from_email = '0xticketguy@gmail.com'
        recipient_list = ['samuelokwu85@gmail.com']

        send_mail(
            email_subject,
            email_message,
            from_email,
            recipient_list,
            fail_silently=False
        )
        logger.info(f"Successfully sent unified admin notification: {subject}")

    except Exception as e:
        logger.error(f"Failed to dispatch unified admin notification '{subject}': {e}", exc_info=True)


@receiver(post_save, sender=PendingCollection)
def notify_admins_of_new_submission(sender, instance, created, **kwargs):
    """
    Sends a detailed notification when a new collection is submitted for review.
    """
    if created and instance.status == 'pending':
        # This message is now more structured and actionable for admins
        send_unified_admin_notification(
            subject=f"New Collection Submission: {instance.name}",
            message=f"""
A new collection has been submitted and requires your review.

**Collection Details:**
- **Name:** {instance.name}
- **Mint Address:** {instance.mint_address}
- **Submitted By:** {instance.submitted_by}
- **Submitted At:** {instance.created.strftime('%Y-%m-%d %H:%M:%S UTC')}

**Action Required:** Please review and approve or reject this submission in the admin panel.
""",
            notification_type='collection_submitted',
            severity='info'
        )


@receiver(post_save, sender=NFTCollection)
def trigger_backfill_for_new_collection(sender, instance, created, **kwargs):
    """
    Auto-trigger historical backfill when a new collection is added.

    This runs ONE TIME when is_listed is set to True for the first time.
    """
    # Only trigger for newly created collections that are listed
    if created and instance.is_listed:
        logger.info(f"🆕 New collection added: {instance.name}")
        logger.info(f"📚 Queuing automatic historical backfill as background task...")

        try:
            # Import background task manager and task classes
            from indexer.background_task_manager import background_task_manager, Task, TaskPriority
            from indexer.services import IndexerService

            # Create async task function
            async def backfill_task():
                """Background task to backfill collection history."""
                indexer = IndexerService()

                # Fetch historical transactions
                logger.info(f"🔍 Fetching historical transactions for {instance.name}...")
                await indexer.process_onchain_events(instance.address)

                # Fetch current market stats
                logger.info(f"📊 Fetching market stats for {instance.name}...")
                await indexer.fetch_and_store_all_market_stats(instance)

                logger.info(f"✅ Backfill complete for {instance.name}")

            # Queue the backfill as a background task (no deadlock)
            task = Task(
                id=f"backfill_{instance.address}_{int(timezone.now().timestamp())}",
                name=f"Backfill {instance.name}",
                function=backfill_task,
                args=(),
                priority=TaskPriority.HIGH
            )
            background_task_manager.add_task(task)

            logger.info(f"✅ Backfill task queued for {instance.name}")

        except Exception as e:
            logger.error(f"❌ Failed to queue backfill for {instance.name}: {e}", exc_info=True)
            # Don't raise - collection is still saved, backfill can be run manually
