# /app/core/api_provider/quicknode_provider.py

import logging
import aiohttp
import websockets
import json
import asyncio  # Import asyncio
from typing import Dict, Optional, Callable
from django.conf import settings
from admin_panel.models import PrimaryProviderSetting
from asgiref.sync import sync_to_async

# Correct the relative import path
from .base import SolanaRPCProvider 

logger = logging.getLogger(__name__)

class QuickNodeProvider(SolanaRPCProvider):
    """
    QuickNode-specific provider with lazy initialization to prevent DB queries on app start.
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
        
        self.name = "quicknode"
        self.ws_url = None # Will be set by _lazy_init

        # 3. Add a lock and a flag to manage initialization
        self._init_lock = asyncio.Lock()
        self._initialized = False
        
        logger.debug("QuickNodeProvider instantiated (lazily).")

    async def _lazy_init(self):
        """Asynchronously performs DB-dependent initialization, only once."""
        if self._initialized:
            return

        async with self._init_lock:
            # Check again inside the lock
            if self._initialized:
                return

            logger.info("Performing lazy initialization for QuickNodeProvider...")
            try:
                # 4. Perform the database query asynchronously
                provider_setting = await sync_to_async(
                    PrimaryProviderSetting.objects.filter(name="quicknode").first
                )()
                
                rpc_url = self._provided_rpc_url or (provider_setting.rpc_url if provider_setting else None)
                api_key = self._provided_api_key or (provider_setting.api_key if provider_setting else None)
                
                if not rpc_url:
                    raise ValueError("QuickNode RPC URL not configured in DB")
                
                # 5. Set the real, authenticated values
                self.api_key = api_key
                
                full_rpc_url = rpc_url.rstrip('/')
                if api_key and api_key not in full_rpc_url:
                    full_rpc_url = f"{full_rpc_url}/{api_key}"
                
                self.rpc_url = full_rpc_url
                self.ws_url = (provider_setting.ws_url if provider_setting and provider_setting.ws_url 
                               else self.rpc_url.replace('https', 'wss'))
                
                self._initialized = True
                logger.info(f"QuickNodeProvider lazy-initialized with RPC: {self._sanitize_url_for_logging(self.rpc_url)}")

            except Exception as e:
                logger.critical(f"Failed to lazy-initialize QuickNodeProvider: {e}", exc_info=True)
                # self._initialized remains False, so it will retry on the next call

    # 6. Ensure _lazy_init is called before any method that needs credentials
    
    async def _async_post(self, payload: dict, timeout: int = 30) -> Optional[dict]:
        """Ensures service is initialized before making a POST request."""
        if not self._initialized:
            await self._lazy_init()
        return await super()._async_post(payload, timeout)

    async def check_availability(self) -> bool:
        """Ensures service is initialized before checking health."""
        if not self._initialized:
            await self._lazy_init()
        if not self._initialized:
            return False
        return await super().check_availability()
    
    async def get_collection_for_mint(self, mint_address: str) -> Optional[str]:
        """
        Standard RPC does not have a direct method for this.
        """
        if not self._initialized:
            await self._lazy_init() # Ensure init just in case
            
        logger.warning(f"QuickNodeProvider (standard RPC) does not support get_collection_for_mint directly.")
        return None

    async def get_metadata(self, mint_address: str) -> Optional[Dict]:
        """
        Standard RPC does not have a direct method for this.
        """
        if not self._initialized:
            await self._lazy_init() # Ensure init just in case
            
        logger.warning(f"QuickNodeProvider (standard RPC) does not support get_metadata directly.")
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