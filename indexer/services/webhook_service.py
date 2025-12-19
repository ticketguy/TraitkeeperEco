# indexer/services/webhook_service.py
import logging
import asyncio
from typing import Dict, List, Optional
from asgiref.sync import sync_to_async

from .parser import TransactionParserService
from core.api_provider.api_providers import APIProviderManager
from ..models import NFTEvent
from nft_data.models import NFTCollection

logger = logging.getLogger(__name__)


class WebhookService:
    """
    Service for processing webhook events from Helius and QuickNode.

    Webhooks are HTTP POST requests sent by the RPC provider when blockchain
    events occur. This is more reliable than WebSocket connections as the
    provider handles monitoring and reconnection.

    Flow:
    1. Receive webhook payload (JSON array of events)
    2. Validate and parse each event
    3. Store in NFTEvent table via existing parser
    4. Trigger downstream processing (vitality, analytics)
    """

    def __init__(self):
        self.provider_manager = APIProviderManager()
        self.parser = TransactionParserService(self.provider_manager)
        logger.info("WebhookService initialized")

    async def process_webhook_payload(self, payload: Dict) -> Dict[str, int]:
        """
        Process incoming webhook payload from Helius or QuickNode.

        This method NEVER raises exceptions to prevent stream termination.

        Args:
            payload: Raw webhook payload (format varies by provider)

        Returns:
            Dict with processing statistics:
            {
                'total_events': int,
                'processed': int,
                'failed': int,
                'skipped': int
            }
        """
        stats = {
            'total_events': 0,
            'processed': 0,
            'failed': 0,
            'skipped': 0
        }

        try:
            # Detect provider and normalize format
            events = self._normalize_webhook_format(payload)
            stats['total_events'] = len(events)

            if not events:
                logger.warning("Webhook payload contained no events")
                return stats

            logger.info(f"Processing webhook batch: {stats['total_events']} events")

            # Process events concurrently (but limit concurrency)
            semaphore = asyncio.Semaphore(10)  # Max 10 concurrent

            async def process_single_event(event_data):
                async with semaphore:
                    return await self._process_single_event(event_data)

            results = await asyncio.gather(
                *[process_single_event(event) for event in events],
                return_exceptions=True
            )

            # Tally results
            for result in results:
                if isinstance(result, Exception):
                    stats['failed'] += 1
                    logger.error(f"Event processing exception: {result}")
                elif result == 'processed':
                    stats['processed'] += 1
                elif result == 'skipped':
                    stats['skipped'] += 1
                elif result == 'failed':
                    stats['failed'] += 1

            logger.info(f"Webhook batch complete: {stats}")
            return stats

        except Exception as e:
            # NEVER raise - always return stats to prevent stream termination
            logger.error(f"Critical error processing webhook payload: {e}", exc_info=True)
            stats['failed'] = stats.get('total_events', 1)  # Mark all as failed
            return stats

    async def _process_single_event(self, event_data: Dict) -> str:
        """
        Process a single event from webhook.

        Returns:
            'processed' | 'skipped' | 'failed'
        """
        signature = event_data.get('signature', 'unknown')

        try:
            # Check if we already processed this event
            if await self._event_already_exists(signature):
                logger.debug(f"[{signature}] Event already processed, skipping")
                return 'skipped'

            # Use existing parser to handle the event
            nft_event = await self.parser.parse_and_store_event(event_data)

            if nft_event:
                logger.info(f"[{signature}] Successfully processed webhook event")

                # Trigger downstream processing (wrapped in try-except to not fail main flow)
                try:
                    await self._trigger_downstream_processing(nft_event)
                except Exception as downstream_error:
                    # Log but don't fail the webhook
                    logger.warning(f"[{signature}] Downstream processing failed: {downstream_error}")

                return 'processed'
            else:
                logger.warning(f"[{signature}] Parser returned None (likely non-tracked collection)")
                return 'skipped'

        except Exception as e:
            # Always log full exception but still return a valid status
            logger.error(f"[{signature}] Failed to process webhook event: {e}", exc_info=True)
            return 'failed'

    async def _event_already_exists(self, signature: str) -> bool:
        """Check if event already exists in database."""
        return await sync_to_async(
            NFTEvent.objects.filter(event_id=signature).exists
        )()

    def _normalize_webhook_format(self, payload: Dict) -> List[Dict]:
        """
        Normalize webhook payload to standard format.

        Helius and QuickNode send different formats:

        Helius Enhanced Webhooks:
        {
            "type": "TRANSFER",
            "signature": "...",
            "nativeTransfers": [...],
            "tokenTransfers": [...],
            ...
        }

        QuickNode Streams:
        {
            "id": "...",
            "data": {
                "signature": "...",
                "transaction": {...}
            }
        }

        This method converts both to a standard list of events.
        """
        # Handle array of events (Helius format)
        if isinstance(payload, list):
            return payload

        # Handle single event object
        if 'signature' in payload:
            return [payload]

        # Handle QuickNode stream format
        if 'data' in payload and isinstance(payload['data'], dict):
            return [payload['data']]

        # Handle nested events
        if 'events' in payload:
            return payload['events']

        logger.warning(f"Unknown webhook format: {list(payload.keys())}")
        return []

    async def _trigger_downstream_processing(self, nft_event: NFTEvent):
        """
        Trigger downstream processing after event is stored.

        This includes:
        - Vitality score recalculation (if significant event)
        - Sweep detection
        - Market stats update
        - Real-time notifications
        """
        try:
            event_type = nft_event.event_type

            # Only trigger vitality updates for significant events
            if event_type in ['SALE', 'LISTING', 'DELISTING']:
                # Import here to avoid circular dependency
                from marketplace.vitality_service import VitalityCalculationService

                # Schedule vitality recalculation (don't await, run in background)
                collection = await sync_to_async(lambda: nft_event.collection)()

                if collection:
                    asyncio.create_task(
                        self._recalculate_vitality(collection.address)
                    )
                    logger.debug(f"Scheduled vitality recalculation for {collection.address}")

        except Exception as e:
            # Don't fail the whole webhook processing if downstream fails
            logger.error(f"Error in downstream processing: {e}", exc_info=True)

    async def _recalculate_vitality(self, collection_address: str):
        """Background task to recalculate vitality for a collection."""
        try:
            from marketplace.vitality_service import VitalityCalculationService

            vitality_service = VitalityCalculationService()
            await vitality_service.calculate_collection_vitality(collection_address)

            logger.info(f"Vitality recalculated for {collection_address}")
        except Exception as e:
            logger.error(f"Failed to recalculate vitality for {collection_address}: {e}", exc_info=True)
