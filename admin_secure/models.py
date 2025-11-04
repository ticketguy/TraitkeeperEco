"""
admin_secure/models.py
Secure storage for sensitive credentials and keys.
Only accessible to superusers with full audit logging.
"""

from django.db import models
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from cryptography.fernet import Fernet
from django.conf import settings
import os
import logging

logger = logging.getLogger(__name__)


class EncryptedSecret(models.Model):
    """
    Store encrypted secrets accessible only to superusers.
    All access is logged for security auditing.
    """

    class SecretType(models.TextChoices):
        PROGRAM_AUTHORITY = 'PROGRAM_AUTHORITY', 'Program Authority Private Key'
        RPC_API_KEY = 'RPC_API_KEY', 'RPC API Key'
        WEBHOOK_SECRET = 'WEBHOOK_SECRET', 'Webhook Secret'
        ENCRYPTION_KEY = 'ENCRYPTION_KEY', 'Encryption Key'
        API_TOKEN = 'API_TOKEN', 'API Token'

    # Basic info
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier for this secret"
    )
    secret_type = models.CharField(
        max_length=50,
        choices=SecretType.choices,
        help_text="Type of secret being stored"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this secret is used for"
    )

    # Encrypted value
    encrypted_value = models.BinaryField(
        help_text="Fernet-encrypted secret value"
    )
    encryption_key_id = models.CharField(
        max_length=50,
        default='v1',
        help_text="Which encryption key version was used (for key rotation)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'admin_panel.AdminUser',
        on_delete=models.PROTECT,
        related_name='created_secrets',
        help_text="Admin user who created this secret"
    )
    last_modified_by = models.ForeignKey(
        'admin_panel.AdminUser',
        on_delete=models.PROTECT,
        related_name='modified_secrets',
        null=True,
        blank=True,
        help_text="Admin user who last modified this secret"
    )

    # Access tracking
    last_accessed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When was this secret last decrypted"
    )
    access_count = models.IntegerField(
        default=0,
        help_text="Number of times this secret has been decrypted"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this secret is currently active"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional expiration date for this secret"
    )

    class Meta:
        verbose_name = "Encrypted Secret"
        verbose_name_plural = "Encrypted Secrets"
        permissions = [
            ("view_encrypted_secret", "Can view encrypted secrets"),
            ("decrypt_secret", "Can decrypt secrets"),
            ("rotate_secret", "Can rotate secret keys"),
        ]
        indexes = [
            models.Index(fields=['secret_type', 'is_active']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.get_secret_type_display()}: {self.name}"

    @classmethod
    def get_encryption_key(cls) -> bytes:
        """
        Get master encryption key from environment.

        Generate key with:
        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
        """
        key_b64 = os.getenv('SECRET_ENCRYPTION_KEY')
        if not key_b64:
            raise ValueError(
                "SECRET_ENCRYPTION_KEY not set in environment. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        return key_b64.encode()

    def encrypt_and_save(self, plaintext_value: str, user):
        """
        Encrypt plaintext value and save to database.

        Args:
            plaintext_value: The secret to encrypt (e.g., private key, API key)
            user: AdminUser performing the encryption
        """
        if not user.is_superuser:
            raise PermissionDenied("Only superusers can encrypt secrets")

        cipher = Fernet(self.get_encryption_key())
        self.encrypted_value = cipher.encrypt(plaintext_value.encode())
        self.encryption_key_id = 'v1'
        self.created_by = user
        self.last_modified_by = user
        self.save()

        logger.info(
            f"Secret encrypted: {self.name} (type: {self.secret_type}) by {user.username}"
        )

        # Log to system_health
        self._log_access_to_health(
            user=user,
            action='ENCRYPTED',
            message=f"Secret '{self.name}' created and encrypted"
        )

    def decrypt_value(self, user) -> str:
        """
        Decrypt secret value (superuser only).

        Args:
            user: AdminUser requesting decryption

        Returns:
            Decrypted plaintext secret

        Raises:
            PermissionDenied: If user is not superuser
            ValueError: If secret has expired
        """
        if not user.is_superuser:
            raise PermissionDenied("Only superusers can decrypt secrets")

        if not self.is_active:
            raise ValueError(f"Secret '{self.name}' is not active")

        if self.expires_at and self.expires_at < timezone.now():
            raise ValueError(f"Secret '{self.name}' has expired")

        try:
            cipher = Fernet(self.get_encryption_key())
            plaintext = cipher.decrypt(self.encrypted_value).decode()

            # Update access tracking
            self.last_accessed_at = timezone.now()
            self.access_count += 1
            self.save(update_fields=['last_accessed_at', 'access_count'])

            logger.warning(
                f"Secret decrypted: {self.name} by {user.username} "
                f"(access count: {self.access_count})"
            )

            # Log to system_health
            self._log_access_to_health(
                user=user,
                action='DECRYPTED',
                message=f"Secret '{self.name}' decrypted by {user.username}"
            )

            return plaintext

        except Exception as e:
            logger.error(f"Failed to decrypt secret '{self.name}': {str(e)}")
            raise

    def rotate_secret(self, new_plaintext_value: str, user):
        """
        Rotate secret to a new value.

        Args:
            new_plaintext_value: New secret value
            user: AdminUser performing rotation
        """
        if not user.is_superuser:
            raise PermissionDenied("Only superusers can rotate secrets")

        old_encryption_key_id = self.encryption_key_id

        cipher = Fernet(self.get_encryption_key())
        self.encrypted_value = cipher.encrypt(new_plaintext_value.encode())
        self.last_modified_by = user
        self.save()

        logger.warning(
            f"Secret rotated: {self.name} by {user.username} "
            f"(key version: {old_encryption_key_id} -> {self.encryption_key_id})"
        )

        # Log to system_health
        self._log_access_to_health(
            user=user,
            action='ROTATED',
            message=f"Secret '{self.name}' rotated by {user.username}",
            level='WARNING'
        )

    def _log_access_to_health(self, user, action: str, message: str, level: str = 'INFO'):
        """Log secret access to system_health app"""
        try:
            from system_health.models import SystemAlert

            alert_level_map = {
                'INFO': SystemAlert.AlertLevel.INFO,
                'WARNING': SystemAlert.AlertLevel.WARNING,
                'ERROR': SystemAlert.AlertLevel.ERROR,
                'CRITICAL': SystemAlert.AlertLevel.CRITICAL,
            }

            SystemAlert.objects.create(
                alert_level=alert_level_map.get(level, SystemAlert.AlertLevel.INFO),
                category=SystemAlert.AlertCategory.SECURITY,
                title=f"Secret {action}: {self.name}",
                message=message,
                source_component='admin_secure',
                metadata={
                    'secret_name': self.name,
                    'secret_type': self.secret_type,
                    'action': action,
                    'user_id': user.id,
                    'username': user.username,
                    'access_count': self.access_count,
                    'encryption_key_id': self.encryption_key_id,
                }
            )
        except Exception as e:
            logger.error(f"Failed to log secret access to system_health: {e}")

    @classmethod
    def get_secret_value(cls, secret_name: str, requesting_component: str = 'system') -> str:
        """
        Retrieve and decrypt a secret value (for system use).

        Args:
            secret_name: Name of the secret to retrieve
            requesting_component: Component requesting the secret (for logging)

        Returns:
            Decrypted secret value

        Note:
            This method is for system components (like SolanaClient).
            It uses a system superuser for decryption and caches the result.
        """
        from django.core.cache import cache
        from admin_panel.models import AdminUser

        # Check cache first (5 minute TTL)
        cache_key = f'encrypted_secret:{secret_name}'
        cached_value = cache.get(cache_key)
        if cached_value:
            return cached_value

        try:
            secret = cls.objects.get(name=secret_name, is_active=True)

            # Get system superuser for decryption
            system_user = AdminUser.objects.filter(
                is_superuser=True,
                username='system'
            ).first()

            if not system_user:
                # Fallback to any superuser
                system_user = AdminUser.objects.filter(is_superuser=True).first()

            if not system_user:
                raise ValueError("No superuser found to decrypt secret")

            decrypted_value = secret.decrypt_value(system_user)

            # Cache for 5 minutes
            cache.set(cache_key, decrypted_value, timeout=300)

            logger.info(
                f"Secret '{secret_name}' retrieved by component: {requesting_component}"
            )

            return decrypted_value

        except cls.DoesNotExist:
            raise ValueError(f"Secret '{secret_name}' not found or not active")


class SecretAccessLog(models.Model):
    """
    Detailed audit log of all secret access attempts.
    Separate from SystemAlert for long-term retention.
    """

    secret = models.ForeignKey(
        EncryptedSecret,
        on_delete=models.CASCADE,
        related_name='access_logs'
    )
    user = models.ForeignKey(
        'admin_panel.AdminUser',
        on_delete=models.PROTECT
    )

    action = models.CharField(
        max_length=50,
        choices=[
            ('DECRYPTED', 'Decrypted'),
            ('ENCRYPTED', 'Encrypted'),
            ('ROTATED', 'Rotated'),
            ('VIEWED', 'Viewed (metadata only)'),
            ('FAILED_DECRYPT', 'Failed Decryption Attempt'),
        ]
    )

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)

    # Context
    requesting_component = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        verbose_name = "Secret Access Log"
        verbose_name_plural = "Secret Access Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['secret', '-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.action} - {self.secret.name} by {self.user.username} at {self.timestamp}"
