# wallet/models.py
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
from datetime import datetime, timedelta
import re
import uuid
import datetime

class CustomUserManager(BaseUserManager):
    def create_user(self, username=None, public_key=None, password=None, **extra_fields):
        if not username and not public_key:
            raise ValueError('Either a username or public key must be provided.')
        
        if not username and public_key:
            unique_id = str(uuid.uuid4())[:8]
            username = f"wallet_{public_key[:6]}_{unique_id}"
        
        email = extra_fields.get('email')
        secondary_identifier = extra_fields.get('secondary_identifier')
        if email and CustomUser.objects.filter(email=email).exists():
            raise ValueError('Email address must be unique.')
        if secondary_identifier and CustomUser.objects.filter(secondary_identifier=secondary_identifier).exists():
            raise ValueError('Secondary identifier must be unique.')
        
        user = self.model(username=username, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        if not username or not password:
            raise ValueError('Superuser must have a username and password.')
        
        return self.create_user(username=username, password=password, **extra_fields)

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True, null=True, blank=True)
    telegram = models.CharField(max_length=100, null=True, blank=True)
    profile_picture = models.URLField(null=True, blank=True)
    profile_banner = models.URLField(null=True, blank=True)
    x_account = models.CharField(max_length=100, null=True, blank=True)
    discord_account = models.CharField(max_length=100, null=True, blank=True)
    secondary_identifier = models.CharField(max_length=150, unique=True, null=True, blank=True)
    
    password_expiry = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    two_factor_enabled = models.BooleanField(default=False)

    objects = CustomUserManager()

    def __str__(self):
        return self.username

    def get_identifier(self):
        if hasattr(self, 'wallet_profile') and self.wallet_profile.public_key:
            return self.wallet_profile.short_public_key
        return self.username or self.email or self.secondary_identifier

    def set_password_for_user(self, password):
        self.set_password(password)
        self.save()

class WalletProfile(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallets'  # Changed from 'wallet_profile' to 'wallets' for multiple support
    )
    public_key = models.CharField(max_length=44, unique=True, db_index=True)
    is_primary = models.BooleanField(default=False, help_text="Primary wallet for this user")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_primary', '-created_at']  # Primary wallets first, then by creation date
        verbose_name = 'Wallet Profile'
        verbose_name_plural = 'Wallet Profiles'

    def __str__(self):
        primary_text = " (Primary)" if self.is_primary else ""
        return f"{self.user.username if self.user else 'Unknown'} - {self.short_public_key}{primary_text}"

    def clean(self):
        super().clean()
        if not re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', self.public_key):
            raise ValidationError('Invalid public key format for Solana.')

    def save(self, *args, **kwargs):
        self.full_clean()

        # If this is marked as primary, unset other primary wallets for this user
        if self.is_primary:
            WalletProfile.objects.filter(user=self.user, is_primary=True).exclude(pk=self.pk).update(is_primary=False)

        # If this is the first wallet for the user, make it primary automatically
        if not self.pk and not WalletProfile.objects.filter(user=self.user).exists():
            self.is_primary = True

        return super().save(*args, **kwargs)

    @property
    def short_public_key(self):
        if self.public_key:
            return f"{self.public_key[:6]}...{self.public_key[-6:]}"
        return ""

    @classmethod
    def get_or_create_profile_and_user(cls, public_key):
        try:
            profile = cls.objects.select_related('user').get(public_key=public_key)
            return profile, profile.user, False
        except cls.DoesNotExist:
            user = CustomUser.objects.create_user(public_key=public_key)
            profile = cls.objects.create(user=user, public_key=public_key, is_primary=True)
            return profile, user, True

    @classmethod
    def get_primary_wallet(cls, user):
        """Get the primary wallet for a user, or the first wallet if no primary is set"""
        try:
            return cls.objects.filter(user=user, is_primary=True).first() or cls.objects.filter(user=user).first()
        except cls.DoesNotExist:
            return None

class PasswordResetCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=15)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.used and timezone.now() < self.expires_at
