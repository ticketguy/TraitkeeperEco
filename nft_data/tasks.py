# nft_data/tasks.py
"""
Background tasks for NFT data operations.
"""
import logging
from asgiref.sync import sync_to_async
from typing import Optional

from .models import PendingCollection
from .retrieval_services.nft_retrieval import NFTRetrievalService
from core.api_provider.api_providers import APIProviderManager
from admin_panel.models import PrimaryProviderSetting

logger = logging.getLogger(__name__)


async def validate_collection_onchain(pending_collection_id: int) -> dict:
    """
    Background task to validate a collection on-chain with automatic failover.

    This runs after user submission to verify the collection address is valid
    without making the user wait. Tries all available RPC providers.

    Args:
        pending_collection_id: ID of the PendingCollection to validate

    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    try:
        # Fetch the pending collection
        pending = await sync_to_async(
            PendingCollection.objects.filter(id=pending_collection_id).first
        )()

        if not pending:
            logger.error(f"PendingCollection {pending_collection_id} not found")
            return {'success': False, 'error': 'Collection not found'}

        mint_address = pending.mint_address
        logger.info(f"🔍 Starting background validation for {mint_address}")

        # Try validation with automatic failover across all providers
        is_valid = await _validate_with_failover(mint_address)

        if is_valid:
            # Update status to pending (ready for admin approval)
            pending.status = 'pending'
            pending.validation_error = None
            await sync_to_async(pending.save)(update_fields=['status', 'validation_error', 'updated_at'])
            logger.info(f"✅ Collection {mint_address} validated successfully - moved to pending approval")

            return {'success': True, 'error': None}
        else:
            # Validation failed with all providers
            pending.status = 'rejected'
            pending.validation_error = (
                "Validation Failed: We couldn't find a valid NFT collection on-chain at this address. "
                "Please double-check the address. It should be the collection/group address, "
                "not an individual NFT's mint address."
            )
            await sync_to_async(pending.save)(update_fields=['status', 'validation_error', 'updated_at'])
            logger.warning(f"❌ Collection {mint_address} validation failed with all providers")

            return {'success': False, 'error': 'Validation failed'}

    except Exception as e:
        logger.error(f"❌ Error in background validation task for {pending_collection_id}: {e}", exc_info=True)

        # Update to rejected with error message
        try:
            pending.status = 'rejected'
            pending.validation_error = f"System error during validation: {str(e)}"
            await sync_to_async(pending.save)(update_fields=['status', 'validation_error', 'updated_at'])
        except Exception as save_error:
            logger.error(f"Failed to update pending collection status: {save_error}")

        return {'success': False, 'error': str(e)}


async def _validate_with_failover(mint_address: str) -> bool:
    """
    Try to validate collection with automatic failover across all RPC providers.

    Args:
        mint_address: The collection mint address to validate

    Returns:
        bool: True if validation succeeded with any provider, False otherwise
    """
    # Get all active providers
    providers = await sync_to_async(list)(
        PrimaryProviderSetting.objects.filter(is_active=True).order_by('-is_primary')
    )

    if not providers:
        logger.error("No active RPC providers configured")
        return False

    logger.info(f"Will attempt validation with {len(providers)} providers")

    # Try each provider in order (primary first)
    for provider_setting in providers:
        provider_name = provider_setting.name

        try:
            logger.info(f"🔄 Attempting validation with {provider_name}...")

            # Initialize the NFT retrieval service
            retrieval_service = NFTRetrievalService()

            # Call the validator
            is_valid = await retrieval_service.validator.validate_collection(mint_address)

            if is_valid:
                logger.info(f"✅ Validation succeeded with {provider_name}")
                return True
            else:
                logger.warning(f"⚠️ Validation returned False with {provider_name} - trying next provider")

        except Exception as e:
            logger.warning(f"⚠️ Validation failed with {provider_name}: {e} - trying next provider")
            continue

    # All providers failed
    logger.error(f"❌ Validation failed with all {len(providers)} providers")
    return False
