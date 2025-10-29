# indexer/api_provider/base.py
import asyncio
import logging
import aiohttp
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, Callable
import websockets
import json
from collections import deque
import time

logger = logging.getLogger(__name__)


# THIS IS THE MISSING CLASS - ADD IT AT THE TOP OF THE FILE
class AsyncRateLimiter:
    """
    An async rate limiter that can handle rates both above and below 1 request/sec.
    """
    def __init__(self, max_requests: int, per_seconds: int = 1):
        self.max_requests = max_requests
        self.per_seconds = per_seconds
        self.request_timestamps = deque()

    async def wait(self):
        """Waits if necessary to not exceed the configured rate limit."""
        while True:
            now = time.monotonic()
            # Remove timestamps older than our time window
            while self.request_timestamps and self.request_timestamps[0] <= now - self.per_seconds:
                self.request_timestamps.popleft()

            if len(self.request_timestamps) < self.max_requests:
                self.request_timestamps.append(now)
                break
            
            # Calculate how long to wait until the oldest request in the window expires
            oldest_request_time = self.request_timestamps[0]
            wait_time = (oldest_request_time + self.per_seconds) - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)


class SolanaRPCProvider(ABC):
    """
    Abstract base class for Solana JSON-RPC providers with built-in rate limiting.
    """
    def __init__(self, rpc_url: str, api_key: Optional[str] = None, 
                 max_requests: int = 40, per_seconds: int = 1):
        if not rpc_url:
            raise ValueError("An RPC URL is required to initialize a provider.")
        self.rpc_url = rpc_url
        self.api_key = api_key
        self.name = "base_rpc_provider"
        self.max_retries = 3
        self.retry_delay_seconds = 2

        # Instantiate the rate limiter with values from the subclass (HeliusProvider, etc.)
        self.rate_limiter = AsyncRateLimiter(max_requests=max_requests, per_seconds=per_seconds)

    def _sanitize_url_for_logging(self, url: str) -> str:
        if self.api_key and self.api_key in url:
            return url.replace(self.api_key, '***')
        if '?api-key=' in url:
            return url.split('?')[0] + '?api-key=***'
        return url

    async def _async_post(self, payload: dict, timeout: int = 30) -> Optional[dict]:
        """Performs a standard asynchronous POST request with rate limiting and retries."""
        # Every single request will now wait here if it's too fast.
        await self.rate_limiter.wait()
        
        logger.info(f"--> Sending RPC request to {self.name}: {payload.get('method')}")
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.rpc_url, json=payload, timeout=timeout) as response:
                        logger.info(f"<-- Received HTTP {response.status} from {self.name} for method {payload.get('method')}")
                        
                        if response.status == 429:
                            logger.warning(f"Rate limited by {self.name}. Backing off for {self.retry_delay_seconds * 2}s (Attempt {attempt + 1}).")
                            await asyncio.sleep(self.retry_delay_seconds * 2)
                            continue # Continue to the next retry attempt

                        response.raise_for_status()
                        return await response.json()
            except Exception as e:
                logger.warning(f"RPC request via {self.name} failed on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay_seconds * (attempt + 1))
                else:
                    logger.error(f"RPC request to {self._sanitize_url_for_logging(self.rpc_url)} failed after {self.max_retries} attempts.")
                    return None
        return None

    async def check_availability(self) -> bool:
        """Checks if the RPC endpoint is healthy and responsive."""
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
        data = await self._async_post(payload, timeout=5)
        is_ok = data.get("result") == "ok" if data else False
        logger.info(f"Provider '{self.name}' availability: {'✅ Available' if is_ok else '❌ Unavailable'}")
        return is_ok

    async def get_account_info(self, account: str) -> Optional[dict]:
        """Fetches raw account info using getAccountInfo RPC method."""
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [account, {"encoding": "base64", "commitment": "confirmed"}]
        }
        response = await self._async_post(payload)
        return response.get("result") if response else None

    async def get_raw_transaction(self, signature: str) -> Optional[Dict[str, Any]]:
        """Fetches the full raw transaction details with enhanced logging."""
        logger.info(f"--- [get_raw_transaction] FETCHING SIGNATURE: {signature} ---")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed", 
                    "maxSupportedTransactionVersion": 0
                }
            ]
        }
        
        response = await self._async_post(payload)

        # --- NEW: DETAILED LOGGING FOR DEBUGGING ---
        if not response:
            logger.error(f"[{signature}] Request failed entirely. _async_post returned None.")
            return None

        if "error" in response:
            logger.error(f"[{signature}] RPC provider returned an error: {response['error']}")
            return None

        result = response.get("result")
        if not result:
            logger.error(f"[{signature}] RPC response is missing 'result' key or result is null/empty. Full response: {response}")
            return None
        # --- END NEW LOGGING ---
        
        logger.info(f"[{signature}] Successfully received valid result from provider.")
        return result

    async def get_transactions(self, signatures: List[str]) -> List[Optional[Dict[str, Any]]]:
        """
        Fetches a batch of raw transactions by their signatures, processing them
        in smaller chunks to respect API rate limits.
        """
        all_transactions = []
        batch_size = 20  # Process 20 signatures at a time (a safe number for most RPCs)
        
        for i in range(0, len(signatures), batch_size):
            batch_signatures = signatures[i:i + batch_size]
            logger.info(f"Processing transaction batch {i//batch_size + 1} of {len(signatures)//batch_size + 1}...")
            
            tasks = [self.get_raw_transaction(sig) for sig in batch_signatures]
            results = await asyncio.gather(*tasks)
            all_transactions.extend(results)
            
            # Wait a moment between batches to be kind to the API
            await asyncio.sleep(1) 
            
        return all_transactions

    async def get_signatures_for_address(self, address: str, limit: int = 100) -> Optional[List[Dict]]:
        """Fetches raw signature history for a given wallet or token address."""
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
            "params": [address, {"limit": limit}]
        }
        response = await self._async_post(payload)
        return response.get("result") if response else None

    async def subscribe_to_logs(self, callback: Callable, program_id: str):
        """
        Establishes a persistent WebSocket connection to subscribe to on-chain program logs.

        This method is designed to be robust, featuring automatic reconnection with
        exponential backoff in case of connection failures.

        Args:
            callback (Callable): An async function that will be called with the raw log data for each received event.
            program_id (str): The public key of the on-chain program to monitor.
        """
        logger.info(f"Attempting to subscribe to logs for program '{program_id}' via {self.name} WebSocket.")
        
        # --- Configuration for connection robustness ---
        max_reconnect_attempts = 3
        base_reconnect_delay_seconds = 2
        
        # The main loop handles the reconnection logic. It will try to connect up to `max_reconnect_attempts`.
        for attempt in range(max_reconnect_attempts):
            try:
                # The 'async with' statement ensures the WebSocket connection is properly closed
                # when the block is exited, either normally or through an exception.
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as websocket:
                    
                    # Construct the standard JSON-RPC request for Solana's 'logsSubscribe' method.
                    # 'mentions' is used to filter logs for transactions that involve the specified program_id.
                    subscription_request = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "logsSubscribe",
                        "params": [
                            {"mentions": [program_id]},
                            {"commitment": "confirmed"}
                        ]
                    }
                    
                    # Send the subscription request to the server.
                    await websocket.send(json.dumps(subscription_request))
                    
                    # Wait for the server's confirmation message for our subscription.
                    response = await websocket.recv()
                    logger.info(f"Subscription confirmed by {self.name}: {response}")
                    
                    # This loop will run indefinitely, processing messages as they arrive.
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            # Check if the message is a data notification from the subscription.
                            if 'params' in data and 'result' in data['params']:
                                # Pass the relevant log data to the user-provided callback function for processing.
                                await callback(data['params']['result'])
                        except json.JSONDecodeError:
                            logger.warning(f"Could not decode JSON from {self.name} WebSocket message: {message}")

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"{self.name} WebSocket connection closed (attempt {attempt + 1}/{max_reconnect_attempts}): {e}")
                if attempt < max_reconnect_attempts - 1:
                    # --- Exponential Backoff ---
                    # Wait before retrying. The delay increases with each failed attempt
                    # (e.g., 2s, 4s, 8s) to avoid overwhelming the server.
                    delay = base_reconnect_delay_seconds * (2 ** attempt)
                    logger.info(f"Will attempt to reconnect in {delay} seconds...")
                    await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"An unexpected error occurred with the {self.name} WebSocket (attempt {attempt + 1}/{max_reconnect_attempts}): {e}")
                if attempt < max_reconnect_attempts - 1:
                    delay = base_reconnect_delay_seconds * (2 ** attempt)
                    logger.info(f"Will attempt to reconnect in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    # After all attempts have failed, log a final error and re-raise the exception.
                    # This signals to the calling code that the subscription has failed permanently.
                    logger.error(f"Permanently failed to connect to {self.name} WebSocket after {max_reconnect_attempts} attempts.")
                    raise

    @abstractmethod
    async def get_collection_for_mint(self, mint_address: str) -> Optional[str]:
        """
        Finds the collection address for a given NFT mint address.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    async def get_metadata(self, mint_address: str) -> Optional[Dict]:
        """
        Fetches the full JSON metadata for a given NFT mint address.
        Must be implemented by subclasses.
        """
        pass