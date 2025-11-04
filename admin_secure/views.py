"""
admin_secure/views.py
Views for decrypting and managing encrypted secrets.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from .models import EncryptedSecret, SecretAccessLog
import logging

logger = logging.getLogger(__name__)


@staff_member_required
def decrypt_secret_view(request, secret_id):
    """
    Decrypt and display a secret value.
    Only accessible to superusers.
    """
    if not request.user.is_superuser:
        raise PermissionDenied("Only superusers can decrypt secrets")

    secret = get_object_or_404(EncryptedSecret, id=secret_id)

    decrypted_value = None
    error = None

    if request.method == 'POST' and 'confirm_decrypt' in request.POST:
        try:
            decrypted_value = secret.decrypt_value(request.user)

            # Log the access
            SecretAccessLog.objects.create(
                secret=secret,
                user=request.user,
                action='DECRYPTED',
                success=True,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                requesting_component='admin_interface'
            )

            messages.success(
                request,
                f"Secret '{secret.name}' decrypted successfully. "
                f"This is access #{secret.access_count}."
            )

        except Exception as e:
            error = str(e)
            logger.error(f"Failed to decrypt secret {secret.name}: {e}")

            # Log failed attempt
            SecretAccessLog.objects.create(
                secret=secret,
                user=request.user,
                action='FAILED_DECRYPT',
                success=False,
                error_message=str(e),
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                requesting_component='admin_interface'
            )

            messages.error(request, f"Failed to decrypt secret: {error}")

    context = {
        'secret': secret,
        'decrypted_value': decrypted_value,
        'error': error,
        'site_header': 'TraitKeeper Admin',
        'site_title': 'Decrypt Secret',
    }

    return render(request, 'admin_secure/decrypt_secret.html', context)


@staff_member_required
def rotate_secret_view(request, secret_id):
    """
    Rotate a secret to a new value.
    Only accessible to superusers.
    """
    if not request.user.is_superuser:
        raise PermissionDenied("Only superusers can rotate secrets")

    secret = get_object_or_404(EncryptedSecret, id=secret_id)

    if request.method == 'POST':
        new_value = request.POST.get('new_value')
        confirm_value = request.POST.get('confirm_value')

        if not new_value:
            messages.error(request, "New secret value is required")
        elif new_value != confirm_value:
            messages.error(request, "Secret values do not match")
        else:
            try:
                secret.rotate_secret(new_value, request.user)

                # Log the rotation
                SecretAccessLog.objects.create(
                    secret=secret,
                    user=request.user,
                    action='ROTATED',
                    success=True,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                    requesting_component='admin_interface'
                )

                messages.success(
                    request,
                    f"Secret '{secret.name}' rotated successfully. "
                    f"Old value has been replaced."
                )

                return redirect('admin:admin_secure_encryptedsecret_changelist')

            except Exception as e:
                logger.error(f"Failed to rotate secret {secret.name}: {e}")

                # Log failed attempt
                SecretAccessLog.objects.create(
                    secret=secret,
                    user=request.user,
                    action='ROTATED',
                    success=False,
                    error_message=str(e),
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                    requesting_component='admin_interface'
                )

                messages.error(request, f"Failed to rotate secret: {str(e)}")

    context = {
        'secret': secret,
        'site_header': 'TraitKeeper Admin',
        'site_title': 'Rotate Secret',
    }

    return render(request, 'admin_secure/rotate_secret.html', context)


@staff_member_required
def secret_access_stats(request):
    """
    View secret access statistics and recent activity.
    """
    if not request.user.is_superuser:
        raise PermissionDenied("Only superusers can view secret statistics")

    from django.db.models import Count, Max
    from datetime import timedelta
    from django.utils import timezone

    # Get secrets with access counts
    secrets = EncryptedSecret.objects.annotate(
        total_accesses=Count('access_logs'),
        last_access=Max('access_logs__timestamp')
    ).order_by('-total_accesses')

    # Recent access logs (last 100)
    recent_logs = SecretAccessLog.objects.select_related(
        'secret', 'user'
    ).order_by('-timestamp')[:100]

    # Access by action type (last 30 days)
    cutoff_date = timezone.now() - timedelta(days=30)
    access_by_action = SecretAccessLog.objects.filter(
        timestamp__gte=cutoff_date
    ).values('action').annotate(count=Count('id'))

    context = {
        'secrets': secrets,
        'recent_logs': recent_logs,
        'access_by_action': access_by_action,
        'site_header': 'TraitKeeper Admin',
        'site_title': 'Secret Access Statistics',
    }

    return render(request, 'admin_secure/access_stats.html', context)


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
