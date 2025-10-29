# nft_data/network_services.py
import logging
import requests
import time
from django.core.cache import cache
from django.conf import settings
from solders.rpc.responses import GetRecentPerformanceSamplesResp
from solana.rpc.api import Client as SolanaClient
from solana.rpc.commitment import Confirmed

logger = logging.getLogger(__name__)

class SolanaNetworkService:
    def __init__(self):
        """Initialize the SolanaNetworkService with API and RPC configurations"""
        # CoinGecko API configuration for Solana price
        self.coingecko_api_url = "https://api.coingecko.com/api/v3"
        self.coingecko_coin_id = "solana"

        # Solana RPC configuration for TPS
        self.primary_rpc_url = getattr(settings, 'SOLANA_RPC_URL', "https://api.mainnet-beta.solana.com")
        self.fallback_rpc_urls = [
            "https://solana-mainnet.g.alchemy.com/v2/demo",
            "https://api.mainnet-beta.solana.com"
        ]
        self.solana_client = SolanaClient(self.primary_rpc_url)

        # Caching configuration
        self.cache_timeout = 30  # 30 seconds for real-time data

    def _get_solana_client(self):
        """Get a working Solana RPC client, trying fallbacks if necessary"""
        try:
            self.solana_client.get_slot(commitment=Confirmed)
            return self.solana_client
        except Exception as e:
            logger.warning(f"Primary Solana RPC failed: {str(e)}, trying fallbacks")

            for fallback_url in self.fallback_rpc_urls:
                try:
                    fallback_client = SolanaClient(fallback_url)
                    fallback_client.get_slot(commitment=Confirmed)
                    logger.info(f"Using fallback RPC: {fallback_url}")
                    return fallback_client
                except Exception as fallback_e:
                    logger.warning(f"Fallback RPC {fallback_url} failed: {str(fallback_e)}")

            logger.error("All Solana RPCs failed, using primary RPC anyway")
            return self.solana_client

    def fetch_with_backoff(self, url: str, params: dict = None, method: str = "GET", json: dict = None, retries: int = 5, initial_delay: float = 10.0) -> dict:
        """Fetch data from an API with exponential backoff for rate limits and server errors"""
        delay = initial_delay
        headers = {"Content-Type": "application/json"}

        for attempt in range(retries):
            try:
                if method.upper() == "GET":
                    response = requests.get(url, params=params, headers=headers, timeout=15)
                else:  # POST
                    response = requests.post(url, params=params, json=json, headers=headers, timeout=15)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:  # Rate limit
                    logger.warning(f"Rate limit hit on attempt {attempt + 1}/{retries}, waiting {delay} seconds")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                elif response.status_code == 500:  # Internal server error
                    logger.warning(f"Server error on attempt {attempt + 1}/{retries}, waiting {delay} seconds")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    logger.error(f"API error: Status {response.status_code}, Response: {response.text}")
                    if attempt < retries - 1:
                        time.sleep(delay)
                        delay *= 2
                    else:
                        return None
            except Exception as e:
                logger.error(f"Error fetching from API on attempt {attempt + 1}/{retries}: {str(e)}")
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                else:
                    return None
        return None

    def get_solana_price(self) -> dict:
        """Fetch the current Solana price from CoinGecko"""
        cache_key = "solana_price"
        cached_price = cache.get(cache_key)
        if cached_price:
            logger.info("Returning cached Solana price")
            return cached_price

        url = f"{self.coingecko_api_url}/simple/price"
        params = {
            "ids": self.coingecko_coin_id,
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        }

        try:
            response = self.fetch_with_backoff(url, params=params)
            if response and self.coingecko_coin_id in response:
                price_data = response[self.coingecko_coin_id]
                result = {
                    "price_usd": price_data.get("usd", 0.0),
                    "market_cap_usd": price_data.get("usd_market_cap", 0.0),
                    "volume_24h_usd": price_data.get("usd_24h_vol", 0.0),
                    "change_24h_percent": price_data.get("usd_24h_change", 0.0),
                }
                cache.set(cache_key, result, self.cache_timeout)
                logger.info(f"Fetched Solana price: {result}")
                return result
            else:
                logger.error("Failed to fetch Solana price from CoinGecko")
                return {"price_usd": 0.0, "market_cap_usd": 0.0, "volume_24h_usd": 0.0, "change_24h_percent": 0.0}
        except Exception as e:
            logger.error(f"Error fetching Solana price: {str(e)}")
            return {"price_usd": 0.0, "market_cap_usd": 0.0, "volume_24h_usd": 0.0, "change_24h_percent": 0.0}

    def get_solana_tps(self) -> dict:
        """Fetch the current Solana TPS using Solana RPC"""
        cache_key = "solana_tps"
        cached_tps = cache.get(cache_key)
        if cached_tps:
            logger.info("Returning cached Solana TPS")
            return cached_tps

        try:
            solana_client = self._get_solana_client()
            response = solana_client.get_recent_performance_samples(limit=60)
            if not isinstance(response, GetRecentPerformanceSamplesResp):
                logger.warning("Failed to fetch recent performance samples")
                return {"average_tps": 0.0, "max_tps": 0.0}

            samples = response.value
            if not samples:
                logger.warning("No performance samples available")
                return {"average_tps": 0.0, "max_tps": 0.0}

            tps_values = [sample.num_transactions / sample.sample_period_secs for sample in samples if sample.sample_period_secs > 0]
            average_tps = sum(tps_values) / len(tps_values) if tps_values else 0.0
            max_tps = max(tps_values) if tps_values else 0.0

            result = {
                "average_tps": round(average_tps, 2),
                "max_tps": round(max_tps, 2),
            }
            cache.set(cache_key, result, self.cache_timeout)
            logger.info(f"Fetched Solana TPS: {result}")
            return result
        except Exception as e:
            logger.error(f"Error fetching Solana TPS: {str(e)}")
            return {"average_tps": 0.0, "max_tps": 0.0}

    def get_network_stats(self) -> dict:
        """Fetch combined Solana price and TPS data"""
        price_data = self.get_solana_price()
        tps_data = self.get_solana_tps()
        return {
            "price": price_data,
            "tps": tps_data,
        }