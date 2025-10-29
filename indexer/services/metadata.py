# indexer/services/metadata.py
import logging
import re
from typing import Optional
from asgiref.sync import sync_to_async

from core.api_provider.api_providers import APIProviderManager
from nft_data.models import NFT, TraitType, TraitValue
from core.cache_manager import cache_manager, CacheType

logger = logging.getLogger(__name__)

class MetadataSyncService:
    """
    Handles fetching, caching, and updating an NFT's metadata, including
    its name, traits, and creators.
    """
    def __init__(self, provider_manager: APIProviderManager):
        self.provider_manager = provider_manager

    async def sync(self, mint_address: str) -> bool:
        """Main entry point to sync metadata for a single NFT."""
        try:
            nft = await sync_to_async(NFT.objects.select_related('collection').filter(mint_address=mint_address).first)()
            if not nft:
                logger.warning(f"Cannot sync metadata, NFT {mint_address} not found.")
                return False

            cache_key = f"metadata:{mint_address}"
            metadata = await cache_manager.get(cache_key, CacheType.METADATA)

            if not metadata:
                logger.debug(f"Cache miss for metadata: {mint_address}. Fetching from provider.")
                provider = await self.provider_manager.get_rpc_provider(nft.collection.address)
                if not provider: return False
                # metadata = await provider.get_metadata(mint_address) # Assumes provider has this method
                if not metadata: return False
                await cache_manager.set(cache_key, metadata, CacheType.METADATA, nft.collection.address)

            await self._apply_metadata_to_nft(nft, metadata)
            return True
        except Exception as e:
            logger.error(f"Error in MetadataSyncService.sync for {mint_address}: {e}", exc_info=True)
            return False

    async def _apply_metadata_to_nft(self, nft: NFT, metadata: dict):
        """Saves fetched metadata to the NFT and its related trait models."""
        update_fields = []
        name = metadata.get('name')
        if name and name != nft.name:
            nft.name = name
            update_fields.append('name')
            number = self._derive_nft_number(name)
            if number is not None and number != nft.number:
                nft.number = number
                update_fields.append('number')

        if update_fields:
            await sync_to_async(nft.save)(update_fields=update_fields)
        
        attributes = metadata.get('attributes') or metadata.get('traits')
        if attributes:
            await self._sync_traits(nft, attributes)
    
    async def _sync_traits(self, nft: NFT, attributes: list):
        """Clears and re-applies all traits for an NFT based on fresh metadata."""
        await sync_to_async(nft.trait_values.clear)()
        for attr in attributes:
            trait_type_name = attr.get('trait_type')
            trait_value_name = attr.get('value')
            if not trait_type_name or not trait_value_name:
                continue
            
            trait_type, _ = await sync_to_async(TraitType.objects.get_or_create)(name=trait_type_name, collection=nft.collection)
            trait_value, _ = await sync_to_async(TraitValue.objects.get_or_create)(trait_type=trait_type, value=trait_value_name)
            await sync_to_async(nft.trait_values.add)(trait_value)
        logger.info(f"Synced {len(attributes)} traits for NFT {nft.mint_address}")

    def _derive_nft_number(self, name: str) -> Optional[int]:
        """Extracts the token number (e.g., #1234) from its name string."""
        match = re.search(r'#(\d+)', name)
        return int(match.group(1)) if match else None
    
    async def handle_burn(self, mint_address: str):
        """
        Handles a burn event by finding the NFT in the database and deleting it.
        """
        if not mint_address:
            return

        try:
            # Find the NFT instance
            nft_to_burn = await sync_to_async(
                NFT.objects.filter(mint_address=mint_address).first
            )()

            if nft_to_burn:
                logger.info(f"🔥 Handling BURN event for NFT {mint_address}. Deleting from database.")
                # Delete the object
                await sync_to_async(nft_to_burn.delete)()
            else:
                logger.warning(f"Received BURN event for {mint_address}, but it was not found in the database.")
        except Exception as e:
            logger.error(f"Error during handle_burn for {mint_address}: {e}", exc_info=True)