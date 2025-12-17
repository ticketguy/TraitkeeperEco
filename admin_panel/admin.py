# admin_panel/admin.py
from django.contrib import admin
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.urls import reverse
from .models import AdminUser, AdminLoginAttempt, AdminLogEntry, PrimaryProviderSetting, MarketplaceProviderSetting
from traitkeeper.admin_site import admin_site
from traitkeeper.admin_utils import AdvancedFilterAdmin
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Group, Permission
from django.http import HttpResponse
from django.template.response import TemplateResponse
import csv
import redis
from django.conf import settings
from django.db import models
from asgiref.sync import async_to_sync
import logging

logger = logging.getLogger(__name__)

REDIS_CHANNEL = "config_updates"

ACTION_FLAGS = {
    1: "Addition",
    2: "Change",
    3: "Deletion",
}
DELETION = 3

class ProtectedActionsAdmin:
    """Base class to handle admin actions in a protected way"""
    
    def __init__(self, model, admin_site):
        # Store protected actions list without modifying actions
        self._protected_actions = getattr(self, '_actions_list', [])
        super().__init__(model, admin_site)
    
    def get_actions(self, request):
        # Get base actions from parent class
        actions = super().get_actions(request)
        
        # Ensure we have actions to work with
        if actions is None:
            return {}
            
        # Filter actions based on permissions
        filtered_actions = {}
        for action_name, action_tuple in actions.items():
            # Check if user has permission for this action
            permission_method_name = f'has_{action_name}_permission'
            if hasattr(self, permission_method_name):
                permission_method = getattr(self, permission_method_name)
                if permission_method(request):
                    filtered_actions[action_name] = action_tuple
            else:
                # If no specific permission method, include action
                filtered_actions[action_name] = action_tuple
                
        return filtered_actions

class AdminUserAdmin(ProtectedActionsAdmin, AdvancedFilterAdmin):
    actions = ['activate_users', 'deactivate_users', 'enable_two_factor', 
               'disable_two_factor', 'reset_login_attempts', 'delete_selected']
    _actions_list = ['activate_users', 'deactivate_users', 'enable_two_factor', 
                     'disable_two_factor', 'reset_login_attempts', 'delete_selected']
    list_display = ['username', 'email', 'is_active', 'is_staff', 'date_joined', 'get_roles']
    list_filter = ['is_active', 'is_staff', 'date_joined', 'groups']
    search_fields = ['username', 'email']
    readonly_fields = ['date_joined', 'last_login', 'password_expiry', 'password_changed_at', 'last_login_ip', 'login_attempts', 'last_login_attempt']
    fieldsets = (
        (None, {
            'fields': ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff',  'groups')
        }),
        ('Important Dates', {
            'fields': ('date_joined', 'last_login', 'password_expiry', 'password_changed_at', 'last_login_attempt'),
            'classes': ('collapse',),
        }),
        ('Security', {
            'fields': ('last_login_ip', 'login_attempts', 'two_factor_enabled'),
            'classes': ('collapse',),
        }),
    )
    filter_horizontal = ('groups', 'user_permissions')
    change_list_template = "admin/change_list.html"

    def has_activate_users_permission(self, request):
        return request.user.has_perm('admin_panel.change_adminuser')

    def has_deactivate_users_permission(self, request):
        return request.user.has_perm('admin_panel.change_adminuser')

    def has_enable_two_factor_permission(self, request):
        return request.user.has_perm('admin_panel.change_adminuser')

    def has_disable_two_factor_permission(self, request):
        return request.user.has_perm('admin_panel.change_adminuser')

    def has_reset_login_attempts_permission(self, request):
        return request.user.has_perm('admin_panel.change_adminuser')

    def get_roles(self, obj):
        return ", ".join([group.name for group in obj.groups.all()])
    get_roles.short_description = 'Roles'

    def activate_users(self, request, queryset):
        if not self.has_activate_users_permission(request):
            self.message_user(request, "You do not have permission to activate users.", level='error')
            return
        updated = queryset.update(is_active=True)
        for user in queryset:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminUser).pk,
                object_id=user.id,
                object_repr=str(user),
                action_flag=2,
                change_message=f"Activated admin user: {user.username}"
            )
        self.message_user(request, f"Activated {updated} admin user(s).")
    activate_users.short_description = "Activate selected admin users"

    def deactivate_users(self, request, queryset):
        if not self.has_deactivate_users_permission(request):
            self.message_user(request, "You do not have permission to deactivate users.", level='error')
            return
        updated = queryset.update(is_active=False)
        for user in queryset:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminUser).pk,
                object_id=user.id,
                object_repr=str(user),
                action_flag=2,
                change_message=f"Deactivated admin user: {user.username}"
            )
        self.message_user(request, f"Deactivated {updated} admin user(s).")
    deactivate_users.short_description = "Deactivate selected admin users"

    def enable_two_factor(self, request, queryset):
        if not self.has_enable_two_factor_permission(request):
            self.message_user(request, "You do not have permission to enable two-factor authentication.", level='error')
            return
        updated = queryset.update(two_factor_enabled=True)
        for user in queryset:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminUser).pk,
                object_id=user.id,
                object_repr=str(user),
                action_flag=2,
                change_message=f"Enabled two-factor authentication for admin user: {user.username}"
            )
        self.message_user(request, f"Enabled two-factor authentication for {updated} admin user(s).")
    enable_two_factor.short_description = "Enable two-factor authentication for selected admin users"

    def disable_two_factor(self, request, queryset):
        if not self.has_disable_two_factor_permission(request):
            self.message_user(request, "You do not have permission to disable two-factor authentication.", level='error')
            return
        updated = queryset.update(two_factor_enabled=False)
        for user in queryset:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminUser).pk,
                object_id=user.id,
                object_repr=str(user),
                action_flag=2,
                change_message=f"Disabled two-factor authentication for admin user: {user.username}"
            )
        self.message_user(request, f"Disabled two-factor authentication for {updated} admin user(s).")
    disable_two_factor.short_description = "Disable two-factor authentication for selected admin users"

    def reset_login_attempts(self, request, queryset):
        if not self.has_reset_login_attempts_permission(request):
            self.message_user(request, "You do not have permission to reset login attempts.", level='error')
            return
        updated = queryset.update(login_attempts=0, last_login_attempt=None)
        for user in queryset:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminUser).pk,
                object_id=user.id,
                object_repr=str(user),
                action_flag=2,
                change_message=f"Reset login attempts for admin user: {user.username}"
            )
        self.message_user(request, f"Reset login attempts for {updated} admin user(s).")
    reset_login_attempts.short_description = "Reset login attempts for selected admin users"

    def delete_selected(self, request, queryset):
        if not self.has_delete_permission(request):
            self.message_user(request, "You do not have permission to delete admin users.", level='error')
            return
        for obj in queryset:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminUser).pk,
                object_id=obj.id,
                object_repr=str(obj),
                action_flag=3,
                change_message=f"Deleted admin user: {obj.username}"
            )
        deleted = queryset.delete()
        self.message_user(request, f"Successfully deleted {deleted[0]} admin user(s).")
    delete_selected.short_description = "Delete selected admin users"

    def save_model(self, request, obj, form, change):
        if not self.has_change_permission(request):
            self.message_user(request, "You do not have permission to edit admin users.", level='error')
            return
        super().save_model(request, obj, form, change)
        if change:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminUser).pk,
                object_id=obj.id,
                object_repr=str(obj),
                action_flag=2,
                change_message=f"Edited admin user: {obj.username} (Fields changed: {', '.join(form.changed_data)})"
            )
        else:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminUser).pk,
                object_id=obj.id,
                object_repr=str(obj),
                action_flag=1,
                change_message=f"Created admin user: {obj.username}"
            )

class AdminLoginAttemptAdmin(ProtectedActionsAdmin, AdvancedFilterAdmin):
    actions = ['delete_selected']
    _actions_list = ['delete_selected']
    list_display = ['user', 'ip_address', 'timestamp', 'success', 'user_agent']
    list_filter = ['success', 'timestamp']
    search_fields = ['ip_address', 'user__username', 'user_agent']
    readonly_fields = ['ip_address', 'user_agent', 'timestamp', 'success']
    fieldsets = (
        (None, {
            'fields': ('ip_address', 'user_agent', 'timestamp', 'success')
        }),
    )
    change_list_template = "admin/change_list.html"

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self.has_delete_permission(request) and 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def delete_selected(self, request, queryset):
        if not self.has_delete_permission(request):
            self.message_user(request, "You do not have permission to delete login attempts.", level='error')
            return
        for obj in queryset:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminLoginAttempt).pk,
                object_id=obj.id,
                object_repr=str(obj),
                action_flag=3,
                change_message=f"Deleted login attempt: {obj.ip_address} at {obj.timestamp}"
            )
        deleted = queryset.delete()
        self.message_user(request, f"Successfully deleted {deleted[0]} login attempt(s).")
    delete_selected.short_description = "Delete selected login attempts"

class AdminLogEntryAdmin(ProtectedActionsAdmin, AdvancedFilterAdmin):
    actions = ['delete_selected']
    _actions_list = ['delete_selected']
    date_hierarchy = 'action_time'
    list_display = [
        'action_time',
        'user_link',
        'content_type',
        'object_link',
        'action_flag_display',
        'get_change_message_display'
    ]
    list_filter = [
        'action_flag',
        'content_type',
        'user',
    ]
    search_fields = [
        'object_repr',
        'change_message',
        'user__username',
    ]
    readonly_fields = [
        'action_time',
        'user',
        'content_type',
        'object_id',
        'object_repr',
        'action_flag',
        'change_message',
    ]
    change_list_template = "admin/logentry_change_list.html"

    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm('admin_panel.delete_adminlogentry')
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_view_permission(self, request, obj=None):
        return request.user.has_perm('admin_panel.view_admin_logs')
    
    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self.has_delete_permission(request) and 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:admin_panel_adminuser_change', args=[obj.user.pk])
            return mark_safe(f'<a href="{url}">{escape(obj.user.username)}</a>')
        return '-'
    user_link.short_description = 'User'
    user_link.admin_order_field = 'user'
    
    def object_link(self, obj):
        if obj.action_flag == DELETION:
            return escape(obj.object_repr)
        elif obj.content_type and obj.object_id:
            try:
                url = reverse(
                    f'admin:{obj.content_type.app_label}_{obj.content_type.model}_change',
                    args=[obj.object_id]
                )
                return mark_safe(f'<a href="{url}">{escape(obj.object_repr)}</a>')
            except:
                return escape(obj.object_repr)
        return '-'
    object_link.short_description = 'Object'
    
    def action_flag_display(self, obj):
        return ACTION_FLAGS.get(obj.action_flag, obj.action_flag)
    action_flag_display.short_description = 'Action'
    action_flag_display.admin_order_field = 'action_flag'
    
    def get_change_message_display(self, obj):
        return obj.change_message if obj.change_message else '-'
    get_change_message_display.short_description = 'Change Message'
    
    def get_users(self):
        return AdminUser.objects.filter(adminlogentry__isnull=False).distinct()
    
    def get_content_types(self):
        return ContentType.objects.filter(adminlogentry__isnull=False).distinct()

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if 'user__id__in' in request.GET:
            selected_user_ids = request.GET.getlist('user__id__in')
            if selected_user_ids:
                queryset = queryset.filter(user__id__in=selected_user_ids)
        if 'content_type__id__in' in request.GET:
            selected_content_type_ids = request.GET.getlist('content_type__id__in')
            if selected_content_type_ids:
                queryset = queryset.filter(content_type__id__in=selected_content_type_ids)
        if 'change_message__icontains' in request.GET:
            queryset = queryset.filter(change_message__icontains=request.GET['change_message__icontains'])
        if 'object_repr__icontains' in request.GET:
            queryset = queryset.filter(object_repr__icontains=request.GET['object_repr__icontains'])
        return queryset

    def changelist_view(self, request, extra_context=None):
        format_type = request.GET.get('format', '')
        if format_type == 'csv':
            queryset = self.get_queryset(request)
            if 'user__id__in' in request.GET:
                selected_user_ids = request.GET.getlist('user__id__in')
                if selected_user_ids:
                    queryset = queryset.filter(user__id__in=selected_user_ids)
            if 'content_type__id__in' in request.GET:
                selected_content_type_ids = request.GET.getlist('content_type__id__in')
                if selected_content_type_ids:
                    queryset = queryset.filter(content_type__id__in=selected_content_type_ids)
            if 'action_time__gte' in request.GET:
                queryset = queryset.filter(action_time__gte=request.GET['action_time__gte'])
            if 'action_time__lte' in request.GET:
                queryset = queryset.filter(action_time__lte=request.GET['action_time__lte'])
            if 'q' in request.GET:
                search_query = request.GET['q']
                queryset = queryset.filter(
                    models.Q(object_repr__icontains=search_query) |
                    models.Q(change_message__icontains=search_query)
                )
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="admin_log_entries.csv"'
            writer = csv.writer(response)
            writer.writerow(['Timestamp', 'User', 'Content Type', 'Object', 'Action', 'Change Message'])
            for entry in queryset:
                writer.writerow([
                    entry.action_time.strftime('%Y-%m-%d %H:%M:%S'),
                    entry.user.username if entry.user else '-',
                    str(entry.content_type) if entry.content_type else '-',
                    entry.object_repr,
                    ACTION_FLAGS.get(entry.action_flag, 'Unknown'),
                    entry.change_message
                ])
            return response
        response = super().changelist_view(request, extra_context)
        if isinstance(response, TemplateResponse):
            cl = response.context_data['cl']
            if cl.paginator:
                current_page = cl.page_num
                num_pages = cl.paginator.num_pages
                start_page = max(1, current_page - 2)
                end_page = min(num_pages, current_page + 2)
                if start_page == 1:
                    end_page = min(num_pages, start_page + 4)
                if end_page == num_pages:
                    start_page = max(1, end_page - 4)
                pagination_range = range(start_page, end_page + 1)
            else:
                pagination_range = []
            selected_users = request.GET.getlist('user__id__in')
            selected_content_types = request.GET.getlist('content_type__id__in')
            extra_context = extra_context or {}
            extra_context['pagination_range'] = pagination_range
            extra_context['selected_users'] = selected_users
            extra_context['selected_content_types'] = selected_content_types
            response.context_data.update(extra_context)
        return response

    def delete_selected(self, request, queryset):
        if not self.has_delete_permission(request):
            self.message_user(request, "You do not have permission to delete log entries.", level='error')
            return
        for obj in queryset:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminLogEntry).pk,
                object_id=obj.id,
                object_repr=str(obj),
                action_flag=3,
                change_message=f"Deleted log entry: {obj.change_message}"
            )
        deleted = queryset.delete()
        self.message_user(request, f"Successfully deleted {deleted[0]} log entrie(s).")
    delete_selected.short_description = "Delete selected log entries"


class GroupAdmin(ProtectedActionsAdmin, admin.ModelAdmin):
    actions = []  # No actions defined
    _actions_list = []  # Reference list for ProtectedActionsAdmin
    list_display = ['name', 'get_permissions']
    filter_horizontal = ('permissions',)

    def get_permissions(self, obj):
        return ", ".join([perm.name for perm in obj.permissions.all()])
    get_permissions.short_description = 'Permissions'

    def has_add_permission(self, request):
        return request.user.has_perm('admin_panel.manage_roles')

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm('admin_panel.manage_roles')

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm('admin_panel.manage_roles')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(Group).pk,
                object_id=obj.id,
                object_repr=str(obj),
                action_flag=2,
                change_message=f"Edited role: {obj.name} (Fields changed: {', '.join(form.changed_data)})"
            )
        else:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(Group).pk,
                object_id=obj.id,
                object_repr=str(obj),
                action_flag=1,
                change_message=f"Created role: {obj.name}"
            )

    def delete_model(self, request, obj):
        AdminLogEntry.objects.log_action(
            user_id=request.user.id,
            content_type_id=ContentType.objects.get_for_model(Group).pk,
            object_id=obj.id,
            object_repr=str(obj),
            action_flag=3,
            change_message=f"Deleted role: {obj.name}"
        )
        super().delete_model(request, obj)


class PrimaryProviderSettingAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'is_primary', 'rpc_url', 'ws_url')
    list_editable = ('is_active', 'is_primary')

    def save_model(self, request, obj, form, change):
        """
        Override save_model to publish a config update message to Redis.
        """
        # Save the object first, as usual
        super().save_model(request, obj, form, change)

        # Now, send the signal
        try:
            # Create a standard (synchronous) redis client
            redis_client = redis.from_url(settings.REDIS_URL)
            # Publish the 'reload' message to the channel
            redis_client.publish(REDIS_CHANNEL, "reload")
            logger.info(f"Published 'reload' signal to {REDIS_CHANNEL} after saving PrimaryProviderSetting.")
        except Exception as e:
            logger.error(f"Could not publish config update to Redis: {e}")

    def log_change(self, request, object, message):
        AdminLogEntry.objects.log_action(
            user_id=request.user.id,
            content_type_id=ContentType.objects.get_for_model(object).pk,
            object_id=object.pk,
            object_repr=str(object),
            action_flag=2, # 2 is for 'change'
            change_message=str(message),
        )

    # This is called when a new object is added
    def log_addition(self, request, object, message):
         AdminLogEntry.objects.log_action(
            user_id=request.user.id,
            content_type_id=ContentType.objects.get_for_model(object).pk,
            object_id=object.pk,
            object_repr=str(object),
            action_flag=1, # 1 is for 'addition'
            change_message=str(message),
        )

    # This is called when an object is deleted
    def log_deletion(self, request, object, object_repr):
        AdminLogEntry.objects.log_action(
            user_id=request.user.id,
            content_type_id=ContentType.objects.get_for_model(object).pk,
            object_id=object.pk,
            object_repr=object_repr,
            action_flag=3, # 3 is for 'deletion'
        )

class MarketplaceProviderSettingAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'base_url', 'created_at', 'updated_at')
    list_editable = ('is_active',)
    readonly_fields = ('created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        """
        Override save_model to publish a config update message to Redis.
        """
        # Save the object first, as usual
        super().save_model(request, obj, form, change)

        # Now, send the signal
        try:
            # Create a standard (synchronous) redis client
            redis_client = redis.from_url(settings.REDIS_URL)
            # Publish the 'reload' message to the channel
            redis_client.publish(REDIS_CHANNEL, "reload")
            logger.info(f"Published 'reload' signal to {REDIS_CHANNEL} after saving MarketplaceProviderSetting.")
        except Exception as e:
            logger.error(f"Could not publish config update to Redis: {e}")

    def log_change(self, request, object, message):
        AdminLogEntry.objects.log_action(
            user_id=request.user.id,
            content_type_id=ContentType.objects.get_for_model(object).pk,
            object_id=object.pk,
            object_repr=str(object),
            action_flag=2,
            change_message=str(message),
        )

    def log_addition(self, request, object, message):
         AdminLogEntry.objects.log_action(
            user_id=request.user.id,
            content_type_id=ContentType.objects.get_for_model(object).pk,
            object_id=object.pk,
            object_repr=str(object),
            action_flag=1,
            change_message=str(message),
        )

    def log_deletion(self, request, object, object_repr):
        AdminLogEntry.objects.log_action(
            user_id=request.user.id,
            content_type_id=ContentType.objects.get_for_model(object).pk,
            object_id=object.pk,
            object_repr=object_repr,
            action_flag=3,
        )

admin_site.register(AdminUser, AdminUserAdmin)
admin_site.register(AdminLoginAttempt, AdminLoginAttemptAdmin)
admin_site.register(AdminLogEntry, AdminLogEntryAdmin)
admin_site.register(Group, GroupAdmin)

admin_site.register(PrimaryProviderSetting, PrimaryProviderSettingAdmin)
admin_site.register(MarketplaceProviderSetting, MarketplaceProviderSettingAdmin)