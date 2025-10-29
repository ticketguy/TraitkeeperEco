# nft_data/services/provider_manager.py

import logging
import asyncio
import aiohttp
import base64
import base58
from typing import Optional, Tuple, List, Dict, Callable
from core.api_provider.api_providers import APIProviderManager
from core.api_provider.helius_provider import HeliusProvider

logger = logging.getLogger(__name__)

class ProviderManager:
    """Manages provider selection and NFT list fetching strategies."""
    def __init__(self):
        self.api_provider_manager = APIProviderManager()
        # Note: The aiohttp session is now managed by the BatchProcessor, 
        # as these methods should only return raw data.

    async def get_rpc_provider(self):
        """Gets the best available general-purpose RPC provider."""
        return await self.api_provider_manager.get_rpc_provider()

    async def get_all_providers(self) -> List:
        """Gets a sorted list of all active providers, with the primary one first."""
        return await self.api_provider_manager.get_all_providers()

    async def get_provider_by_name(self, name: str):
        """Gets a specific provider by its name."""
        return await self.api_provider_manager.get_provider_by_name(name)

    async def get_current_provider_name(self) -> str:
        """Gets the name of the provider currently in use."""
        return await self.api_provider_manager.get_current_provider_name()

    async def get_provider_with_fallback(self, prefer_helius=False) -> Tuple[Optional[object], bool]:
        """Gets a provider, optionally preferring Helius, and indicates if it is Helius."""
        if prefer_helius:
            helius_provider = await self.api_provider_manager.get_provider_by_name('helius')
            if helius_provider and await helius_provider.check_availability():
                return helius_provider, True
            logger.warning("Helius provider was requested but is not available, falling back.")
        
        provider = await self.api_provider_manager.get_rpc_provider()
        is_helius = isinstance(provider, HeliusProvider) if provider else False
        return provider, is_helius

    async def fetch_using_helius_assets_by_group(self, collection_id: str, last_fetched=None) -> List[Dict]:
        """Strategy to fetch NFT list using Helius's getAssetsByGroup."""
        try:
            provider, is_helius = await self.get_provider_with_fallback(prefer_helius=True)
            if not provider or not is_helius:
                logger.warning("Helius provider not available for getAssetsByGroup.")
                return []

            # Define the specific fetch function for this strategy
            async def fetch_page(page: int, page_size: int):
                return await provider.get_nfts_by_group(collection_id, page, page_size)
            
            # Get total supply to help with pagination
            collection_data = await provider.get_das_collection(collection_id)
            total_supply = 0
            if collection_data and "result" in collection_data:
                total_supply = collection_data.get("result", {}).get("totalItems", 0)

            if total_supply == 0:
                logger.warning(f"Helius reported 0 total supply for {collection_id}. Proceeding with fetch but pagination may be incomplete.")

            # Use the generic paginator to get the raw list of NFTs
            raw_nfts = await self._paginated_fetch(
                collection_id=collection_id,
                fetch_method=fetch_page,
                total_supply=total_supply
            )
            logger.info(f"Fetched {len(raw_nfts)} raw NFTs using Helius getAssetsByGroup.")
            return raw_nfts
            
        except Exception as e:
            logger.error(f"Error in fetch_using_helius_assets_by_group for {collection_id}: {e}", exc_info=True)
            return []

    async def fetch_using_das(self, collection_id: str, last_fetched=None) -> List[Dict]:
        """Strategy to fetch NFT list using the DAS API."""
        # This is often functionally identical to getAssetsByGroup but kept for logical separation
        return await self.fetch_using_helius_assets_by_group(collection_id, last_fetched)

    async def fetch_using_program_accounts(self, collection_id: str, last_fetched=None) -> List[Dict]:
        """
        Fetch NFTs using Solana getProgramAccounts as fallback.
        Returns raw account data including mint addresses.
        """
        logger.info(f"--- Starting fetch_using_program_accounts for {collection_id} ---")
        
        try:
            METAPLEX_PROGRAM_ID = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"
            METADATA_ACCOUNT_SIZE = 679
            all_nfts = []
            max_retries = 3
            
            provider = await self.api_provider_manager.get_rpc_provider()
            if provider is None:
                logger.error("No RPC provider available for getProgramAccounts")
                return []

            for attempt in range(max_retries):
                try:
                    payload = {
                        "jsonrpc": "2.0",
                        "id": "getProgramAccounts",
                        "method": "getProgramAccounts",
                        "params": [
                            METAPLEX_PROGRAM_ID,
                            {
                                "encoding": "base64",
                                "filters": [
                                    {"memcmp": {"offset": 326, "bytes": collection_id}},
                                    {"dataSize": METADATA_ACCOUNT_SIZE}
                                ]
                            }
                        ]
                    }
                    
                    async with aiohttp.ClientSession() as session:
                        headers = {}
                        if hasattr(provider, 'api_key') and provider.api_key:
                            headers["Authorization"] = f"Bearer {provider.api_key}"
                            
                        async with session.post(
                            provider.rpc_url,
                            json=payload,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=90)
                        ) as response:
                            response.raise_for_status()
                            data = await response.json()
                    
                    if "result" not in data or not isinstance(data["result"], list):
                        logger.warning(f"Invalid response structure on attempt {attempt + 1}")
                        if attempt == max_retries - 1:
                            return []
                        continue
                    
                    accounts = data["result"]
                    logger.info(f"Retrieved {len(accounts)} program accounts for {collection_id}")
                    
                    # Process each account
                    for account in accounts:
                        try:
                            pubkey = account.get("pubkey")
                            account_data = account.get("account", {})
                            data_base64 = account_data.get("data", ["", ""])[0] if isinstance(account_data.get("data"), list) else account_data.get("data", "")
                            
                            if not pubkey or not data_base64:
                                continue
                            
                            # Decode the metadata account
                            decoded_data = base64.b64decode(data_base64)
                            
                            # Extract mint address (offset 33, 32 bytes)
                            mint_bytes = decoded_data[33:65]
                            mint_address = base58.b58encode(mint_bytes).decode('utf-8')
                            
                            # Extract update authority (offset 1, 32 bytes)
                            update_authority_bytes = decoded_data[1:33]
                            update_authority = base58.b58encode(update_authority_bytes).decode('utf-8')
                            
                            all_nfts.append({
                                "id": mint_address,
                                "mint": mint_address,
                                "metadata_account": pubkey,
                                "update_authority": update_authority,
                                "collection": collection_id
                            })
                            
                        except Exception as e:
                            logger.warning(f"Error processing account {pubkey}: {e}")
                            continue
                    
                    # getProgramAccounts returns all results at once
                    logger.info(f"--- Finished fetch_using_program_accounts. Found {len(all_nfts)} NFTs ---")
                    return all_nfts
                    
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                    if attempt == max_retries - 1:
                        logger.error(f"All retries failed for getProgramAccounts", exc_info=True)
                    else:
                        await asyncio.sleep(2 ** attempt)

            return all_nfts

        except Exception as e:
            logger.error(f"--- ERROR in fetch_using_program_accounts for {collection_id}: {e} ---", exc_info=True)
            return []

    async def _paginated_fetch(self, collection_id: str, fetch_method: Callable, total_supply: int = 0, max_page_size: int = 100, max_retries: int = 3, last_fetched=None) -> List[Dict]:
        """Generic pagination helper that fetches and returns RAW data."""
        page_size = min(max_page_size, total_supply) if total_supply > 0 else max_page_size
        all_nfts_raw = []
        page = 1
        has_more = True

        while has_more:
            nfts_batch = []
            for attempt in range(max_retries):
                try:
                    data = await fetch_method(page, page_size)
                    
                    if not isinstance(data, dict) or "result" not in data:
                        logger.warning(f"Invalid response structure on page {page}, attempt {attempt + 1}")
                        has_more = False
                        break
                    
                    nfts_batch = data["result"].get("items", [])
                    all_nfts_raw.extend(nfts_batch)
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    logger.warning(f"Page {page} attempt {attempt + 1}/{max_retries} failed: {e}")
                    if attempt == max_retries - 1:
                        has_more = False # All retries failed, stop paginating
                        break
                    await asyncio.sleep(2 ** attempt)
            
            if has_more and (not nfts_batch or len(nfts_batch) < page_size or (total_supply and len(all_nfts_raw) >= total_supply)):
                has_more = False
            elif has_more:
                page += 1

        return all_nfts_raw