# admin_panel/signals.py

import logging
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import AdminUser
# Import the new, centralized service to handle all notification logic.
from notifications.services import NotificationService

logger = logging.getLogger(__name__)
ADMIN_GROUP_NAME = 'Administrators'

def create_admin_group():
    """
    Creates or retrieves the default 'Administrators' group and assigns
    all permissions for the admin_panel app to it.
    This is a setup utility correctly placed here.
    """
    group, created = Group.objects.get_or_create(name=ADMIN_GROUP_NAME)
    if created:
        content_types = ContentType.objects.filter(app_label='admin_panel')
        permissions = Permission.objects.filter(content_type__in=content_types)
        group.permissions.add(*permissions)
        logger.info(f"Created admin group '{ADMIN_GROUP_NAME}' with initial permissions.")
    return group

@receiver(post_save, sender=AdminUser)
def handle_user_save(sender, instance: AdminUser, created: bool, **kwargs):
    """
    Signal handler for when an AdminUser is saved. Handles user creation,
    permissions, and delegates notification sending.
    """
    if instance.is_staff:
        if created:
            # Add the new user to the default admin group.
            admin_group = create_admin_group()
            instance.groups.add(admin_group)
            
            # Set initial password expiration.
            AdminUser.objects.filter(pk=instance.pk).update(
                password_expiry=timezone.now() + timedelta(days=90)
            )
            
            # Delegate the task of sending a welcome email.
            NotificationService.send_admin_welcome_email(instance)
            logger.info(f"New admin user '{instance.username}' created and welcome notification triggered.")
            
        else:
            # Logic for tracking user activation/deactivation.
            try:
                # Use the tracker field if available, otherwise query the DB.
                if instance.tracker.has_changed('is_active'):
                    if not instance.is_active:
                        logger.warning(f"Admin user deactivated: {instance.username}")
                        # Call the notification service.
                        NotificationService.send_admin_deactivation_email(instance)
                    else:
                        logger.info(f"Admin user reactivated: {instance.username}")
                        # Call the notification service.
                        NotificationService.send_admin_reactivation_email(instance)
            except AttributeError:
                # Fallback if tracker is not used.
                pass

@receiver(pre_save, sender=AdminUser)
def handle_password_change(sender, instance: AdminUser, **kwargs):
    """
    Updates password expiry date when an admin's password is changed.
    NOTE: This is a user management task and correctly remains here.
    """
    if instance.pk:  # Only for existing users.
        try:
            old_instance = AdminUser.objects.get(pk=instance.pk)
            if old_instance.password != instance.password:
                instance.password_changed_at = timezone.now()
                instance.password_expiry = timezone.now() + timedelta(days=90)
                logger.info(f"Password changed for admin user: {instance.username}. Expiry updated.")
        except AdminUser.DoesNotExist:
            pass

@receiver(post_delete, sender=AdminUser)
def handle_admin_deletion(sender, instance: AdminUser, **kwargs):
    """
    Signal handler for admin user deletion.
    Delegates the task of notifying other admins.
    """
    if instance.is_staff:
        logger.warning(f"Admin user deleted: {instance.username}")
        # Call the notification service to alert other admins.
        NotificationService.notify_admins_of_deletion(instance)

# Additional signals related to admin user activity can be added here.