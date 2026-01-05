"""
Wallet App Signals
Auto-creates custodial wallets for users who sign up without connecting a wallet.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_custodial_wallet_for_new_user(sender, instance, created, **kwargs):
    """
    Signal handler to automatically create a custodial wallet for new users.

    When a user signs up via:
    - Traditional signup (username/password)
    - Google OAuth
    - Any method other than wallet connection

    This creates an in-app custodial wallet for them automatically.

    Args:
        sender: The CustomUser model
        instance: The user instance that was saved
        created: Boolean indicating if this is a new user
        **kwargs: Additional arguments
    """
    if not created:
        # Only run for new users
        return

    # Avoid circular imports
    from wallet.models import WalletProfile
    from wallet.services.custodial_service import CustodialWalletService

    try:
        # Check if user already has a wallet
        # (they might have connected a wallet during signup)
        existing_wallets = WalletProfile.objects.filter(user=instance).exists()

        if existing_wallets:
            logger.info(f"User {instance.username} already has a wallet, skipping custodial creation")
            return

        # Create custodial wallet
        logger.info(f"Creating custodial wallet for new user: {instance.username}")

        wallet_profile, custodial_wallet = CustodialWalletService.create_custodial_wallet(instance)

        logger.info(
            f"✅ Auto-created custodial wallet for {instance.username}: "
            f"{wallet_profile.public_key}"
        )

    except Exception as e:
        # Log error but don't fail user creation
        logger.error(
            f"❌ Failed to create custodial wallet for {instance.username}: {e}",
            exc_info=True
        )
        # Don't raise - user account should still be created even if wallet creation fails
