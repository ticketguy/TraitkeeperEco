# nft_data/signals.py
"""
Signals for NFT data models.

Handles automatic tasks when collections are added/updated.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from nft_data.models import NFTCollection

logger = logging.getLogger(__name__)


@receiver(post_save, sender=NFTCollection)
def trigger_backfill_for_new_collection(sender, instance, created, **kwargs):
    """
    Auto-trigger historical backfill when a new collection is added.

    This runs ONE TIME when is_listed is set to True for the first time.
    """
    # Only trigger for newly created collections that are listed
    if created and instance.is_listed:
        logger.info(f"🆕 New collection added: {instance.name}")
        logger.info(f"📚 Triggering automatic historical backfill...")

        try:
            # Import here to avoid circular dependency
            from django.core.management import call_command

            # Run backfill in background thread to avoid blocking
            # Note: This uses call_command which handles async internally
            call_command('backfill_collection', instance.address)

            logger.info(f"✅ Backfill queued for {instance.name}")

        except Exception as e:
            logger.error(f"❌ Failed to trigger backfill for {instance.name}: {e}", exc_info=True)
            # Don't raise - collection is still saved, backfill can be run manually
