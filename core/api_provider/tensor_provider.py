# indexer/api_provider/tensor_provider.py - ENHANCED FOR COMPLETE RAW DATA CAPTURE
import aiohttp
import logging
import random
import json
from django.conf import settings
from django.core.cache import cache
import redis
from typing import Dict, List, Optional
import asyncio
from datetime import datetime, timedelta
from django.utils import timezone
from datetime import timezone as dt_timezone
from asgiref.sync import sync_to_async
from decimal import Decimal
from core.cache_manager import cache_manager, CacheType

logger = logging.getLogger(__name__)


class TensorRateLimiter:
    """Rate limiter for Tensor API - 1 request per second."""
    
    def __init__(self):
        self.last_request_time = None
        self.min_interval = 1.0  # 1 second between requests
        self.consecutive_failures = 0
        self.backoff_until = None
        
    async def wait_if_needed(self):
        now = datetime.now()
        
        # Check backoff period
        if self.backoff_until and now < self.backoff_until:
            wait_time = (self.backoff_until - now).total_seconds()
            logger.info(f"Tensor rate limiter: waiting {wait_time:.1f}s (backoff)")
            await asyncio.sleep(wait_time)
            return
        
        # Ensure minimum interval between requests
        if self.last_request_time:
            elapsed = (now - self.last_request_time).total_seconds()
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                logger.debug(f"Tensor rate limiter: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
        
        self.last_request_time = datetime.now()
    
    def on_rate_limit_hit(self, retry_after=None):
        self.consecutive_failures += 1
        backoff_seconds = min(2 ** self.consecutive_failures, 60)
        self.backoff_until = datetime.now() + timedelta(seconds=backoff_seconds)
        logger.warning(f"Tensor rate limit hit, backing off for {backoff_seconds}s")

    def on_success(self):
        self.consecutive_failures = 0
        self.backoff_until = None


class TensorProvider:
    """
    ENHANCED Tensor API provider - Complete raw data capture for multi-source analytics.
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.mainnet.tensordev.io/api/v1"
        self.name = "tensor"
        self.max_retries = 3
        self.rate_limiter = TensorRateLimiter()
        self.redis_client = redis.from_url(settings.REDIS_URL) if hasattr(settings, 'REDIS_URL') else None
        self._collection_cache = {}
        
        logger.info(f"Initialized TensorProvider with base_url: {self.base_url}")
        logger.info(f"Tensor API key configured: {'Yes' if self.api_key else 'No'}")

    async def _async_get(self, endpoint: str, params: dict = None, **kwargs) -> Optional[dict]:
        """HTTP GET request with enhanced logging."""
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            'accept': 'application/json',
            'x-tensor-api-key': self.api_key,
            'User-Agent': 'TraitKeeper/1.0'
        }
        
        # Log the request details
        logger.info(f"Tensor API Call: GET {url}")
        if params:
            logger.info(f"Tensor API Params: {params}")
        
        for attempt in range(self.max_retries):
            try:
                await self.rate_limiter.wait_if_needed()
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, 
                        headers=headers,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                        **kwargs
                    ) as response:
                        
                        # Log response status
                        logger.info(f"Tensor HTTP {response.status}: {url}")
                        
                        if response.status == 429:
                            retry_after = response.headers.get('Retry-After')
                            logger.warning(f"Tensor Rate limited, retry after: {retry_after}")
                            self.rate_limiter.on_rate_limit_hit(retry_after)
                            continue
                        
                        elif response.status >= 500:
                            error_text = await response.text()
                            logger.error(f"Tensor Server error {response.status}: {error_text[:200]}")
                            if attempt < self.max_retries - 1:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            return None
                        
                        elif response.status == 404:
                            logger.warning(f"Tensor Endpoint not found: {url}")
                            return None
                        
                        elif response.status == 401:
                            logger.error(f"Tensor Authentication failed: {url}")
                            return None
                        
                        elif response.status == 403:
                            logger.error(f"Tensor API forbidden: {url}")
                            return None
                        
                        elif response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Tensor HTTP error {response.status}: {error_text[:200]}")
                            return None
                        
                        # Success - log response preview
                        self.rate_limiter.on_success()
                        result = await response.json()
                        
                        # Log response preview
                        if isinstance(result, list):
                            logger.info(f"Tensor Response: Array with {len(result)} items")
                            if result and len(result) > 0:
                                logger.info(f"Tensor First item preview: {str(result[0])[:150]}...")
                        elif isinstance(result, dict):
                            logger.info(f"Tensor Response: Object with keys: {list(result.keys())}")
                            logger.info(f"Tensor Response preview: {str(result)[:200]}...")
                        else:
                            logger.info(f"Tensor Response: {type(result)} - {str(result)[:200]}")
                        
                        return result
                        
            except Exception as e:
                logger.error(f"Tensor Request exception (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.error(f"Tensor Request failed after {self.max_retries} attempts: {url}")
                return None
        
        return None

    def _is_valid_uuid(self, potential_uuid: str) -> bool:
        """Check if a string is a valid UUID format."""
        try:
            import uuid
            uuid.UUID(potential_uuid)
            return True
        except (ValueError, TypeError):
            return False

    def _is_solana_address(self, address: str) -> bool:
        """Check if a string is a Solana address format."""
        if not address or not isinstance(address, str):
            return False
        
        # Solana addresses are 43-44 characters and use base58 encoding
        if len(address) not in [43, 44]:
            return False
        
        # Check for valid base58 characters (no 0, O, I, l)
        valid_chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return all(c in valid_chars for c in address)

    async def check_availability(self) -> bool:
        """Check if the Tensor API is available."""
        try:
            logger.info(f"Checking Tensor API availability...")
            response = await self._async_get("/rpc/priority_fees")
            is_available = response is not None
            logger.info(f"Tensor API Available: {is_available}")
            return is_available
        except Exception as e:
            logger.error(f"Error checking Tensor availability: {str(e)}")
            return False

    async def find_collection_symbol(self, collection_address: str, collection_name: str = None) -> Optional[str]:
        """
        Finds a collection's Tensor UUID.

        It follows a multi-step process:
        1. Checks the local database for a stored, verified identifier.
        2. If not found, falls back to searching the Tensor API by the on-chain address.
        3. If still not found, it searches the Tensor API by the collection's name.

        Args:
            collection_address (str): The on-chain address of the collection.
            collection_name (str): The name of the collection, used for API searching.

        Returns:
            Optional[str]: The Tensor UUID string, or None if not found.
        """
        try:
            from indexer.models import MarketplaceIdentifier
            from nft_data.models import NFTCollection

            # Step 1: Query the local database for the collection. This is the fastest and most reliable source.
            collection = await sync_to_async(
                NFTCollection.objects.filter(address=collection_address).first
            )()

            if collection:
                # Check if we have a stored identifier for Tensor for this collection.
                marketplace_id = await sync_to_async(
                    MarketplaceIdentifier.objects.filter(collection=collection, marketplace='tensor').first
                )()
                if marketplace_id and marketplace_id.identifier_value:
                    logger.info(f"Tensor: Found UUID in DB: {marketplace_id.identifier_value}")
                    return marketplace_id.identifier_value

            # Step 2: (Fallback) If not in DB, search the Tensor API by the on-chain address.
            logger.info(f"Tensor: UUID not in DB. Searching API by address: {collection_address}")
            find_response = await self._async_get("/collections/find_collection", params={'filter': collection_address})
            if find_response and isinstance(find_response, dict) and find_response.get('collId'):
                uuid = find_response['collId']
                logger.info(f"Tensor: Found UUID via address search: {uuid}")
                await self._store_collection_uuid(collection_address, uuid) # Save for next time
                return uuid

            # Step 3: (Fallback) If still not found, search the Tensor API by name.
            if collection_name:
                logger.info(f"Tensor: UUID not found by address. Searching API by name: '{collection_name}'")
                uuid = await self._search_collection_by_name(collection_name, collection_address)
                if uuid:
                    logger.info(f"Tensor: Found UUID via name search: {uuid}")
                    await self._store_collection_uuid(collection_address, uuid) # Save for next time
                    return uuid

        except Exception as e:
            logger.error(f"Tensor: Error finding collection UUID for {collection_address}: {e}")

        # If all lookups fail, return None.
        logger.warning(f"Tensor: Could not find UUID for {collection_address} after all checks.")
        return None

    async def get_collection_data(self, collection_symbol: str, collection_address: str, priority_tier: str) -> Dict:
        """
        Fetches and processes statistics for a single collection from Tensor.

        This method checks the cache, fetches data from the API if necessary using
        the collection's UUID (symbol), parses the detailed raw response, and caches
        the result with a priority-aware TTL.

        Args:
            collection_symbol (str): The Tensor-specific UUID for the collection.
            collection_address (str): The on-chain address of the collection.
            priority_tier (str): The priority tier ('VIP', 'ACTIVE', 'INACTIVE').

        Returns:
            Dict: A dictionary containing the processing status, stats, and raw data.
        """
        # Step 1: Check the central cache for existing data.
        cache_key = f"tensor:collection:{collection_symbol}"
        cached_data = await cache_manager.get(cache_key)
        if cached_data:
            logger.info(f"💾 ✅ Cache HIT for Tensor UUID '{collection_symbol}'")
            return cached_data

        # Step 2: Prepare result structure and fetch from API.
        result = {"success": False, "stats": {}, "raw_data": {}, "error": None}
        collection_info = await self._get_collection_info(collection_symbol)
        
        if collection_info:
            # Step 3: If the API call is successful, parse the comprehensive raw data.
            result["raw_data"] = collection_info
            stats = collection_info.get('stats', {})
            
            # Extract and convert all available metrics from the stats object.
            floor_price = self._convert_lamports_to_sol(stats.get('buyNowPrice', 0))
            volume_24h = self._convert_lamports_to_sol(stats.get('volume24h', 0))
            total_supply = self._safe_int_convert(stats.get('numMints', 0))
            listed_count = self._safe_int_convert(stats.get('numListed', 0))
            
            # Assemble the final, clean statistics object.
            result["stats"] = {
                "collection_name": collection_info.get('name', collection_symbol),
                "tensor_uuid": collection_symbol,
                "floor_price": floor_price,
                "volume_24h": volume_24h,
                "total_supply": total_supply,
                "listed_count": listed_count,
                "highest_bid": self._convert_lamports_to_sol(stats.get('sellNowPrice', 0)),
                "price_change_24h": self._safe_float_convert(stats.get('floor24h', 0)),
                "total_volume": self._convert_lamports_to_sol(stats.get('volumeAll', 0)),
                "sales_count_24h": self._safe_int_convert(stats.get('sales24h', 0)),
                "data_completeness_score": self._calculate_data_completeness(stats),
            }
            result["success"] = True

            # Step 4: Cache the successful result with a priority-aware TTL.
            ttl = cache_manager.get_ttl(CacheType.PROVIDER, priority_tier)
            await cache_manager.set(cache_key, result, ttl=ttl)
            logger.info(f"💾 Cached Tensor data for '{collection_symbol}' with priority '{priority_tier}' (TTL: {ttl}s)")
        else:
            result["error"] = f"Collection UUID '{collection_symbol}' not found on Tensor"

        return result

    def _convert_lamports_to_sol(self, lamports_value) -> float:
        """Convert lamports to SOL with error handling."""
        try:
            if lamports_value is None or lamports_value == "":
                return 0.0
            return float(lamports_value) / 1e9
        except (ValueError, TypeError) as e:
            logger.warning(f"Error converting lamports {lamports_value}: {e}")
            return 0.0

    def _safe_float_convert(self, value) -> float:
        """Safely convert value to float."""
        try:
            if value is None or value == "":
                return 0.0
            return float(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Error converting to float {value}: {e}")
            return 0.0

    def _safe_int_convert(self, value) -> int:
        """Safely convert value to int."""
        try:
            if value is None or value == "":
                return 0
            return int(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Error converting to int {value}: {e}")
            return 0

    def _safe_decimal_convert(self, value) -> Decimal:
        """Safely convert value to Decimal for precision."""
        try:
            if value is None or value == "":
                return Decimal('0')
            return Decimal(str(value))
        except (ValueError, TypeError) as e:
            logger.warning(f"Error converting to Decimal {value}: {e}")
            return Decimal('0')

    def _calculate_data_completeness(self, stats: dict) -> float:
        """Calculate how complete the data is (0.0 to 1.0)."""
        try:
            required_fields = [
                'buyNowPrice', 'numListed', 'volume24h', 'volume7d', 'volumeAll',
                'numMints', 'sales24h', 'sales7d', 'numBids', 'pctListed'
            ]
            
            present_fields = sum(1 for field in required_fields if stats.get(field) is not None)
            return present_fields / len(required_fields)
        except Exception:
            return 0.0

    # ==================== EXISTING METHODS (UNCHANGED) ====================

    async def get_collection_listings(self, collection_id: str, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get individual NFT listings for a collection."""
        try:
            params = {
                'collId': collection_id,
                'sortBy': 'ListingPriceAsc',
                'limit': limit,
                'offset': offset
            }
            
            response = await self._async_get("/mint/collection", params=params)
            
            if not response or not isinstance(response, dict):
                return []
            
            mints = response.get('mints', [])
            formatted_listings = []
            
            for mint_data in mints:
                if isinstance(mint_data, dict):
                    listing = mint_data.get('listing')
                    if not listing:
                        continue
                    
                    price_lamports = listing.get('price', 0)
                    price_sol = float(Decimal(str(price_lamports)) / Decimal('1000000000')) if price_lamports else 0
                    
                    onchain_data = mint_data.get('onchainData', {}).get('data', {})
                    mint_address = mint_data.get('mint', '')
                    
                    formatted_listing = {
                        'listing_id': listing.get('txId', mint_address),
                        'mint_address': mint_address,
                        'collection_address': collection_id,
                        'price': price_sol,
                        'seller_address': listing.get('seller', ''),
                        'listed_at': self._convert_timestamp(listing.get('blockTime')),
                        'expires_at': None,
                        'marketplace': 'tensor',
                        'marketplace_url': f"https://tensor.trade/item/{mint_address}",
                        'listing_type': 'FIXED_PRICE',
                        'status': 'ACTIVE',
                        'nft_name': onchain_data.get('name', ''),
                        'nft_image': mint_data.get('imageUri', ''),
                        'raw_data': mint_data
                    }
                    formatted_listings.append(formatted_listing)
            
            logger.info(f"Tensor: Retrieved {len(formatted_listings)} listings for collection {collection_id}")
            return formatted_listings
            
        except Exception as e:
            logger.error(f"Tensor: Error getting collection listings for {collection_id}: {str(e)}")
            return []

    async def get_collection_activities(self, collection_id: str, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get collection activities - REQUIRED BY SERVICES.PY"""
        try:
            params = {
                'collId': collection_id,
                'sortBy': 'ListingPriceAsc',
                'limit': limit,
                'offset': offset
            }
            
            response = await self._async_get("/collections/tx_history", params=params)
            
            if not response or not isinstance(response, dict):
                return []
            
            transactions = response.get('transactions', [])
            formatted_activities = []
            
            for tx in transactions:
                if isinstance(tx, dict):
                    formatted_activity = {
                        'event_id': tx.get('txId', f"{tx.get('mint', 'unknown')}_{tx.get('blockTime', 0)}"),
                        'event_type': self._map_tensor_activity_type(tx.get('type', '')),
                        'mint_address': tx.get('mint', ''),
                        'collection_address': collection_id,
                        'amount': float(Decimal(str(tx.get('grossAmountLamports', 0))) / Decimal('1000000000')) if tx.get('grossAmountLamports') else 0,
                        'buyer': tx.get('buyer', ''),
                        'seller': tx.get('seller', ''),
                        'timestamp': self._convert_timestamp(tx.get('blockTime')),
                        'marketplace': 'tensor',
                        'signature': tx.get('txId', ''),
                        'raw_data': tx
                    }
                    formatted_activities.append(formatted_activity)
            
            logger.info(f"Tensor: Retrieved {len(formatted_activities)} activities for collection {collection_id}")
            return formatted_activities
            
        except Exception as e:
            logger.error(f"Tensor: Error getting collection activities for {collection_id}: {str(e)}")
            return []

    def _map_tensor_activity_type(self, tensor_type: str) -> str:
        """Map Tensor activity types to services.py expected types."""
        type_mapping = {
            'buy': 'SALE',
            'sell': 'SALE',
            'list': 'LISTING', 
            'delist': 'DELISTING',
            'bid': 'BID',
            'cancel_bid': 'BID_CANCELLED',
            'mint': 'MINT',
            'transfer': 'TRANSFER',
            'burn': 'BURN'
        }
        return type_mapping.get(tensor_type.lower(), tensor_type.upper())

    def _convert_timestamp(self, block_time) -> datetime:
        """Convert block time to datetime object."""
        try:
            if isinstance(block_time, (int, float)):
                return datetime.fromtimestamp(block_time, tz=dt_timezone.utc)
            elif isinstance(block_time, str):
                return datetime.fromisoformat(block_time.replace('Z', '+00:00'))
            else:
                return timezone.now()
        except Exception:
            return timezone.now()
            
    async def _search_collection_by_name(self, collection_name: str, collection_address: str) -> Optional[str]:
        """
        FIXED: Search collections using correct endpoint with query parameter.
        """
        try:
            # FIXED: Add the missing query parameter!
            params = {'query': collection_name}
            search_response = await self._async_get("/collections/search_collections", params=params)
            
            if not search_response or not isinstance(search_response, dict):
                logger.warning(f"Tensor: Invalid search response format")
                return None
            
            collections = search_response.get('collections', [])
            logger.info(f"Tensor: Search returned {len(collections)} collections")
            
            # FIXED: Use correct field names from actual API response
            for i, collection in enumerate(collections):
                if not isinstance(collection, dict):
                    continue
                
                coll_name = collection.get('name', '')
                coll_id = collection.get('collId')  # FIXED: Use 'collId' not 'id' or 'uuid'
                
                if i < 3:  # Log first 3 for debugging
                    logger.info(f"Tensor Collection {i + 1}:")
                    logger.info(f"   Name: '{coll_name}'")
                    logger.info(f"   UUID: {coll_id}")
                
                # Check name match
                if collection_name and coll_name:
                    coll_name_lower = coll_name.lower()
                    collection_name_lower = collection_name.lower()
                    
                    # Exact match
                    if coll_name_lower == collection_name_lower:
                        logger.info(f"Tensor EXACT NAME MATCH: '{coll_name}' -> UUID: {coll_id}")
                        return coll_id
                    
                    # Partial match
                    elif collection_name_lower in coll_name_lower or coll_name_lower in collection_name_lower:
                        logger.info(f"Tensor PARTIAL NAME MATCH: '{coll_name}' -> UUID: {coll_id}")
                        return coll_id
            
            logger.warning(f"Tensor: No name match found for '{collection_name}'")
            return None
            
        except Exception as e:
            logger.error(f"Tensor: Error searching by name '{collection_name}': {e}")
            return None

    async def _verify_collection_uuid(self, uuid: str) -> bool:
        """Verify that a collection UUID is still valid by testing API call."""
        try:
            params = {
                'collId': uuid,
                'limit': 1,
                'sortBy': 'ListingPriceAsc'
            }
            test_response = await self._async_get("/mint/collection", params=params)
            
            if test_response and isinstance(test_response, dict):
                # Check if we got valid data back
                return 'mints' in test_response or 'stats' in test_response
                
            return False
            
        except Exception as e:
            logger.warning(f"Tensor: Error verifying UUID {uuid}: {e}")
            return False

    async def _get_marketplace_identifier(self, collection_address: str):
        """Get MarketplaceIdentifier for Tensor from database."""
        try:
            from indexer.models import MarketplaceIdentifier
            from nft_data.models import NFTCollection
            
            # Get collection object
            collection = await sync_to_async(
                NFTCollection.objects.filter(address=collection_address).first
            )()
            
            if not collection:
                return None
            
            # Get existing marketplace identifier
            marketplace_id = await sync_to_async(
                MarketplaceIdentifier.objects.filter(
                    collection=collection,
                    marketplace='tensor'
                ).first
            )()
            
            return marketplace_id
            
        except Exception as e:
            logger.error(f"Error getting MarketplaceIdentifier: {e}")
            return None

    async def _store_collection_uuid(self, collection_address: str, uuid: str):
        """Store collection UUID in MarketplaceIdentifier and caches."""
        try:
            from indexer.models import MarketplaceIdentifier
            from nft_data.models import NFTCollection
            
            # Get or create collection
            collection, created = await sync_to_async(
                NFTCollection.objects.get_or_create
            )(
                address=collection_address,
                defaults={'name': f'Collection {collection_address[:8]}'}
            )
            
            # Store in MarketplaceIdentifier
            marketplace_id, created = await sync_to_async(
                MarketplaceIdentifier.objects.update_or_create
            )(
                collection=collection,
                marketplace='tensor',
                defaults={
                    'identifier_value': uuid
                }
            )
            
            # Store in caches
            self._collection_cache[collection_address] = uuid
            
            # Store in cache manager
            cache_key = f"tensor_symbol:{collection_address}"
            try:
                await cache_manager.set(cache_key, uuid, CacheType.PROVIDER, collection_address)
            except Exception as e:
                logger.warning(f"Tensor: Error caching UUID via cache manager: {e}")
            
            logger.info(f"Tensor: Stored UUID {uuid} for collection {collection_address}")
            
        except Exception as e:
            logger.error(f"Error storing collection UUID: {e}")

    async def _get_collection_info(self, collection_uuid: str) -> Optional[Dict]:
        """Get collection info using the find_collection endpoint."""
        try:
            logger.info(f"Tensor: Getting collection info for UUID: {collection_uuid}")
            
            # Use find_collection endpoint with the UUID as filter
            collection_response = await self._async_get("/collections/find_collection", params={
                'filter': collection_uuid
            })
            
            if collection_response and isinstance(collection_response, dict):
                logger.info(f"Tensor: find_collection response keys: {list(collection_response.keys())}")
                
                # The response is the collection object directly
                return collection_response
            else:
                logger.warning(f"Tensor: Invalid response format for UUID {collection_uuid}")
            
            logger.warning(f"Tensor: No collection found for UUID {collection_uuid}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting collection info for {collection_uuid}: {e}", exc_info=True)
            return None

    # ==================== NEW METHODS FOR BATCH OPERATIONS ====================

    async def get_batch_collection_data(self, collection_data: List[Dict]) -> Dict[str, Dict]:
        """
        Processes a batch of collections to fetch their stats from Tensor.

        It calls find_collection_symbol to get both the Tensor UUID and the priority
        tier for each collection, then fetches and caches the data accordingly.

        Args:
            collection_data (List[Dict]): A list of dictionaries with collection 'address' and 'name'.

        Returns:
            Dict: A dictionary mapping each collection address to its fetched data.
        """
        results = {}
        for collection_info in collection_data:
            collection_address = collection_info['address']
            collection_name = collection_info.get('name')
            try:
                # Find the UUID for the collection.
                uuid = await self.find_collection_symbol(collection_address, collection_name)

                if uuid:
                    # Get priority from collection object
                    from nft_data.models import NFTCollection
                    collection = await sync_to_async(
                        NFTCollection.objects.filter(address=collection_address).first
                    )()
                    priority = collection.priority_tier if collection else 'INACTIVE'

                    # Pass all required info to the main data fetching method.
                    data = await self.get_collection_data(uuid, collection_address, priority)
                    results[collection_address] = data
                else:
                    logger.warning(f"Tensor: Could not find UUID for {collection_address}, skipping batch entry.")
                    results[collection_address] = {"success": False, "error": "Collection UUID not found"}

                # Add a delay between each collection to respect rate limits.
                await asyncio.sleep(1.1)
            except Exception as e:
                logger.error(f"Tensor: Error in batch processing for {collection_address}: {e}")
                results[collection_address] = {"success": False, "error": str(e)}
        
        return results

    def get_supported_metrics(self) -> List[str]:
        """
        Return list of metrics this provider supports.
        Used by MetricsCalculationService for multi-source aggregation.
        """
        return [
            'floor_price',
            'floor_price_net_fees',
            'highest_bid',
            'price_change_24h',
            'price_change_7d',
            'volume_24h',
            'volume_7d',
            'total_volume',
            'total_supply',
            'listed_count',
            'percent_listed',
            'listing_change_24h',
            'listing_change_7d',
            'sales_count_24h',
            'sales_count_7d',
            'sales_count_all',
            'bid_count',
            'market_cap',
            'average_price_24h',
            'bid_to_listing_ratio',
        ]

    def get_provider_priority(self) -> int:
        """
        Return priority for this provider in multi-source aggregation.
        Higher number = higher priority.
        """
        return 8  # High priority - Tensor has comprehensive data

    def get_provider_info(self) -> Dict:
        """
        Return provider metadata for analytics and debugging.
        """
        return {
            "name": "tensor",
            "display_name": "Tensor",
            "api_base": self.base_url,
            "rate_limit": "1 request/second",
            "data_freshness": "Real-time",
            "supported_metrics": self.get_supported_metrics(),
            "priority": self.get_provider_priority(),
            "strengths": [
                "Comprehensive analytics data",
                "Real-time price changes",
                "Detailed supply metrics",
                "Bid/ask spread data",
                "Market cap calculations"
            ],
            "limitations": [
                "Rate limited",
                "Requires collection UUID mapping",
                "May not have all collections"
            ]
        }

    # ==================== HELPER METHODS FOR MULTI-SOURCE FLOW ====================

    def extract_key_metrics(self, raw_response: Dict) -> Dict:
        """
        Extract key metrics from raw API response.
        Used by MetricsCalculationService for standardized data processing.
        """
        if not raw_response.get("success") or not raw_response.get("stats"):
            return {}
        
        stats = raw_response["stats"]
        
        return {
            "floor_price": stats.get("floor_price", 0),
            "volume_24h": stats.get("volume_24h", 0),
            "listed_count": stats.get("listed_count", 0),
            "total_supply": stats.get("total_supply", 0),
            "price_change_24h": stats.get("price_change_24h", 0),
            "highest_bid": stats.get("highest_bid", 0),
            "bid_count": stats.get("bid_count", 0),
            "percent_listed": stats.get("percent_listed", 0),
            "market_cap": stats.get("market_cap", 0),
            "data_quality": raw_response.get("stats", {}).get("data_completeness_score", 0),
        }

    def get_data_confidence_score(self, raw_response: Dict) -> float:
        """
        Return confidence score (0.0 to 1.0) for this data source.
        Used by MetricsCalculationService for weighted aggregation.
        """
        if not raw_response.get("success"):
            return 0.0
        
        stats = raw_response.get("stats", {})
        
        # Base confidence on data completeness and recent activity
        completeness = stats.get("data_completeness_score", 0)
        has_activity = stats.get("has_recent_activity", False)
        
        confidence = completeness * 0.7
        if has_activity:
            confidence += 0.3
        
        return min(1.0, confidence)
    

    # ==================== WEBSOCKET SUBSCRIPTION STUBS ====================
    
    async def subscribe_logs(self, callback, **kwargs):
        """
        Stub method for WebSocket subscriptions.
        Tensor doesn't provide WebSocket APIs, so this is a no-op.
        """
        logger.warning("Tensor Eden doesn't support WebSocket subscriptions - subscribe_logs is a no-op")
        return False
        
    async def subscribe_to_nft_events(self, callback, **kwargs):
        """
        Stub method for NFT event subscriptions.
        Tensor doesn't provide real-time WebSocket APIs.
        """
        logger.warning("Tensor doesn't support real-time event subscriptions")
        return False