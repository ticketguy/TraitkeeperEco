# indexer/api_provider/magic_eden_provider.py 
import logging
import random
import json
from django.conf import settings
from django.core.cache import cache
import redis
from typing import Dict, List, Optional
import asyncio
from datetime import datetime, timezone as dt_timezone, timedelta
from django.utils import timezone
import pytz
from asgiref.sync import sync_to_async
from core.cache_manager import cache_manager, CacheType
from decimal import Decimal
import re
import aiohttp

logger = logging.getLogger(__name__)

class RateLimiter:
    """Enhanced rate limiter for Magic Eden API."""
    
    def __init__(self):
        self.requests = []
        self.max_requests_per_minute = 15
        self.consecutive_failures = 0
        self.backoff_until = None
        
    async def wait_if_needed(self):
        now = datetime.now()
        
        # Check backoff
        if self.backoff_until and now < self.backoff_until:
            wait_time = (self.backoff_until - now).total_seconds()
            logger.info(f"🕒 ME Rate limiter: waiting {wait_time:.1f}s for backoff")
            await asyncio.sleep(wait_time)
            return
        
        # Clean old requests
        minute_ago = now - timedelta(minutes=1)
        self.requests = [req for req in self.requests if req > minute_ago]
        
        # Check limit
        if len(self.requests) >= self.max_requests_per_minute:
            wait_time = 60 - (now - self.requests[0]).total_seconds()
            logger.info(f"🕒 ME Rate limiter: waiting {wait_time:.1f}s for rate limit")
            await asyncio.sleep(wait_time)
        
        self.requests.append(now)
    
    def on_rate_limit_hit(self, retry_after=None):
        self.consecutive_failures += 1
        backoff_seconds = min(60 * (2 ** (self.consecutive_failures - 1)), 300)
        self.backoff_until = datetime.now() + timedelta(seconds=backoff_seconds)
        logger.warning(f"🚫 ME Rate limit hit, backing off for {backoff_seconds}s")

    def on_success(self):
        self.consecutive_failures = 0
        self.backoff_until = None

class MagicEdenProvider:
    """
    REWRITTEN Magic Eden provider that ONLY uses manually set slug fields.
    No automatic slug generation - must be set manually in admin.
    """
    
    def __init__(self, api_key: str = None, base_url: str = "https://api-mainnet.magiceden.dev/v2"):
        self.api_key = api_key
        self.base_url = (base_url or "https://api-mainnet.magiceden.dev/v2").rstrip('/')
        self.name = "magic_eden"
        self.max_retries = 3
        self.rate_limiter = RateLimiter()
        self.redis_client = redis.from_url(settings.REDIS_URL) if hasattr(settings, 'REDIS_URL') else None
        
        logger.info("=" * 80)
        logger.info("🚀 INITIALIZING MAGIC EDEN PROVIDER v4.0 - SLUG FIELD ONLY")
        logger.info("=" * 80)
        logger.info(f"📍 Base URL: {self.base_url}")
        logger.info(f"🔑 API Key: {'✅ Configured' if self.api_key else '❌ Missing'}")
        logger.info(f"📦 Redis: {'✅ Available' if self.redis_client else '❌ Not configured'}")
        logger.info("📋 Mode: MANUAL SLUG ONLY - No automatic generation")
        logger.info("=" * 80)

    # ==================== SLUG VALIDATION ====================

    def _validate_slug(self, slug: str) -> tuple[bool, str]:
        """
        Validate a Magic Eden slug with detailed logging.
        Returns (is_valid, cleaned_slug_or_error_message)
        """
        logger.debug(f"🔍 SLUG VALIDATION: Input slug: '{slug}'")
        
        if not slug:
            logger.warning(f"❌ SLUG VALIDATION: Empty slug provided")
            return False, "Empty slug"
        
        # Strip whitespace and newlines
        clean_slug = str(slug).strip().replace('\n', '').replace('\r', '')
        logger.debug(f"🔍 SLUG VALIDATION: After cleaning: '{clean_slug}'")
        
        # Check minimum length
        if len(clean_slug) < 2:
            logger.warning(f"❌ SLUG VALIDATION: Slug too short: '{clean_slug}' (length: {len(clean_slug)})")
            return False, f"Slug too short: '{clean_slug}'"
        
        # Check maximum length (ME has limits)
        if len(clean_slug) > 50:
            logger.warning(f"❌ SLUG VALIDATION: Slug too long: '{clean_slug}' (length: {len(clean_slug)})")
            return False, f"Slug too long: '{clean_slug}'"
        
        # Validate format - should be lowercase letters, numbers, underscores
        valid_pattern = re.compile(r'^[a-z0-9_]+$')
        if not valid_pattern.match(clean_slug):
            logger.warning(f"❌ SLUG VALIDATION: Invalid format: '{clean_slug}' (should be lowercase letters, numbers, underscores only)")
            return False, f"Invalid format: '{clean_slug}'"
        
        logger.debug(f"✅ SLUG VALIDATION: Valid slug: '{clean_slug}'")
        return True, clean_slug

    # ==================== COLLECTION LOOKUP ====================

    async def find_collection_symbol(self, collection_address: str, collection_name: str = None) -> Optional[str]:
        """
        Get collection slug ONLY from manually set database field.
        NO automatic generation - must be set manually in admin.
        """
        logger.info("🔥" * 60)
        logger.info(f"🎯 SLUG LOOKUP START: {collection_address}")
        logger.info(f"🎯 Collection Name: '{collection_name}'")
        logger.info("🔥" * 60)
        
        # Validate input
        if not collection_address:
            logger.error(f"❌ SLUG LOOKUP: No collection address provided")
            return None
        
        logger.info(f"📊 SLUG LOOKUP: Looking up collection in database...")
        
        try:
            # Import here to avoid circular imports
            from nft_data.models import NFTCollection
            
            logger.debug(f"📊 SLUG LOOKUP: Querying NFTCollection.objects.filter(address='{collection_address}')")
            
            collection = await sync_to_async(
                NFTCollection.objects.filter(address=collection_address).first
            )()
            
            if not collection:
                logger.error(f"❌ SLUG LOOKUP: Collection not found in database: {collection_address}")
                logger.info("🔥" * 60)
                return None
            
            logger.info(f"✅ SLUG LOOKUP: Found collection in database")
            logger.info(f"📋 Collection Details:")
            logger.info(f"   📝 Name: '{collection.name}'")
            logger.info(f"   🏷️  Display Name: '{collection.display_name}'")
            logger.info(f"   🔗 Slug: '{collection.slug}'")
            logger.info(f"   📍 Address: {collection.address}")
            
            # Check if slug is set
            if not collection.slug:
                logger.error(f"❌ SLUG LOOKUP: Collection has NO SLUG SET!")
                logger.error(f"❌ Please set the 'slug' field manually in the admin for collection:")
                logger.error(f"   📝 Name: '{collection.name}'")
                logger.error(f"   🏷️  Display Name: '{collection.display_name}'")
                logger.error(f"   📍 Address: {collection.address}")
                logger.info("🔥" * 60)
                return None
            
            # Validate the slug
            is_valid, result = self._validate_slug(collection.slug)
            if not is_valid:
                logger.error(f"❌ SLUG LOOKUP: Invalid slug in database: {result}")
                logger.error(f"❌ Please fix the 'slug' field in admin for collection {collection.address}")
                logger.info("🔥" * 60)
                return None
            
            logger.info(f"✅ SLUG LOOKUP: Using valid slug: '{result}'")
            logger.info("🔥" * 60)
            return result
            
        except Exception as e:
            logger.error(f"❌ SLUG LOOKUP: Database error: {str(e)}")
            logger.info("🔥" * 60)
            return None

    # ==================== HTTP CLIENT METHODS ====================

    async def _async_get(self, endpoint: str, params: dict = None, **kwargs) -> Optional[dict]:
        """HTTP GET request with enhanced logging."""
        url = f"{self.base_url}{endpoint}"
        request_id = f"req_{int(datetime.now().timestamp() * 1000) % 100000}"
        
        headers = {
            'accept': 'application/json',
            'User-Agent': 'TraitKeeper/4.0'
        }
        
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        logger.info(f"🌐 [{request_id}] ME API REQUEST START")
        logger.info(f"🌐 [{request_id}] URL: {url}")
        if params:
            logger.info(f"🌐 [{request_id}] Params: {params}")
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"🌐 [{request_id}] Attempt {attempt + 1}/{self.max_retries}")
                await self.rate_limiter.wait_if_needed()
                
                start_time = datetime.now()
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, 
                        headers=headers,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                        **kwargs
                    ) as response:
                        
                        response_time = (datetime.now() - start_time).total_seconds() * 1000
                        logger.info(f"🌐 [{request_id}] HTTP {response.status} ({response_time:.0f}ms)")
                        
                        if response.status == 429:
                            retry_after = response.headers.get('Retry-After')
                            logger.warning(f"🌐 [{request_id}] ⚠️  Rate limited, retry after: {retry_after}")
                            self.rate_limiter.on_rate_limit_hit(retry_after)
                            continue
                        
                        elif response.status >= 500:
                            error_text = await response.text()
                            logger.error(f"🌐 [{request_id}] ❌ Server error {response.status}: {error_text[:200]}")
                            if attempt < self.max_retries - 1:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            return None
                        
                        elif response.status == 404:
                            logger.warning(f"🌐 [{request_id}] 🔍 Not found on Magic Eden: {endpoint}")
                            return None
                        
                        elif response.status == 401:
                            logger.error(f"🌐 [{request_id}] 🔐 Authentication failed: {endpoint}")
                            return None
                        
                        elif response.status != 200:
                            error_text = await response.text()
                            logger.error(f"🌐 [{request_id}] ❌ HTTP error {response.status}: {error_text[:200]}")
                            return None
                        
                        # Success
                        self.rate_limiter.on_success()
                        result = await response.json()
                        
                        logger.info(f"🌐 [{request_id}] ✅ SUCCESS - Response received")
                        self._log_response_structure(request_id, endpoint, result)
                        return result
                        
            except Exception as e:
                logger.error(f"🌐 [{request_id}] ❌ Request exception (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.error(f"🌐 [{request_id}] ❌ Request failed after {self.max_retries} attempts")
                return None
        
        return None

    def _log_response_structure(self, request_id: str, endpoint: str, result):
        """Log detailed response structure for debugging."""
        if isinstance(result, list):
            logger.info(f"🌐 [{request_id}] 📋 Response: Array with {len(result)} items")
            if result and len(result) > 0:
                first_item = result[0]
                if isinstance(first_item, dict):
                    logger.info(f"🌐 [{request_id}] 📋 First item keys: {list(first_item.keys())}")
                
        elif isinstance(result, dict):
            logger.info(f"🌐 [{request_id}] 📄 Response: Object with {len(result)} keys")
            logger.info(f"🌐 [{request_id}] 📄 Response keys: {list(result.keys())}")
            
            if 'stats' in endpoint:
                self._log_stats_response_details(request_id, result)

    def _log_stats_response_details(self, request_id: str, result: dict):
        """Log detailed stats response analysis."""
        logger.info(f"📊 [{request_id}] STATS RESPONSE ANALYSIS:")
        
        floor_price = result.get("floorPrice", 0)
        logger.info(f"📊 [{request_id}]   💰 Floor Price (lamports): {floor_price}")
        if floor_price:
            floor_sol = float(Decimal(str(floor_price)) / Decimal('1000000000'))
            logger.info(f"📊 [{request_id}]   💰 Floor Price (SOL): {floor_sol:.6f}")
        
        volume_all = result.get("volumeAll", 0)
        logger.info(f"📊 [{request_id}]   📈 Volume All (lamports): {volume_all}")
        if volume_all:
            volume_sol = float(Decimal(str(volume_all)) / Decimal('1000000000'))
            logger.info(f"📊 [{request_id}]   📈 Volume All (SOL): {volume_sol:.6f}")
        
        listed_count = result.get("listedCount", 0)
        logger.info(f"📊 [{request_id}]   📋 Listed Count: {listed_count}")

    # ==================== COLLECTION DATA METHODS ====================

    async def get_collection_data(self, collection_slug: str, collection_address: str, priority_tier: str) -> Dict:
        """
        Fetches and processes statistics for a single collection from Magic Eden.

        This method validates the input slug, checks the central cache, fetches data
        from the API if necessary, parses the raw response into a clean format, and
        caches the final result with a TTL based on the collection's priority.

        Args:
            collection_slug (str): The Magic Eden specific slug for the collection.
            collection_address (str): The on-chain address of the collection.
            priority_tier (str): The priority tier ('VIP', 'ACTIVE', 'INACTIVE') of the collection.

        Returns:
            Dict: A dictionary containing the processing status, stats, and raw data.
        """
        # Step 1: Validate the provided slug to ensure it's in a correct format.
        is_valid, clean_slug = self._validate_slug(collection_slug)
        if not is_valid:
            return {"success": False, "error": f"Invalid slug: {clean_slug}"}

        # Step 2: Check the central cache for existing data to avoid redundant API calls.
        cache_key = f"magic_eden:collection:{clean_slug}"
        cached_data = await cache_manager.get(cache_key)
        if cached_data:
            logger.info(f"💾 ✅ Cache HIT for ME slug '{clean_slug}'")
            return cached_data

        # Step 3: If not cached, prepare the result structure and fetch from the API.
        result = {"success": False, "stats": {}, "raw_data": {}, "error": None}
        stats_response = await self._async_get(f"/collections/{clean_slug}/stats")
        
        if stats_response:
            # Step 4: If the API call is successful, parse the raw data.
            raw_floor_price = stats_response.get("floorPrice", 0)
            raw_volume_all = stats_response.get("volumeAll", 0)
            raw_listed_count = stats_response.get("listedCount", 0)
            raw_avg_price_24h = stats_response.get("avgPrice24hr", 0)

            # Convert lamport values to SOL for consistency.
            floor_price = float(Decimal(str(raw_floor_price)) / Decimal('1000000000')) if raw_floor_price else 0.0
            volume_all = float(Decimal(str(raw_volume_all)) / Decimal('1000000000')) if raw_volume_all else 0.0
            avg_price_24h = float(Decimal(str(raw_avg_price_24h)) / Decimal('1000000000')) if raw_avg_price_24h else 0.0

            # Assemble the final, clean statistics object.
            final_stats = {
                "floor_price": floor_price,
                "listed_count": int(raw_listed_count),
                "total_volume": volume_all,
                "volume_24h": 0.0,  # Note: ME stats API does not provide this directly
                "avg_price_24h": avg_price_24h,
                "symbol": stats_response.get("symbol", clean_slug)
            }
            
            result["stats"] = final_stats
            result["success"] = True
            result["raw_data"] = stats_response

            # Step 5: Cache the successful result with a priority-aware TTL.
            await cache_manager.set(cache_key, result, CacheType.PROVIDER, collection_address)
            ttl = cache_manager.get_ttl(CacheType.PROVIDER, priority_tier)
            logger.info(f"💾 Cached ME data for '{clean_slug}' with priority '{priority_tier}' (TTL: {ttl}s)")
        else:
            result["error"] = f"Collection '{clean_slug}' not found on Magic Eden"

        return result

    # ==================== BATCH PROCESSING ====================

    async def get_batch_collection_data(self, collections: List[Dict]) -> Dict[str, Dict]:
        """
        Processes a batch of collections to fetch their stats from Magic Eden.

        It retrieves the manually set slug and priority for each collection from the
        database and then calls a helper to fetch and cache the data.

        Args:
            collections (List[Dict]): A list of dictionaries, each containing a collection 'address'.

        Returns:
            Dict: A dictionary mapping each collection address to its fetched data.
        """
        logger.info(f"🚀 ME BATCH PROCESSING START: {len(collections)} collections")
        results = {}
        
        for collection_info in collections:
            address = collection_info['address']
            try:
                # Retrieve the collection's database record to get its slug and priority.
                from nft_data.models import NFTCollection
                db_collection = await sync_to_async(
                    NFTCollection.objects.filter(address=address).first
                )()

                if not db_collection or not db_collection.slug:
                    logger.error(f"❌ No slug set for collection {address}")
                    results[address] = {"success": False, "error": "No slug set in database"}
                    continue
                
                # Get the priority and slug to pass down the call chain.
                priority = db_collection.priority_tier
                slug = db_collection.slug
                
                # Use the helper method to fetch data for this specific collection.
                data = await self._fetch_collection_with_address(address, slug, priority)
                results[address] = data

            except Exception as e:
                logger.error(f"❌ Error processing ME collection {address}: {e}")
                results[address] = {"success": False, "error": str(e)}
        
        logger.info("🏁 ME BATCH PROCESSING COMPLETE!")
        return results

    
    async def _fetch_collection_with_address(self, address: str, slug: str, priority_tier: str) -> dict:
        """
        A helper method that calls get_collection_data and formats the result.

        This acts as a bridge during batch processing to ensure the original on-chain
        address is included in the final returned data.

        Args:
            address (str): The on-chain address of the collection.
            slug (str): The Magic Eden slug for the collection.
            priority_tier (str): The priority tier of the collection.

        Returns:
            dict: The fetched data, augmented with the collection address and slug.
        """
        try:
            # Pass all required info to the main data fetching method.
            data = await self.get_collection_data(slug, address, priority_tier)
            
            # Add context to the returned dictionary.
            data['collection_address'] = address
            data['magic_eden_slug'] = slug
            return data
        except Exception as e:
            logger.error(f"❌ Error in _fetch_collection_with_address for {address}: {e}")
            return {"success": False, "error": str(e)}

    # ==================== UTILITY METHODS ====================

    async def check_availability(self) -> bool:
        """Check if the Magic Eden API is available."""
        try:
            logger.info(f"🔍 Checking Magic Eden API availability...")
            
            # Test with a known collection slug
            response = await self._async_get("/collections/okay_bears/stats")
            is_available = bool(response and isinstance(response, dict))
            
            logger.info(f"🔍 Magic Eden API Available: {'✅ YES' if is_available else '❌ NO'}")
            return is_available
            
        except Exception as e:
            logger.error(f"🔍 Error checking availability: {str(e)}")
            return False

    async def clear_cache(self, collection_address: str = None) -> bool:
        """Clear cache for specific collection or all collections using cache manager."""
        try:
            if collection_address:
                logger.info(f"💾 Clearing cache for collection {collection_address} using cache manager")
                
                # Use cache manager to clear Magic Eden provider cache
                invalidated_count = await cache_manager.invalidate_by_dependency('provider_data', collection_address)
                
                # Also clear specific ME cache keys
                me_cache_key = f"me_symbol:{collection_address}"
                magic_eden_cache_key = f"magic_eden:collection:{collection_address}"
                
                await cache_manager.delete(me_cache_key)
                await cache_manager.delete(magic_eden_cache_key)
                
                logger.info(f"💾 Cache manager cleared {invalidated_count} dependency keys plus direct ME keys for {collection_address}")
                return True
                
            else:
                logger.info(f"💾 Clearing ALL Magic Eden caches using cache manager...")
                
                # Clear all Magic Eden related patterns
                if cache_manager.redis_client:
                    patterns_to_clear = ["me_symbol:*", "magic_eden:*"]
                    total_cleared = 0
                    
                    for pattern in patterns_to_clear:
                        cleared_count = await cache_manager._delete_pattern(pattern[:-1])  # Remove * for _delete_pattern
                        total_cleared += cleared_count
                        logger.info(f"💾 Cleared {cleared_count} keys matching '{pattern}'")
                    
                    logger.info(f"💾 Total cleared: {total_cleared} Magic Eden cache keys")
                    
                # Also clear Django cache
                cache.clear()
                logger.info(f"💾 Cleared Django cache")
                
                return True
                
        except Exception as e:
            logger.error(f"💾 Error clearing cache: {e}")
            return False

    async def get_me_url_for_collection(self, collection_address: str) -> Optional[str]:
        """Get the Magic Eden marketplace URL for a collection."""
        try:
            from nft_data.models import NFTCollection
            
            collection = await sync_to_async(
                NFTCollection.objects.filter(address=collection_address).first
            )()
            
            if collection and collection.slug:
                url = f"https://magiceden.io/marketplace/{collection.slug}"
                logger.info(f"🔗 ME URL for {collection_address}: {url}")
                return url
            else:
                logger.warning(f"🔗 No slug found for collection {collection_address}")
                return None
            
        except Exception as e:
            logger.error(f"🔗 Error getting ME URL for {collection_address}: {str(e)}")
            return None

    # ==================== ACTIVITIES AND LISTINGS ====================

    async def get_collection_activities(self, collection_slug: str, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get collection activities using manually set slug."""
        logger.info(f"🏃 Getting activities for slug: '{collection_slug}'")
        
        # Validate slug
        is_valid, validated_slug_or_error = self._validate_slug(collection_slug)
        if not is_valid:
            logger.error(f"❌ Invalid slug for activities: {validated_slug_or_error}")
            return []
        
        clean_slug = validated_slug_or_error
        logger.info(f"🏃 Using validated slug: '{clean_slug}'")
        
        try:
            params = {
                'offset': offset, 
                'limit': min(limit, 100)  # ME API limit
            }
            
            logger.info(f"🏃 Fetching activities with params: {params}")
            activities_response = await self._async_get(f"/collections/{clean_slug}/activities", params=params)
            
            if not activities_response:
                logger.warning(f"🏃 No activities response for '{clean_slug}'")
                return []
            
            logger.info(f"🏃 Processing {len(activities_response)} raw activities")
            
            formatted_activities = []
            for i, activity in enumerate(activities_response):
                if isinstance(activity, dict):
                    try:
                        me_type = activity.get('type', '')
                        mapped_type = self._map_me_activity_type(me_type)
                        
                        # Convert price
                        raw_price = activity.get('price', 0)
                        price_sol = float(Decimal(str(raw_price)) / Decimal('1000000000')) if raw_price else 0
                        
                        formatted_activity = {
                            'event_id': activity.get('signature', f"{activity.get('mintAddress', 'unknown')}_{activity.get('blockTime', 0)}"),
                            'event_type': mapped_type,
                            'mint_address': activity.get('mintAddress', ''),
                            'collection_address': activity.get('collectionAddress', ''),
                            'amount': price_sol,
                            'buyer': activity.get('buyer', ''),
                            'seller': activity.get('seller', ''),
                            'timestamp': self._convert_timestamp(activity.get('blockTime')),
                            'marketplace': 'magic_eden',
                            'signature': activity.get('signature', ''),
                            'raw_data': activity
                        }
                        formatted_activities.append(formatted_activity)
                        
                        logger.debug(f"🏃 Activity {i+1}: {mapped_type} - {price_sol:.6f} SOL")
                        
                    except Exception as e:
                        logger.warning(f"🏃 Error processing activity #{i}: {e}")
                        continue
            
            logger.info(f"🏃 ✅ Retrieved {len(formatted_activities)} formatted activities")
            return formatted_activities
            
        except Exception as e:
            logger.error(f"🏃 ❌ Error getting activities for '{collection_slug}': {str(e)}")
            return []

    async def get_collection_listings(self, collection_slug: str, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get individual NFT listings for a collection using manually set slug."""
        logger.info(f"📋 Getting listings for slug: '{collection_slug}'")
        
        # Validate slug
        is_valid, validated_slug_or_error = self._validate_slug(collection_slug)
        if not is_valid:
            logger.error(f"❌ Invalid slug for listings: {validated_slug_or_error}")
            return []
        
        clean_slug = validated_slug_or_error
        logger.info(f"📋 Using validated slug: '{clean_slug}'")
        
        try:
            params = {
                'offset': offset, 
                'limit': min(limit, 100),  # ME API limit
                'sortBy': 'price_asc'
            }
            
            logger.info(f"📋 Fetching listings with params: {params}")
            response = await self._async_get(f"/collections/{clean_slug}/listings", params=params)
            
            if not response or not isinstance(response, list):
                logger.warning(f"📋 No listings response for '{clean_slug}'")
                return []
            
            logger.info(f"📋 Processing {len(response)} raw listings")
            
            formatted_listings = []
            for i, listing in enumerate(response):
                if isinstance(listing, dict):
                    try:
                        price_lamports = listing.get('price', 0)
                        price_sol = float(Decimal(str(price_lamports)) / Decimal('1000000000')) if price_lamports else 0
                        
                        formatted_listing = {
                            'listing_id': listing.get('pdaAddress', listing.get('signature', '')),
                            'mint_address': listing.get('mintAddress', ''),
                            'collection_address': clean_slug,
                            'price': price_sol,
                            'seller_address': listing.get('seller', ''),
                            'listed_at': self._convert_timestamp(listing.get('listedAt')),
                            'expires_at': self._convert_timestamp(listing.get('expiresAt')),
                            'marketplace': 'magic_eden',
                            'marketplace_url': f"https://magiceden.io/item-details/{listing.get('mintAddress', '')}",
                            'listing_type': 'FIXED_PRICE',
                            'status': 'ACTIVE',
                            'raw_data': listing
                        }
                        formatted_listings.append(formatted_listing)
                        
                        logger.debug(f"📋 Listing {i+1}: {price_sol:.6f} SOL")
                        
                    except Exception as e:
                        logger.warning(f"📋 Error processing listing #{i}: {e}")
                        continue
            
            logger.info(f"📋 ✅ Retrieved {len(formatted_listings)} formatted listings")
            return formatted_listings
            
        except Exception as e:
            logger.error(f"📋 ❌ Error getting listings for '{collection_slug}': {str(e)}")
            return []

    def _map_me_activity_type(self, me_type: str) -> str:
        """Map Magic Eden activity types to standard types."""
        type_mapping = {
            'buyNow': 'SALE',
            'acceptBid': 'SALE', 
            'list': 'LISTING',
            'delist': 'DELISTING',
            'bid': 'BID',
            'cancelBid': 'BID_CANCELLED',
            'mint': 'MINT',
            'transfer': 'TRANSFER',
            'burn': 'BURN'
        }
        
        mapped_type = type_mapping.get(me_type.lower(), me_type.upper())
        
        if me_type.lower() not in type_mapping:
            logger.warning(f"🏃 ⚠️ Unknown activity type '{me_type}', using raw value '{mapped_type}'")
        
        return mapped_type

    def _convert_timestamp(self, block_time) -> datetime:
        """Convert block time to datetime object."""
        try:
            if isinstance(block_time, (int, float)):
                return datetime.fromtimestamp(block_time, tz=dt_timezone.utc)
            elif isinstance(block_time, str):
                return datetime.fromisoformat(block_time.replace('Z', '+00:00'))
            else:
                return timezone.now()
        except Exception as e:
            logger.debug(f"⏰ Timestamp conversion error for '{block_time}': {e}")
            return timezone.now()

    # ==================== DEPRECATED/LEGACY METHODS ====================

    async def get_all_collections(self, force_refresh=False):
        """DEPRECATED: Collections API no longer used."""
        logger.warning("❌ get_all_collections() is DEPRECATED - using manual slug approach")
        return {"deprecated": True, "message": "Using manual slug approach"}

    async def find_collection_symbol_v2(self, collection_address: str, collection_name: str, collections_data: dict) -> Optional[str]:
        """DEPRECATED: Use find_collection_symbol() instead."""
        logger.warning("❌ find_collection_symbol_v2() is DEPRECATED - using find_collection_symbol()")
        return await self.find_collection_symbol(collection_address, collection_name)

    async def get_collection_by_slug(self, collection_slug: str) -> Optional[str]:
        """DEPRECATED: Use get_collection_data() instead."""
        logger.warning("❌ get_collection_by_slug() is DEPRECATED - use get_collection_data()")
        is_valid, result = self._validate_slug(collection_slug)
        return result if is_valid else None

    # ==================== WEBSOCKET SUBSCRIPTION STUBS ====================
    
    async def subscribe_logs(self, callback, **kwargs):
        """
        Stub method for WebSocket subscriptions.
        Magic Eden doesn't provide WebSocket APIs, so this is a no-op.
        """
        logger.warning("Magic Eden doesn't support WebSocket subscriptions - subscribe_logs is a no-op")
        return False
        
    async def subscribe_to_nft_events(self, callback, **kwargs):
        """
        Stub method for NFT event subscriptions.
        Magic Eden doesn't provide real-time WebSocket APIs.
        """
        logger.warning("Magic Eden doesn't support real-time event subscriptions")
        return False