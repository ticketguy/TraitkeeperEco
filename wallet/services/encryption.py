"""
Wallet Encryption Service

Handles secure encryption and decryption of private keys using AES-256.
Uses user's password with PBKDF2 key derivation for maximum security.

SECURITY NOTES:
- Private keys are NEVER stored in plaintext
- Encryption uses AES-256-CBC with PBKDF2-derived keys
- Each encryption uses a unique random salt
- 600,000+ PBKDF2 iterations (OWASP recommended)
"""

import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import logging

logger = logging.getLogger(__name__)


class WalletEncryptionService:
    """
    Service for encrypting/decrypting wallet private keys.

    Encryption Flow:
    1. Derive encryption key from user password using PBKDF2
    2. Encrypt private key with AES-256-CBC
    3. Return base64-encoded ciphertext + salt

    Decryption Flow:
    1. Derive encryption key from password + stored salt
    2. Decrypt ciphertext
    3. Return plaintext private key
    """

    # Security parameters (OWASP recommendations)
    PBKDF2_ITERATIONS = 600000  # 600k iterations (2023 OWASP standard)
    KEY_LENGTH = 32  # 256 bits for AES-256
    SALT_LENGTH = 32  # 256-bit salt
    IV_LENGTH = 16  # 128-bit IV for AES-CBC

    @classmethod
    def _derive_key(cls, password: str, salt: bytes) -> bytes:
        """
        Derive encryption key from password using PBKDF2-HMAC-SHA256.

        Args:
            password: User's password
            salt: Cryptographic salt

        Returns:
            bytes: 256-bit encryption key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=cls.KEY_LENGTH,
            salt=salt,
            iterations=cls.PBKDF2_ITERATIONS,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))

    @classmethod
    def encrypt_private_key(cls, private_key: str, password: str) -> tuple[str, str]:
        """
        Encrypt a private key with user's password.

        Args:
            private_key: Base58-encoded private key
            password: User's password

        Returns:
            tuple: (encrypted_key_base64, salt_hex)

        Example:
            encrypted, salt = encrypt_private_key("5J...", "user_password")
        """
        try:
            # Generate random salt and IV
            salt = os.urandom(cls.SALT_LENGTH)
            iv = os.urandom(cls.IV_LENGTH)

            # Derive encryption key from password
            key = cls._derive_key(password, salt)

            # Encrypt private key with AES-256-CBC
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()

            # Pad plaintext to AES block size (16 bytes)
            plaintext = private_key.encode('utf-8')
            padding_length = 16 - (len(plaintext) % 16)
            padded_plaintext = plaintext + bytes([padding_length] * padding_length)

            # Encrypt
            ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()

            # Combine IV + ciphertext (IV needed for decryption)
            encrypted_data = iv + ciphertext

            # Return base64-encoded encrypted data and hex-encoded salt
            encrypted_key_b64 = base64.b64encode(encrypted_data).decode('utf-8')
            salt_hex = salt.hex()

            logger.info(f"✅ Private key encrypted successfully (salt: {salt_hex[:16]}...)")
            return encrypted_key_b64, salt_hex

        except Exception as e:
            logger.error(f"❌ Encryption failed: {e}")
            raise ValueError(f"Failed to encrypt private key: {str(e)}")

    @classmethod
    def decrypt_private_key(cls, encrypted_key_b64: str, salt_hex: str, password: str) -> str:
        """
        Decrypt a private key using user's password.

        Args:
            encrypted_key_b64: Base64-encoded encrypted key (IV + ciphertext)
            salt_hex: Hex-encoded salt used during encryption
            password: User's password

        Returns:
            str: Decrypted private key in base58 format

        Raises:
            ValueError: If password is incorrect or decryption fails
        """
        try:
            # Decode inputs
            encrypted_data = base64.b64decode(encrypted_key_b64)
            salt = bytes.fromhex(salt_hex)

            # Extract IV and ciphertext
            iv = encrypted_data[:cls.IV_LENGTH]
            ciphertext = encrypted_data[cls.IV_LENGTH:]

            # Derive decryption key from password
            key = cls._derive_key(password, salt)

            # Decrypt with AES-256-CBC
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()

            # Decrypt
            padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

            # Remove PKCS7 padding
            padding_length = padded_plaintext[-1]
            plaintext = padded_plaintext[:-padding_length]

            # Decode to string
            private_key = plaintext.decode('utf-8')

            logger.info("✅ Private key decrypted successfully")
            return private_key

        except ValueError as e:
            logger.warning(f"⚠️ Decryption failed (likely wrong password): {e}")
            raise ValueError("Incorrect password or corrupted data")
        except Exception as e:
            logger.error(f"❌ Decryption error: {e}")
            raise ValueError(f"Failed to decrypt private key: {str(e)}")

    @classmethod
    def verify_password(cls, encrypted_key_b64: str, salt_hex: str, password: str) -> bool:
        """
        Verify if a password can decrypt the private key (without returning the key).

        Args:
            encrypted_key_b64: Encrypted private key
            salt_hex: Salt used for encryption
            password: Password to test

        Returns:
            bool: True if password is correct, False otherwise
        """
        try:
            cls.decrypt_private_key(encrypted_key_b64, salt_hex, password)
            return True
        except:
            return False
