# admin_panel/decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden, JsonResponse


def admin_permission_required(permission_codename, raise_exception=False):
    """
    Decorator to check if the user has a specific admin permission.

    Usage:
        @admin_permission_required('can_manage_providers')
        def my_view(request):
            ...

    Args:
        permission_codename: The codename of the required permission
        raise_exception: If True, raises PermissionDenied. If False, redirects to dashboard.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('admin_panel:login')

            # Check if user has the required permission
            if not request.user.has_admin_permission(permission_codename):
                if raise_exception:
                    raise PermissionDenied(f"Permission '{permission_codename}' required")

                messages.error(
                    request,
                    f"You don't have permission to access this page. Required permission: {permission_codename}"
                )
                return redirect('admin:index')

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def any_admin_permission_required(*permission_codenames, raise_exception=False):
    """
    Decorator to check if the user has ANY of the specified admin permissions.

    Usage:
        @any_admin_permission_required('can_view_logs', 'can_manage_users')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('admin_panel:login')

            # Superusers always pass
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Check if user has any of the required permissions
            has_permission = any(
                request.user.has_admin_permission(perm)
                for perm in permission_codenames
            )

            if not has_permission:
                if raise_exception:
                    raise PermissionDenied(
                        f"One of these permissions required: {', '.join(permission_codenames)}"
                    )

                messages.error(
                    request,
                    f"You don't have permission to access this page."
                )
                return redirect('admin:index')

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def all_admin_permissions_required(*permission_codenames, raise_exception=False):
    """
    Decorator to check if the user has ALL of the specified admin permissions.

    Usage:
        @all_admin_permissions_required('can_view_providers', 'can_edit_providers')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('admin_panel:login')

            # Superusers always pass
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Check if user has all of the required permissions
            missing_permissions = [
                perm for perm in permission_codenames
                if not request.user.has_admin_permission(perm)
            ]

            if missing_permissions:
                if raise_exception:
                    raise PermissionDenied(
                        f"Missing permissions: {', '.join(missing_permissions)}"
                    )

                messages.error(
                    request,
                    f"You don't have all required permissions to access this page."
                )
                return redirect('admin:index')

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def superuser_required(view_func):
    """
    Decorator to require superuser access.
    Only superusers (master admins) can access the decorated view.

    Usage:
        @superuser_required
        def my_view(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_panel:login')

        if not request.user.is_superuser:
            messages.error(
                request,
                "Only master administrators can access this page."
            )
            return redirect('admin:index')

        return view_func(request, *args, **kwargs)
    return wrapper


def ajax_permission_required(permission_codename):
    """
    Decorator for AJAX views that require specific permission.
    Returns JSON error response instead of redirect.

    Usage:
        @ajax_permission_required('can_manage_providers')
        def my_api_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({
                    'error': 'Authentication required'
                }, status=401)

            if not request.user.has_admin_permission(permission_codename):
                return JsonResponse({
                    'error': f'Permission denied. Required: {permission_codename}'
                }, status=403)

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
