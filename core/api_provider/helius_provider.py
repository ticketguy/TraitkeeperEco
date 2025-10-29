import logging
import aiohttp
import asyncio  # Import asyncio
from typing import Dict, Optional, List, Callable
from django.conf import settings
from admin_panel.models import PrimaryProviderSetting
from asgiref.sync import sync_to_async

# Correct the relative import path now that it's in 'core'
from .base import SolanaRPCProvider 

logger = logging.getLogger(__name__)

class HeliusProvider(SolanaRPCProvider):
    """
    Helius-specific provider with lazy initialization to prevent DB queries on app start.
    """
    def __init__(self, rpc_url: Optional[str] = None, api_key: Optional[str] = None):
        # 1. Store provided args, DO NOT query DB here
        self._provided_rpc_url = rpc_url
        self._provided_api_key = api_key
        
        # 2. Call super() with placeholder values
        super().__init__(
            rpc_url="http://placeholder.com", # This will be replaced
            api_key=None,
            max_requests=1,
            per_seconds=2
        )
        
        self.name = "helius"
        self.rest_api_url = "https://api.helius.xyz"
        self.ws_url = None # Will be set by _lazy_init
        
        # 3. Add a lock and a flag to manage initialization
        self._init_lock = asyncio.Lock()
        self._initialized = False
        
        logger.debug("HeliusProvider instantiated (lazily).")

    async def _lazy_init(self):
        """Asynchronously performs DB-dependent initialization, only once."""
        # If already initialized, do nothing.
        if self._initialized:
            return

        # Use a lock to prevent multiple coroutines from initializing at the same time
        async with self._init_lock:
            # Check again inside the lock in case it was initialized while waiting
            if self._initialized:
                return

            logger.info("Performing lazy initialization for HeliusProvider...")
            try:
                # 4. Perform the database query asynchronously
                provider_setting = await sync_to_async(
                    PrimaryProviderSetting.objects.filter(name="helius").first
                )()
                
                rpc_url = self._provided_rpc_url or (provider_setting.rpc_url if provider_setting else None)
                api_key = self._provided_api_key or (provider_setting.api_key if provider_setting else None)
                
                if not api_key: raise ValueError("Helius API key not configured in DB")
                if not rpc_url: raise ValueError("Helius RPC URL not configured in DB")
                
                # 5. Set the real, authenticated values on the instance
                self.api_key = api_key
                self.rpc_url = f"{rpc_url.rstrip('/')}?api-key={api_key}"
                self.ws_url = (provider_setting.ws_url if provider_setting and provider_setting.ws_url 
                               else f"wss://mainnet.helius-rpc.com/?api-key={api_key}")
                
                # 6. Mark as initialized
                self._initialized = True
                logger.info(f"HeliusProvider lazy-initialized with RPC: {self._sanitize_url_for_logging(self.rpc_url)}")

            except Exception as e:
                logger.critical(f"Failed to lazy-initialize HeliusProvider: {e}", exc_info=True)
                # self._initialized remains False, so it will retry on the next call

    # 7. Ensure _lazy_init is called before any method that needs credentials
    
    async def _async_post(self, payload: dict, timeout: int = 30) -> Optional[dict]:
        """Ensures service is initialized before making a POST request."""
        if not self._initialized:
            await self._lazy_init()
        # If init failed, rpc_url will still be the placeholder, and this will fail (which is correct)
        return await super()._async_post(payload, timeout)

    async def check_availability(self) -> bool:
        """Ensures service is initialized before checking health."""
        if not self._initialized:
            await self._lazy_init()
        # If init failed, we can't check availability
        if not self._initialized:
            return False
        return await super().check_availability()
        
    async def get_das_collection(self, collection_id: str) -> Optional[Dict]:
        """
        NEW: Fetches collection details using Helius's getAsset method.
        This is used to get the total number of items in a collection.
        """
        if not self._initialized:
            await self._lazy_init() # Ensure we are initialized
            
        payload = {
            "jsonrpc": "2.0", "id": "1", "method": "getAsset",
            "params": {"id": collection_id}
        }
        try:
            response = await self._async_post(payload)
            # The totalItems is not directly available, so we return the whole asset data
            return response if response and "result" in response else None
        except Exception as e:
            logger.error(f"Helius failed to get DAS collection for {collection_id}: {e}")
            return None

    async def get_nfts_by_group(self, collection_id: str, page: int, page_size: int) -> Optional[Dict]:
        """
        NEW: Fetches a paginated list of NFTs in a collection using Helius's getAssetsByGroup.
        """
        if not self._initialized:
            await self._lazy_init() # Ensure we are initialized
            
        payload = {
            "jsonrpc": "2.0", "id": "1", "method": "getAssetsByGroup",
            "params": {
                "groupKey": "collection",
                "groupValue": collection_id,
                "page": page,
                "limit": page_size
            }
        }
        try:
            return await self._async_post(payload)
        except Exception as e:
            logger.error(f"Helius failed to get NFTs by group for {collection_id} on page {page}: {e}")
            return None
            
    async def get_assets_by_creator(self, creator_address: str, limit: int = 1000) -> Optional[Dict]:
        """
        NEW: Fetches assets by a specific creator address.
        """
        if not self._initialized:
            await self._lazy_init() # Ensure we are initialized
            
        payload = {
            "jsonrpc": "2.0", "id": "1", "method": "getAssetsByCreator",
            "params": {
                "creatorAddress": creator_address,
                "onlyVerified": True,
                "page": 1,
                "limit": limit
            }
        }
        try:
            return await self._async_post(payload)
        except Exception as e:
            logger.error(f"Helius failed to get assets by creator for {creator_address}: {e}")
            return None

    async def get_collection_activities(self, collection_address: str, limit: int = 100) -> List[Dict]:
        """Fetches raw enriched collection activities using Helius's parsed transaction history API."""
        if not self._initialized:
            await self._lazy_init() # Ensure we are initialized
            
        url = f"{self.rest_api_url}/v0/addresses/{collection_address}/transactions"
        params = {'api-key': self.api_key, 'limit': limit}
        
        try:
            # This method doesn't use _async_post, so it needs its own session
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            logger.error(f"Failed to get Helius collection activities for {collection_address}: {e}")
            return []

    async def get_collection_for_mint(self, mint_address: str) -> Optional[str]:
        """
        Uses the Helius getAsset API to find an NFT's collection address.
        """
        if not self._initialized:
            await self._lazy_init() # Ensure we are initialized
            
        payload = {
            "jsonrpc": "2.0", "id": "1", "method": "getAsset",
            "params": {"id": mint_address}
        }
        try:
            response = await self._async_post(payload)
            if response and "result" in response:
                grouping = response["result"].get("grouping", [])
                for group in grouping:
                    if group.get("group_key") == "collection":
                        collection_address = group.get("group_value")
                        logger.debug(f"Helius found collection {collection_address} for mint {mint_address}")
                        return collection_address
            return None
        except Exception as e:
            logger.error(f"Helius failed to get collection for mint {mint_address}: {e}")
            return None

    async def get_metadata(self, mint_address: str) -> Optional[Dict]:
        """
        Uses the Helius getAsset API to fetch the full JSON metadata for an NFT.
        """
        if not self._initialized:
            await self._lazy_init() # Ensure we are initialized
            
        payload = {
            "jsonrpc": "2.0", "id": "1", "method": "getAsset",
            "params": {"id": mint_address}
        }
        try:
            response = await self._async_post(payload)
            if response and "result" in response:
                content = response["result"].get("content", {})
                metadata = content.get("metadata", {})
                if metadata:
                    files = content.get("files", [])
                    # Ensure files is a list and not empty before indexing
                    if files and isinstance(files, list) and 'uri' in files[0]:
                        metadata['image_url'] = files[0]['uri']
                return metadata
            return None
        except Exception as e:
            logger.error(f"Helius failed to get metadata for mint {mint_address}: {e}")
            return None

    async def validate_address(self, address: str) -> bool:
        """Validate if an address is valid Solana base58."""
        # This method doesn't require API keys, so no init needed
        try:
            from solders.pubkey import Pubkey
            Pubkey.from_string(address)
            return True
        except Exception:
            return False