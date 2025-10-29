# admin_panel/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import uuid
from django.utils import timezone

User = get_user_model()

class AdminUserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not username:
            raise ValueError('Admin users must have a username')
        if not email:
            raise ValueError('Admin users must have an email address')
        
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(username, email, password, **extra_fields)

class AdminUser(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=True)  # All admin users are staff by default
    date_joined = models.DateTimeField(default=timezone.now)
    
    # Override PermissionsMixin fields to add related_name
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        related_name='admin_user_set',
        related_query_name='admin_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='admin_user_set',
        related_query_name='admin_user',
    )
    
    # Admin-specific fields
    password_expiry = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    two_factor_enabled = models.BooleanField(default=False)
    login_attempts = models.PositiveIntegerField(default=0)
    last_login_attempt = models.DateTimeField(null=True, blank=True)

    objects = AdminUserManager()

    USERNAME_FIELD = 'username'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = 'Admin User'
        verbose_name_plural = 'Admin Users'
        permissions = [
            ("view_admin_logs", "Can view admin logs"),
            ("manage_roles", "Can manage roles and permissions"),
        ]

    def __str__(self):
        return self.username

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    def get_short_name(self):
        return self.first_name or self.username

class AdminLoginAttempt(models.Model):
    # Generic relation to allow different user types
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    user_obj = GenericForeignKey('content_type', 'object_id')
    
    # Keep the original user field for backward compatibility and queries
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='login_attempts')
    
    ip_address = models.GenericIPAddressField()
    timestamp = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=False)
    user_agent = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{'Successful' if self.success else 'Failed'} login attempt from {self.ip_address}"

    class Meta:
        verbose_name = 'Admin Login Attempt'
        verbose_name_plural = 'Admin Login Attempts'
        ordering = ['-timestamp']

    def set_user(self, user_instance):
        """Helper method to set the correct user object"""
        if isinstance(user_instance, User):
            self.user = user_instance
            self.content_type = ContentType.objects.get_for_model(User)
            self.object_id = user_instance.id
        else:
            self.user = None
            self.content_type = ContentType.objects.get_for_model(user_instance.__class__)
            self.object_id = user_instance.id

class AdminLogEntryManager(models.Manager):
    def log_action(self, user_id, content_type_id, object_id, object_repr, action_flag, change_message=''):
        self.create(
            user_id=user_id,
            content_type_id=content_type_id,
            object_id=object_id,
            object_repr=object_repr,
            action_flag=action_flag,
            change_message=change_message
        )

class AdminLogEntry(models.Model):
    action_time = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(AdminUser, on_delete=models.CASCADE)  # Use AdminUser instead of CustomUser
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.TextField(null=True, blank=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.PositiveSmallIntegerField()
    change_message = models.TextField(blank=True)

    objects = AdminLogEntryManager()

    class Meta:
        verbose_name = 'Admin Log Entry'
        verbose_name_plural = 'Admin Log Entries'
        ordering = ['-action_time']

    def __str__(self):
        return f"{self.action_time} - {self.user} - {self.get_action_flag_display()} - {self.object_repr}"

    def get_action_flag_display(self):
        return {
            1: "Addition",
            2: "Change",
            3: "Deletion"
        }.get(self.action_flag, "Unknown")


class PrimaryProviderSetting(models.Model):
    name = models.CharField(max_length=50, unique=True)
    rpc_url = models.URLField(max_length=200)
    api_key = models.CharField(max_length=100, blank=True, null=True)
    ws_url = models.CharField(
        max_length=200, 
        blank=True, 
        null=True, 
        help_text="WebSocket URL for real-time subscriptions (optional)"
    )  # Changed from URLField to CharField
    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Primary Provider Setting'
        verbose_name_plural = 'Primary Provider Settings'

    def __str__(self):
        return f"Provider: {self.name} ({'Primary' if self.is_primary else 'Secondary'})"

    def save(self, *args, **kwargs):
        if self.is_primary:
            # Ensure only one provider is primary
            PrimaryProviderSetting.objects.filter(is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)