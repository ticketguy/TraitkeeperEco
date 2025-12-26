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

    async def process_onchain_events(self, collection_address: str, max_signatures: int = None):
            """
            Fetches and processes ALL historical on-chain events for a collection.

            Uses pagination to fetch the complete transaction history from collection creation.

            Args:
                collection_address: The collection's on-chain address
                max_signatures: Optional limit for testing (default: None = fetch all)
            """
            logger.info(f"Starting COMPLETE historical indexing for collection: {collection_address}")
            logger.info(f"⚠️  This will fetch ALL transactions from collection creation")

            # 1. Get a healthy, available provider
            provider = await self.provider_manager.get_rpc_provider(collection_address)
            if not provider:
                logger.error(f"Could not get an available provider for {collection_address}. Aborting.")
                return

            try:
                all_signatures = []
                before_signature = None
                page_num = 0

                # 2. Paginate through ALL signatures
                logger.info(f"📚 Starting pagination to fetch complete history...")

                while True:
                    page_num += 1
                    logger.info(f"📄 Fetching page {page_num}...")

                    # Fetch batch of signatures (1000 at a time)
                    signatures_data = await provider.get_signatures_for_address(
                        collection_address,
                        limit=1000,
                        before=before_signature
                    )

                    if not signatures_data:
                        logger.info(f"✅ Reached end of history at page {page_num}")
                        break

                    batch_size = len(signatures_data)
                    all_signatures.extend([s['signature'] for s in signatures_data])
                    logger.info(f"   Found {batch_size} signatures (Total: {len(all_signatures)})")

                    # Check if we've hit optional limit
                    if max_signatures and len(all_signatures) >= max_signatures:
                        logger.info(f"⚠️  Reached max_signatures limit: {max_signatures}")
                        all_signatures = all_signatures[:max_signatures]
                        break

                    # If we got less than 1000, we've reached the end
                    if batch_size < 1000:
                        logger.info(f"✅ Complete history fetched (last page had {batch_size} signatures)")
                        break

                    # Set 'before' to the oldest signature from this batch for next page
                    before_signature = signatures_data[-1]['signature']

                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.5)

                if not all_signatures:
                    logger.warning(f"No transaction history found for collection address {collection_address}.")
                    return

                logger.info(f"📊 TOTAL SIGNATURES FOUND: {len(all_signatures)}")
                logger.info(f"🔄 Processing transactions in batches...")

                # 3. Process signatures in batches to avoid overwhelming the parser
                BATCH_SIZE = 100
                total_batches = (len(all_signatures) + BATCH_SIZE - 1) // BATCH_SIZE

                for i in range(0, len(all_signatures), BATCH_SIZE):
                    batch = all_signatures[i:i + BATCH_SIZE]
                    batch_num = (i // BATCH_SIZE) + 1

                    logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} transactions)...")

                    # Fetch full transaction data for this batch
                    transactions = await provider.get_transactions(batch)

                    # Parse each transaction
                    for tx in transactions:
                        if tx:
                            await self.parser.parse_and_store_event(tx)

                    # Delay between batches
                    await asyncio.sleep(1)

                logger.info(f"✅ COMPLETE historical indexing finished for {collection_address}")
                logger.info(f"   Total transactions processed: {len(all_signatures)}")

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
            logger.info(f"📡 Fetching market stats from APIs for {collection.name} ({collection.address[:16]}...)")

            # Define all providers that supply market-level stats
            providers_to_query = ['magic_eden', 'tensor']
            logger.info(f"   → Querying {len(providers_to_query)} providers: {providers_to_query}")
            
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

                        logger.info(f"   💾 Storing {provider_name} data: Floor={stats_data.get('floor_price', 0)}, "
                                   f"Vol 24h={stats_data.get('volume_24h', 0)}, Listed={stats_data.get('listed_count', 0)}")

                        # Wrap the DB upsert in a sync function so sync_to_async receives a proper callable
                        @sync_to_async
                        def _upsert_collection_market_stats():
                            from django.utils import timezone
                            return CollectionMarketStats.objects.update_or_create(
                                collection=collection,
                                source=provider_name,
                                defaults={
                                    'floor_price': stats_data.get('floor_price'),
                                    'volume_24h': stats_data.get('volume_24h'),
                                    'listed_count': stats_data.get('listed_count'),
                                    'total_supply': stats_data.get('total_supply'),
                                    'sales_count_24h': stats_data.get('sales_count_24h'),
                                    'owners_count': stats_data.get('owners_count'),
                                    'raw_data': raw_data,
                                    'timestamp': timezone.now()  # FIX: Update timestamp on every save
                                }
                            )

                        saved_tuple = await _upsert_collection_market_stats()
                        saved_obj, created = saved_tuple
                        action = "Created" if created else "Updated"
                        logger.info(f"   ✅ {action} CollectionMarketStats record for '{provider_name}'")
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

    async def calculate_and_store_blockchain_volume(self, collection: NFTCollection):
        """
        Calculate volume metrics from indexed NFTEvent data and store as source='blockchain'.

        This provides cross-marketplace volume data calculated from your own indexed transactions.
        Even at 90-95% accuracy, this gives a more complete picture than single-marketplace APIs.

        Calculates:
        - volume_24h: Total SOL volume in last 24 hours
        - volume_7d: Total SOL volume in last 7 days
        - sales_count_24h: Number of sales in last 24 hours
        - sales_count_7d: Number of sales in last 7 days

        Args:
            collection: NFTCollection to calculate for
        """
        from django.db.models import Sum, Count
        from datetime import timedelta
        from django.utils import timezone

        try:
            logger.info(f"💎 Calculating blockchain volume from NFTEvent for {collection.name}")

            now = timezone.now()
            cutoff_24h = now - timedelta(hours=24)
            cutoff_7d = now - timedelta(days=7)

            # Calculate 24h metrics
            result_24h = await sync_to_async(
                NFTEvent.objects.filter(
                    collection_address=collection.address,
                    event_type='SALE',
                    timestamp__gte=cutoff_24h
                ).aggregate
            )(
                total_volume=Sum('amount'),
                sales_count=Count('event_id')
            )

            volume_24h = float(result_24h['total_volume'] or 0)
            sales_count_24h = result_24h['sales_count'] or 0

            # Calculate 7d metrics
            result_7d = await sync_to_async(
                NFTEvent.objects.filter(
                    collection_address=collection.address,
                    event_type='SALE',
                    timestamp__gte=cutoff_7d
                ).aggregate
            )(
                total_volume=Sum('amount'),
                sales_count=Count('event_id')
            )

            volume_7d = float(result_7d['total_volume'] or 0)
            sales_count_7d = result_7d['sales_count'] or 0

            # Get total supply from NFT count
            total_supply = await sync_to_async(collection.nfts.count)()

            # Get active listings count (NFTListing model)
            from indexer.models import NFTListing
            listed_count = await sync_to_async(
                NFTListing.objects.filter(
                    collection_address=collection.address,
                    status='active'
                ).count
            )()

            logger.info(f"   📊 Blockchain stats: Vol 24h={volume_24h:.2f} SOL, "
                       f"Sales={sales_count_24h}, Vol 7d={volume_7d:.2f} SOL")

            # Store as source='blockchain'
            @sync_to_async
            def _upsert_blockchain_stats():
                return CollectionMarketStats.objects.update_or_create(
                    collection=collection,
                    source='blockchain',
                    defaults={
                        'volume_24h': volume_24h,
                        'sales_count_24h': sales_count_24h,
                        'listed_count': listed_count,
                        'total_supply': total_supply,
                        'raw_data': {
                            'volume_7d': volume_7d,
                            'sales_count_7d': sales_count_7d,
                            'source': 'calculated_from_nftevent',
                            'accuracy_note': '90-95% accurate - some transactions may be missed'
                        },
                        'timestamp': now
                    }
                )

            saved_tuple = await _upsert_blockchain_stats()
            saved_obj, created = saved_tuple
            action = "Created" if created else "Updated"
            logger.info(f"   ✅ {action} blockchain volume stats")

            return {
                'success': True,
                'volume_24h': volume_24h,
                'sales_count_24h': sales_count_24h,
                'volume_7d': volume_7d
            }

        except Exception as e:
            logger.error(f"Failed to calculate blockchain volume for {collection.address}: {str(e)}")
            return {'success': False, 'error': str(e)}