# indexer/api_provider/generic_provider.py

import logging
from .base import SolanaRPCProvider 

logger = logging.getLogger(__name__)

class GenericProvider(SolanaRPCProvider):
    def __init__(self, rpc_url: str, api_key: str = None):
        super().__init__(rpc_url, api_key)
        self.name = 'generic'
        
        if self.rpc_url.startswith('https://'):
            self.ws_url = self.rpc_url.replace('https://', 'wss://', 1)
        elif self.rpc_url.startswith('http://'):
            self.ws_url = self.rpc_url.replace('http://', 'ws://', 1)
        else:
            self.ws_url = None
            logger.warning(f"Could not construct a ws_url for generic provider with RPC URL: {self.rpc_url}")

    async def get_collection_for_mint(self, mint_address: str) -> dict:
        # Generic providers don't have a standard way to do this
        logger.warning("get_collection_for_mint is not supported by the generic provider.")
        raise NotImplementedError("This method is not implemented for the generic provider.")

    async def get_metadata(self, mint_address: str) -> dict:
        # Generic providers don't have a standard way to do this
        logger.warning("get_metadata is not supported by the generic provider.")
        raise NotImplementedError("This method is not implemented for the generic provider.")

    async def check_availability(self):
        return await super().check_availability()