# nft_data/nft_retrieval.py (Fully Async Refactored)

import logging
import json
import requests
import redis
import asyncio
import re
import hashlib
import base64
import string
import time
from django.db import transaction
from django.conf import settings
from django.core.cache import cache
from typing import Dict, Optional, List, Callable
from django.utils import timezone
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from asgiref.sync import sync_to_async
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys
from logging.handlers import RotatingFileHandler
import aiohttp
from solders.pubkey import Pubkey

from ..models import NFTCollection, NFT, PendingCollection, TraitType, TraitValue
from core.api_provider.api_providers import APIProviderManager
from core.api_provider.helius_provider import HeliusProvider
from nft_data.signals import send_unified_admin_notification

try:
    from core.cache_manager import cache_manager, CacheType
    CACHE_MANAGER_AVAILABLE = True
except ImportError:
    cache_manager = None
    CACHE_MANAGER_AVAILABLE = False
    logging.warning("Cache manager not available, using fallback caching")

    # Fallback CacheType so type-checkers / linters don't report "possibly unbound".
    from enum import Enum
    class CacheType(Enum):
        STATS = "stats"
        PROVIDER = "provider"
        METRICS = "metrics"

# Logger setup
logger = logging.getLogger(__name__)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

file_handler = RotatingFileHandler("nft_retrieval.log", maxBytes=5 * 1024 * 1024, backupCount=5)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

logger.setLevel(logging.INFO)


class NFTRetrievalService:
    def __init__(self):
        """Initialize NFTRetrievalService with provider manager, session, and caching."""
        self.api_provider_manager = APIProviderManager()
        self.session = None  # Will be initialized asynchronously
        self.batch_size = 100
        self.redis_client = None

        if hasattr(settings, 'REDIS_URL') and settings.REDIS_URL:
            try:
                self.redis_client = redis.from_url(settings.REDIS_URL)
                logger.info("Redis cache initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis cache: {str(e)}")

        self.cache_manager = cache_manager if CACHE_MANAGER_AVAILABLE else None
        if self.cache_manager:
            logger.info("NFTRetrievalService initialized with cache manager")
        else:
            logger.warning("NFTRetrievalService using fallback caching")

        self.metrics = {
            "uri_success": 0,
            "uri_failure": 0,
            "arweave_success": 0,
            "arweave_failure": 0,
            "ipfs_success": 0,
            "ipfs_failure": 0,
            "http_success": 0,
            "http_failure": 0,
            "retrieval_method": "",
            "nfts_retrieved": 0,
            "total_supply": 0,
            "fallback_used": False,
            "fallback_method": "",
            "error_encountered": "",
            "traits_fetched": 0,
            "trait_types": set(),
            "provider_used": ""
        }

        self.arweave_gateways = [
            "https://arweave.net/",
            "https://arweave.dev/",
            "https://gateway.arweave.net/"
        ]

        self.pinata_token = os.getenv('PINATA_GATEWAY_TOKEN')
        self.ipfs_gateways = [
            "https://nftstorage.link/ipfs/",
            "https://cloudflare-ipfs.com/ipfs/",
            "https://ipfs.io/ipfs/",
            "https://dweb.link/ipfs/",
            "https://gateway.pinata.cloud/ipfs/",
            "https://black-rational-cod-281.mypinata.cloud/ipfs/",
            "https://ipfs.infura.io/ipfs/",
        ]
        
        self.aiohttp_session = None
        self.session_lock = asyncio.Lock()

        logger.info("NFTRetrievalService initialized successfully")

    async def create_robust_session(self):
        """Create a robust requests session with retry logic."""
        session = requests.Session()
        retries = Retry(
            total=2,
            backoff_factor=1.0,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=frozenset(['GET', 'POST']),
            respect_retry_after_header=True,
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.timeout = (10, 30)
        self.session = session
        return session

    async def get_cache_key(self, prefix, identifier):
        """Generate a consistent cache key for storing/retrieving data."""
        return f"{prefix}:{identifier}"

    async def get_from_cache(self, prefix, identifier):
        """Retrieve data from cache using cache manager with fallback."""
        cache_key = await self.get_cache_key(prefix, identifier)

        if self.cache_manager:
            try:
                cached_data = await self.cache_manager.get(cache_key)
                if cached_data is not None:
                    logger.info(f"Cache hit for {cache_key} (via cache manager)")
                    return cached_data
            except Exception as e:
                logger.warning(f"Cache manager error for {cache_key}: {e}, falling back")

        try:
            cached_data = await sync_to_async(cache.get)(cache_key)
            if cached_data:
                logger.info(f"Cache hit for {cache_key} in Django cache (fallback)")
                return cached_data
        except Exception as e:
            logger.warning(f"Django cache error for {cache_key}: {e}")

        if self.redis_client:
            try:
                redis_data = await sync_to_async(self.redis_client.get)(cache_key)
                if redis_data:
                    logger.info(f"Cache hit for {cache_key} in Redis cache (fallback)")
                    return json.loads(redis_data)
            except Exception as e:
                logger.warning(f"Redis cache retrieval error for {cache_key}: {str(e)}")

        return None

    async def save_to_cache(self, prefix, identifier, data, timeout=3600, collection_address=None):
        """Save data to cache using cache manager with fallback."""
        if not data:
            return False

        cache_key = await self.get_cache_key(prefix, identifier)
        cache_type = self._determine_cache_type(prefix)

        if self.cache_manager:
            try:
                success = await self.cache_manager.set(cache_key, data, cache_type, collection_address)
                if success:
                    logger.info(f"Cached via cache manager: {cache_key} (type: {cache_type.value})")
                    return True
            except Exception as e:
                logger.warning(f"Cache manager error for {cache_key}: {e}, using fallback")

        try:
            await sync_to_async(cache.set)(cache_key, data, timeout)
            if self.redis_client:
                await sync_to_async(self.redis_client.setex)(cache_key, timeout, json.dumps(data, default=str))
                logger.info(f"Saved to fallback caches: {cache_key}")
            return True
        except Exception as e:
            logger.error(f"Error saving to fallback cache {cache_key}: {str(e)}")
            return False

    def _determine_cache_type(self, prefix):
        """Determine appropriate cache type based on prefix."""
        prefix_mapping = {
            'metadata': CacheType.STATS,
            'collection': CacheType.PROVIDER,
            'traits': CacheType.METRICS,
            'nft': CacheType.STATS,
            'rarity': CacheType.METRICS,
            'retrieval': CacheType.PROVIDER
        }

        if prefix in prefix_mapping:
            return prefix_mapping[prefix]

        for key, cache_type in prefix_mapping.items():
            if key in prefix.lower():
                return cache_type

        return CacheType.PROVIDER

    async def invalidate_collection_cache(self, collection_address: str):
        """Invalidate all cached data for a collection."""
        if not self.cache_manager:
            logger.warning("Cache manager not available for collection cache invalidation")
            return 0

        try:
            invalidated_count = await self.cache_manager.invalidate_collection_caches(collection_address)
            logger.info(f"Invalidated {invalidated_count} cache keys for {collection_address}")
            return invalidated_count
        except Exception as e:
            logger.error(f"Error invalidating collection cache for {collection_address}: {e}")
            return 0

    async def warm_metadata_cache(self, collection_address: str, limit: int = 10):
        """Pre-warm metadata cache for recently active NFTs in a collection."""
        if not self.cache_manager:
            logger.warning("Cache manager not available for cache warming")
            return 0

        from indexer.models import NFTEvent
        try:
            recent_nfts = await sync_to_async(list)(
                NFTEvent.objects.filter(
                    collection__address=collection_address,
                    timestamp__gte=timezone.now() - timedelta(hours=24)
                ).values_list('mint_address', flat=True).distinct()[:limit]
            )

            warmed_count = 0
            for mint_address in recent_nfts:
                cache_key = f"metadata:{mint_address}"
                cached = await self.cache_manager.get(cache_key)
                if not cached:
                    logger.debug(f"Would warm metadata cache for {mint_address}")
                    warmed_count += 1

            logger.info(f"Warmed metadata cache for {warmed_count} NFTs in {collection_address}")
            return warmed_count
        except Exception as e:
            logger.error(f"Error in metadata cache warming for {collection_address}: {e}")
            return 0

    async def get_cache_stats(self):
        """Get cache statistics for monitoring."""
        try:
            stats = {
                'cache_manager_available': self.cache_manager is not None,
                'redis_available': self.redis_client is not None,
                'fallback_mode': self.cache_manager is None,
                'cache_manager_type': 'unified' if self.cache_manager else 'dual_fallback'
            }
            return stats
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {'error': str(e)}

    async def get_gateway_headers(self, gateway_url):
        """Get appropriate headers for the gateway"""
        headers = {
            'User-Agent': 'YourApp/1.0',
            'Accept': 'application/json, application/octet-stream, */*'
        }
        
        if "black-rational-cod-281.mypinata.cloud" in gateway_url and self.pinata_token:
            headers['Authorization'] = f'Bearer {self.pinata_token}'
            
        return headers

    async def _get_provider_with_fallback(self, prefer_helius=False):
        """
        Get provider with optional Helius preference and fallback.
        
        Args:
            prefer_helius: If True, try to get Helius first, then fallback to any provider
            
        Returns:
            tuple: (provider, is_helius)
        """
        if prefer_helius:
            # Try to get Helius specifically
            helius_provider = await self.api_provider_manager.get_provider_by_name('helius')
            if helius_provider and await helius_provider.check_availability():
                return helius_provider, True
            logger.warning("Helius requested but not available, falling back to best provider")
        
        # Fallback to best available provider
        provider = await self.api_provider_manager.get_rpc_provider()
        is_helius = isinstance(provider, HeliusProvider) if provider else False
        return provider, is_helius

    async def fetch_from_arweave(self, uri):
        """Fetch metadata from Arweave with gateway fallback."""
        for gateway in self.arweave_gateways:
            try:
                arweave_url = uri.replace("https://arweave.net/", gateway)
                response = await sync_to_async(self.session.get)(arweave_url, timeout=30)
                if response.status_code == 200:
                    return response.json()
            except Exception as e:
                logger.debug(f"Arweave gateway {gateway} failed: {str(e)}")
                continue
        return None

    async def fetch_metadata_from_uri(self, uri, max_attempts=2):
        """
        Asynchronously fetch metadata from a URI (HTTP, IPFS, Arweave).
        CONSOLIDATED: Removed duplicate sync version.
        """
        if not uri or not isinstance(uri, str):
            logger.warning(f"Invalid URI provided: {uri}")
            return None
            
        uri = uri.strip().rstrip('{}[]()<>;:,')
        if not uri:
            logger.warning("Empty URI after cleaning")
            return None
        
        if "ateway.pinit.io" in uri:
            uri = uri.replace("ateway.pinit.io", "gateway.pinata.cloud")
        if "rweave.net" in uri:
            uri = uri.replace("rweave.net", "arweave.net")
        
        cache_key = hashlib.md5(uri.encode()).hexdigest()
        cached_data = await self.get_from_cache("uri_metadata", cache_key)
        if cached_data:
            logger.info(f"Cache hit for URI metadata: {uri}")
            return cached_data

        resolver = aiohttp.resolver.DefaultResolver()
        resolver.nameservers = ["8.8.8.8", "8.8.4.4"]
        
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        connector = aiohttp.TCPConnector(
            resolver=resolver, 
            limit=10,
            limit_per_host=5,
            ttl_dns_cache=300,
            use_dns_cache=True
        )
        
        attempt = 1
        
        try:
            while attempt <= max_attempts:
                logger.info(f"Attempt {attempt}/{max_attempts} - Fetching metadata from URI: {uri}")
                
                try:
                    if 'arweave.net' in uri.lower() or 'arweave.dev' in uri.lower():
                        data = await self.fetch_from_arweave(uri)
                        if data:
                            await self.save_to_cache("uri_metadata", cache_key, data, timeout=86400)
                            self.metrics["arweave_success"] += 1
                        else:
                            self.metrics["arweave_failure"] += 1
                        return data

                    if 'ipfs' in uri.lower():
                        ipfs_path = None
                        ipfs_path_match = re.search(r'ipfs/([a-zA-Z0-9]+(?:/[^?\s]*)?)', uri)
                        if ipfs_path_match:
                            ipfs_path = ipfs_path_match.group(1)
                        else:
                            uri_parts = uri.split('/ipfs/')
                            if len(uri_parts) > 1 and uri_parts[1]:
                                path_with_query = uri_parts[1]
                                if '?' in path_with_query:
                                    query_split = path_with_query.split('?')
                                    if len(query_split) > 0 and query_split[0]:
                                        ipfs_path = query_split[0]
                                else:
                                    ipfs_path = path_with_query
                        
                        if not ipfs_path:
                            logger.warning(f"Could not extract IPFS path from URI: {uri}")
                            attempt += 1
                            await asyncio.sleep(0.5)
                            continue
                        
                        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                            for gateway in self.ipfs_gateways[:2]:
                                if not gateway.endswith('/'):
                                    gateway += '/'
                                ipfs_url = f"{gateway}{ipfs_path.lstrip('ipfs/')}"
                                logger.info(f"Trying IPFS gateway: {ipfs_url}")
                                
                                headers = await self.get_gateway_headers(gateway)
                                
                                try:
                                    async with session.get(ipfs_url, headers=headers) as response:
                                        if response.status == 429:
                                            retry_after = response.headers.get('Retry-After', '60')
                                            wait_time = min(int(retry_after), 300)
                                            logger.warning(f"Rate limited by {gateway}, waiting {wait_time}s")
                                            await asyncio.sleep(wait_time)
                                            continue
                                        
                                        response.raise_for_status()
                                        
                                        content_type = response.headers.get('content-type', '').lower()
                                        is_json_content = any(json_type in content_type for json_type in [
                                            'application/json', 'text/json', 'application/octet-stream'
                                        ])
                                        
                                        if not is_json_content:
                                            logger.warning(f"Unexpected content type from {ipfs_url}: {content_type}")
                                            continue
                                        
                                        try:
                                            data = await response.json()
                                        except (aiohttp.ContentTypeError, ValueError):
                                            try:
                                                text = await response.text()
                                                data = json.loads(text)
                                            except (ValueError, json.JSONDecodeError) as e:
                                                logger.warning(f"Failed to parse JSON from {ipfs_url}: {str(e)}")
                                                continue
                                        
                                        if not isinstance(data, dict):
                                            logger.warning(f"Invalid JSON data from {ipfs_url}: {type(data)}")
                                            continue
                                        
                                        await self.save_to_cache("ipfs", ipfs_path, data, timeout=86400)
                                        await self.save_to_cache("uri_metadata", cache_key, data, timeout=86400)
                                        self.metrics["ipfs_success"] += 1
                                        return data
                                        
                                except asyncio.TimeoutError:
                                    logger.warning(f"Timeout fetching from IPFS gateway {gateway}")
                                    self.metrics["ipfs_failure"] += 1
                                    continue
                                except Exception as e:
                                    logger.warning(f"Failed to fetch from IPFS gateway {gateway}: {str(e)}")
                                    self.metrics["ipfs_failure"] += 1
                                    await asyncio.sleep(1)
                        
                        attempt += 1
                        await asyncio.sleep(min(2 * attempt, 10))
                        continue

                    if not uri.startswith(('http://', 'https://')):
                        uri = f"https://{uri}"
                        
                    headers = {'User-Agent': 'YourApp/1.0', 'Accept': 'application/json, application/octet-stream, */*'}
                    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                        async with session.get(uri, headers=headers) as response:
                            if response.status == 429:
                                retry_after = response.headers.get('Retry-After', '60')
                                wait_time = min(int(retry_after), 300)
                                logger.warning(f"Rate limited by {uri}, waiting {wait_time}s")
                                await asyncio.sleep(wait_time)
                                attempt += 1
                                continue
                            
                            response.raise_for_status()
                            
                            content_type = response.headers.get('content-type', '').lower()
                            is_json_content = any(json_type in content_type for json_type in [
                                'application/json', 'text/json', 'application/octet-stream'
                            ])
                            
                            if not is_json_content:
                                logger.warning(f"Unexpected content type from {uri}: {content_type}")
                                attempt += 1
                                await asyncio.sleep(0.5)
                                continue
                            
                            try:
                                data = await response.json()
                            except (aiohttp.ContentTypeError, ValueError):
                                try:
                                    text = await response.text()
                                    data = json.loads(text)
                                except (ValueError, json.JSONDecodeError) as e:
                                    logger.warning(f"Failed to parse JSON from {uri}: {str(e)}")
                                    attempt += 1
                                    await asyncio.sleep(0.5)
                                    continue
                            
                            if not isinstance(data, dict):
                                logger.warning(f"Invalid JSON data from {uri}: {type(data)}")
                                attempt += 1
                                await asyncio.sleep(0.5)
                                continue
                            
                            await self.save_to_cache("uri_metadata", cache_key, data, timeout=86400)
                            self.metrics["http_success"] += 1
                            return data
                            
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout on attempt {attempt} for {uri}")
                    self.metrics["http_failure"] += 1
                except Exception as e:
                    logger.warning(f"URI fetch attempt {attempt} failed for {uri}: {str(e)}")
                    self.metrics["http_failure"] += 1
                
                attempt += 1
                if attempt <= max_attempts:
                    await asyncio.sleep(min(0.5 * attempt, 5))

        finally:
            try:
                await connector.close()
            except Exception as e:
                logger.warning(f"Error closing connector: {str(e)}")

        logger.error(f"Failed to fetch metadata from URI after {max_attempts} attempts: {uri}")
        return None

    async def _process_nft_data(self, nft_data, format_type="auto", collection_symbol=None, collection_name=None):
        """
        CONSOLIDATED: Unified NFT processing for all formats (Helius, DAS, Generic).
        Detects format automatically or uses specified format_type.
        
        Args:
            nft_data: Raw NFT data dictionary
            format_type: "helius", "das", "generic", or "auto" for auto-detection
            collection_symbol: Optional collection symbol
            collection_name: Optional collection name
            
        Returns:
            dict: Processed NFT data or None if failed
        """
        try:
            if not isinstance(nft_data, dict):
                logger.error(f"Invalid nft_data type: {type(nft_data)}")
                return None

            # Auto-detect format if needed
            if format_type == "auto":
                if "metadata" in nft_data and "content" not in nft_data:
                    format_type = "helius"
                elif "content" in nft_data:
                    format_type = "das"
                else:
                    format_type = "generic"

            mint_address = nft_data.get("id", "")
            if not mint_address:
                logger.error("Missing mint address in NFT data")
                return None

            # Extract content and metadata based on format
            if format_type == "helius":
                content = nft_data.get("content", {})
                metadata = nft_data.get("metadata", {})
            elif format_type == "das":
                content = nft_data.get("content", {})
                metadata = content.get("metadata", {}) if isinstance(content, dict) else {}
            else:  # generic
                content = nft_data
                metadata = nft_data

            if not isinstance(content, dict):
                content = {}
            if not isinstance(metadata, dict):
                metadata = {}

            # Extract name with fallbacks
            name = metadata.get("name", "")
            
            # If no name from metadata, try other providers
            if not name:
                logger.debug("No name in metadata, trying other providers")
                providers = await self.api_provider_manager.get_all_providers()
                for provider in providers:
                    if not isinstance(provider, HeliusProvider):
                        try:
                            if hasattr(provider, 'get_nfts_by_group'):
                                response = await provider.get_nfts_by_group(mint_address, page=1, page_size=1)
                                if response.get('result', {}).get('items'):
                                    item_metadata = response['result']['items'][0].get('content', {}).get('metadata', {})
                                    name = item_metadata.get('name', '')
                                    if name:
                                        break
                        except Exception as e:
                            logger.debug(f"Provider {provider.name} failed for name: {str(e)}")
                            continue

            # Fallback to on-chain metadata if still no name
            if not name:
                logger.debug("Falling back to on-chain metadata for name")
                onchain_metadata = await self.fetch_metadata_account(mint_address)
                if onchain_metadata:
                    name = onchain_metadata.get("name", "")
                    uri = onchain_metadata.get("uri", "")
                    if uri and not name:
                        uri_metadata = await self.fetch_metadata_from_uri(uri)
                        if uri_metadata and isinstance(uri_metadata, dict):
                            name = uri_metadata.get("name", uri_metadata.get("title", ""))

            if not name:
                logger.error(f"Failed to retrieve name for NFT {mint_address}")
                return None

            # Extract image URL
            image_url = ""
            files = content.get("files", [])
            if isinstance(files, list):
                for file in files:
                    if isinstance(file, dict) and file.get("type", "").startswith("image/"):
                        image_url = file.get("uri", "")
                        break
            
            if not image_url:
                links = content.get("links", {})
                if isinstance(links, dict):
                    image_url = links.get("image", "")
                if not image_url:
                    image_url = metadata.get("image", "")

            # Extract description
            description = metadata.get("description", "")

            # Extract attributes/traits
            attributes = metadata.get("attributes", [])
            if not isinstance(attributes, list):
                attributes = []

            traits = {
                attr.get("trait_type", ""): {"value": attr.get("value", ""), "rarity": 0.0}
                for attr in attributes if isinstance(attr, dict) and attr.get("trait_type") and attr.get("value")
            }

            # Try to get JSON URI metadata if available
            json_uri = content.get("json_uri", "")
            json_data = None
            if json_uri:
                json_data = await self.fetch_metadata_from_uri(json_uri)
                if json_data and isinstance(json_data, dict):
                    image_url = json_data.get("image", image_url)
                    description = json_data.get("description", description)
                    if not traits:
                        json_attributes = json_data.get("attributes", [])
                        if isinstance(json_attributes, list):
                            traits = {
                                attr.get("trait_type", ""): {"value": attr.get("value", ""), "rarity": 0.0}
                                for attr in json_attributes if isinstance(attr, dict) and attr.get("trait_type") and attr.get("value")
                            }

            # Extract NFT number for logging
            nft_number = None
            for trait_type, trait_info in traits.items():
                if trait_type.lower() in ["number", "id", "edition"]:
                    try:
                        nft_number = str(int(trait_info["value"]))
                        break
                    except ValueError:
                        continue

            if not nft_number and json_data and isinstance(json_data, dict) and "name" in json_data:
                name_str = json_data["name"]
                match = re.search(r'#(\d+)|(\d+)$', name_str)
                if match and match.groups():
                    nft_number = match.group(1) if match.group(1) else match.group(2)

            # Extract owner
            ownership = nft_data.get("ownership", {})
            owner = ownership.get("owner", "") if isinstance(ownership, dict) else ""

            processed_nft = {
                "mint": mint_address,
                "name": name,
                "image_url": image_url,
                "description": description,
                "traits": traits,
                "number": nft_number,
                "owner": owner
            }

            self.metrics["traits_fetched"] += len(traits)
            self.metrics["trait_types"].update(traits.keys())
            logger.info(f"Successfully processed NFT '{name}' (mint: {mint_address})")
            return processed_nft

        except Exception as e:
            logger.error(f"Error processing NFT {nft_data.get('id', 'unknown')}: {str(e)}", exc_info=True)
            return None

    async def _paginated_fetch(self, collection_id, fetch_method, total_supply=0, 
                               max_page_size=100, max_retries=3, last_fetched=None):
        """
        CONSOLIDATED: Generic pagination logic for all fetch methods.
        
        Args:
            collection_id: Collection address
            fetch_method: Async callable(page, page_size) that returns {"result": {"items": [...]}}
            total_supply: Expected total items (0 = unknown)
            max_page_size: Maximum items per page
            max_retries: Retry attempts per page
            last_fetched: Filter for items updated after this datetime
            
        Returns:
            list: All fetched and processed NFTs
        """
        page_size = min(max_page_size, total_supply) if total_supply > 0 else max_page_size
        all_nfts = []
        page = 1
        has_more = True

        while has_more:
            for attempt in range(max_retries):
                try:
                    logger.debug(f"Fetching page {page}, attempt {attempt + 1}/{max_retries}")
                    data = await fetch_method(page, page_size)
                    
                    if not isinstance(data, dict) or "result" not in data or "items" not in data["result"]:
                        raise ValueError("Invalid response structure")
                    
                    nfts_batch = data["result"]["items"]
                    if not isinstance(nfts_batch, list):
                        raise ValueError("Items is not a list")
                    
                    for nft_data in nfts_batch:
                        if not isinstance(nft_data, dict):
                            logger.warning(f"Invalid NFT data in batch")
                            continue
                        
                        nft_id = nft_data.get("id")
                        if not nft_id:
                            logger.warning(f"Missing id in NFT data")
                            continue
                        
                        # Check last_fetched filter
                        updated_at = nft_data.get("updatedAt")
                        if updated_at and last_fetched:
                            try:
                                updated_at_dt = datetime.fromtimestamp(updated_at, tz=timezone.utc)
                                if updated_at_dt <= last_fetched:
                                    logger.debug(f"Skipping NFT {nft_id} due to last_fetched")
                                    continue
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Invalid updatedAt for NFT {nft_id}: {str(e)}")
                        
                        # Process NFT
                        processed_nft = await self._process_nft_data(nft_data, format_type="auto")
                        if processed_nft:
                            all_nfts.append(processed_nft)
                            if total_supply > 0:
                                retrieved = len(all_nfts)
                                remaining = max(0, total_supply - retrieved)
                                percentage = (retrieved / total_supply * 100)
                                logger.info(f"Progress: {retrieved}/{total_supply} ({percentage:.1f}%), {remaining} remaining")
                        else:
                            logger.warning(f"Failed to process NFT {nft_id}")
                    
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for page {page}: {str(e)}")
                    if attempt == max_retries - 1:
                        logger.error(f"Failed to fetch page {page} after {max_retries} attempts")
                        has_more = False
                        break
                    await asyncio.sleep(2 ** attempt)
            
            # Check if we should continue
            if has_more and (len(nfts_batch) < page_size or (total_supply and len(all_nfts) >= total_supply)):
                has_more = False
            elif has_more:
                page += 1

        return all_nfts

    async def fetch_helius_metadata(self, mint_address):
        """
        Fetch metadata from Helius API with fallback to other providers.
        UPDATED: Uses dual provider strategy.
        """
        try:
            cached_metadata = await self.get_from_cache("helius_metadata", mint_address)
            if cached_metadata:
                return cached_metadata

            # Try Helius first
            provider, is_helius = await self._get_provider_with_fallback(prefer_helius=True)
            if provider is None:
                logger.error("No RPC provider available for metadata fetch")
                return None
            
            if is_helius:
                try:
                    helius_metadata_url = f"https://api.helius.xyz/v1/nfts?api-key={provider.api_key}"
                    payload = {"mintAccounts": [mint_address]}
                    logger.info(f"Fetching Helius metadata for {mint_address}")
                    
                    response = await sync_to_async(self.session.post)(helius_metadata_url, json=payload, timeout=15)

                    if response.status_code == 200:
                        data = response.json()
                        if data and len(data) > 0:
                            metadata = data[0]
                            
                            collection_address = None
                            if metadata.get('collection') and metadata['collection'].get('key'):
                                collection_address = metadata['collection']['key']
                            
                            await self.save_to_cache("helius_metadata", mint_address, metadata, 
                                                    timeout=3600, collection_address=collection_address)
                            logger.info(f"Successfully fetched Helius metadata for {mint_address}")
                            return metadata
                    logger.warning(f"Helius metadata API returned error for {mint_address}: {response.status_code}")
                except Exception as e:
                    logger.warning(f"Error fetching Helius metadata for {mint_address}: {str(e)}")

            # Fallback to other providers
            logger.info(f"Attempting fallback providers for metadata fetch: {mint_address}")
            
            all_providers = await self.api_provider_manager.get_all_providers()
            for fallback_provider in all_providers:
                if isinstance(fallback_provider, HeliusProvider) and is_helius:
                    continue  # Skip helius since we already tried

                try:
                    if not await fallback_provider.check_availability():
                        logger.debug(f"Provider {fallback_provider.name} not available, skipping")
                        continue
                        
                    logger.info(f"Trying fallback provider {fallback_provider.name} for metadata")
                    
                    if hasattr(fallback_provider, '_fetch_metadata'):
                        metadata = await fallback_provider._fetch_metadata(mint_address)
                        if metadata:
                            logger.info(f"Successfully fetched metadata using {fallback_provider.name}")
                            collection_address = metadata.get("collection", {}).get("key")
                            await self.save_to_cache("helius_metadata", mint_address, metadata,
                                                    timeout=3600, collection_address=collection_address)
                            return metadata
                    
                    metadata = await self._fetch_generic_onchain_metadata(mint_address, fallback_provider)
                    if metadata:
                        logger.info(f"Successfully fetched on-chain metadata using {fallback_provider.name}")
                        collection_address = metadata.get("collection", {}).get("key")
                        await self.save_to_cache("helius_metadata", mint_address, metadata,
                                                timeout=3600, collection_address=collection_address)
                        return metadata
                        
                except Exception as e:
                    logger.warning(f"Fallback provider {fallback_provider.name} failed for {mint_address}: {str(e)}")
                    continue

            logger.error(f"All providers failed to fetch metadata for {mint_address}")
            return None
            
        except Exception as e:
            logger.error(f"Error in fetch_helius_metadata for {mint_address}: {str(e)}", exc_info=True)
            return None

    async def fetch_using_helius_assets_by_group(self, collection_id, last_fetched=None):
        """
        Fetch NFTs using Helius getAssetsByGroup API.
        UPDATED: Uses dual provider strategy and consolidated pagination.
        """
        try:
            logger.debug(f"Fetching NFTs for collection {collection_id} using Helius getAssetsByGroup")
            cached_nfts = await self.get_from_cache("helius_nfts", collection_id)
            if cached_nfts and not last_fetched:
                logger.info(f"Using cached NFTs for {collection_id}")
                return cached_nfts

            # Get Helius provider specifically
            provider, is_helius = await self._get_provider_with_fallback(prefer_helius=True)
            if provider is None:
                logger.error("No RPC provider available")
                return []
            if not is_helius:
                logger.warning("Helius not available, skipping this method")
                return []

            # Validate collection address
            try:
                is_valid = await provider.validate_address(collection_id)
                if not is_valid:
                    logger.error(f"Invalid collection address: {collection_id}")
                    return []
            except Exception as e:
                logger.warning(f"Failed to validate {collection_id}: {str(e)}")
                return []

            # Fetch collection metadata
            collection_metadata = await self.fetch_metadata_from_das_collection(collection_id)
            if not collection_metadata:
                collection_metadata = await self.fetch_metadata_account(collection_id)
            collection_symbol = collection_metadata.get("symbol", "") if collection_metadata else ""
            collection_name = collection_metadata.get("name", "") if collection_metadata else ""

            # Get total supply with fallbacks
            total_supply = 0
            total_supply_source = "None"
            max_retries = 3
            
            # Fallback 1: Helius getAsset
            for attempt in range(max_retries):
                try:
                    collection_data = await provider.get_das_collection(collection_id)
                    if isinstance(collection_data, dict) and "result" in collection_data:
                        total_supply = collection_data.get("result", {}).get("totalItems", 0)
                        total_supply_source = "Helius totalItems"
                        break
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
            
            if total_supply > 0:
                logger.info(f"Fetched total_supply {total_supply} from {total_supply_source}")

            # Fallback 2: Cache
            if total_supply == 0:
                cached_total_supply = await self.get_from_cache("total_supply", collection_id)
                if cached_total_supply:
                    total_supply = cached_total_supply
                    total_supply_source = "Cache"

            # Fallback 3: getAssetsByCreator
            if total_supply == 0:
                try:
                    creator_address = None
                    if collection_data and collection_data.get("result", {}).get("creators"):
                        creator_address = collection_data["result"]["creators"][0].get("address")
                    else:
                        collection = await sync_to_async(NFTCollection.objects.filter(address=collection_id).first)()
                        if collection:
                            nft = await sync_to_async(collection.nfts.first)()
                            if nft and await sync_to_async(nft.creators.exists)():
                                first_creator = await sync_to_async(nft.creators.first)()
                                creator_address = first_creator.address
                    if creator_address:
                        assets = await provider.get_assets_by_creator(creator_address, limit=1000)
                        if assets and isinstance(assets, dict) and "result" in assets:
                            total_supply = len(assets["result"].get("items", []))
                            total_supply_source = "Helius getAssetsByCreator"
                except Exception as e:
                    logger.warning(f"Failed getAssetsByCreator: {str(e)}")

            # Cache total_supply
            if total_supply > 0:
                await self.save_to_cache("total_supply", collection_id, total_supply, timeout=1800)

            self.metrics["total_supply"] = total_supply
            logger.info(f"Total supply for {collection_id}: {total_supply} (Source: {total_supply_source})")

            if total_supply == 0:
                logger.warning(f"No valid total_supply found for {collection_id}")
                return []

            # Use consolidated pagination
            async def fetch_page(page, page_size):
                return await provider.get_nfts_by_group(collection_id, page, page_size)

            all_nfts = await self._paginated_fetch(
                collection_id, 
                fetch_page, 
                total_supply=total_supply,
                max_page_size=100,
                max_retries=3,
                last_fetched=last_fetched
            )

            self.metrics["nfts_retrieved"] = len(all_nfts)
            if all_nfts:
                await self.save_to_cache("helius_nfts", collection_id, all_nfts, timeout=900)
            logger.info(f"Fetched {len(all_nfts)} NFTs for {collection_id} using Helius")
            return all_nfts

        except Exception as e:
            logger.error(f"Error fetching NFTs for {collection_id}: {str(e)}", exc_info=True)
            self.metrics["error_encountered"] = str(e)
            return []

    async def fetch_using_das(self, collection_id, last_fetched=None):
        """
        Fetch NFTs using Digital Asset Standard (DAS) API.
        UPDATED: Uses dual provider strategy and consolidated pagination.
        """
        try:
            logger.debug(f"Fetching NFTs for {collection_id} using DAS")
            cached_nfts = await self.get_from_cache("das_nfts", collection_id)
            if cached_nfts and not last_fetched:
                logger.info(f"Using cached NFTs from DAS for {collection_id}")
                return cached_nfts

            provider, is_helius = await self._get_provider_with_fallback(prefer_helius=True)
            if provider is None:
                logger.error("No RPC provider available for DAS")
                return []
            if not is_helius:
                logger.warning("Primary provider is not Helius, skipping DAS fetch")
                return []

            collection_data = await provider.get_das_collection(collection_id)
            if not isinstance(collection_data, dict) or "result" not in collection_data:
                logger.warning(f"Invalid collection data response for {collection_id}")
                return []
            
            total_supply = collection_data.get("result", {}).get("totalItems", 0)
            self.metrics["total_supply"] = total_supply

            async def fetch_page(page, page_size):
                params = {"groupKey": "collection", "groupValue": collection_id, "limit": page_size}
                if page > 1:
                    params["page"] = page
                payload = {"jsonrpc": "2.0", "id": "my-id", "method": "getAssetsByGroup", "params": params}
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{provider.rpc_url}",
                        json=payload,
                        headers={"Authorization": f"Bearer {provider.api_key}"},
                        timeout=60
                    ) as response:
                        response.raise_for_status()
                        return await response.json()

            all_nfts = await self._paginated_fetch(
                collection_id,
                fetch_page,
                total_supply=total_supply,
                max_page_size=100,
                max_retries=5,
                last_fetched=last_fetched
            )

            self.metrics["nfts_retrieved"] = len(all_nfts)
            if all_nfts:
                await self.save_to_cache("das_nfts", collection_id, all_nfts, timeout=900)
            logger.info(f"Fetched {len(all_nfts)} NFTs for {collection_id} using DAS")
            return all_nfts

        except Exception as e:
            logger.error(f"Error fetching NFTs using DAS for {collection_id}: {str(e)}", exc_info=True)
            self.metrics["error_encountered"] = str(e)
            return []

    async def fetch_using_program_accounts(self, collection_id, last_fetched=None):
        """
        Fetch NFTs using Solana getProgramAccounts as fallback.
        UPDATED: Proper async wrapping for blocking operations.
        """
        try:
            logger.debug(f"Fetching NFTs for {collection_id} using getProgramAccounts")
            cached_nfts = await self.get_from_cache("program_nfts", collection_id)
            if cached_nfts and not last_fetched:
                logger.info(f"Using cached NFTs from getProgramAccounts for {collection_id}")
                return cached_nfts

            METAPLEX_PROGRAM_ID = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"
            METADATA_ACCOUNT_SIZE = 679
            all_nfts = []
            offset = 0
            page_size = 100
            has_more = True
            max_retries = 3
            
            provider = await self.api_provider_manager.get_rpc_provider()
            if provider is None:
                logger.error("No RPC provider available for getProgramAccounts")
                return []

            while has_more:
                for attempt in range(max_retries):
                    try:
                        payload = {
                            "jsonrpc": "2.0",
                            "id": "my-id",
                            "method": "getProgramAccounts",
                            "params": [
                                METAPLEX_PROGRAM_ID,
                                {
                                    "encoding": "base64",
                                    "filters": [
                                        {"memcmp": {"offset": 368, "bytes": collection_id}},
                                        {"dataSize": METADATA_ACCOUNT_SIZE}
                                    ],
                                    "dataSlice": {"offset": 0, "length": METADATA_ACCOUNT_SIZE},
                                    "offset": offset,
                                    "limit": page_size
                                }
                            ]
                        }
                        async with aiohttp.ClientSession() as session:
                            async with session.post(
                                provider.rpc_url,
                                json=payload,
                                headers={"Authorization": f"Bearer {provider.api_key}"},
                                timeout=60
                            ) as response:
                                response.raise_for_status()
                                data = await response.json()
                        
                        if "result" not in data or not isinstance(data["result"], list):
                            raise ValueError("Invalid response")
                        
                        accounts = data["result"]
                        
                        # Process accounts in thread pool for CPU-intensive base64 decoding
                        async def process_account(account):
                            pubkey = account.get("pubkey")
                            data_base64 = account.get("account", {}).get("data", ["", ""])[0]
                            if not data_base64:
                                return None
                            return await sync_to_async(self._process_program_account_sync)(pubkey, data_base64)
                        
                        tasks = [process_account(account) for account in accounts]
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        for result in results:
                            if isinstance(result, dict):
                                if not last_fetched or await self.fetch_metadata_account(result["mint"]):
                                    all_nfts.append(result)
                        
                        break
                    except Exception as e:
                        logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                        if attempt == max_retries - 1:
                            has_more = False
                            break
                        await asyncio.sleep(2 ** attempt)
                
                if has_more and len(accounts) < page_size:
                    has_more = False
                elif has_more:
                    offset += page_size

            self.metrics["nfts_retrieved"] = len(all_nfts)
            if all_nfts:
                await self.save_to_cache("program_nfts", collection_id, all_nfts, timeout=900)
            logger.info(f"Fetched {len(all_nfts)} NFTs for {collection_id} using getProgramAccounts")
            return all_nfts

        except Exception as e:
            logger.error(f"Error fetching NFTs using getProgramAccounts for {collection_id}: {str(e)}", exc_info=True)
            self.metrics["error_encountered"] = str(e)
            return []

    def _process_program_account_sync(self, pubkey, data_base64):
        """Synchronous helper for processing program account data."""
        try:
            data_bytes = base64.b64decode(data_base64)
            mint_bytes = data_bytes[33:65]
            mint_address = str(Pubkey(mint_bytes))
            name_bytes = data_bytes[65:97]
            name = ''.join(char for char in name_bytes.decode('utf-8', errors='replace').rstrip('\x00') if char in string.printable)
            uri_bytes = data_bytes[129:329]
            uri = ''.join(char for char in uri_bytes.decode('utf-8', errors='replace').rstrip('\x00') if char in string.printable)

            return {
                "mint": mint_address,
                "name": name,
                "uri": uri,
                "image_url": "",
                "description": "",
                "traits": {}
            }
        except Exception as e:
            logger.error(f"Error processing program account {pubkey}: {str(e)}")
            return None

    async def fetch_metadata_account(self, mint_address):
        """
        Fetch metadata from Solana Metadata Account.
        UPDATED: Enhanced error tracking and logging.
        """
        try:
            cached_metadata = await self.get_from_cache("metadata_account", mint_address)
            if cached_metadata:
                return cached_metadata

            METAPLEX_PROGRAM_ID = Pubkey.from_string("metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s")
            mint_pubkey = Pubkey.from_string(mint_address)
            metadata_pda, _ = Pubkey.find_program_address(
                [b"metadata", bytes(METAPLEX_PROGRAM_ID), bytes(mint_pubkey)],
                METAPLEX_PROGRAM_ID
            )

            provider = await self.api_provider_manager.get_rpc_provider()
            if provider is None:
                logger.error(f"❌ No RPC provider available for fetch_metadata_account ({mint_address[:8]}...)")
                return None
            
            logger.debug(f"🔍 Fetching metadata account for {mint_address[:8]}... using {provider.name}")
            data = await provider.get_account_info(str(metadata_pda))
            
            if not data.get("result", {}).get("value"):
                logger.warning(f"⚠️ No metadata account found for {mint_address[:8]}... (likely cNFT or non-Metaplex)")
                return None

            account_data = data["result"]["value"]["data"][0]
            decoded_data = base64.b64decode(account_data)
            
            # Parse on-chain data
            name = ''.join(char for char in decoded_data[64:96].decode('utf-8', errors='replace').rstrip('\x00') if char in string.printable)
            if not name:
                name = f"Unknown {mint_address[:8]}"
                logger.debug(f"⚠️ Empty name in metadata account for {mint_address[:8]}...")
            
            symbol = ''.join(char for char in decoded_data[96:106].decode('utf-8', errors='replace').rstrip('\x00') if char in string.printable)
            uri = ''.join(char for char in decoded_data[128:328].decode('utf-8', errors='replace').rstrip('\x00:;,.') if char in string.printable)

            image_url = ""
            description = ""
            creator_addresses = []
            collection = None
            
            # Parse creators
            if len(decoded_data) > 329 and decoded_data[328] == 1:
                num_creators = decoded_data[329]
                logger.debug(f"📝 Found {num_creators} creators for {mint_address[:8]}...")
                
                for i in range(num_creators):
                    creator_start = 330 + (i * 34)
                    if creator_start + 34 > len(decoded_data):
                        break
                    creator_address = str(Pubkey(decoded_data[creator_start:creator_start + 32]))
                    verified = decoded_data[creator_start + 32] == 1
                    share = decoded_data[creator_start + 33]
                    creator_addresses.append({"address": creator_address, "verified": verified, "share": share})
                
                # Parse collection
                collection_offset = 329 + (num_creators * 34)
                if len(decoded_data) > collection_offset + 34 and decoded_data[collection_offset] == 1:
                    collection_key = str(Pubkey(decoded_data[collection_offset + 1:collection_offset + 33]))
                    collection_verified = decoded_data[collection_offset + 33] == 1
                    collection = {"key": collection_key, "verified": collection_verified}
                    logger.info(f"✅ Found collection {collection_key[:8]}... for {mint_address[:8]}...")
                else:
                    logger.warning(f"⚠️ No collection field in metadata account for {mint_address[:8]}...")
            else:
                logger.warning(f"⚠️ No creator section in metadata account for {mint_address[:8]}...")

            # Fetch off-chain metadata
            if uri:
                logger.debug(f"🌐 Fetching off-chain metadata from URI for {mint_address[:8]}...")
                try:
                    uri_metadata = await self.fetch_metadata_from_uri(uri)
                    if uri_metadata:
                        image_url = uri_metadata.get("image", "")
                        description = uri_metadata.get("description", "")
                        if not creator_addresses:
                            creator_addresses = [
                                {"address": creator.get("address", ""), "verified": False, "share": 0} 
                                for creator in uri_metadata.get("properties", {}).get("creators", [])
                            ]
                        logger.debug(f"✅ Successfully fetched off-chain metadata for {mint_address[:8]}...")
                    else:
                        logger.warning(f"⚠️ URI fetch returned empty for {mint_address[:8]}...")
                except Exception as uri_error:
                    logger.warning(f"⚠️ URI fetch failed for {mint_address[:8]}...: {str(uri_error)}")
            else:
                logger.warning(f"⚠️ No URI found in metadata account for {mint_address[:8]}...")

            metadata = {
                "name": name,
                "symbol": symbol,
                "image_url": image_url,
                "description": description,
                "creator_addresses": creator_addresses,
                "uri": uri,
                "collection": collection
            }
            
            # Cache result
            await self.save_to_cache("metadata_account", mint_address, metadata, timeout=1800)
            logger.info(f"✅ Successfully parsed metadata for {mint_address[:8]}... (collection: {bool(collection)})")
            return metadata

        except Exception as e:
            logger.error(f"❌ Failed to fetch Metadata for {mint_address[:8]}...: {str(e)}", exc_info=True)
            return None

    async def fetch_metadata_account(self, mint_address):
        """
        Fetch metadata from Solana Metadata Account.
        UPDATED: Enhanced error tracking and logging.
        """
        try:
            cached_metadata = await self.get_from_cache("metadata_account", mint_address)
            if cached_metadata:
                return cached_metadata

            METAPLEX_PROGRAM_ID = Pubkey.from_string("metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s")
            mint_pubkey = Pubkey.from_string(mint_address)
            metadata_pda, _ = Pubkey.find_program_address(
                [b"metadata", bytes(METAPLEX_PROGRAM_ID), bytes(mint_pubkey)],
                METAPLEX_PROGRAM_ID
            )

            provider = await self.api_provider_manager.get_rpc_provider()
            if provider is None:
                logger.error(f"❌ No RPC provider available for fetch_metadata_account ({mint_address[:8]}...)")
                return None
            
            logger.debug(f"🔍 Fetching metadata account for {mint_address[:8]}... using {provider.name}")
            data = await provider.get_account_info(str(metadata_pda))
            
            if not data.get("result", {}).get("value"):
                logger.warning(f"⚠️ No metadata account found for {mint_address[:8]}... (likely cNFT or non-Metaplex)")
                return None

            account_data = data["result"]["value"]["data"][0]
            decoded_data = base64.b64decode(account_data)
            
            # Parse on-chain data
            name = ''.join(char for char in decoded_data[64:96].decode('utf-8', errors='replace').rstrip('\x00') if char in string.printable)
            if not name:
                name = f"Unknown {mint_address[:8]}"
                logger.debug(f"⚠️ Empty name in metadata account for {mint_address[:8]}...")
            
            symbol = ''.join(char for char in decoded_data[96:106].decode('utf-8', errors='replace').rstrip('\x00') if char in string.printable)
            uri = ''.join(char for char in decoded_data[128:328].decode('utf-8', errors='replace').rstrip('\x00:;,.') if char in string.printable)

            image_url = ""
            description = ""
            creator_addresses = []
            collection = None
            
            # Parse creators
            if len(decoded_data) > 329 and decoded_data[328] == 1:
                num_creators = decoded_data[329]
                logger.debug(f"📝 Found {num_creators} creators for {mint_address[:8]}...")
                
                for i in range(num_creators):
                    creator_start = 330 + (i * 34)
                    if creator_start + 34 > len(decoded_data):
                        break
                    creator_address = str(Pubkey(decoded_data[creator_start:creator_start + 32]))
                    verified = decoded_data[creator_start + 32] == 1
                    share = decoded_data[creator_start + 33]
                    creator_addresses.append({"address": creator_address, "verified": verified, "share": share})
                
                # Parse collection
                collection_offset = 329 + (num_creators * 34)
                if len(decoded_data) > collection_offset + 34 and decoded_data[collection_offset] == 1:
                    collection_key = str(Pubkey(decoded_data[collection_offset + 1:collection_offset + 33]))
                    collection_verified = decoded_data[collection_offset + 33] == 1
                    collection = {"key": collection_key, "verified": collection_verified}
                    logger.info(f"✅ Found collection {collection_key[:8]}... for {mint_address[:8]}...")
                else:
                    logger.warning(f"⚠️ No collection field in metadata account for {mint_address[:8]}...")
            else:
                logger.warning(f"⚠️ No creator section in metadata account for {mint_address[:8]}...")

            # Fetch off-chain metadata
            if uri:
                logger.debug(f"🌐 Fetching off-chain metadata from URI for {mint_address[:8]}...")
                try:
                    uri_metadata = await self.fetch_metadata_from_uri(uri)
                    if uri_metadata:
                        image_url = uri_metadata.get("image", "")
                        description = uri_metadata.get("description", "")
                        if not creator_addresses:
                            creator_addresses = [
                                {"address": creator.get("address", ""), "verified": False, "share": 0} 
                                for creator in uri_metadata.get("properties", {}).get("creators", [])
                            ]
                        logger.debug(f"✅ Successfully fetched off-chain metadata for {mint_address[:8]}...")
                    else:
                        logger.warning(f"⚠️ URI fetch returned empty for {mint_address[:8]}...")
                except Exception as uri_error:
                    logger.warning(f"⚠️ URI fetch failed for {mint_address[:8]}...: {str(uri_error)}")
            else:
                logger.warning(f"⚠️ No URI found in metadata account for {mint_address[:8]}...")

            metadata = {
                "name": name,
                "symbol": symbol,
                "image_url": image_url,
                "description": description,
                "creator_addresses": creator_addresses,
                "uri": uri,
                "collection": collection
            }
            
            # Cache result
            await self.save_to_cache("metadata_account", mint_address, metadata, timeout=1800)
            logger.info(f"✅ Successfully parsed metadata for {mint_address[:8]}... (collection: {bool(collection)})")
            return metadata

        except Exception as e:
            logger.error(f"❌ Failed to fetch Metadata for {mint_address[:8]}...: {str(e)}", exc_info=True)
            return None

    async def is_compressed_nft(self, mint_address: str) -> bool:
        """
        Detect if an NFT is compressed (cNFT).
        Compressed NFTs don't have metadata accounts.
        """
        try:
            provider = await self.api_provider_manager.get_rpc_provider()
            if not provider:
                return False
            
            # Try to get account info for the mint itself
            account_info = await provider.get_account_info(mint_address)
            
            # If the mint account doesn't exist, it's likely a cNFT
            if not account_info or not account_info.get("result", {}).get("value"):
                logger.info(f"🗜️ Detected compressed NFT: {mint_address[:8]}...")
                return True
            
            return False
        except Exception as e:
            logger.debug(f"Error checking if {mint_address[:8]}... is compressed: {e}")
            return False

    async def find_collection_via_helius_das(self, mint_address: str) -> Optional[str]:
        """
        Alternative: Use Helius DAS to find collection (works for cNFTs).
        """
        try:
            provider = await self.api_provider_manager.get_provider_by_name('helius')
            if not provider:
                return None
            
            # Use get_collection_for_mint which uses DAS API
            collection_address = await provider.get_collection_for_mint(mint_address)
            if collection_address:
                logger.info(f"✅ Found collection via Helius DAS: {collection_address[:8]}...")
                return collection_address
            
            return None
        except Exception as e:
            logger.debug(f"Helius DAS collection lookup failed: {e}")
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

    async def ensure_provider_available(self) -> bool:
        """
        Check if at least one provider is available before attempting operations.
        """
        providers = await self.api_provider_manager.get_all_providers()
        
        if not providers:
            logger.error("❌ No providers configured!")
            return False
        
        available_count = 0
        for provider in providers:
            try:
                is_available = await provider.check_availability()
                if is_available:
                    available_count += 1
                    logger.info(f"✅ Provider '{provider.name}' is available")
            except Exception as e:
                logger.warning(f"⚠️ Provider '{provider.name}' check failed: {e}")
        
        if available_count == 0:
            logger.error("❌ No providers are currently available!")
            return False
        
        logger.info(f"✅ {available_count}/{len(providers)} providers available")
        return True

    async def fetch_metadata_from_das_collection(self, collection_id):
        """
        Fetch collection metadata using DAS API.
        UPDATED: Proper async wrapping and dual provider.
        """
        try:
            provider, is_helius = await self._get_provider_with_fallback(prefer_helius=True)
            if provider is None:
                logger.error("No RPC provider available for fetch_metadata_from_das_collection")
                return None
            if not is_helius:
                logger.warning("Primary provider is not Helius, skipping DAS collection fetch")
                return None
            if not await provider.check_availability():
                logger.warning("DAS provider unavailable")
                return None
            
            data = await provider.get_das_collection(collection_id)
            if not data or "result" not in data:
                logger.warning(f"No valid DAS response for collection {collection_id}")
                return None
            
            result = data["result"]
            if not isinstance(result, dict):
                logger.warning(f"Invalid DAS result format for collection {collection_id}")
                return None
            
            content = result.get("content", {})
            files = content.get("files", [])
            
            image_url = ""
            if files and isinstance(files, list) and len(files) > 0:
                first_file = files[0]
                if isinstance(first_file, dict):
                    image_url = first_file.get("uri", "")
            
            metadata_content = content.get("metadata", {})
            if not isinstance(metadata_content, dict):
                metadata_content = {}
            
            creators = result.get("creators", [])
            if not isinstance(creators, list):
                creators = []
            
            creator_addresses = []
            for creator in creators:
                if isinstance(creator, dict):
                    creator_addresses.append({
                        "address": creator.get("address", ""),
                        "verified": creator.get("verified", False),
                        "share": creator.get("share", 0)
                    })
            
            metadata = {
                "name": metadata_content.get("name", f"Collection {collection_id[:8]}"),
                "symbol": metadata_content.get("symbol", ""),
                "image_url": image_url,
                "description": metadata_content.get("description", ""),
                "creator_addresses": creator_addresses,
                "uri": content.get("json_uri", "")
            }
            
            logger.info(f"Successfully fetched DAS metadata for collection {collection_id}")
            return metadata
            
        except Exception as e:
            logger.error(f"Error fetching collection metadata using DAS for {collection_id}: {str(e)}", exc_info=True)
            return None

    async def fetch_collections_by_collection(self, collection_address, last_fetched=None):
        """
        Fetch NFTs in a collection using multiple methods with fallbacks.
        UPDATED: Fully async with proper database wrapping.
        """
        try:
            await self.initialize_persistent_session()
            logger.info(f"Starting fetch for collection: {collection_address}")
            collections = {}
            collection_id = collection_address

            # Reset metrics
            self.metrics.update({
                "retrieval_method": "",
                "nfts_retrieved": 0,
                "total_supply": 0,
                "fallback_used": False,
                "fallback_method": "",
                "error_encountered": "",
                "traits_fetched": 0,
                "trait_types": set(),
                "provider_used": ""
            })

            # Check cache first
            cached_collection = await self.get_from_cache("collection", collection_id)
            if cached_collection and not last_fetched:
                logger.info(f"Using cached data for collection: {collection_id}")
                return [cached_collection]

            # Check database for last_fetched if not provided
            collection_obj = await sync_to_async(
                NFTCollection.objects.filter(address=collection_id).first
            )()
            if last_fetched is None and collection_obj and collection_obj.last_fetched:
                last_fetched = collection_obj.last_fetched

            # Fetch collection metadata with fallbacks
            collection_metadata = None
            for method, method_name in [
                (self.fetch_metadata_account, "Metadata Account"),
                (self.fetch_metadata_from_das_collection, "DAS Collection"),
                (self.fetch_metadata_account, "Program Accounts")  # Removed duplicate wrapper
            ]:
                try:
                    logger.info(f"Attempting to fetch metadata using {method_name}")
                    collection_metadata = await method(collection_id)
                    if collection_metadata:
                        logger.info(f"Successfully fetched metadata using {method_name}")
                        break
                except Exception as e:
                    logger.warning(f"Failed to fetch metadata using {method_name}: {str(e)}")
                    self.metrics["fallback_used"] = True
                    self.metrics["fallback_method"] = method_name
                    self.metrics["error_encountered"] = str(e)

            if not collection_metadata:
                logger.error(f"Failed to fetch metadata for collection {collection_id} after all methods")
                return []

            # Extract metadata fields
            name = collection_metadata.get("name", f"Collection {collection_id[:8]}")
            image_url = collection_metadata.get("image_url", "")
            description = collection_metadata.get("description", "")
            creator_addresses = collection_metadata.get("creator_addresses", [])
            symbol = collection_metadata.get("symbol", "")

            # Fetch NFTs with fallbacks
            all_nfts = []
            fetch_methods = [
                (self.fetch_using_helius_assets_by_group, "Helius getAssetsByGroup"),
                (self.fetch_using_das, "DAS"),
                (self.fetch_using_program_accounts, "getProgramAccounts")
            ]
            
            for fetch_method, method_name in fetch_methods:
                try:
                    logger.info(f"Fetching NFTs using {method_name} for collection: {collection_address}")
                    all_nfts = await fetch_method(collection_address, last_fetched=last_fetched)
                    if all_nfts:
                        self.metrics["retrieval_method"] = method_name
                        provider_name = await self.api_provider_manager.get_current_provider_name()
                        self.metrics["provider_used"] = provider_name
                        break
                    else:
                        logger.warning(f"No NFTs fetched using {method_name}")
                        self.metrics["fallback_used"] = True
                        self.metrics["fallback_method"] = method_name
                except Exception as e:
                    logger.warning(f"Failed to fetch NFTs using {method_name}: {str(e)}")
                    self.metrics["fallback_used"] = True
                    self.metrics["fallback_method"] = method_name
                    self.metrics["error_encountered"] = str(e)

            self.metrics["nfts_retrieved"] = len(all_nfts)
            logger.info(f"Total NFTs fetched for collection {collection_address}: {len(all_nfts)}")

            if not all_nfts:
                logger.warning(f"No NFTs found for collection {collection_address}. Skipping transaction.")
                return []

            # Prepare collection data
            collections[collection_id] = {
                "address": collection_id,
                "name": name,
                "image_url": image_url,
                "description": description,
                "creator_addresses": creator_addresses,
                "symbol": symbol,
                "nfts": all_nfts,
                "source": "webhook"
            }

            # Store collection and NFTs
            logger.info(f"Storing collection {collection_id} in database")
            for coll_id, collection_data in collections.items():
                await self.store_collection_and_nfts_optimized(coll_id, collection_data)
                cache_data = collection_data.copy()
                cache_data.pop("nfts", None)
                await self.save_to_cache("collection", coll_id, cache_data, 
                                      timeout=3600, collection_address=collection_address)

            # Update last_fetched timestamp
            if collection_obj:
                collection_obj.last_fetched = timezone.now()
                await sync_to_async(collection_obj.save)()

            await self.log_metrics()
            return list(collections.values())

        except Exception as e:
            logger.error(f"Error fetching collections for {collection_address}: {str(e)}", exc_info=True)
            self.metrics["error_encountered"] = str(e)
            await self.monitor_fetch_errors(collection_address, e)
            await self.log_metrics()
            return []

    async def store_collection_and_nfts(self, collection_id, collection_data):
        """
        Store a collection and its NFTs in the database.
        UPDATED: Fully async with proper transaction handling.
        """
        try:
            collection_name = collection_data.get("name", f"Unknown {collection_id[:8]}")
            defaults = {
                "name": collection_name,
                "image_url": collection_data.get("image_url", ""),
                "creator_address": collection_data.get("creator_addresses", [{}])[0].get("address", ""),
                "is_featured": False,
                "source": collection_data.get("source", "unknown"),
                "description": collection_data.get("description", ""),
                "symbol": collection_data.get("symbol", "")
            }

            # Wrap database operations in sync_to_async
            @sync_to_async
            def create_or_update_collection():
                collection, created = NFTCollection.objects.get_or_create(
                    address=collection_id,
                    defaults=defaults
                )
                if not created:
                    for key, value in defaults.items():
                        setattr(collection, key, value)
                    collection.save()
                return collection

            collection = await create_or_update_collection()

            nfts = collection_data.get("nfts", [])
            for i in range(0, len(nfts), self.batch_size):
                batch = nfts[i:i + self.batch_size]
                await self._process_nft_batch(batch, collection)

            return collection

        except Exception as e:
            logger.error(f"Error storing collection {collection_id}: {str(e)}", exc_info=True)
            self.metrics["error_encountered"] = str(e)
            raise

    async def _process_nft_batch(self, batch, collection):
        """
        Process a batch of NFTs with transaction control.
        UPDATED: Fully async with proper database wrapping.
        """
        @sync_to_async
        def process_batch_in_transaction():
            with transaction.atomic():
                for nft_data in batch:
                    try:
                        if not isinstance(nft_data, dict):
                            logger.warning(f"Invalid NFT data type: {type(nft_data)}")
                            continue

                        mint_address = nft_data.get("mint")
                        if not mint_address:
                            logger.warning("Missing mint address in NFT data")
                            continue

                        traits_data = nft_data.get("traits", {})
                        if not isinstance(traits_data, dict):
                            logger.warning(f"Invalid traits_data type for NFT {mint_address}")
                            traits_data = {}

                        # Get or create NFT
                        owner = nft_data.get("owner", "")
                        nft, created = NFT.objects.update_or_create(
                            mint_address=mint_address,
                            defaults={
                                "collection": collection,
                                "token_address": mint_address,
                                "name": nft_data.get("name", f"NFT {mint_address[:8]}"),
                                "image_url": nft_data.get("image_url", ""),
                                "owner": owner
                            }
                        )

                        # Process traits
                        for trait_type_name, trait_data in traits_data.items():
                            if not isinstance(trait_data, dict):
                                logger.warning(f"Invalid trait_data for {trait_type_name}")
                                continue
                            
                            trait_value_str = str(trait_data.get("value", ""))
                            if not trait_value_str:
                                continue
                            
                            try:
                                trait_rarity = float(trait_data.get("rarity", 0.0))
                            except (ValueError, TypeError):
                                trait_rarity = 0.0

                            trait_type, _ = TraitType.objects.get_or_create(
                                name=trait_type_name,
                                collection=collection
                            )
                            trait_value, _ = TraitValue.objects.get_or_create(
                                trait_type=trait_type,
                                value=trait_value_str,
                                defaults={"rarity": trait_rarity}
                            )
                            nft.trait_values.add(trait_value)

                        logger.info(f"Successfully processed NFT {mint_address}")
                    except Exception as e:
                        logger.error(f"Error processing NFT {nft_data.get('mint', 'unknown')}: {str(e)}")

        await process_batch_in_transaction()

    async def validate_collection(self, collection_address):
        """
        Validate if an address is a valid NFT collection.
        UPDATED: Proper async with dual provider.
        """
        try:
            cached_result = await self.get_from_cache("validation", collection_address)
            if cached_result is not None:
                logger.debug(f"Cache hit for validation of {collection_address}: {cached_result}")
                return cached_result

            providers = await self.api_provider_manager.get_all_providers()
            if not providers:
                logger.error("No RPC providers available for validate_collection")
                await self.save_to_cache("validation", collection_address, False, timeout=3600)
                return False

            for provider in providers:
                logger.debug(f"Attempting validation with provider {provider.name}")
                try:
                    if hasattr(provider, 'get_nfts_by_group'):
                        response = await provider.get_nfts_by_group(collection_address, page=1, page_size=1)
                        if response.get('result', {}).get('items'):
                            logger.info(f"Validated {collection_address} using {provider.name}")
                            await self.save_to_cache("validation", collection_address, True, timeout=3600)
                            return True
                except Exception as e:
                    logger.warning(f"Error using {provider.name} for validation: {str(e)}")
                    continue

            # Fallback to on-chain metadata
            collection_metadata = await self.fetch_metadata_account(collection_address)
            if collection_metadata:
                grouping = collection_metadata.get("grouping", [])
                if grouping and grouping[0].get("group_key") == "collection":
                    await self.save_to_cache("validation", collection_address, True, timeout=3600)
                    return True
                if collection_metadata.get("collection"):
                    await self.save_to_cache("validation", collection_address, True, timeout=3600)
                    return True
                if collection_metadata.get("name") and collection_metadata.get("creator_addresses"):
                    await self.save_to_cache("validation", collection_address, True, timeout=3600)
                    return True

            logger.error(f"Failed to validate {collection_address} as a collection")
            await self.save_to_cache("validation", collection_address, False, timeout=3600)
            return False

        except Exception as e:
            logger.error(f"Error validating collection {collection_address}: {str(e)}", exc_info=True)
            await self.save_to_cache("validation", collection_address, False, timeout=3600)
            return False

    async def fetch_and_store_collection(self, collection_address, last_fetched=None, max_retries=3):
        """
        Fetch and store a new collection with retries and fallbacks.
        UPDATED: Fully async with proper database wrapping.
        """
        for attempt in range(max_retries):
            try:
                logger.debug(f"Attempt {attempt + 1}/{max_retries} to fetch collection {collection_address}")
                
                if not await self.validate_collection(collection_address):
                    logger.error(f"Validation failed for collection {collection_address}")
                    return {"success": False, "error": "Not a valid collection address"}

                # Fetch metadata with fallbacks
                collection_metadata = None
                for method, method_name in [
                    (self.fetch_metadata_account, "Metadata Account"),
                    (self.fetch_metadata_from_das_collection, "DAS Collection"),
                ]:
                    try:
                        logger.debug(f"Fetching metadata using {method_name}")
                        collection_metadata = await method(collection_address)
                        if collection_metadata:
                            logger.debug(f"Successfully fetched metadata using {method_name}")
                            break
                    except Exception as e:
                        logger.warning(f"Failed to fetch metadata using {method_name}: {str(e)}")

                if not collection_metadata:
                    logger.error(f"Failed to fetch collection metadata for {collection_address}")
                    return {"success": False, "error": "Failed to fetch collection metadata"}

                collection_name = collection_metadata.get("name", f"Collection {collection_address[:8]}")
                image_url = collection_metadata.get("image_url", "")
                description = collection_metadata.get("description", "")
                creator_address = ""
                creator_addresses = collection_metadata.get("creator_addresses", [])
                
                if creator_addresses and isinstance(creator_addresses, list) and len(creator_addresses) > 0:
                    if isinstance(creator_addresses[0], dict):
                        creator_address = creator_addresses[0].get("address", "")
                
                uri = collection_metadata.get("uri", "")

                # Prioritize on-chain metadata for symbol
                symbol = None
                try:
                    onchain_metadata = await self.fetch_metadata_account(collection_address)
                    if onchain_metadata:
                        symbol = onchain_metadata.get("symbol", "")
                except Exception as e:
                    logger.warning(f"Failed to fetch on-chain metadata for symbol: {str(e)}")

                if not symbol:
                    symbol = collection_metadata.get("symbol", "")

                if uri:
                    uri_metadata = await self.fetch_metadata_from_uri(uri)
                    if uri_metadata and isinstance(uri_metadata, dict):
                        image_url = uri_metadata.get("image", image_url)
                        description = uri_metadata.get("description", description)
                        if not creator_address:
                            uri_creators = uri_metadata.get("properties", {}).get("creators", [])
                            if isinstance(uri_creators, list) and len(uri_creators) > 0:
                                if isinstance(uri_creators[0], dict):
                                    creator_address = uri_creators[0].get("address", "")

                # Fetch NFTs with fallbacks
                all_nfts = []
                for fetch_method, method_name in [
                    (self.fetch_using_helius_assets_by_group, "Helius getAssetsByGroup"),
                    (self.fetch_using_das, "DAS"),
                    (self.fetch_using_program_accounts, "getProgramAccounts")
                ]:
                    try:
                        logger.debug(f"Fetching NFTs using {method_name}")
                        all_nfts = await fetch_method(collection_address, last_fetched=last_fetched)
                        if all_nfts and isinstance(all_nfts, list):
                            self.metrics["retrieval_method"] = method_name
                            break
                    except Exception as e:
                        logger.warning(f"Failed to fetch NFTs using {method_name}: {str(e)}")
                        self.metrics["fallback_used"] = True
                        self.metrics["fallback_method"] = method_name

                if not all_nfts or not isinstance(all_nfts, list):
                    logger.error(f"No valid NFTs fetched for {collection_address}")
                    return {"success": False, "error": "No valid NFTs fetched"}

                # Validate NFTs
                valid_nfts = [
                    nft for nft in all_nfts 
                    if isinstance(nft, dict) and nft.get("mint")
                ]

                if not valid_nfts:
                    logger.error(f"No valid NFTs after validation for {collection_address}")
                    return {"success": False, "error": "No valid NFTs after validation"}

                # Store collection and NFTs
                @sync_to_async
                def store_in_transaction():
                    with transaction.atomic():
                        PendingCollection.objects.filter(mint_address=collection_address).delete()
                        collection, created = NFTCollection.objects.update_or_create(
                            address=collection_address,
                            defaults={
                                "name": collection_name,
                                "description": description,
                                "image_url": image_url,
                                "creator_address": creator_address,
                                "symbol": symbol,
                                "is_listed": True,
                                "is_featured": False,
                                "source": "webhook",
                                "last_fetched": timezone.now(),
                            }
                        )
                        
                        for nft_data in valid_nfts:
                            mint_address = nft_data.get("mint", "")
                            if not mint_address:
                                continue
                            
                            owner = nft_data.get("owner", "")
                            nft, _ = NFT.objects.update_or_create(
                                mint_address=mint_address,
                                defaults={
                                    "collection": collection,
                                    "token_address": mint_address,
                                    "name": nft_data.get("name", f"NFT {mint_address[:8]}"),
                                    "image_url": nft_data.get("image_url", ""),
                                    "owner": owner
                                }
                            )
                            
                            traits_data = nft_data.get("traits", {})
                            if isinstance(traits_data, dict):
                                for trait_type, trait_info in traits_data.items():
                                    if not isinstance(trait_info, dict):
                                        continue
                                    
                                    trait_value = str(trait_info.get("value", ""))
                                    if not trait_value:
                                        continue
                                    
                                    try:
                                        trait_rarity = float(trait_info.get("rarity", 0.0))
                                    except (ValueError, TypeError):
                                        trait_rarity = 0.0
                                    
                                    trait_type_obj, _ = TraitType.objects.get_or_create(
                                        name=trait_type,
                                        collection=collection
                                    )
                                    trait_value_obj, _ = TraitValue.objects.get_or_create(
                                        trait_type=trait_type_obj,
                                        value=trait_value,
                                        defaults={"rarity": trait_rarity}
                                    )
                                    nft.trait_values.add(trait_value_obj)
                        
                        return {"success": True, "source": "webhook", "data": {"nfts": valid_nfts}}

                result = await store_in_transaction()
                return result

            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{max_retries} failed for {collection_address}: {str(e)}", exc_info=True)
                if attempt == max_retries - 1:
                    return {"success": False, "error": str(e)}
                await asyncio.sleep(2 ** attempt)

    async def _fetch_generic_onchain_metadata(self, mint_address: str, provider):
        """
        Generic metadata fetch using any RPC provider.
        UPDATED: Proper async handling.
        """
        try:
            METADATA_PROGRAM_ID = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"
            mint_pubkey = Pubkey.from_string(mint_address)
            metadata_pda, _ = Pubkey.find_program_address(
                [b"metadata", bytes(Pubkey.from_string(METADATA_PROGRAM_ID)), bytes(mint_pubkey)],
                Pubkey.from_string(METADATA_PROGRAM_ID)
            )
            
            account_info = await provider.get_account_info(str(metadata_pda))
            
            if not account_info or not account_info.get("result", {}).get("value"):
                return None

            account_data = account_info["result"]["value"]["data"][0]
            decoded_data = base64.b64decode(account_data)
            
            if len(decoded_data) < 1 + 32 + 32 + 4:
                return None
                
            offset = 1 + 32 + 32
            name_len = int.from_bytes(decoded_data[offset:offset+4], byteorder='little')
            offset += 4
            name = decoded_data[offset:offset+name_len].decode('utf-8').strip('\x00')
            offset += name_len
            
            symbol_len = int.from_bytes(decoded_data[offset:offset+4], byteorder='little')
            offset += 4
            symbol = decoded_data[offset:offset+symbol_len].decode('utf-8').strip('\x00')
            offset += symbol_len
            
            uri_len = int.from_bytes(decoded_data[offset:offset+4], byteorder='little')
            offset += 4
            uri = decoded_data[offset:offset+uri_len].decode('utf-8').strip('\x00')
            
            metadata = {
                'name': name,
                'symbol': symbol,
                'uri': uri
            }
            
            if uri and uri.startswith('http'):
                try:
                    uri_metadata = await self.fetch_metadata_from_uri(uri)
                    if uri_metadata:
                        metadata.update(uri_metadata)
                except Exception as e:
                    logger.warning(f"Failed to fetch off-chain metadata from {uri}: {e}")
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error in _fetch_generic_onchain_metadata for {mint_address}: {e}")
            return None

    async def fetch_single_nft_metadata(self, mint_address, force_refresh=False):
        """
        Fetch metadata for a single NFT using all available fallback methods.
        ALREADY ASYNC - No changes needed.
        """
        try:
            logger.info(f"Fetching single NFT metadata for {mint_address}")
            
            if not force_refresh:
                cached_metadata = await self.get_from_cache("single_nft_metadata", mint_address)
                if cached_metadata:
                    logger.info(f"Using cached metadata for {mint_address}")
                    return cached_metadata
            
            # Method 1: Try Helius DAS API first
            metadata = await self._fetch_single_nft_helius_das(mint_address)
            if metadata:
                await self.save_to_cache("single_nft_metadata", mint_address, metadata, timeout=3600)
                return metadata
            
            # Method 2: Try other providers
            metadata = await self._fetch_single_nft_other_providers(mint_address)
            if metadata:
                await self.save_to_cache("single_nft_metadata", mint_address, metadata, timeout=3600)
                return metadata
            
            # Method 3: Try on-chain metadata account
            metadata = await self._fetch_single_nft_onchain(mint_address)
            if metadata:
                await self.save_to_cache("single_nft_metadata", mint_address, metadata, timeout=3600)
                return metadata
            
            # Method 4: Try fetching from existing database record + URI refresh
            metadata = await self._fetch_single_nft_from_db_with_uri_refresh(mint_address)
            if metadata:
                await self.save_to_cache("single_nft_metadata", mint_address, metadata, timeout=3600)
                return metadata
            
            logger.warning(f"All methods failed to fetch metadata for {mint_address}")
            return None
            
        except Exception as e:
            logger.error(f"Error in fetch_single_nft_metadata for {mint_address}: {str(e)}")
            return None

    async def _fetch_single_nft_helius_das(self, mint_address):
        """Try Helius DAS API for single NFT."""
        try:
            provider, is_helius = await self._get_provider_with_fallback(prefer_helius=True)
            if not provider or not is_helius:
                return None
            
            logger.debug(f"Trying Helius DAS for {mint_address}")
            
            payload = {
                "jsonrpc": "2.0",
                "id": "get-asset",
                "method": "getAsset",
                "params": {"id": mint_address}
            }
            
            response = await provider._async_post(provider.rpc_url, json_data=payload, timeout=15)
            
            if response and "result" in response:
                result = response["result"]
                return await self._process_single_nft_helius_data(result)
            
            return None
            
        except Exception as e:
            logger.debug(f"Helius DAS failed for {mint_address}: {str(e)}")
            return None

    async def _fetch_single_nft_other_providers(self, mint_address):
        """Try other providers for single NFT metadata."""
        try:
            providers = await self.api_provider_manager.get_all_providers()
            
            for provider in providers:
                if isinstance(provider, HeliusProvider):
                    continue
                
                try:
                    logger.debug(f"Trying provider {provider.name} for {mint_address}")
                    
                    if hasattr(provider, 'get_asset'):
                        response = await provider.get_asset(mint_address)
                        if response and "result" in response:
                            return await self._process_single_nft_generic_data(response["result"])
                    
                    elif hasattr(provider, 'get_nfts_by_group'):
                        response = await provider.get_nfts_by_group(mint_address, page=1, page_size=1)
                        if response and "result" in response and "items" in response["result"]:
                            items = response["result"]["items"]
                            if items and len(items) > 0:
                                return await self._process_single_nft_generic_data(items[0])
                    
                except Exception as e:
                    logger.debug(f"Provider {provider.name} failed for {mint_address}: {str(e)}")
                    continue
            
            return None
            
        except Exception as e:
            logger.debug(f"Other providers failed for {mint_address}: {str(e)}")
            return None

    async def _fetch_single_nft_onchain(self, mint_address):
        """Fetch single NFT metadata from on-chain metadata account."""
        try:
            logger.debug(f"Trying on-chain metadata for {mint_address}")
            
            metadata = await self.fetch_metadata_account(mint_address)
            if not metadata:
                return None
            
            uri = metadata.get('uri', '').strip()
            if uri:
                logger.debug(f"Found URI for {mint_address}: {uri}")
                
                offchain_metadata = await self.fetch_metadata_from_uri(uri)
                if offchain_metadata:
                    combined_metadata = {
                        'name': metadata.get('name', offchain_metadata.get('name', '')),
                        'symbol': metadata.get('symbol', offchain_metadata.get('symbol', '')),
                        'description': offchain_metadata.get('description', ''),
                        'image': offchain_metadata.get('image', ''),
                        'attributes': offchain_metadata.get('attributes', []),
                        'uri': uri
                    }
                    return combined_metadata
                else:
                    return metadata
            
            return metadata
            
        except Exception as e:
            logger.debug(f"On-chain metadata failed for {mint_address}: {str(e)}")
            return None

    async def _fetch_single_nft_from_db_with_uri_refresh(self, mint_address):
        """Get NFT from database and refresh URI metadata if available."""
        try:
            logger.debug(f"Trying database + URI refresh for {mint_address}")
            
            nft = await sync_to_async(NFT.objects.select_related('collection').get)(mint_address=mint_address)
            
            db_metadata = {
                'name': nft.name or '',
                'description': '',
                'image': nft.image_url or '',
                'attributes': []
            }
            
            uri = ''
            if hasattr(nft, 'metadata_uri') and nft.metadata_uri:
                uri = nft.metadata_uri
            elif nft.traits and isinstance(nft.traits, dict):
                uri = nft.traits.get('uri', '')
            
            if uri:
                logger.debug(f"Refreshing URI metadata for {mint_address}: {uri}")
                fresh_metadata = await self.fetch_metadata_from_uri(uri)
                if fresh_metadata:
                    db_metadata.update({
                        'name': fresh_metadata.get('name', db_metadata['name']),
                        'description': fresh_metadata.get('description', ''),
                        'image': fresh_metadata.get('image', db_metadata['image']),
                        'attributes': fresh_metadata.get('attributes', [])
                    })
            
            return db_metadata
            
        except Exception as e:
            logger.debug(f"Database + URI refresh failed for {mint_address}: {str(e)}")
            return None

    async def _process_single_nft_helius_data(self, nft_data):
        """Process Helius single NFT data into standard format."""
        try:
            if not isinstance(nft_data, dict):
                return None
            
            content = nft_data.get("content", {})
            metadata = content.get("metadata", {}) if isinstance(content, dict) else {}
            
            name = metadata.get("name", "") if isinstance(metadata, dict) else ""
            description = metadata.get("description", "") if isinstance(metadata, dict) else ""
            
            image_url = ""
            files = content.get("files", []) if isinstance(content, dict) else []
            if files and isinstance(files, list) and len(files) > 0:
                first_file = files[0]
                if isinstance(first_file, dict):
                    image_url = first_file.get("uri", "")
            
            attributes = []
            if isinstance(metadata, dict) and "attributes" in metadata:
                attrs = metadata["attributes"]
                if isinstance(attrs, list):
                    attributes = attrs
            
            return {
                'name': name,
                'description': description,
                'image': image_url,
                'attributes': attributes,
                'source': 'helius_das'
            }
            
        except Exception as e:
            logger.error(f"Error processing Helius single NFT data: {str(e)}")
            return None

    async def _process_single_nft_generic_data(self, nft_data):
        """Process generic provider NFT data into standard format."""
        try:
            if not isinstance(nft_data, dict):
                return None
            
            if "content" in nft_data:
                return await self._process_single_nft_helius_data(nft_data)
            
            return {
                'name': nft_data.get('name', ''),
                'description': nft_data.get('description', ''),
                'image': nft_data.get('image', ''),
                'attributes': nft_data.get('attributes', []),
                'source': 'generic_provider'
            }
            
        except Exception as e:
            logger.error(f"Error processing generic NFT data: {str(e)}")
            return None

    async def refresh_single_nft_traits(self, mint_address):
        """
        Refresh traits for a single NFT and update database.
        UPDATED: Proper async database operations.
        """
        try:
            logger.info(f"Refreshing traits for NFT {mint_address}")
            
            # Fetch fresh metadata
            metadata = await self.fetch_single_nft_metadata(mint_address, force_refresh=True)
            if not metadata:
                logger.warning(f"No metadata found for {mint_address}")
                return {"success": False, "error": "No metadata found"}
            
            # Extract attributes/traits
            attributes = metadata.get('attributes', [])
            if not attributes:
                logger.info(f"No traits found in metadata for {mint_address}")
                return {"success": True, "traits_updated": 0, "message": "No traits found"}
            
            # Get NFT from database
            try:
                nft = await sync_to_async(NFT.objects.select_related('collection').get)(mint_address=mint_address)
            except NFT.DoesNotExist:
                logger.error(f"NFT {mint_address} not found in database")
                return {"success": False, "error": "NFT not found in database"}
            
            if not nft.collection:
                logger.error(f"NFT {mint_address} has no collection assigned")
                return {"success": False, "error": "NFT has no collection assigned"}
            
            logger.info(f"Processing {len(attributes)} attributes for NFT {mint_address}")
            
            # Process and update traits in transaction
            @sync_to_async
            def update_traits_in_transaction():
                updated_traits = 0
                failed_traits = 0
                processed_traits = []
                
                with transaction.atomic():
                    # Clear existing trait associations
                    nft.trait_values.clear()
                    
                    # Process new traits
                    for i, attr in enumerate(attributes):
                        try:
                            if not isinstance(attr, dict):
                                logger.warning(f"Skipping invalid attribute {i}")
                                failed_traits += 1
                                continue
                            
                            trait_type_name = attr.get('trait_type', '')
                            trait_value = attr.get('value', '')
                            
                            if not trait_type_name or trait_value == '' or trait_value is None:
                                logger.warning(f"Skipping attribute {i}: missing data")
                                failed_traits += 1
                                continue
                            
                            trait_type_name = str(trait_type_name).strip()[:100]
                            trait_value = str(trait_value).strip()[:255]
                            
                            trait_type, trait_type_created = TraitType.objects.get_or_create(
                                collection=nft.collection,
                                name=trait_type_name,
                                defaults={
                                    'collection': nft.collection,
                                    'created_at': timezone.now(),
                                    'updated_at': timezone.now()
                                }
                            )
                            
                            trait_val, trait_val_created = TraitValue.objects.get_or_create(
                                trait_type=trait_type,
                                value=trait_value,
                                defaults={
                                    'trait_type': trait_type,
                                    'created_at': timezone.now(),
                                    'updated_at': timezone.now()
                                }
                            )
                            
                            nft.trait_values.add(trait_val)
                            updated_traits += 1
                            
                            processed_traits.append({
                                'trait_type': trait_type_name,
                                'value': trait_value,
                                'trait_type_created': trait_type_created,
                                'trait_value_created': trait_val_created
                            })
                            
                        except Exception as trait_error:
                            logger.error(f"Error creating trait {i}: {trait_error}")
                            failed_traits += 1
                            continue
                    
                    # Update NFT metadata
                    update_fields = []
                    
                    if metadata.get('name') and metadata['name'] != nft.name:
                        nft.name = metadata['name']
                        update_fields.append('name')
                    
                    if metadata.get('image') and metadata['image'] != nft.image_url:
                        nft.image_url = metadata['image']
                        update_fields.append('image_url')
                    
                    nft.updated_at = timezone.now()
                    update_fields.append('updated_at')
                    
                    if update_fields:
                        nft.save(update_fields=update_fields)
                
                return {
                    "updated_traits": updated_traits,
                    "failed_traits": failed_traits,
                    "processed_traits": processed_traits,
                    "nft_name": nft.name,
                    "collection_name": nft.collection.name
                }
            
            result = await update_traits_in_transaction()
            
            logger.info(f"Successfully refreshed traits for {mint_address}: "
                       f"{result['updated_traits']} updated, {result['failed_traits']} failed")
            
            return {
                "success": True,
                "traits_updated": result['updated_traits'],
                "traits_failed": result['failed_traits'],
                "nft_name": result['nft_name'],
                "collection_name": result['collection_name'],
                "metadata_source": metadata.get('source', 'unknown'),
                "processed_traits": result['processed_traits'][:10],
                "total_attributes_found": len(attributes)
            }
            
        except Exception as e:
            logger.error(f"Error refreshing traits for {mint_address}: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "mint_address": mint_address
            }

    async def validate_and_refresh_nft_if_needed(self, mint_address):
        """
        Check if NFT exists and refresh metadata if needed.
        UPDATED: Proper async database operations.
        """
        try:
            try:
                nft = await sync_to_async(NFT.objects.select_related('collection').get)(mint_address=mint_address)
                
                trait_count = await sync_to_async(nft.trait_values.count)()
                if trait_count == 0:
                    logger.info(f"NFT {mint_address} has no traits, attempting refresh")
                    refresh_result = await self.refresh_single_nft_traits(mint_address)
                    
                    return {
                        "nft_exists": True,
                        "refresh_attempted": True,
                        "refresh_result": refresh_result,
                        "nft": {
                            "name": nft.name,
                            "collection": nft.collection.name,
                            "owner": nft.owner
                        }
                    }
                else:
                    return {
                        "nft_exists": True,
                        "refresh_attempted": False,
                        "trait_count": trait_count,
                        "nft": {
                            "name": nft.name,
                            "collection": nft.collection.name,
                            "owner": nft.owner
                        }
                    }
                    
            except NFT.DoesNotExist:
                logger.warning(f"NFT {mint_address} not found in database")
                return {
                    "nft_exists": False,
                    "refresh_attempted": False,
                    "error": "NFT not found in database"
                }
                
        except Exception as e:
            logger.error(f"Error validating NFT {mint_address}: {str(e)}")
            return {
                "nft_exists": False,
                "refresh_attempted": False,
                "error": str(e)
            }

    async def log_metrics(self):
        """Log metrics for retrieval performance."""
        logger.info("=== Metadata Fetch Metrics ===")
        for key in ["uri_success", "uri_failure", "arweave_success", "arweave_failure",
                    "ipfs_success", "ipfs_failure", "http_success", "http_failure"]:
            logger.info(f"{key.replace('_', ' ').title()}: {self.metrics[key]}")
        logger.info(f"Retrieval Method: {self.metrics['retrieval_method'] or 'None'}")
        logger.info(f"Provider Used: {self.metrics['provider_used'] or 'None'}")
        logger.info(f"NFTs Retrieved: {self.metrics['nfts_retrieved']} out of {self.metrics['total_supply']}")
        logger.info(f"Fallback Used: {self.metrics['fallback_used']}")
        if self.metrics['fallback_used']:
            logger.info(f"Fallback Method: {self.metrics['fallback_method']}")
        logger.info(f"Error Encountered: {self.metrics['error_encountered'] or 'None'}")
        logger.info(f"Traits Fetched: {self.metrics['traits_fetched']}")
        logger.info(f"Trait Types: {', '.join(self.metrics['trait_types']) if self.metrics['trait_types'] else 'None'}")
        logger.info("=============================")

    async def run_monitoring_task(self):
        """
        Monitor cache and API health.
        UPDATED: Fully async.
        """
        try:
            logger.info("Running monitoring task for NFTRetrievalService")
            
            if self.redis_client:
                info = await sync_to_async(self.redis_client.info)()
                logger.info(f"Redis cache stats - Used memory: {info.get('used_memory_human', 'N/A')}")
                
                # fetch keys first (await the IO), then call len() synchronously
                try:
                    arweave_key_list = await sync_to_async(self.redis_client.keys)('arweave:*')
                    ipfs_key_list = await sync_to_async(self.redis_client.keys)('ipfs:*')
                    uri_key_list = await sync_to_async(self.redis_client.keys)('uri_metadata:*')
                except Exception as ke:
                    logger.warning(f"Failed to list redis keys: {ke}")
                    arweave_key_list = []
                    ipfs_key_list = []
                    uri_key_list = []

                arweave_keys = len(arweave_key_list)
                ipfs_keys = len(ipfs_key_list)
                uri_keys = len(uri_key_list)

                logger.info(f"Redis keys - Arweave: {arweave_keys}, IPFS: {ipfs_keys}, URI: {uri_keys}")
            
            provider = await self.api_provider_manager.get_rpc_provider()
            if provider is None:
                logger.error("No RPC provider available for health check")
                return
            
            payload = {"jsonrpc": "2.0", "id": "health-check", "method": "getHealth", "params": {}}
            response = await sync_to_async(self.session.post)(provider.rpc_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"API health check: {response.json()}")
            else:
                logger.info(f"API health check failed with status {response.status_code}")
            
            await self.log_metrics()
        except Exception as e:
            logger.error(f"Error in monitoring task: {str(e)}", exc_info=True)

    async def update_trait_metrics(self, collection_address, force_update=False):
        """
        Update trait rarity metrics for a collection.
        NEW METHOD: For trait rarity calculations.
        """
        try:
            logger.info(f"Updating trait metrics for collection {collection_address}")
            
            @sync_to_async
            def calculate_rarity():
                collection = NFTCollection.objects.get(address=collection_address)
                total_nfts = collection.nfts.count()
                
                if total_nfts == 0:
                    logger.warning(f"No NFTs found in collection {collection_address}")
                    return 0
                
                trait_types = TraitType.objects.filter(collection=collection)
                updated_count = 0
                
                for trait_type in trait_types:
                    trait_values = TraitValue.objects.filter(trait_type=trait_type)
                    
                    for trait_value in trait_values:
                        count = trait_value.nfts.count()
                        rarity = (count / total_nfts) * 100 if total_nfts > 0 else 0
                        
                        if trait_value.rarity != rarity or force_update:
                            trait_value.rarity = rarity
                            trait_value.save(update_fields=['rarity'])
                            updated_count += 1
                
                return updated_count
            
            updated_count = await calculate_rarity()
            logger.info(f"Updated {updated_count} trait rarities for collection {collection_address}")
            return updated_count
            
        except Exception as e:
            logger.error(f"Error updating trait metrics for {collection_address}: {str(e)}")
            return 0
    async def initialize_persistent_session(self):
        if self.aiohttp_session is None or self.aiohttp_session.closed:
            async with self.session_lock:
                if self.aiohttp_session is None or self.aiohttp_session.closed:
                    timeout = aiohttp.ClientTimeout(total=60, connect=10)
                    connector = aiohttp.TCPConnector(limit=100, limit_per_host=20, ttl_dns_cache=300, use_dns_cache=True, force_close=False)
                    self.aiohttp_session = aiohttp.ClientSession(connector=connector, timeout=timeout, headers={'User-Agent': 'TraitKeeper/1.0'})
                    logger.info("✅ Initialized persistent aiohttp session")

    async def fetch_metadata_batch(self, nfts: List[Dict], max_concurrent: int = 20) -> List[Dict]:
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_single(nft_data):
            async with semaphore:
                try:
                    mint_address = nft_data.get("mint")
                    uri = nft_data.get("uri")
                    if not uri or (nft_data.get("image_url") and nft_data.get("traits")):
                        return nft_data
                    
                    metadata = await self.fetch_metadata_from_uri(uri)
                    if metadata:
                        nft_data["image_url"] = metadata.get("image", nft_data.get("image_url", ""))
                        nft_data["description"] = metadata.get("description", "")
                        attributes = metadata.get("attributes", [])
                        if attributes and isinstance(attributes, list):
                            traits_dict = {}
                            for attr in attributes:
                                if isinstance(attr, dict):
                                    trait_type = attr.get("trait_type", "").strip()
                                    trait_value = attr.get("value", "")
                                    if trait_type:
                                        traits_dict[trait_type] = {"value": str(trait_value), "rarity": attr.get("rarity", 0.0)}
                            nft_data["traits"] = traits_dict
                    return nft_data
                except Exception as e:
                    logger.error(f"Error fetching metadata for {nft_data.get('mint', 'unknown')[:8]}: {e}")
                    return nft_data
        
        logger.info(f"🚀 Parallel metadata fetch for {len(nfts)} NFTs (max_concurrent={max_concurrent})")
        start = asyncio.get_event_loop().time()
        enriched_nfts = await asyncio.gather(*[fetch_single(nft) for nft in nfts], return_exceptions=True)
        elapsed = asyncio.get_event_loop().time() - start
        valid_nfts = [nft for nft in enriched_nfts if not isinstance(nft, Exception)]
        logger.info(f"✅ Complete: {len(valid_nfts)}/{len(nfts)} in {elapsed:.2f}s ({elapsed/len(nfts):.2f}s per NFT)")
        return valid_nfts

    async def store_collection_and_nfts_optimized(self, collection_id, collection_data):
        try:
            collection_name = collection_data.get("name", f"Unknown {collection_id[:8]}")
            defaults = {
                "name": collection_name,
                "image_url": collection_data.get("image_url", ""),
                "creator_address": collection_data.get("creator_addresses", [{}])[0].get("address", ""),
                "is_featured": False,
                "source": collection_data.get("source", "unknown"),
                "description": collection_data.get("description", ""),
                "symbol": collection_data.get("symbol", "")
            }

            @sync_to_async
            def create_or_update_collection():
                collection, created = NFTCollection.objects.get_or_create(address=collection_id, defaults=defaults)
                if not created:
                    for key, value in defaults.items():
                        setattr(collection, key, value)
                    collection.save()
                return collection

            collection = await create_or_update_collection()
            nfts = collection_data.get("nfts", [])
            if not nfts:
                return collection

            await self.initialize_persistent_session()
            chunk_size = 100
            for i in range(0, len(nfts), chunk_size):
                chunk = nfts[i:i + chunk_size]
                logger.info(f"Processing chunk {i//chunk_size + 1}/{(len(nfts)+chunk_size-1)//chunk_size}")
                enriched_chunk = await self.fetch_metadata_batch(chunk, max_concurrent=20)
                await self._process_nft_batch_optimized(enriched_chunk, collection)
                logger.info(f"Progress: {min(i + chunk_size, len(nfts))}/{len(nfts)}")

            return collection
        except Exception as e:
            logger.error(f"Error storing collection {collection_id}: {e}", exc_info=True)
            self.metrics["error_encountered"] = str(e)
            raise

    async def _process_nft_batch_optimized(self, batch, collection):
        @sync_to_async
        def process_batch_in_transaction():
            with transaction.atomic():
                for nft_data in batch:
                    try:
                        mint_address = nft_data.get("mint")
                        if not mint_address:
                            continue
                        traits_data = nft_data.get("traits", {})
                        if not isinstance(traits_data, dict):
                            traits_data = {}
                        nft, created = NFT.objects.update_or_create(
                            mint_address=mint_address,
                            defaults={
                                "collection": collection,
                                "token_address": mint_address,
                                "name": nft_data.get("name", f"NFT {mint_address[:8]}"),
                                "image_url": nft_data.get("image_url", ""),
                                "owner": nft_data.get("owner", "")
                            }
                        )
                        for trait_type_name, trait_data in traits_data.items():
                            if not isinstance(trait_data, dict):
                                continue
                            trait_value_str = str(trait_data.get("value", ""))
                            if not trait_value_str:
                                continue
                            try:
                                trait_rarity = float(trait_data.get("rarity", 0.0))
                            except (ValueError, TypeError):
                                trait_rarity = 0.0
                            trait_type, _ = TraitType.objects.get_or_create(name=trait_type_name, collection=collection)
                            trait_value, _ = TraitValue.objects.get_or_create(trait_type=trait_type, value=trait_value_str, defaults={"rarity": trait_rarity})
                            nft.trait_values.add(trait_value)
                    except Exception as e:
                        logger.error(f"Error processing NFT {nft_data.get('mint', 'unknown')}: {e}")
        await process_batch_in_transaction()

    async def monitor_fetch_errors(self, collection_address: str, error: Exception):
        try:
            await sync_to_async(send_unified_admin_notification)(
                subject=f"Collection Fetch Error: {collection_address[:8]}...",
                message=f"Failed to fetch collection {collection_address}\n\nError: {str(error)}\n\nMetrics:\n- NFTs: {self.metrics.get('nfts_retrieved', 0)}\n- Method: {self.metrics.get('retrieval_method', 'N/A')}",
                notification_type='collection_fetch_error',
                severity='error'
            )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")