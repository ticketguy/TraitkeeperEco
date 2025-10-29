# nft_data/services/batch_processor.py

import logging
import asyncio
import aiohttp
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handles parallel processing and enrichment of NFT data."""

    def __init__(self, metadata_fetcher):
        """Initializes the processor with a dependency on the MetadataFetcher."""
        self.metadata_fetcher = metadata_fetcher
        self.aiohttp_session = None
        self.session_lock = asyncio.Lock()
        logger.info("🔧 BatchProcessor initialized")

    async def initialize_persistent_session(self):
        """Creates a single, reusable aiohttp session for performance."""
        if self.aiohttp_session is None or self.aiohttp_session.closed:
            async with self.session_lock:
                if self.aiohttp_session is None or self.aiohttp_session.closed:
                    timeout = aiohttp.ClientTimeout(total=60, connect=10)
                    connector = aiohttp.TCPConnector(
                        limit=100,
                        limit_per_host=20,
                        ttl_dns_cache=300,
                        use_dns_cache=True
                    )
                    self.aiohttp_session = aiohttp.ClientSession(
                        connector=connector,
                        timeout=timeout,
                        headers={'User-Agent': 'TraitKeeper/1.0'}
                    )
                    logger.info("✅ Initialized persistent aiohttp session")
                    logger.info(f"   - Connection limit: 100")
                    logger.info(f"   - Per-host limit: 20")
                    logger.info(f"   - Timeout: 60s")

    async def close_persistent_session(self):
        """Closes the shared aiohttp session."""
        if self.aiohttp_session and not self.aiohttp_session.closed:
            await self.aiohttp_session.close()
            self.aiohttp_session = None
            logger.info("🔒 Closed persistent aiohttp session")

    async def fetch_metadata_batch(self, nfts: List[Dict], max_concurrent: int = 20) -> List[Dict]:
        """
        Takes a list of processed NFTs and enriches them by fetching their URI metadata in parallel.
        """
        logger.info(f"🚀 Starting parallel metadata fetch...")
        logger.info(f"   NFTs to process: {len(nfts)}")
        logger.info(f"   Max concurrent: {max_concurrent}")
        
        semaphore = asyncio.Semaphore(max_concurrent)
        successful_enrichments = 0
        skipped_already_complete = 0
        skipped_no_uri = 0
        failed_enrichments = 0
        
        async def fetch_single(nft_data: Dict) -> Dict:
            nonlocal successful_enrichments, skipped_already_complete, skipped_no_uri, failed_enrichments
            
            async with semaphore:
                mint = nft_data.get('mint', 'unknown')[:8]
                uri = nft_data.get("uri")
                
                # Skip if no URI or if it already seems to have off-chain data
                if not uri:
                    skipped_no_uri += 1
                    logger.debug(f"   ⏭️ Skipping {mint}...: No URI")
                    return nft_data
                
                if nft_data.get("image_url") and nft_data.get("traits"):
                    skipped_already_complete += 1
                    logger.debug(f"   ⏭️ Skipping {mint}...: Already has metadata")
                    return nft_data

                try:
                    logger.debug(f"   📡 Fetching {mint}... from URI")
                    metadata = await self.metadata_fetcher.fetch_metadata_from_uri(uri, self.aiohttp_session)
                    
                    if metadata:
                        # Enrich the existing nft_data dict with new info
                        nft_data["name"] = metadata.get("name", nft_data.get("name", ""))
                        nft_data["image_url"] = metadata.get("image", nft_data.get("image_url", ""))
                        nft_data["description"] = metadata.get("description", nft_data.get("description", ""))
                        
                        # Try multiple possible trait/attribute formats
                        traits_dict = {}
                        
                        # Format 1: Standard "attributes" array
                        attributes = metadata.get("attributes", [])
                        if attributes and isinstance(attributes, list):
                            logger.debug(f"      Found {len(attributes)} attributes (standard format)")
                            for attr in attributes:
                                if isinstance(attr, dict):
                                    # Support both "trait_type"/"value" and "name"/"value" formats
                                    trait_type = attr.get("trait_type") or attr.get("name")
                                    trait_value = attr.get("value")
                                    
                                    if trait_type and trait_value is not None:
                                        traits_dict[str(trait_type)] = {
                                            "value": str(trait_value),
                                            "rarity": 0.0
                                        }
                        
                        # Format 2: Alternative "traits" array
                        if not traits_dict:
                            traits = metadata.get("traits", [])
                            if traits and isinstance(traits, list):
                                logger.debug(f"      Found {len(traits)} traits (alternative format)")
                                for trait in traits:
                                    if isinstance(trait, dict):
                                        trait_type = trait.get("trait_type") or trait.get("name") or trait.get("type")
                                        trait_value = trait.get("value")
                                        
                                        if trait_type and trait_value is not None:
                                            traits_dict[str(trait_type)] = {
                                                "value": str(trait_value),
                                                "rarity": 0.0
                                            }
                        
                        # Format 3: Nested in "properties"
                        if not traits_dict:
                            properties = metadata.get("properties", {})
                            if isinstance(properties, dict):
                                prop_traits = properties.get("traits") or properties.get("attributes")
                                if prop_traits and isinstance(prop_traits, list):
                                    logger.debug(f"      Found {len(prop_traits)} traits (properties format)")
                                    for trait in prop_traits:
                                        if isinstance(trait, dict):
                                            trait_type = trait.get("trait_type") or trait.get("name") or trait.get("type")
                                            trait_value = trait.get("value")
                                            
                                            if trait_type and trait_value is not None:
                                                traits_dict[str(trait_type)] = {
                                                    "value": str(trait_value),
                                                    "rarity": 0.0
                                                }
                        
                        if traits_dict:
                            nft_data["traits"] = traits_dict
                            successful_enrichments += 1
                            logger.debug(f"   ✅ Enriched {mint}... with {len(traits_dict)} traits")
                        else:
                            successful_enrichments += 1
                            logger.warning(f"   ⚠️ Enriched {mint}... but found NO traits in metadata")
                            logger.debug(f"      Metadata keys: {list(metadata.keys())}")
                    else:
                        failed_enrichments += 1
                        logger.debug(f"   ⚠️ Failed to fetch metadata for {mint}...")
                    
                    return nft_data
                    
                except Exception as e:
                    failed_enrichments += 1
                    logger.warning(f"   ❌ Error enriching NFT {mint}... via URI {uri[:30]}...: {e}")
                    return nft_data
        
        start_time = asyncio.get_event_loop().time()
        
        tasks = [fetch_single(nft) for nft in nfts]
        enriched_nfts = await asyncio.gather(*tasks)
        
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        nfts_per_sec = len(nfts) / duration if duration > 0 else float('inf')

        logger.info(f"✅ Parallel fetch complete!")
        logger.info(f"   Duration: {duration:.2f}s ({nfts_per_sec:.2f} NFTs/sec)")
        logger.info(f"   Total processed: {len(enriched_nfts)}")
        logger.info(f"   Successfully enriched: {successful_enrichments}")
        logger.info(f"   Skipped (already complete): {skipped_already_complete}")
        logger.info(f"   Skipped (no URI): {skipped_no_uri}")
        logger.info(f"   Failed: {failed_enrichments}")
        
        return enriched_nfts

    async def _process_nft_data(self, nft_data: Dict) -> Optional[Dict]:
        """
        Standardizes raw NFT data from any provider into a consistent format
        before it's enriched and saved.
        """
        if not isinstance(nft_data, dict):
            logger.warning(f"⚠️ Skipping invalid raw NFT data (type: {type(nft_data)})")
            return None

        mint = nft_data.get("id") or nft_data.get("mint")
        if not mint:
            logger.warning(f"⚠️ Skipping NFT data: no mint/id field found. Keys: {list(nft_data.keys())}")
            return None

        content = nft_data.get("content", {})
        metadata = content.get("metadata", {})
        links = content.get("links", {})

        processed = {
            "mint": mint,
            "name": metadata.get("name", ""),
            "uri": content.get("json_uri", ""),
            "image_url": links.get("image", ""),
            "description": metadata.get("description", ""),
            "traits": {},
            "owner": nft_data.get("ownership", {}).get("owner", "")
        }
        
        logger.debug(f"   ✅ Processed NFT {mint[:8]}...")
        return processed