# nft_data/services/collection_validator.py

import logging
from typing import Optional
from asgiref.sync import sync_to_async

from .provider_manager import ProviderManager
from .cache_service import CacheService
from .metadata_fetcher import MetadataFetcher

logger = logging.getLogger(__name__)


class CollectionValidator:
    """Handles validation of collection addresses and resolution of collections for NFTs."""

    def __init__(self, provider_manager, cache_service, metadata_fetcher):
        """Initializes the validator with its dependencies."""

        self.provider_manager = provider_manager
        self.cache_service = cache_service
        self.metadata_fetcher = metadata_fetcher

    async def validate_collection(self, collection_address: str) -> bool:
        """
        Validate if an address is a valid NFT collection by checking providers.
        """
        try:
            cached_result = await self.cache_service.get_from_cache("validation", collection_address)
            if cached_result is not None:
                logger.debug(f"Cache hit for validation of {collection_address}: {cached_result}")
                return cached_result

            providers = await self.provider_manager.get_all_providers()
            if not providers:
                logger.error("No RPC providers available for validate_collection")
                await self.cache_service.save_to_cache("validation", collection_address, False, timeout=3600)
                return False

            for provider in providers:
                logger.debug(f"Attempting validation with provider {provider.name}")
                try:
                    if hasattr(provider, 'get_nfts_by_group'):
                        response = await provider.get_nfts_by_group(collection_address, page=1, page_size=1)
                        if response and response.get('result', {}).get('items'):
                            logger.info(f"Validated {collection_address} using {provider.name}")
                            await self.cache_service.save_to_cache("validation", collection_address, True, timeout=3600)
                            return True
                except Exception as e:
                    logger.warning(f"Error using {provider.name} for validation: {str(e)}")
                    continue

            # Fallback to on-chain metadata check
            collection_metadata = await self.metadata_fetcher.fetch_metadata_account(collection_address)
            if collection_metadata:
                # This logic is based on the structure of a valid collection metadata account
                if (collection_metadata.get("name") and collection_metadata.get("creator_addresses")) or collection_metadata.get("collection"):
                    await self.cache_service.save_to_cache("validation", collection_address, True, timeout=3600)
                    return True

            logger.error(f"Failed to validate {collection_address} as a collection after all methods.")
            await self.cache_service.save_to_cache("validation", collection_address, False, timeout=3600)
            return False

        except Exception as e:
            logger.error(f"Critical error during validation for {collection_address}: {str(e)}", exc_info=True)
            await self.cache_service.save_to_cache("validation", collection_address, False, timeout=3600)
            return False

    async def is_compressed_nft(self, mint_address: str) -> bool:
        """
        Detect if an NFT is compressed (cNFT) by checking for its mint account.
        Compressed NFTs don't have traditional mint accounts.
        """
        try:
            provider = await self.provider_manager.get_rpc_provider()
            if not provider:
                return False
            
            account_info = await provider.get_account_info(mint_address)
            
            # If the mint account itself doesn't exist on-chain, it's very likely a cNFT
            if not account_info or not account_info.get("value"):
                logger.info(f"🗜️ Detected compressed NFT (or invalid address): {mint_address[:8]}...")
                return True
            
            return False
        except Exception as e:
            logger.debug(f"Error checking if {mint_address[:8]}... is compressed: {e}")
            return False

    async def find_collection_via_helius_das(self, mint_address: str) -> Optional[str]:
        """
        Use the Helius DAS API as a method to find an NFT's collection.
        This works well for both standard and compressed NFTs.
        """
        try:
            provider = await self.provider_manager.get_provider_by_name('helius')
            if not provider:
                return None
            
            collection_address = await provider.get_collection_for_mint(mint_address)
            if collection_address:
                logger.info(f"✅ Found collection via Helius DAS: {collection_address[:8]}...")
                return collection_address
            
            return None
        except Exception as e:
            logger.debug(f"Helius DAS collection lookup failed for {mint_address}: {e}")
            return None

    async def resolve_collection_for_nft(self, mint_address: str) -> Optional[str]:
        """
        Comprehensive collection resolution with multiple fallback methods.
        """
        logger.info(f"🔍 Resolving collection for NFT: {mint_address[:8]}...")
        
        # Method 1: Try Helius DAS first (works for cNFTs and regular NFTs)
        collection_address = await self.find_collection_via_helius_das(mint_address)
        if collection_address:
            logger.info(f"✅ Method 1 SUCCESS (Helius DAS): {collection_address[:8]}...")
            return collection_address
        
        # Method 2: Check if it's a compressed NFT
        is_cnft = await self.is_compressed_nft(mint_address)
        if is_cnft:
            logger.warning(f"⚠️ NFT {mint_address[:8]}... is compressed - cannot use Metaplex metadata")
            return None
        
        # Method 3: Try Metaplex metadata account (traditional NFTs)
        logger.info(f"📝 Method 3: Trying Metaplex metadata account...")
        metadata = await self.fetch_metadata_account(mint_address)
        if metadata and metadata.get("collection"):
            collection_address = metadata["collection"]["key"]
            logger.info(f"✅ Method 3 SUCCESS (Metaplex): {collection_address[:8]}...")
            return collection_address
        
        # Method 4: Try other providers
        logger.info(f"🔄 Method 4: Trying other providers...")
        providers = await self.api_provider_manager.get_all_providers()
        for provider in providers:
            if hasattr(provider, 'get_collection_for_mint'):
                try:
                    collection_address = await provider.get_collection_for_mint(mint_address)
                    if collection_address:
                        logger.info(f"✅ Method 4 SUCCESS ({provider.name}): {collection_address[:8]}...")
                        return collection_address
                except Exception as e:
                    logger.debug(f"Provider {provider.name} failed: {e}")
                    continue
        
        logger.error(f"❌ All methods failed to find collection for {mint_address[:8]}...")
        return None