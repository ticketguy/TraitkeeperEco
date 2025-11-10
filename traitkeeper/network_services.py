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
        # Pyth Network API configuration for Solana price
        self.pyth_api_url = "https://hermes.pyth.network/v2/updates/price/latest"
        # SOL/USD price feed ID from Pyth Network
        self.sol_usd_price_feed = "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"

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
        """Fetch the current Solana price from Pyth Network on-chain oracle"""
        cache_key = "solana_price"
        cache_key_24h = "solana_price_24h_ago"

        cached_price = cache.get(cache_key)
        if cached_price:
            logger.info("Returning cached Solana price from Pyth")
            return cached_price

        try:
            # Fetch real-time price from Pyth Network with shorter retry delays
            url = f"{self.pyth_api_url}?ids[]={self.sol_usd_price_feed}"
            response = self.fetch_with_backoff(url, method="GET", retries=3, initial_delay=2.0)

            if not response or 'parsed' not in response:
                logger.error("Failed to fetch Solana price from Pyth Network")
                return {"price_usd": 0.0, "market_cap_usd": 0.0, "volume_24h_usd": 0.0, "change_24h_percent": 0.0}

            # Extract price data from Pyth response
            price_feed = response['parsed'][0]
            price_data = price_feed['price']

            # Pyth price is in format: price * 10^expo
            # Example: price: "14523000000", expo: -8 = $145.23
            raw_price = int(price_data['price'])
            expo = int(price_data['expo'])
            current_price = raw_price * (10 ** expo)

            # Calculate 24-hour change
            price_24h_ago = cache.get(cache_key_24h)
            change_24h_percent = 0.0

            if price_24h_ago and price_24h_ago > 0:
                change_24h_percent = ((current_price - price_24h_ago) / price_24h_ago) * 100
                logger.info(f"24h price change: {change_24h_percent:.2f}% (from ${price_24h_ago:.2f} to ${current_price:.2f})")
            else:
                # Store current price for 24h comparison (expires in 24 hours)
                cache.set(cache_key_24h, current_price, 86400)  # 24 hours in seconds
                logger.info(f"Stored baseline price for 24h tracking: ${current_price:.2f}")

            result = {
                "price_usd": round(current_price, 2),
                "market_cap_usd": 0.0,  # Pyth doesn't provide this
                "volume_24h_usd": 0.0,  # Pyth doesn't provide this
                "change_24h_percent": round(change_24h_percent, 2),
            }

            cache.set(cache_key, result, self.cache_timeout)
            logger.info(f"Fetched Solana price from Pyth: ${result['price_usd']} (24h: {result['change_24h_percent']}%)")
            return result

        except Exception as e:
            logger.error(f"Error fetching Solana price from Pyth: {str(e)}")
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