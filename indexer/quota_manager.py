# indexer/quota_manager.py
import asyncio
import logging
import time
from typing import Dict, Optional, Any
from django.conf import settings
from django.utils import timezone

# Refactored to use the central, site-wide cache manager
from core.cache_manager import cache_manager, CacheType

logger = logging.getLogger(__name__)

class ProviderQuotaManager:
    """
    Manages API provider quotas and rate limits using the central CacheManager.
    It ensures API usage is tracked, limited, and distributed according to collection priority.
    """
    def __init__(self, provider_manager):
        self.provider_manager = provider_manager
        
        # Load configurations from settings.py for easy management
        self.provider_configs = getattr(settings, 'PROVIDER_QUOTA_CONFIGS', {})
        self.priority_allocations = getattr(settings, 'PROVIDER_PRIORITY_ALLOCATIONS', {})
        logger.info("ProviderQuotaManager initialized with settings-based configuration.")

    async def get_wrapped_provider_if_quota_available(self, provider, priority_tier: str = 'ACTIVE'):
        """
        Checks if a SINGLE, specific provider has available API quota.

        This method does not loop or choose between providers. It only answers
        "yes" or "no" for the one provider it is given.

        Args:
            provider: The provider instance to check.
            priority_tier (str): The priority tier for the request (e.g., 'ACTIVE').

        Returns:
            QuotaAwareProviderWrapper: A wrapped instance if the provider has quota.
            None: If the provider's quota is exhausted.
        """
        provider_name = provider.name.lower()
        
        # 1. Check the cache to see if the provider's daily/tier usage is below its limit.
        has_quota = await self._check_quota_available(provider_name, priority_tier)
        
        # 2. If it has quota, return the provider wrapped in our proxy class,
        # which will handle rate-limiting and usage tracking for subsequent calls.
        if has_quota:
            logger.debug(f"Quota available for {provider_name}. Preparing provider.")
            return QuotaAwareProviderWrapper(provider, self, priority_tier, None)
        # 3. If it does not have quota, log a warning and return None.
        # The APIProviderManager will then continue its loop to check the next provider.
        else:
            logger.warning(f"Quota exhausted for {provider_name} on tier {priority_tier}.")
            return None

    async def _check_quota_available(self, provider_name: str, priority_tier: str) -> bool:
        """Checks if both the daily and tier-specific quotas are within limits."""
        config = self._get_provider_config(provider_name)
        if not config:
            return False

        today = timezone.now().date().isoformat()
        daily_limit = config['daily_credits']
        tier_allocation = self.priority_allocations.get(priority_tier, 0.10)
        tier_limit = int(daily_limit * tier_allocation)

        # Get usage stats from the central cache_manager
        daily_usage_key = f"quota:{provider_name}:daily:{today}"
        tier_usage_key = f"quota:{provider_name}:tier:{priority_tier}:{today}"
        
        daily_usage = await cache_manager.get(daily_usage_key) or 0
        tier_usage = await cache_manager.get(tier_usage_key) or 0

        return daily_usage < daily_limit and tier_usage < tier_limit

    async def _apply_rate_limiting(self, provider_name: str):
        """Enforces a delay between requests to respect provider rate limits."""
        config = self._get_provider_config(provider_name)
        # Calculate min delay based on requests per second
        min_delay = 1.0 / config['requests_per_second'] if config else 0.2

        # Use the cache for persistent, scalable rate limiting
        rate_limit_key = f"rate_limit:{provider_name}:last_request_time"
        last_request_time = await cache_manager.get(rate_limit_key) or 0
        
        time_since_last = time.time() - last_request_time
        if time_since_last < min_delay:
            sleep_time = min_delay - time_since_last
            logger.debug(f"Rate limiting {provider_name}: sleeping for {sleep_time:.3f}s")
            await asyncio.sleep(sleep_time)
        
        # Update the last request time in the cache
        await cache_manager.set(rate_limit_key, time.time(), cache_type=CacheType.RATE_LIMIT)

    async def _track_request(self, provider_name: str, priority_tier: str):
        """Increments usage counters in the cache after a request is made."""
        today = timezone.now().date().isoformat()
        ttl = 86400  # 24 hours

        # Get existing counts
        daily_usage_key = f"quota:{provider_name}:daily:{today}"
        tier_usage_key = f"quota:{provider_name}:tier:{priority_tier}:{today}"
        daily_usage = (await cache_manager.get(daily_usage_key) or 0) + 1
        tier_usage = (await cache_manager.get(tier_usage_key) or 0) + 1
        
        # Set the new incremented values
        await cache_manager.set(daily_usage_key, daily_usage, cache_type=CacheType.STATS)
        await cache_manager.set(tier_usage_key, tier_usage, cache_type=CacheType.STATS)

    def _get_provider_config(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """Gets the configuration for a provider from settings."""
        # In the future, this could auto-detect the plan (e.g., 'free' vs 'developer')
        plan = 'free' # Default to the most restrictive plan
        return self.provider_configs.get(provider_name, {}).get(plan)

class QuotaAwareProviderWrapper:
    """
    A proxy that wraps a real provider instance. It intercepts all method calls
    to automatically apply rate limiting and track quota usage before execution.
    """
    def __init__(self, provider, quota_manager, priority_tier, collection_address):
        self._provider = provider
        self._quota_manager = quota_manager
        self._priority_tier = priority_tier
        self._collection_address = collection_address
        
    def __getattr__(self, name):
        """Intercepts all method calls to the wrapped provider."""
        attr = getattr(self._provider, name)
        
        # If the attribute is a callable method, wrap it.
        if callable(attr):
            async def wrapper(*args, **kwargs):
                # 1. Enforce rate limit before the call
                await self._quota_manager._apply_rate_limiting(self._provider.name.lower())
                
                # 2. Track the request to increment quota usage
                await self._quota_manager._track_request(self._provider.name.lower(), self._priority_tier)
                
                # 3. Execute the actual provider method (e.g., get_transactions)
                return await attr(*args, **kwargs)
            return wrapper
        
        # If it's just an attribute (like 'name'), return it directly
        return attr