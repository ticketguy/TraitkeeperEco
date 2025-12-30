from django import template

register = template.Library()


@register.filter(name='has_permission')
def has_permission(user, permission_codename):
    """
    Check if user has a specific admin permission through their role.
    Usage in template: {% if user|has_permission:"can_view_dashboard" %}
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if hasattr(user, 'has_admin_permission'):
        return user.has_admin_permission(permission_codename)

    return False


@register.filter(name='has_any_permission')
def has_any_permission(user, permissions_string):
    """
    Check if user has ANY of the specified permissions.
    Usage: {% if user|has_any_permission:"can_view_users,can_create_users" %}
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    permissions = [p.strip() for p in permissions_string.split(',')]

    if hasattr(user, 'has_admin_permission'):
        return any(user.has_admin_permission(perm) for perm in permissions)

    return False
