"""
Solana Wallet Service

Handles Solana keypair generation, mnemonic phrases, and key conversion.

Dependencies:
- solders (Solana SDK for Python)
- mnemonic (BIP39 mnemonic phrase generation)
"""

import base58
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
except ImportError:
    logger.warning("⚠️ solders not installed - using fallback implementation")
    Keypair = None
    Pubkey = None

try:
    from mnemonic import Mnemonic
except ImportError:
    logger.warning("⚠️ mnemonic library not installed - seed phrase generation disabled")
    Mnemonic = None


class SolanaWalletService:
    """
    Service for generating and managing Solana wallets.

    Features:
    - Generate new keypairs with BIP39 seed phrases
    - Convert between keypair and base58 formats
    - Derive keypairs from seed phrases
    """

    @classmethod
    def generate_keypair(cls) -> Tuple[Keypair, str]:
        """
        Generate a new Solana keypair with a 12-word BIP39 seed phrase.

        Returns:
            Tuple[Keypair, str]: (keypair, seed_phrase)

        Example:
            keypair, seed_phrase = SolanaWalletService.generate_keypair()
            # seed_phrase: "word1 word2 word3 ... word12"
            # keypair.pubkey(): "7xKXt...Abc"
        """
        try:
            if not Keypair:
                raise ImportError("solders library is required for keypair generation")

            if Mnemonic:
                # Generate 12-word seed phrase
                mnemo = Mnemonic("english")
                seed_phrase = mnemo.generate(strength=128)  # 128 bits = 12 words

                # Derive keypair from seed phrase
                seed = mnemo.to_seed(seed_phrase)[:32]  # Use first 32 bytes as seed
                keypair = Keypair.from_seed(seed)

                logger.info(f"✅ Generated keypair with seed phrase: {keypair.pubkey()}")
                return keypair, seed_phrase
            else:
                # Fallback: generate random keypair without seed phrase
                keypair = Keypair()
                logger.warning(f"⚠️ Generated keypair without seed phrase (mnemonic library missing): {keypair.pubkey()}")
                return keypair, ""

        except Exception as e:
            logger.error(f"❌ Keypair generation failed: {e}")
            raise ValueError(f"Failed to generate Solana keypair: {str(e)}")

    @classmethod
    def from_seed_phrase(cls, seed_phrase: str) -> Keypair:
        """
        Derive a keypair from a BIP39 seed phrase.

        Args:
            seed_phrase: 12 or 24-word mnemonic phrase

        Returns:
            Keypair: Derived Solana keypair

        Example:
            keypair = from_seed_phrase("word1 word2 ... word12")
        """
        try:
            if not Mnemonic:
                raise ImportError("mnemonic library is required")

            mnemo = Mnemonic("english")

            # Validate seed phrase
            if not mnemo.check(seed_phrase):
                raise ValueError("Invalid seed phrase")

            # Derive keypair
            seed = mnemo.to_seed(seed_phrase)[:32]
            keypair = Keypair.from_seed(seed)

            logger.info(f"✅ Derived keypair from seed phrase: {keypair.pubkey()}")
            return keypair

        except Exception as e:
            logger.error(f"❌ Seed phrase derivation failed: {e}")
            raise ValueError(f"Failed to derive keypair from seed phrase: {str(e)}")

    @classmethod
    def keypair_to_base58(cls, keypair: Keypair) -> str:
        """
        Convert a Keypair to base58-encoded private key string.

        Args:
            keypair: Solana Keypair

        Returns:
            str: Base58-encoded private key

        Example:
            private_key_b58 = keypair_to_base58(keypair)
            # Returns: "5J3mBbAH..."
        """
        try:
            # Get secret key bytes (64 bytes: 32 private + 32 public)
            secret_bytes = bytes(keypair)

            # Encode to base58
            private_key_b58 = base58.b58encode(secret_bytes).decode('utf-8')

            return private_key_b58

        except Exception as e:
            logger.error(f"❌ Base58 encoding failed: {e}")
            raise ValueError(f"Failed to convert keypair to base58: {str(e)}")

    @classmethod
    def keypair_from_base58(cls, private_key_b58: str) -> Keypair:
        """
        Convert a base58-encoded private key to a Keypair.

        Args:
            private_key_b58: Base58-encoded private key

        Returns:
            Keypair: Reconstructed Solana keypair

        Example:
            keypair = keypair_from_base58("5J3mBbAH...")
        """
        try:
            # Decode base58 to bytes
            secret_bytes = base58.b58decode(private_key_b58)

            # Create keypair from secret bytes
            keypair = Keypair.from_bytes(secret_bytes)

            logger.info(f"✅ Reconstructed keypair from base58: {keypair.pubkey()}")
            return keypair

        except Exception as e:
            logger.error(f"❌ Base58 decoding failed: {e}")
            raise ValueError(f"Failed to create keypair from base58: {str(e)}")

    @classmethod
    def validate_public_key(cls, public_key: str) -> bool:
        """
        Validate if a string is a valid Solana public key.

        Args:
            public_key: Public key string to validate

        Returns:
            bool: True if valid, False otherwise

        Example:
            is_valid = validate_public_key("7xKXt...")
        """
        try:
            if not Pubkey:
                # Fallback validation: check length and base58 characters
                import re
                return bool(re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', public_key))

            # Try to create Pubkey object
            Pubkey.from_string(public_key)
            return True

        except:
            return False
