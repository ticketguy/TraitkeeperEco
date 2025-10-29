# indexer/services/main.py
import asyncio
import logging
from asgiref.sync import sync_to_async
from nft_data.models import NFTCollection
from analytics.services.main import MetricsCalculationService

# New: Import the specialists from their own files
from .parser import TransactionParserService
from .metadata import MetadataSyncService

from core.api_provider.api_providers import APIProviderManager
from ..models import FailedTransaction, CollectionMarketStats
from core.cache_manager import cache_manager
from ..nft_constants import MARKETPLACE_PROGRAMS

logger = logging.getLogger(__name__)


class IndexerService:
    """
    High-level orchestrator for the indexing process. It coordinates API providers,
    delegates parsing and syncing to specialized services, and manages workflows
    like real-time subscriptions and retrying failed transactions.
    """
    def __init__(self):
        self.provider_manager = APIProviderManager()
        self.parser = TransactionParserService(self.provider_manager)
        self.metadata_sync = MetadataSyncService(self.provider_manager)
        self.metrics_service = MetricsCalculationService()
        logger.info("IndexerService orchestrator initialized.")

    async def update_collection_after_retrieval(self, collection_address: str):
        """A full refresh workflow for a collection after its NFTs are added/updated."""
        try:
            await self.process_onchain_events(collection_address)

            # Resolve NFTCollection instance (metrics methods expect a model instance)
            collection_obj = await sync_to_async(
                lambda: NFTCollection.objects.filter(address=collection_address).first()
            )()

            if collection_obj:
                # MetricsCalculationService methods are now natively async - call directly
                await self.metrics_service.update_collection_metrics(collection_obj)
                
                # Trait metrics now takes collection_address (string) instead of collection object
                trait_result = await self.metrics_service.update_trait_metrics(collection_obj.address)
                
                # Handle smart skipping (returns None if no activity)
                if trait_result:
                    logger.info(f"✓ Trait metrics updated for {collection_obj.name}")
                else:
                    logger.info(f"⚡ Trait metrics skipped for {collection_obj.name} - no activity")
            else:
                logger.warning(f"Collection object not found for address {collection_address}; skipping metrics update.")

            await cache_manager.invalidate_collection_caches(collection_address)
            logger.info(f"Completed post-retrieval update for collection {collection_address}")
        except Exception as e:
            logger.error(f"Error in update_collection_after_retrieval: {e}", exc_info=True)

    async def process_onchain_events(self, collection_address: str):
            """
            Fetches and processes historical on-chain events for a given collection address.
            This corrected version fetches the signature history of the collection itself.
            """
            logger.info(f"Starting DIRECT indexing for collection: {collection_address}")
            
            # 1. Get a healthy, available provider using your existing manager.
            provider = await self.provider_manager.get_rpc_provider(collection_address)
            if not provider:
                logger.error(f"Could not get an available provider for {collection_address}. Aborting.")
                return

            try:
                # 2. Get the transaction signatures that involved the collection address directly.
                # This is the key change in logic. We're asking for the collection's history.
                logger.info(f"Fetching transaction signatures for collection address: {collection_address}")
                # You can increase the limit as needed.
                signatures_data = await provider.get_signatures_for_address(collection_address, limit=1000)
                
                if not signatures_data:
                    logger.warning(f"No transaction history found for collection address {collection_address}.")
                    return

                signatures_to_fetch = [s['signature'] for s in signatures_data]
                logger.info(f"Found {len(signatures_to_fetch)} signatures. Fetching full transaction details...")
                
                # 3. Get the full transaction data for those signatures.
                transactions = await provider.get_transactions(signatures_to_fetch)

                # 4. Process each valid transaction using your parser.
                for tx in transactions:
                    if tx:
                        await self.parser.parse_and_store_event(tx)

            except Exception as e:
                logger.error(f"Failed to process event history for collection {collection_address}: {e}", exc_info=True)

    async def subscribe_to_collection_activity(self, collection_address: str, user_callback: callable):
        """Subscribes to live on-chain events and processes them."""
        
        # ✅ NEW: Add validation and logging
        logger.info("=" * 80)
        logger.info("INITIALIZING REAL-TIME WEBSOCKET SUBSCRIPTIONS")
        logger.info("=" * 80)
        
        # Get program IDs to subscribe to
        program_ids = list(MARKETPLACE_PROGRAMS.values())
        
        if not program_ids:
            logger.error("❌ CRITICAL: MARKETPLACE_PROGRAMS is empty! No programs to subscribe to.")
            logger.error("Check indexer/nft_constants.py - MARKETPLACE_PROGRAMS dict")
            return
        
        logger.info(f"📋 Will subscribe to {len(program_ids)} marketplace programs:")
        for i, prog_id in enumerate(program_ids, 1):
            logger.info(f"   {i}. {prog_id}")
        
        async def internal_callback(raw_event_data):
            """Internal callback that parses events and calls user callback."""
            try:
                signature = raw_event_data.get('signature', 'unknown')
                logger.info(f"🔔 LIVE EVENT RECEIVED: {signature}")
                
                # Parse the event
                nft_event = await self.parser.parse_and_store_event(raw_event_data)
                
                if not nft_event:
                    return

                # Resolve collection address robustly (support both dict and model instance)
                collection_address = None
                if isinstance(nft_event, dict):
                    # common keys used by different parsers/providers
                    collection_address = nft_event.get('collection') or nft_event.get('collection_address') or nft_event.get('collection_id')
                else:
                    # model-like object: try attribute access safely
                    coll_attr = getattr(nft_event, 'collection', None)
                    if isinstance(coll_attr, str):
                        collection_address = coll_attr
                    elif coll_attr is not None:
                        # coll_attr may be a NFTCollection instance or a related model
                        collection_address = getattr(coll_attr, 'address', None)

                if collection_address:
                    # fetch NFTCollection instance before passing to metrics updater
                    try:
                        collection_obj = await sync_to_async(NFTCollection.objects.get)(address=collection_address)
                    except NFTCollection.DoesNotExist:
                        collection_obj = None

                    if collection_obj:
                        # Use existing metrics_service instance - methods are now natively async
                        await self.metrics_service.update_collection_metrics(collection_obj)
                # ... proceed with any user callback invocation ...
            except Exception as e:
                # don't call e.get(...) — log the exception properly
                logger.exception(f"Error handling live event {raw_event_data.get('signature', 'unknown')}: {e}")
        
        logger.info("🚀 Starting WebSocket subscription manager...")
        logger.info(f"DEBUG: About to call subscribe_to_programs with {len(program_ids)} programs")

        # This will run forever in the background, reconnecting as needed
        await self.provider_manager.subscribe_to_programs(program_ids, internal_callback)

    async def retry_failed_transactions(self, limit: int = 50):
        """Finds and retries a batch of failed transactions."""
        failed_txs = await sync_to_async(list)(
            FailedTransaction.objects.order_by('created_at')[:limit]
        )
        logger.info(f"Found {len(failed_txs)} failed transactions to retry.")

        for tx in failed_txs:
            nft_event = await self.parser.parse_and_store_event(tx.event_data)
            if nft_event:
                logger.info(f"Successfully retried and processed failed transaction {tx.event_id}")
                await sync_to_async(tx.delete)()
            else:
                tx.retry_count += 1
                await sync_to_async(tx.save)(update_fields=['retry_count'])

# ===================================================================
# 4. Market Stats Fetcher and Storer
# ===================================================================
    async def fetch_and_store_all_market_stats(self, collection: NFTCollection):
            """
            NEW & CORRECTED: Fetches raw market stats in parallel from all active API providers
            and stores them in the CollectionMarketStats model.
            """
            logger.info(f"Fetching all market stats for {collection.name} ({collection.address})")

            # Define all providers that supply market-level stats
            providers_to_query = ['magic_eden', 'tensor']
            
            # --- Helper function to encapsulate the logic for one provider ---
            async def _fetch_provider_stats(provider_name: str):
                provider = await self.provider_manager.get_provider_by_name(provider_name)
                
                if not provider or not await provider.check_availability():
                    logger.warning(f"Provider '{provider_name}' is not available for market stats.")
                    return None

                # STEP 1: Find the marketplace-specific identifier (slug or UUID) for the collection.
                # Both MagicEdenProvider and TensorProvider have this 'find_collection_symbol' method.
                marketplace_id = await provider.find_collection_symbol(collection.address, collection.name)

                if not marketplace_id:
                    logger.warning(f"Could not find a marketplace ID for {collection.address} on {provider_name}.")
                    return None
                
                # STEP 2: Use the correct identifier to call the correct 'get_collection_data' method.
                # We also pass the priority tier to allow the provider to set a smart cache TTL.
                stats_result = await provider.get_collection_data(marketplace_id, collection.address, collection.priority_tier)
                
                # Add the provider's name to the result for processing later.
                if stats_result:
                    stats_result['source'] = provider_name
                
                return stats_result

            # --- Main execution ---
            # Create a task for each provider to run them concurrently.
            tasks = [_fetch_provider_stats(name) for name in providers_to_query]
            
            # Execute all API calls in parallel and wait for them all to complete.
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process the results from each provider.
            for result in results:
                if result is None:
                    continue # Skip if provider was unavailable or had no ID
                    
                if isinstance(result, Exception):
                    logger.error(f"An exception occurred while fetching market stats: {result}", exc_info=True)
                    continue

                if result and result.get('success'):
                    provider_name = result.get('source')
                    stats_data = result.get('stats', {})
                    raw_data = result.get('raw_data', {}) # Store the complete raw response
                    
                    try:
                        # Ensure provider result is a dict before using .get
                        if not isinstance(result, dict):
                            raise RuntimeError(f"Invalid provider result: {result}")

                        # Wrap the DB upsert in a sync function so sync_to_async receives a proper callable
                        @sync_to_async
                        def _upsert_collection_market_stats():
                            return CollectionMarketStats.objects.update_or_create(
                                collection=collection,
                                source=provider_name,
                                defaults={
                                    'floor_price': stats_data.get('floor_price'),
                                    'volume_24h': stats_data.get('volume_24h'),
                                    'total_volume': stats_data.get('total_volume'),
                                    'listed_count': stats_data.get('listed_count'),
                                    'total_supply': stats_data.get('total_supply'),
                                    'average_price_24h': stats_data.get('avg_price_24h'),
                                    'highest_bid': stats_data.get('highest_bid'),
                                    'market_cap': stats_data.get('market_cap'),
                                    'sales_count_24h': stats_data.get('sales_count_24h'),
                                    'raw_data': raw_data
                                }
                            )

                        saved_tuple = await _upsert_collection_market_stats()
                        saved_obj, created = saved_tuple
                        logger.info(f"Successfully stored market stats from '{provider_name}' for {collection.name}.")
                    except Exception as e:
                        # Use str(e) instead of e.get(...)
                        logger.error(f"Failed to save market stats from '{provider_name}' to database: {e}")
                else:
                    # result might be a dict or some other error object — handle both safely
                    if isinstance(result, dict):
                        error_message = result.get('error', 'Unknown error')
                        provider_name = result.get('source', provider_name or 'unknown provider')
                    else:
                        error_message = str(result)
                        provider_name = provider_name or 'unknown provider'
                    logger.warning(f"Failed to fetch market stats from '{provider_name}': {error_message}")