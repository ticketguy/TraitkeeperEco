# nft_data/services/nft_retrieval.py

import logging
from django.utils import timezone
from asgiref.sync import sync_to_async
from nft_data.models import NFTCollection
from nft_data.signals import send_unified_admin_notification

# Import the new, specialized services
from .cache_service import CacheService
from .provider_manager import ProviderManager
from .metadata_fetcher import MetadataFetcher
from .collection_validator import CollectionValidator
from .batch_processor import BatchProcessor
from .nft_storage import NFTStorage

logger = logging.getLogger(__name__)


class NFTRetrievalService:
    """Orchestrates the fetching, processing, and storing of NFT collections."""

    def __init__(self):
        """Initializes and wires together all necessary services."""
        self.metrics = self._reset_metrics()
        
        # Initialize all the specialized services
        self.cache_service = CacheService()
        self.provider_manager = ProviderManager()
        self.metadata_fetcher = MetadataFetcher(self.cache_service, self.metrics, self.provider_manager)
        self.validator = CollectionValidator(self.provider_manager, self.cache_service, self.metadata_fetcher)
        self.batch_processor = BatchProcessor(self.metadata_fetcher)
        self.storage = NFTStorage(self.batch_processor)
        
        logger.info("NFTRetrievalService initialized with all sub-services.")

    def _reset_metrics(self) -> dict:
        """Returns a clean dictionary for tracking metrics for a run."""
        return {
            "retrieval_method": "", "nfts_retrieved": 0, "total_supply": 0,
            "fallback_used": False, "fallback_method": "", "error_encountered": "",
            "traits_fetched": 0, "trait_types": set(), "provider_used": ""
        }

    async def fetch_collections_by_collection(self, collection_address: str, last_fetched=None):
        """
        The main entry point to fetch, enrich, and store a full NFT collection.
        """
        self.metrics = self._reset_metrics()
        logger.info(f"🚀 ========== STARTING COLLECTION FETCH ==========")
        logger.info(f"📍 Collection Address: {collection_address}")
        logger.info(f"⏰ Last Fetched: {last_fetched}")
        logger.info(f"=" * 60)

        try:
            # 1. Validate the collection address
            logger.info(f"🔍 STEP 1: Validating collection address...")
            validation_result = await self.validator.validate_collection(collection_address)
            logger.info(f"✅ Validation result: {validation_result}")
            
            if not validation_result:
                logger.error(f"❌ Validation failed for collection {collection_address}. Aborting.")
                return []

            # 2. Fetch the collection's own metadata (on-chain with fallbacks)
            logger.info(f"📦 STEP 2: Fetching collection metadata...")
            logger.info(f"   Trying primary method: fetch_metadata_account")
            collection_metadata = await self.metadata_fetcher.fetch_metadata_account(collection_address)
            
            if not collection_metadata:
                logger.warning(f"⚠️ Primary metadata fetch failed. Trying fallback: DAS API")
                collection_metadata = await self.metadata_fetcher.fetch_metadata_from_das_collection(collection_address)
                if collection_metadata:
                    logger.info(f"✅ Fallback DAS API succeeded")
                else:
                    logger.warning(f"⚠️ Fallback DAS API also failed")

            if not collection_metadata:
                logger.error(f"❌ Failed to fetch any metadata for collection {collection_address}. Aborting.")
                return []
            
            logger.info(f"✅ Collection metadata retrieved:")
            logger.info(f"   Name: {collection_metadata.get('name', 'N/A')}")
            logger.info(f"   Symbol: {collection_metadata.get('symbol', 'N/A')}")
            logger.info(f"   Image URL: {collection_metadata.get('image_url', 'N/A')[:50]}...")

            # 3. Fetch the raw list of all NFTs in the collection using fallback strategies
            logger.info(f"🎯 STEP 3: Fetching NFT list with fallback strategies...")
            raw_nfts = []
            fetch_strategies = [
                (self.provider_manager.fetch_using_helius_assets_by_group, "Helius getAssetsByGroup"),
                (self.provider_manager.fetch_using_program_accounts, "getProgramAccounts")
            ]
            
            for strategy_index, (fetch_method, method_name) in enumerate(fetch_strategies, 1):
                try:
                    logger.info(f"📡 Strategy {strategy_index}/{len(fetch_strategies)}: {method_name}")
                    logger.info(f"   Calling: {fetch_method.__name__}")
                    
                    raw_nfts = await fetch_method(collection_address, last_fetched=last_fetched)
                    
                    logger.info(f"   Result: {len(raw_nfts) if raw_nfts else 0} NFTs returned")
                    
                    if raw_nfts:
                        self.metrics["retrieval_method"] = method_name
                        self.metrics["nfts_retrieved"] = len(raw_nfts)
                        logger.info(f"✅ Successfully fetched {len(raw_nfts)} raw NFTs using {method_name}")
                        
                        # Log sample of first NFT
                        if len(raw_nfts) > 0:
                            sample_nft = raw_nfts[0]
                            logger.info(f"   Sample NFT data structure:")
                            logger.info(f"   - Keys: {list(sample_nft.keys())}")
                            logger.info(f"   - Mint: {sample_nft.get('mint', sample_nft.get('id', 'N/A'))[:16]}...")
                        
                        break
                    else:
                        logger.warning(f"⚠️ Strategy {method_name} returned no NFTs. Trying next fallback.")
                        self.metrics["fallback_used"] = True
                        self.metrics["fallback_method"] = method_name
                        
                except Exception as e:
                    logger.error(f"❌ Strategy {method_name} failed with exception: {e}", exc_info=True)
                    self.metrics["fallback_used"] = True
                    self.metrics["fallback_method"] = method_name

            if not raw_nfts:
                logger.error(f"❌ All strategies failed to fetch any NFTs for {collection_address}. Aborting.")
                logger.error(f"   Strategies attempted: {[name for _, name in fetch_strategies]}")
                return []

            # 4. Prepare the final data payload for the storage service
            logger.info(f"📋 STEP 4: Preparing data payload for storage...")
            final_collection_data = {
                **collection_metadata,
                "address": collection_address,
                "nfts": raw_nfts,
                "source": "webhook"
            }
            logger.info(f"   Payload contains {len(raw_nfts)} NFTs")
            logger.info(f"   Collection name: {final_collection_data.get('name')}")

            # 5. Pass the data to the storage service to enrich and save
            logger.info(f"💾 STEP 5: Passing data to storage service...")
            logger.info(f"   Calling: store_collection_and_nfts_optimized")
            
            await self.storage.store_collection_and_nfts_optimized(collection_address, final_collection_data)
            
            logger.info(f"✅ Storage service completed successfully")

            # (Optional) Update last_fetched timestamp in the database
            logger.info(f"🕐 STEP 6: Updating last_fetched timestamp...")
            await self.update_last_fetched(collection_address)

            logger.info(f"🎉 ========== COLLECTION FETCH COMPLETED SUCCESSFULLY ==========")
            return [final_collection_data]

        except Exception as e:
            logger.critical(f"💥 CRITICAL FAILURE in fetch_collections_by_collection for {collection_address}", exc_info=True)
            logger.critical(f"   Error: {str(e)}")
            self.metrics["error_encountered"] = str(e)
            await self.monitor_fetch_errors(collection_address, e)
            return []
        finally:
            await self.log_metrics()
            logger.info(f"🔒 Closing persistent session...")
            await self.batch_processor.close_persistent_session()
            logger.info(f"=" * 60)
            logger.info(f"🏁 Finished collection fetch for: {collection_address}")
            logger.info(f"=" * 60)
    
    async def update_last_fetched(self, collection_address: str):
        """Updates the last_fetched timestamp for a collection."""
        try:
            @sync_to_async
            def _update_db():
                NFTCollection.objects.filter(address=collection_address).update(last_fetched=timezone.now())
            await _update_db()
            logger.info(f"✅ Updated last_fetched timestamp for {collection_address}")
        except Exception as e:
            logger.error(f"❌ Could not update last_fetched for {collection_address}: {e}")

    async def monitor_fetch_errors(self, collection_address: str, error: Exception):
        """Sends a notification if a critical error occurs."""
        try:
            await sync_to_async(send_unified_admin_notification)(
                subject=f"Collection Fetch Error: {collection_address[:8]}...",
                message=f"Failed to fetch collection {collection_address}\n\nError: {str(error)}",
                notification_type='collection_fetch_error',
                severity='error'
            )
            logger.info(f"📧 Error notification sent for {collection_address}")
        except Exception as e:
            logger.error(f"❌ Failed to send error notification: {e}")

    async def log_metrics(self):
        """Logs the metrics for the completed run."""
        logger.info("📊 ========== RETRIEVAL RUN METRICS ==========")
        for key, value in self.metrics.items():
            if key == "trait_types" and isinstance(value, set):
                logger.info(f"   {key.replace('_', ' ').title():<25}: {len(value)} types")
            else:
                logger.info(f"   {key.replace('_', ' ').title():<25}: {value}")
        logger.info("=" * 60)