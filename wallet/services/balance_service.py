# wallet/services/balance_service.py

"""
Service for fetching wallet balances from Solana blockchain.
"""

import logging
from typing import Dict, List, Optional
from decimal import Decimal
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Common SPL token addresses
KNOWN_TOKENS = {
    'USDC': 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    'USDT': 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',
    'BONK': 'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263',
    'SOL': 'So11111111111111111111111111111111111111112',  # Wrapped SOL
}


class WalletBalanceService:
    """Service for fetching and caching wallet balances from Solana."""

    def __init__(self, rpc_url: str = None):
        """
        Initialize the balance service.

        Args:
            rpc_url: Solana RPC URL. If None, uses a default public endpoint.
        """
        self.rpc_url = rpc_url or 'https://api.mainnet-beta.solana.com'
        self.client = Client(self.rpc_url)

    def get_sol_balance(self, wallet_address: str) -> Optional[Decimal]:
        """
        Get SOL balance for a wallet.

        Args:
            wallet_address: The wallet's public key as a string

        Returns:
            Decimal: SOL balance, or None if error
        """
        cache_key = f'sol_balance_{wallet_address}'
        cached = cache.get(cache_key)

        if cached is not None:
            return Decimal(str(cached))

        try:
            pubkey = Pubkey.from_string(wallet_address)
            response = self.client.get_balance(pubkey)

            if response.value is not None:
                # Convert lamports to SOL (1 SOL = 1_000_000_000 lamports)
                balance = Decimal(response.value) / Decimal('1000000000')

                # Cache for 30 seconds
                cache.set(cache_key, float(balance), timeout=30)

                return balance

        except Exception as e:
            logger.error(f"Error fetching SOL balance for {wallet_address}: {e}")

        return None

    def get_token_accounts(self, wallet_address: str) -> List[Dict]:
        """
        Get all SPL token accounts for a wallet.

        Args:
            wallet_address: The wallet's public key as a string

        Returns:
            List of token account data with balances
        """
        cache_key = f'token_accounts_{wallet_address}'
        cached = cache.get(cache_key)

        if cached is not None:
            return cached

        try:
            pubkey = Pubkey.from_string(wallet_address)

            # Get token accounts owned by this wallet
            response = self.client.get_token_accounts_by_owner(
                pubkey,
                {"programId": Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")}
            )

            token_accounts = []

            if response.value:
                for account in response.value:
                    try:
                        # Parse account data
                        account_data = account.account.data

                        # Token account structure: mint(32 bytes), owner(32 bytes), amount(8 bytes), ...
                        if len(account_data) >= 72:
                            # Extract mint address (first 32 bytes)
                            mint_bytes = account_data[:32]
                            mint_pubkey = Pubkey(mint_bytes)

                            # Extract amount (bytes 64-72, little-endian u64)
                            amount_bytes = account_data[64:72]
                            amount = int.from_bytes(amount_bytes, 'little')

                            # Extract decimals (byte 44)
                            decimals = account_data[44] if len(account_data) > 44 else 9

                            token_accounts.append({
                                'mint': str(mint_pubkey),
                                'amount': amount,
                                'decimals': decimals,
                                'ui_amount': amount / (10 ** decimals),
                            })

                    except Exception as e:
                        logger.warning(f"Error parsing token account: {e}")
                        continue

            # Cache for 30 seconds
            cache.set(cache_key, token_accounts, timeout=30)

            return token_accounts

        except Exception as e:
            logger.error(f"Error fetching token accounts for {wallet_address}: {e}")

        return []

    def get_wallet_summary(self, wallet_address: str) -> Dict:
        """
        Get a summary of wallet balances including SOL and known tokens.

        Args:
            wallet_address: The wallet's public key as a string

        Returns:
            Dict with balance information
        """
        summary = {
            'sol_balance': Decimal('0'),
            'tokens': [],
            'total_value_usd': None,  # Would need price oracle
        }

        # Get SOL balance
        sol_balance = self.get_sol_balance(wallet_address)
        if sol_balance:
            summary['sol_balance'] = sol_balance

        # Get token balances
        token_accounts = self.get_token_accounts(wallet_address)

        for account in token_accounts:
            mint = account['mint']

            # Check if this is a known token
            token_symbol = None
            for symbol, known_mint in KNOWN_TOKENS.items():
                if mint == known_mint:
                    token_symbol = symbol
                    break

            if account['ui_amount'] > 0:  # Only include tokens with non-zero balance
                summary['tokens'].append({
                    'symbol': token_symbol or f"{mint[:6]}...",
                    'mint': mint,
                    'balance': Decimal(str(account['ui_amount'])),
                    'decimals': account['decimals'],
                })

        return summary

    def get_multiple_wallets_summary(self, wallet_addresses: List[str]) -> Dict:
        """
        Get combined balance summary for multiple wallets.

        Args:
            wallet_addresses: List of wallet public keys

        Returns:
            Dict with aggregated balance information
        """
        total_sol = Decimal('0')
        all_tokens = {}

        for address in wallet_addresses:
            summary = self.get_wallet_summary(address)

            # Add SOL
            total_sol += summary['sol_balance']

            # Aggregate tokens
            for token in summary['tokens']:
                mint = token['mint']
                if mint in all_tokens:
                    all_tokens[mint]['balance'] += token['balance']
                else:
                    all_tokens[mint] = token.copy()

        return {
            'total_sol': total_sol,
            'tokens': list(all_tokens.values()),
            'wallet_count': len(wallet_addresses),
        }
