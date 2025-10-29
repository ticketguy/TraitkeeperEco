# nft_data/services/nft_storage.py

import logging
from django.db import transaction
from django.utils import timezone

try:
    from asgiref.sync import sync_to_async
except Exception:
    import asyncio
    from functools import wraps

    def sync_to_async(func, thread_sensitive=False):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
        return wrapper

from nft_data.models import NFTCollection, NFT, TraitType, TraitValue

logger = logging.getLogger(__name__)


class NFTStorage:
    """Handles the storage of enriched NFT and Collection data into the database."""

    def __init__(self, batch_processor):
        """Initializes the storage service with a dependency on the BatchProcessor."""
        self.batch_processor = batch_processor
        self.db_batch_size = 100
        logger.info(f"📦 NFTStorage initialized with batch size: {self.db_batch_size}")

    async def store_collection_and_nfts_optimized(self, collection_id: str, collection_data: dict):
        """
        Orchestrates the enrichment and storage of a collection and its NFTs.
        """
        logger.info(f"💾 ========== STARTING STORAGE PROCESS ==========")
        logger.info(f"   Collection ID: {collection_id}")
        logger.info(f"   Collection Data Keys: {list(collection_data.keys())}")
        
        try:
            # 1. Prepare data for the Collection record
            collection_name = collection_data.get("name", f"Unknown {collection_id[:8]}")
            logger.info(f"📝 STORAGE STEP 1: Preparing collection record...")
            logger.info(f"   Name: {collection_name}")
            logger.info(f"   Image URL: {collection_data.get('image_url', 'N/A')[:50]}...")
            logger.info(f"   Description: {collection_data.get('description', 'N/A')[:50]}...")

            # Define the synchronous function for DB operations
            @sync_to_async
            def _create_or_update_collection_db():
                logger.info(f"   🔄 Executing DB transaction for collection...")
                
                # --- Safely extract the single creator address ---
                creator_addresses_list = collection_data.get("creator_addresses", [])
                primary_creator_address = ""
                if creator_addresses_list and isinstance(creator_addresses_list[0], dict):
                    primary_creator_address = creator_addresses_list[0].get("address", "")
                    logger.info(f"   Creator Address: {primary_creator_address[:16]}...")
                else:
                    logger.warning(f"   ⚠️ No valid creator address found")

                # Define the defaults using correct model field names
                defaults = {
                    "name": collection_name,
                    "image_url": collection_data.get("image_url", ""),
                    "creator_address": primary_creator_address,
                    "is_featured": False,
                    "source": collection_data.get("source", "unknown"),
                    "description": collection_data.get("description", ""),
                    "symbol": collection_data.get("symbol", ""),
                    "last_fetched": timezone.now()
                }

                with transaction.atomic():
                    collection, created = NFTCollection.objects.get_or_create(
                        address=collection_id,
                        defaults=defaults
                    )
                    
                    action = "Created" if created else "Found existing"
                    logger.info(f"   ✅ {action} collection record (PK: {collection.pk})")
                    
                    if not created:
                        update_needed = False
                        for key, value in defaults.items():
                            if getattr(collection, key) != value:
                                setattr(collection, key, value)
                                update_needed = True
                        
                        if update_needed:
                            collection.save()
                            logger.info(f"   ✅ Updated existing collection record")
                        else:
                            logger.info(f"   ℹ️ No updates needed for collection record")
                    
                return collection

            # Execute the database operation
            collection = await _create_or_update_collection_db()
            logger.info(f"✅ Collection record ready: {collection_name} (PK: {collection.pk})")

            # 2. Get the raw list of NFTs to process
            raw_nfts = collection_data.get("nfts", [])
            logger.info(f"📋 STORAGE STEP 2: Processing raw NFT data...")
            logger.info(f"   Raw NFTs count: {len(raw_nfts)}")
            
            if not raw_nfts:
                logger.warning(f"⚠️ No raw NFTs provided for collection {collection_name}, storage complete.")
                return collection

            # Log sample of raw NFT structure
            if len(raw_nfts) > 0:
                sample = raw_nfts[0]
                logger.info(f"   Sample raw NFT structure:")
                logger.info(f"   - Type: {type(sample)}")
                logger.info(f"   - Keys: {list(sample.keys()) if isinstance(sample, dict) else 'N/A'}")

            # 3. Standardize the raw data format
            logger.info(f"🔧 STORAGE STEP 3: Standardizing NFT data format...")
            processed_nfts = []
            skipped_count = 0
            
            for idx, nft_data in enumerate(raw_nfts):
                processed = await self.batch_processor._process_nft_data(nft_data)
                if processed:
                    processed_nfts.append(processed)
                else:
                    skipped_count += 1
                    if skipped_count <= 3:  # Only log first few failures
                        logger.warning(f"   ⚠️ Skipped invalid NFT at index {idx}")
            
            logger.info(f"   ✅ Standardized: {len(processed_nfts)} NFTs")
            logger.info(f"   ⚠️ Skipped: {skipped_count} invalid NFTs")
            
            if len(processed_nfts) > 0:
                sample = processed_nfts[0]
                logger.info(f"   Sample processed NFT:")
                logger.info(f"   - Mint: {sample.get('mint', 'N/A')[:16]}...")
                logger.info(f"   - Name: {sample.get('name', 'N/A')}")
                logger.info(f"   - URI: {sample.get('uri', 'N/A')[:50]}...")
            
            # 4. Enrich the processed NFTs with off-chain metadata in parallel
            logger.info(f"🌐 STORAGE STEP 4: Enriching NFTs with off-chain metadata...")
            logger.info(f"   Initializing persistent HTTP session...")
            
            await self.batch_processor.initialize_persistent_session()
            
            logger.info(f"   Starting parallel metadata fetch for {len(processed_nfts)} NFTs...")
            enriched_nfts = await self.batch_processor.fetch_metadata_batch(
                processed_nfts, 
                max_concurrent=20
            )
            
            logger.info(f"   ✅ Enrichment complete: {len(enriched_nfts)} NFTs enriched")
            
            # Check how many have traits
            nfts_with_traits = sum(1 for nft in enriched_nfts if nft.get("traits"))
            logger.info(f"   📊 NFTs with traits: {nfts_with_traits}/{len(enriched_nfts)}")

            # 5. Save the fully enriched NFTs to the database in batches
            logger.info(f"💾 STORAGE STEP 5: Saving enriched NFTs to database...")
            logger.info(f"   Total NFTs to save: {len(enriched_nfts)}")
            logger.info(f"   Batch size: {self.db_batch_size}")
            logger.info(f"   Number of batches: {(len(enriched_nfts) + self.db_batch_size - 1) // self.db_batch_size}")
            
            total_saved = 0
            for batch_num, i in enumerate(range(0, len(enriched_nfts), self.db_batch_size), 1):
                batch = enriched_nfts[i:i + self.db_batch_size]
                logger.info(f"   📦 Processing batch {batch_num}: NFTs {i+1}-{min(i+self.db_batch_size, len(enriched_nfts))}")
                
                await self._process_nft_batch_in_db(batch, collection)
                
                total_saved += len(batch)
                logger.info(f"   ✅ Batch {batch_num} saved. Total saved: {total_saved}/{len(enriched_nfts)}")
            
            logger.info(f"🎉 ========== STORAGE PROCESS COMPLETED ==========")
            logger.info(f"   Collection: {collection_name}")
            logger.info(f"   NFTs Saved: {total_saved}")
            logger.info(f"=" * 60)
            
            return collection

        except Exception as e:
            logger.error(f"💥 CRITICAL ERROR during storage for collection {collection_id}", exc_info=True)
            logger.error(f"   Error: {str(e)}")
            raise


    async def _process_nft_batch_in_db(self, batch: list, collection: NFTCollection):
        """Saves a batch of enriched NFT data within a single database transaction."""
        logger.info(f"      🔄 Starting DB transaction for batch of {len(batch)} NFTs...")
        
        # Define the synchronous function that will run within the transaction
        def _process_batch_in_transaction():
            nfts_created = 0
            nfts_updated = 0
            traits_created = 0
            errors = 0
            
            with transaction.atomic():
                for nft_data in batch:
                    try:
                        mint_address = nft_data.get("mint")
                        if not mint_address:
                            logger.warning("      ⚠️ Skipping NFT: missing mint address")
                            errors += 1
                            continue

                        # Create or update the NFT object
                        nft, created = NFT.objects.update_or_create(
                            mint_address=mint_address,
                            defaults={
                                "collection": collection,
                                "name": nft_data.get("name", f"NFT {mint_address[:8]}"),
                                "image_url": nft_data.get("image_url", ""),
                                "owner": nft_data.get("owner", "")
                            }
                        )
                        
                        if created:
                            nfts_created += 1
                        else:
                            nfts_updated += 1
                        
                        # Clear old trait associations
                        nft.trait_values.clear()

                        traits_data = nft_data.get("traits", {})
                        if isinstance(traits_data, dict) and traits_data:
                            for trait_type_name, trait_info in traits_data.items():
                                if not isinstance(trait_info, dict):
                                    continue
                                
                                trait_value_str = str(trait_info.get("value", ""))
                                if not trait_type_name or not trait_value_str:
                                    continue
                                
                                try:
                                    trait_rarity = float(trait_info.get("rarity", 0.0))
                                except (ValueError, TypeError):
                                    trait_rarity = 0.0

                                # Get or create the TraitType
                                trait_type, _ = TraitType.objects.get_or_create(
                                    name=trait_type_name,
                                    collection=collection
                                )
                                
                                # Get or create the TraitValue
                                trait_value, trait_value_created = TraitValue.objects.get_or_create(
                                    trait_type=trait_type,
                                    value=trait_value_str,
                                    defaults={"rarity": trait_rarity}
                                )
                                
                                if trait_value_created:
                                    traits_created += 1
                                
                                # Associate the TraitValue with the NFT
                                nft.trait_values.add(trait_value)

                    except Exception as e:
                        mint = nft_data.get('mint', 'unknown')
                        logger.error(f"      ❌ Error processing NFT {mint[:8]}...: {e}")
                        errors += 1
            
            logger.info(f"      ✅ Batch transaction complete:")
            logger.info(f"         - NFTs created: {nfts_created}")
            logger.info(f"         - NFTs updated: {nfts_updated}")
            logger.info(f"         - Traits created: {traits_created}")
            if errors > 0:
                logger.warning(f"         - Errors: {errors}")

        # Run the synchronous database operations
        await sync_to_async(_process_batch_in_transaction, thread_sensitive=True)()