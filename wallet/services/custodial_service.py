"""
Custodial Wallet Service
Handles automatic wallet creation for users who sign up without connecting a wallet.
"""
import os
import base64
import logging
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet
from solders.keypair import Keypair
from solders.pubkey import Pubkey

logger = logging.getLogger(__name__)


class CustodialWalletService:
    """Service for creating and managing custodial wallets."""

    @staticmethod
    def generate_encryption_key(password: str, salt: bytes) -> bytes:
        """
        Generate an encryption key from a password and salt using PBKDF2.

        Args:
            password: User's password or system secret
            salt: Random salt for key derivation

        Returns:
            32-byte encryption key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    @staticmethod
    def encrypt_private_key(private_key_bytes: bytes, password: str, salt: bytes) -> str:
        """
        Encrypt a private key using Fernet (AES-256).

        Args:
            private_key_bytes: The private key bytes to encrypt
            password: Password for encryption
            salt: Salt for key derivation

        Returns:
            Base64 encoded encrypted private key
        """
        key = CustodialWalletService.generate_encryption_key(password, salt)
        f = Fernet(key)
        encrypted = f.encrypt(private_key_bytes)
        return base64.b64encode(encrypted).decode('utf-8')

    @staticmethod
    def decrypt_private_key(encrypted_private_key: str, password: str, salt: bytes) -> bytes:
        """
        Decrypt an encrypted private key.

        Args:
            encrypted_private_key: Base64 encoded encrypted key
            password: Password for decryption
            salt: Salt used during encryption

        Returns:
            Decrypted private key bytes
        """
        key = CustodialWalletService.generate_encryption_key(password, salt)
        f = Fernet(key)
        encrypted_bytes = base64.b64decode(encrypted_private_key)
        return f.decrypt(encrypted_bytes)

    @staticmethod
    def create_custodial_wallet(user):
        """
        Create a new custodial wallet for a user.

        This generates a new Solana keypair, encrypts the private key,
        and creates a CustodialWallet record linked to a WalletProfile.

        Args:
            user: CustomUser instance

        Returns:
            tuple: (WalletProfile, CustodialWallet) instances
        """
        from wallet.models import WalletProfile, CustodialWallet
        from django.conf import settings

        try:
            # Check if user already has a custodial wallet
            existing_wallet = WalletProfile.objects.filter(
                user=user,
                custodial_data__isnull=False
            ).first()

            if existing_wallet:
                logger.info(f"User {user.username} already has a custodial wallet")
                return existing_wallet, existing_wallet.custodial_data

            # Generate new Solana keypair
            keypair = Keypair()
            public_key = str(keypair.pubkey())
            private_key_bytes = bytes(keypair)

            # Generate salt for encryption
            salt = os.urandom(32)
            salt_hex = salt.hex()

            # Use system secret for encryption (not user password)
            # This way wallets persist even if user changes password
            encryption_password = settings.SECRET_KEY + user.username

            # Encrypt private key
            encrypted_private_key = CustodialWalletService.encrypt_private_key(
                private_key_bytes,
                encryption_password,
                salt
            )

            # Create WalletProfile
            wallet_profile = WalletProfile.objects.create(
                user=user,
                public_key=public_key,
                is_primary=True,  # First wallet is primary
                is_custodial=True,
                wallet_name=f"{user.username}'s Wallet"
            )

            # Create CustodialWallet
            custodial_wallet = CustodialWallet.objects.create(
                wallet_profile=wallet_profile,
                encrypted_private_key=encrypted_private_key,
                salt=salt_hex,
                encryption_version='v1'
            )

            logger.info(f"✅ Created custodial wallet for user {user.username}: {public_key}")

            return wallet_profile, custodial_wallet

        except Exception as e:
            logger.error(f"❌ Failed to create custodial wallet for user {user.username}: {e}")
            raise

    @staticmethod
    def get_private_key(custodial_wallet, user):
        """
        Retrieve and decrypt the private key for a custodial wallet.

        Args:
            custodial_wallet: CustodialWallet instance
            user: CustomUser instance

        Returns:
            Keypair instance
        """
        from django.conf import settings

        try:
            # Reconstruct encryption password
            encryption_password = settings.SECRET_KEY + user.username

            # Decrypt private key
            salt = bytes.fromhex(custodial_wallet.salt)
            private_key_bytes = CustodialWalletService.decrypt_private_key(
                custodial_wallet.encrypted_private_key,
                encryption_password,
                salt
            )

            # Reconstruct keypair
            keypair = Keypair.from_bytes(private_key_bytes)

            return keypair

        except Exception as e:
            logger.error(f"❌ Failed to decrypt private key: {e}")
            raise

    @staticmethod
    def export_private_key(custodial_wallet, user, mark_exported=True):
        """
        Export the private key for a custodial wallet (for user to take custody).

        Args:
            custodial_wallet: CustodialWallet instance
            user: CustomUser instance
            mark_exported: Whether to mark the wallet as exported

        Returns:
            str: Base58 encoded private key
        """
        from django.utils import timezone
        import base58

        try:
            # Get the keypair
            keypair = CustodialWalletService.get_private_key(custodial_wallet, user)

            # Mark as exported
            if mark_exported:
                custodial_wallet.is_exported = True
                custodial_wallet.exported_at = timezone.now()
                custodial_wallet.save()
                logger.warning(f"⚠️ Private key exported for user {user.username}")

            # Return base58 encoded private key
            return base58.b58encode(bytes(keypair)).decode('utf-8')

        except Exception as e:
            logger.error(f"❌ Failed to export private key: {e}")
            raise
