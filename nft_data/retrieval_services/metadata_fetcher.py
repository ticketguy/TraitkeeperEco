# nft_data/retrieval_services/metadata_fetcher.py

import logging
import asyncio
import aiohttp
import re
import os
import json
import base64
import hashlib
import string
from typing import Optional, Dict
from solders.pubkey import Pubkey

logger = logging.getLogger(__name__)

class MetadataFetcher:
    """Handles fetching and parsing of on-chain and off-chain metadata for a single asset."""

    def __init__(self, cache_service, metrics, provider_manager):
        self.cache_service = cache_service
        self.metrics = metrics
        self.provider_manager = provider_manager
        self.pinata_token = os.getenv('PINATA_GATEWAY_TOKEN')
        
        self.arweave_gateways = [
            "https://arweave.net/",
            "https://arweave.dev/",
            "https://gateway.arweave.net/"
        ]
        
        self.ipfs_gateways = [
            "https://nftstorage.link/ipfs/",
            "https://cloudflare-ipfs.com/ipfs/",
            "https://ipfs.io/ipfs/",
            "https://dweb.link/ipfs/",
            "https://gateway.pinata.cloud/ipfs/",
            "https://black-rational-cod-281.mypinata.cloud/ipfs/",
            "https://ipfs.infura.io/ipfs/",
        ]
        
        logger.info(f"🔧 MetadataFetcher initialized")
        logger.info(f"   - Arweave gateways: {len(self.arweave_gateways)}")
        logger.info(f"   - IPFS gateways: {len(self.ipfs_gateways)}")
        logger.info(f"   - Pinata token: {'configured' if self.pinata_token else 'not configured'}")

    async def get_gateway_headers(self, gateway_url: str) -> Dict:
        """Gets appropriate headers for a given gateway URL."""
        headers = {
            'User-Agent': 'TraitKeeper/1.0',
            'Accept': 'application/json, application/octet-stream, */*'
        }
        if "black-rational-cod-281.mypinata.cloud" in gateway_url and self.pinata_token:
            headers['Authorization'] = f'Bearer {self.pinata_token}'
        return headers

    async def fetch_from_arweave(self, uri: str, session: aiohttp.ClientSession) -> Optional[Dict]:
        """Fetches data from Arweave, trying multiple gateways."""
        logger.debug(f"   🌐 Attempting Arweave fetch for: {uri[:50]}...")
        
        for gateway_idx, gateway in enumerate(self.arweave_gateways, 1):
            try:
                arweave_url = uri.replace("https://arweave.net/", gateway)
                logger.debug(f"      Gateway {gateway_idx}/{len(self.arweave_gateways)}: {gateway}")
                
                async with session.get(arweave_url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug(f"      ✅ Arweave success on gateway {gateway_idx}")
                        return data
                    else:
                        logger.debug(f"      ⚠️ Gateway returned status {response.status}")
                        
            except Exception as e:
                logger.debug(f"      ❌ Gateway {gateway_idx} failed: {e}")
                continue
        
        logger.debug(f"   ❌ All Arweave gateways failed")
        return None

    async def fetch_metadata_from_uri(self, uri: str, session: aiohttp.ClientSession, max_attempts: int = 2) -> Optional[Dict]:
        """Fetches and parses metadata from a given URI (IPFS, HTTP, etc.)."""
        if not uri or not isinstance(uri, str):
            logger.debug(f"   ⚠️ Invalid URI: {uri}")
            return None
        
        uri = uri.strip().rstrip('\x00').rstrip('{}[]()<>;:,')
        if not uri:
            logger.debug(f"   ⚠️ Empty URI after cleaning")
            return None
        
        # Check cache first
        cache_key_hash = hashlib.md5(uri.encode()).hexdigest()
        cached_data = await self.cache_service.get_from_cache("uri_metadata", cache_key_hash)
        if cached_data:
            logger.debug(f"   💾 Cache hit for URI: {uri[:30]}...")
            return cached_data

        logger.debug(f"   🌐 Fetching URI: {uri[:50]}...")
        
        for attempt in range(max_attempts):
            try:
                # Arweave Handling
                if 'arweave.net' in uri.lower() or 'arweave.dev' in uri.lower():
                    logger.debug(f"   📡 Detected Arweave URI (attempt {attempt + 1}/{max_attempts})")
                    data = await self.fetch_from_arweave(uri, session)
                    if data:
                        await self.cache_service.save_to_cache("uri_metadata", cache_key_hash, data)
                        logger.debug(f"   ✅ Arweave fetch successful")
                        return data

                # IPFS Handling
                elif 'ipfs' in uri.lower():
                    logger.debug(f"   📡 Detected IPFS URI (attempt {attempt + 1}/{max_attempts})")
                    ipfs_path_match = re.search(r'ipfs/([a-zA-Z0-9]+(?:/[^?\s]*)?)', uri)
                    ipfs_path = ipfs_path_match.group(1) if ipfs_path_match else None
                    
                    if not ipfs_path:
                        logger.debug(f"   ⚠️ Could not extract IPFS path from URI")
                        continue

                    logger.debug(f"   IPFS path: {ipfs_path[:50]}...")
                    
                    for gateway_idx, gateway in enumerate(self.ipfs_gateways, 1):
                        ipfs_url = f"{gateway.rstrip('/')}/{ipfs_path}"
                        headers = await self.get_gateway_headers(gateway)
                        
                        try:
                            logger.debug(f"      Gateway {gateway_idx}/{len(self.ipfs_gateways)}: {gateway[:30]}...")
                            
                            async with session.get(ipfs_url, headers=headers, timeout=30) as response:
                                if response.status == 200:
                                    data = await response.json(content_type=None)
                                    if isinstance(data, dict):
                                        await self.cache_service.save_to_cache("uri_metadata", cache_key_hash, data)
                                        logger.debug(f"      ✅ IPFS success on gateway {gateway_idx}")
                                        return data
                                else:
                                    logger.debug(f"      ⚠️ Gateway returned status {response.status}")
                                    
                        except Exception as e:
                            logger.debug(f"      ❌ Gateway {gateway_idx} failed: {str(e)[:50]}")
                            continue
                    
                    logger.debug(f"   ❌ All IPFS gateways failed")

                # Standard HTTP Handling
                else:
                    logger.debug(f"   📡 Standard HTTP fetch (attempt {attempt + 1}/{max_attempts})")
                    async with session.get(uri, timeout=30) as response:
                        if response.status == 200:
                            data = await response.json(content_type=None)
                            if isinstance(data, dict):
                                await self.cache_service.save_to_cache("uri_metadata", cache_key_hash, data)
                                logger.debug(f"   ✅ HTTP fetch successful")
                                return data
                        else:
                            logger.debug(f"   ⚠️ HTTP returned status {response.status}")
                
            except Exception as e:
                logger.warning(f"   ❌ URI fetch attempt {attempt + 1} failed: {str(e)[:100]}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(1 * (attempt + 1))
        
        logger.debug(f"   ❌ All attempts failed for URI")
        return None

    async def fetch_metadata_account(self, mint_address):
        """
        Fetch metadata from Solana Metadata Account.
        """
        logger.info(f"🔍 Fetching metadata account for: {mint_address[:16]}...")
        
        try:
            # Check cache first
            cached_metadata = await self.cache_service.get_from_cache("metadata_account", mint_address)
            if cached_metadata:
                logger.info(f"   💾 Cache hit for {mint_address[:8]}...")
                return cached_metadata

            # Derive PDA
            METAPLEX_PROGRAM_ID = Pubkey.from_string("metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s")
            mint_pubkey = Pubkey.from_string(mint_address)
            metadata_pda, _ = Pubkey.find_program_address(
                [b"metadata", bytes(METAPLEX_PROGRAM_ID), bytes(mint_pubkey)],
                METAPLEX_PROGRAM_ID
            )
            
            logger.debug(f"   📍 Metadata PDA: {str(metadata_pda)}")

            # Get provider
            provider = await self.provider_manager.get_rpc_provider()
            if provider is None:
                logger.error(f"   ❌ No RPC provider available")
                return None
            
            logger.debug(f"   🔗 Using provider: {provider.name}")
            
            # Fetch account info
            data = await provider.get_account_info(str(metadata_pda))
            
            if not data.get("result", {}).get("value"):
                logger.warning(f"   ⚠️ No metadata account found (likely cNFT or non-Metaplex)")
                return None

            logger.debug(f"   ✅ Metadata account found, parsing...")
            
            # Decode account data
            account_data = data["result"]["value"]["data"][0]
            decoded_data = base64.b64decode(account_data)
            logger.debug(f"   📊 Decoded data length: {len(decoded_data)} bytes")
            
            # Parse on-chain data
            name = ''.join(char for char in decoded_data[64:96].decode('utf-8', errors='replace').rstrip('\x00') if char in string.printable)
            if not name:
                name = f"Unknown {mint_address[:8]}"
                logger.debug(f"   ⚠️ Empty name field, using default")
            else:
                logger.debug(f"   📛 Name: {name}")
            
            symbol = ''.join(char for char in decoded_data[96:106].decode('utf-8', errors='replace').rstrip('\x00') if char in string.printable)
            logger.debug(f"   🏷️ Symbol: {symbol}")
            
            uri = ''.join(char for char in decoded_data[128:328].decode('utf-8', errors='replace').rstrip('\x00:;,.') if char in string.printable)
            logger.debug(f"   🌐 URI: {uri[:50]}...")

            image_url = ""
            description = ""
            creator_addresses = []
            collection = None
            
            # Parse creators
            if len(decoded_data) > 329 and decoded_data[328] == 1:
                num_creators = decoded_data[329]
                logger.debug(f"   👥 Found {num_creators} creator(s)")
                
                for i in range(num_creators):
                    creator_start = 330 + (i * 34)
                    if creator_start + 34 > len(decoded_data):
                        break
                    creator_address = str(Pubkey(decoded_data[creator_start:creator_start + 32]))
                    verified = decoded_data[creator_start + 32] == 1
                    share = decoded_data[creator_start + 33]
                    creator_addresses.append({"address": creator_address, "verified": verified, "share": share})
                    logger.debug(f"      Creator {i+1}: {creator_address[:16]}... (verified: {verified}, share: {share}%)")
                
                # Parse collection
                collection_offset = 329 + (num_creators * 34)
                if len(decoded_data) > collection_offset + 34 and decoded_data[collection_offset] == 1:
                    collection_key = str(Pubkey(decoded_data[collection_offset + 1:collection_offset + 33]))
                    collection_verified = decoded_data[collection_offset + 33] == 1
                    collection = {"key": collection_key, "verified": collection_verified}
                    logger.info(f"   📦 Collection: {collection_key[:16]}... (verified: {collection_verified})")
                else:
                    logger.warning(f"   ⚠️ No collection field in metadata account")
            else:
                logger.warning(f"   ⚠️ No creator section in metadata account")

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
            await self.cache_service.save_to_cache("metadata_account", mint_address, metadata, timeout=1800)
            logger.info(f"   ✅ Metadata parsed successfully (collection: {bool(collection)})")
            return metadata

        except Exception as e:
            logger.error(f"   ❌ Failed to fetch metadata for {mint_address[:8]}...: {str(e)}", exc_info=True)
            return None

    async def fetch_metadata_from_das_collection(self, collection_id: str) -> Optional[Dict]:
        """Fetches collection metadata using Helius DAS API."""
        logger.info(f"🔍 Fetching DAS collection metadata for: {collection_id[:16]}...")
        
        try:
            provider, is_helius = await self.provider_manager.get_provider_with_fallback(prefer_helius=True)
            if not provider or not is_helius:
                logger.warning(f"   ⚠️ Helius provider not available for DAS")
                return None

            logger.debug(f"   📡 Calling DAS API...")
            data = await provider.get_das_collection(collection_id)
            
            if not data or "result" not in data:
                logger.warning(f"   ⚠️ No result from DAS API")
                return None
            
            result = data["result"]
            content = result.get("content", {})
            metadata_content = content.get("metadata", {})
            
            logger.debug(f"   📊 Parsing DAS response...")
            
            name = metadata_content.get("name", "")
            symbol = metadata_content.get("symbol", "")
            description = metadata_content.get("description", "")
            
            logger.debug(f"   📛 Name: {name}")
            logger.debug(f"   🏷️ Symbol: {symbol}")
            
            image_url = ""
            files = content.get("files", [])
            if files and isinstance(files, list):
                image_url = files[0].get("uri", "")
                logger.debug(f"   🖼️ Image URL: {image_url[:50]}...")
            else:
                logger.debug(f"   ⚠️ No files/image found in DAS response")

            metadata = {
                "name": name,
                "symbol": symbol,
                "image_url": image_url,
                "description": description,
                "creator_addresses": result.get("creators", []),
                "uri": content.get("json_uri", "")
            }
            
            logger.info(f"   ✅ DAS metadata fetched successfully")
            return metadata
            
        except Exception as e:
            logger.error(f"   ❌ Error fetching DAS collection metadata: {e}", exc_info=True)
            return None