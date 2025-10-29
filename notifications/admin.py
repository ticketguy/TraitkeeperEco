from django.contrib import admin
from django.utils.safestring import mark_safe
from django.contrib.admin.models import LogEntry as AdminLogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.admin import actions as admin_actions
from traitkeeper.admin_site import admin_site
from .models import AdminNotification
from django.utils.translation import gettext_lazy as _
from admin_panel.admin import ProtectedActionsAdmin
from .models import Notification, NotificationPreference


# Register your models here.
class AdminNotificationAdmin(ProtectedActionsAdmin, admin.ModelAdmin):
    actions = ['mark_as_read', 'mark_as_unread', 'delete_selected']
    _actions_list = ['mark_as_read', 'mark_as_unread', 'delete_selected']
    list_display = ['type', 'severity_colored', 'message_rendered', 'admin_user', 'created_at', 'is_read']
    list_filter = ['type', 'severity', 'created_at', 'is_read']
    search_fields = ['message']
    change_list_template = "admin/change_list.html"

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self.has_delete_permission(request) and 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def severity_colored(self, obj):
        color_map = {
            'info': 'green',
            'warning': 'orange',
            'error': 'red'
        }
        color = color_map.get(obj.severity, 'black')
        return mark_safe(f'<span style="color: {color};">{obj.get_severity_display()}</span>')
    severity_colored.short_description = "Severity"

    def message_rendered(self, obj):
        # Render the message with HTML support
        return mark_safe(obj.message)
    message_rendered.short_description = "Message"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_details'] = True  # Enable details rendering in template
        return super().changelist_view(request, extra_context)

    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        for notification in queryset:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminNotification).pk,
                object_id=notification.id,
                object_repr=str(notification),
                action_flag=2,
                change_message=f"Marked notification as read: {notification.message}"
            )
        self.message_user(request, f"Marked {updated} notification(s) as read.")
    mark_as_read.short_description = "Mark selected notifications as read"

    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        for notification in queryset:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminNotification).pk,
                object_id=notification.id,
                object_repr=str(notification),
                action_flag=2,
                change_message=f"Marked notification as unread: {notification.message}"
            )
        self.message_user(request, f"Marked {updated} notification(s) as unread.")
    mark_as_unread.short_description = "Mark selected notifications as unread"

    def delete_selected(self, request, queryset):
        if not self.has_delete_permission(request):
            self.message_user(request, "You do not have permission to delete notifications.", level='error')
            return
        for obj in queryset:
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminNotification).pk,
                object_id=obj.id,
                object_repr=str(obj),
                action_flag=3,
                change_message=f"Deleted notification: {obj.message}"
            )
        deleted = queryset.delete()
        self.message_user(request, f"Successfully deleted {deleted[0]} notification(s).")
    delete_selected.short_description = "Delete selected notifications"

admin.site.register(AdminNotification, AdminNotificationAdmin)
admin_site.register(Notification)
admin_site.register(NotificationPreference)