# indexer/api_provider/api_providers.py
import asyncio
import logging
import os
import websockets
from websockets import ConnectionClosed
import json
import importlib
import threading
from typing import List, Dict, Optional, Callable
from django.conf import settings
from django.core.cache import cache
from asgiref.sync import sync_to_async
from django.utils.functional import cached_property
from admin_panel.models import PrimaryProviderSetting
from indexer.quota_manager import ProviderQuotaManager

logger = logging.getLogger(__name__)


class APIProviderManager:
    """
    Manages multiple Solana RPC providers, handling dynamic loading, availability checks,
    failover, and WebSocket subscriptions. Acts as the control station.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        logger.info(f"Initializing APIProviderManager in thread {threading.current_thread().name}")
        self.current_provider = None
        self.quota_manager = ProviderQuotaManager(self)
        
        # ✅ Add manual caching attributes to avoid re-querying the database
        self._rpc_providers_cache = None
        self._primary_provider_name_cache = None
        self._initialized = True

    @cached_property
    def _provider_classes(self) -> Dict:
        """ ✅ UNCHANGED: Lazily loads provider classes from files. No DB access. """
        provider_dir = os.path.join(os.path.dirname(__file__))
        provider_classes = {}
        for filename in os.listdir(provider_dir):
            if filename.endswith('_provider.py') and filename != 'base.py':
                provider_name = filename[:-12]
                module_name = f"core.api_provider.{provider_name}_provider"
                try:
                    module = importlib.import_module(module_name)
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and hasattr(attr, '__bases__') and any(
                            'SolanaRPCProvider' in str(base) for base in attr.__bases__
                        ):
                            provider_classes[provider_name] = attr
                            logger.debug(f"Loaded provider class {attr_name} for {provider_name}")
                            break
                except ImportError as e:
                    logger.error(f"Failed to import provider module {module_name}: {e}")
                    continue
        return provider_classes

    async def get_rpc_providers(self) -> Dict:
        if self._rpc_providers_cache is not None:
            return self._rpc_providers_cache

        logger.info("First-time access: Initializing providers from database...")
        
        @sync_to_async
        def _get_providers_from_db():
            initialized_providers = {}
            provider_settings = PrimaryProviderSetting.objects.filter(is_active=True)
            for provider_setting in provider_settings:
                provider_name = provider_setting.name.lower()
                if provider_name in self._provider_classes:
                    try:
                        instance = self._provider_classes[provider_name](
                            rpc_url=provider_setting.rpc_url,
                            api_key=provider_setting.api_key
                        )
                        initialized_providers[provider_name] = instance
                        logger.info(f"Initialized provider {provider_name}")
                    except Exception as e:
                        logger.error(f"Failed to initialize {provider_name}: {e}")
            return initialized_providers

        self._rpc_providers_cache = await _get_providers_from_db()
        return self._rpc_providers_cache

    async def get_primary_provider_name(self) -> Optional[str]:
        if self._primary_provider_name_cache is not None:
            return self._primary_provider_name_cache

        logger.info("First-time access: Fetching primary provider from database...")
        
        @sync_to_async
        def _get_primary_name_from_db():
            try:
                primary_setting = PrimaryProviderSetting.objects.get(is_primary=True, is_active=True)
                logger.info(f"🔧 Primary provider set to: {primary_setting.name.lower()}")
                return primary_setting.name.lower()
            except PrimaryProviderSetting.DoesNotExist:
                logger.warning("⚠️ No primary provider configured in database.")
                return None

        self._primary_provider_name_cache = await _get_primary_name_from_db()
        return self._primary_provider_name_cache

    async def get_rpc_provider(self, collection_address: Optional[str] = None, priority_tier: str = 'ACTIVE'):
        """ Finds and returns a single, usable provider. """
        for provider in await self.get_all_providers():
            if await provider.check_availability():
                wrapped_provider = await self.quota_manager.get_wrapped_provider_if_quota_available(
                    provider,
                    priority_tier
                )
                if wrapped_provider:
                    self.current_provider = wrapped_provider
                    return wrapped_provider
        
        logger.error("No available provider with sufficient quota was found.")
        self.current_provider = None
        return None

    async def get_all_providers(self) -> list:
        primary_name = await self.get_primary_provider_name()
        
        primary_provider = None
        other_providers = []
        
        rpc_providers_dict = await self.get_rpc_providers()
        for name, provider_instance in rpc_providers_dict.items():
            if name == primary_name:
                primary_provider = provider_instance
            else:
                other_providers.append(provider_instance)
        
        sorted_providers = []
        if primary_provider:
            sorted_providers.append(primary_provider)
        sorted_providers.extend(other_providers)
        
        if primary_name:
            logger.debug(f"Provider order set with '{primary_name}' as primary.")
            
        return sorted_providers

    async def get_provider_by_name(self, name: str):
            """
            Gets a SPECIFIC provider by name, only if it's active and available.
            """
            all_providers = await self.get_rpc_providers()
            provider = all_providers.get(name.lower())

            if not provider:
                logger.warning(f"Provider '{name}' not found or is not active.")
                return None

            if await provider.check_availability():
                # You can add quota checks here if needed
                logger.info(f"Successfully retrieved specific provider: {name}")
                return provider
            
            logger.warning(f"Provider '{name}' was found but is not available.")
            return None

    async def get_current_provider_name(self) -> str:
        """Get the name of the current active provider."""
        if self.current_provider:
            return self.current_provider.name
        
        provider = await self.get_rpc_provider()
        return provider.name if provider else "None"

    def force_reload(self):
            """Clears the internal cache to force a re-query from the database."""
            logger.info("🔄 Forcing reload of provider configuration due to external signal.")
            self._rpc_providers_cache = None
            self._primary_provider_name_cache = None

    async def subscribe_to_programs(self, program_ids: List[str], process_log_callback: Callable):
        """
        Establishes and maintains a persistent WebSocket subscription.
        Runs forever with automatic reconnection.
        """
        logger.info("=" * 80)
        logger.info("WEBSOCKET SUBSCRIPTION MANAGER STARTED")
        logger.info("=" * 80)
        logger.info(f"📡 Programs to monitor: {len(program_ids)}")
        
        reconnect_attempt = 0
        
        while True:
            try:
                reconnect_attempt += 1
                logger.info(f"🔄 Connection attempt #{reconnect_attempt}")
                
                providers_to_try = await self.get_all_providers()
                
                if not providers_to_try:
                    logger.error("❌ No active providers found. Waiting 60 seconds...")
                    await asyncio.sleep(60)
                    continue

                logger.info(f"📋 Found {len(providers_to_try)} provider(s) to try")
                
                for provider in providers_to_try:
                    try:
                        logger.info(f"🔍 Checking provider: {provider.name}")
                        
                        if not await provider.check_availability():
                            logger.warning(f"⚠️ Provider '{provider.name}' is not available, trying next...")
                            continue
                        
                        logger.info(f"✅ Provider '{provider.name}' is available")
                        
                        ws_url = getattr(provider, 'ws_url', None)
                        if not ws_url:
                            logger.error(f"❌ Provider '{provider.name}' has no ws_url configured!")
                            continue
                        
                        logger.info(f"🔌 Connecting to WebSocket: {ws_url[:50]}...")
                        
                        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as websocket:
                            logger.info(f"✅✅✅ WebSocket CONNECTED to '{provider.name}' ✅✅✅")

                            for prog_id in program_ids:
                                logger.info(f"📨 Subscribing to program: {prog_id[:20]}...")
                                
                                subscription_request = {
                                    "jsonrpc": "2.0", 
                                    "id": 1, 
                                    "method": "logsSubscribe",
                                    "params": [
                                        {"mentions": [str(prog_id)]}, 
                                        {"commitment": "confirmed"}
                                    ]
                                }
                                
                                await websocket.send(json.dumps(subscription_request))
                                response = await websocket.recv()
                                response_data = json.loads(response)
                                
                                if "result" in response_data:
                                    logger.info(f"✅ Subscription confirmed for {prog_id[:20]}... (ID: {response_data['result']})")
                                else:
                                    logger.warning(f"⚠️ Unexpected subscription response: {response}")
                            
                            logger.info("=" * 80)
                            logger.info("🎧 LISTENING FOR LIVE EVENTS - WebSocket Active")
                            logger.info("=" * 80)
                            
                            message_count = 0
                            async for message in websocket:
                                try:
                                    message_count += 1
                                    data = json.loads(message)
                                    
                                    if 'params' in data and 'result' in data['params']:
                                        log_result = data['params']['result']
                                        signature = log_result.get('value', {}).get('signature')
                                        
                                        if not signature:
                                            logger.warning(f"📭 Message #{message_count} has no signature")
                                            continue

                                        logger.info(f"🔔 LIVE EVENT #{message_count}: Signature {signature}")
                                        
                                        full_transaction = await provider.get_raw_transaction(signature)

                                        if full_transaction:
                                            logger.info(f"📦 Full transaction fetched for {signature}")
                                            await process_log_callback(full_transaction)
                                        else:
                                            logger.error(f"❌ Failed to fetch transaction details for {signature}")

                                except json.JSONDecodeError as e:
                                    logger.warning(f"⚠️ Failed to parse WebSocket message: {e}")
                                except Exception as e:
                                    logger.error(f"❌ Error processing WebSocket message: {e}", exc_info=True)

                    except ConnectionClosed as e:
                        logger.warning(f"🔌 WebSocket connection closed for '{provider.name}': {e}")
                        logger.info("Will try next provider or reconnect...")
                                            
                    except Exception as e:
                        logger.error(f"❌ WebSocket error with '{provider.name}': {e}", exc_info=True)
                        logger.info("Trying next provider...")
                
                logger.error("=" * 80)
                logger.error("❌ ALL PROVIDERS FAILED - Reconnecting in 30 seconds...")
                logger.error("=" * 80)
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"❌ CRITICAL ERROR in WebSocket manager: {e}", exc_info=True)
                logger.info("Restarting connection cycle in 30 seconds...")
                await asyncio.sleep(30)