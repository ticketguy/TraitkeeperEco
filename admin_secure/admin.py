"""
admin_secure/admin.py
Admin interface for encrypted secrets management.
Only accessible to superusers.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages
from .models import EncryptedSecret, SecretAccessLog
from .forms import EncryptedSecretForm


@admin.register(EncryptedSecret)
class EncryptedSecretAdmin(admin.ModelAdmin):
    form = EncryptedSecretForm
    list_display = [
        'name',
        'secret_type',
        'is_active',
        'access_count',
        'last_accessed_at',
        'created_by',
        'decrypt_button'
    ]
    list_filter = ['secret_type', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = [
        'encrypted_value',
        'encryption_key_id',
        'access_count',
        'last_accessed_at',
        'created_at',
        'updated_at',
        'created_by',
        'last_modified_by'
    ]

    fieldsets = (
        ('Secret Information', {
            'fields': ('name', 'secret_type', 'description', 'plaintext_value', 'is_active')
        }),
        ('Advanced', {
            'fields': ('expires_at',),
            'classes': ('collapse',)
        }),
        ('Security (Read-Only)', {
            'fields': ('encrypted_value', 'encryption_key_id'),
            'classes': ('collapse',),
            'description': 'These fields are automatically managed. Do not edit manually.'
        }),
        ('Access Tracking', {
            'fields': ('access_count', 'last_accessed_at'),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'created_by', 'last_modified_by'),
            'classes': ('collapse',)
        }),
    )

    def decrypt_button(self, obj):
        """Add decrypt button to list view"""
        if obj.is_active:
            return format_html(
                '<a class="button" href="{}" target="_blank" '
                'style="background-color: #e67e22; color: white; padding: 5px 10px; '
                'border-radius: 3px; text-decoration: none;">🔓 Decrypt</a>',
                reverse('admin_secure:decrypt_secret', args=[obj.id])
            )
        return format_html(
            '<span style="color: #95a5a6;">Inactive</span>'
        )
    decrypt_button.short_description = 'Actions'

    def rotate_button(self, obj):
        """Add rotate button"""
        if obj.is_active:
            return format_html(
                '<a class="button" href="{}" '
                'style="background-color: #3498db; color: white; padding: 5px 10px; '
                'border-radius: 3px; text-decoration: none;">🔄 Rotate</a>',
                reverse('admin_secure:rotate_secret', args=[obj.id])
            )
        return '-'
    rotate_button.short_description = 'Rotate'

    def has_module_permission(self, request):
        """Only superusers can see this module"""
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        """Only superusers can view secrets"""
        return request.user.is_superuser

    def has_add_permission(self, request):
        """Only superusers can add secrets"""
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        """Only superusers can change secrets"""
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete secrets"""
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        """Set created_by or last_modified_by"""
        if not change:
            obj.created_by = request.user
        obj.last_modified_by = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'created_by',
            'last_modified_by'
        )


@admin.register(SecretAccessLog)
class SecretAccessLogAdmin(admin.ModelAdmin):
    list_display = [
        'timestamp',
        'secret',
        'user',
        'action',
        'success',
        'requesting_component'
    ]
    list_filter = ['action', 'success', 'timestamp']
    search_fields = ['secret__name', 'user__username', 'requesting_component']
    readonly_fields = [
        'secret',
        'user',
        'action',
        'timestamp',
        'ip_address',
        'user_agent',
        'success',
        'error_message',
        'requesting_component',
        'metadata'
    ]

    fieldsets = (
        ('Access Information', {
            'fields': ('secret', 'user', 'action', 'timestamp', 'success')
        }),
        ('Request Details', {
            'fields': ('ip_address', 'user_agent', 'requesting_component')
        }),
        ('Error Details', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        """Logs are automatically created, not manually added"""
        return False

    def has_change_permission(self, request, obj=None):
        """Logs cannot be modified"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete logs"""
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        """Only superusers can view logs"""
        return request.user.is_superuser

    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related('secret', 'user')
