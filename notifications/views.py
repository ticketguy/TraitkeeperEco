from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.conf import settings
from .models import Notification, NotificationPreference
import json

@login_required
def notifications_view(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:20]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    notification_prefs = {
        pref.notification_type: pref for pref in NotificationPreference.objects.filter(user=request.user)
    }
    for notification_type, _ in NotificationPreference.NOTIFICATION_TYPES:
        if notification_type not in notification_prefs:
            notification_prefs[notification_type] = NotificationPreference(
                user=request.user,
                notification_type=notification_type,
                enabled=True
            )

    context = {
        'notifications': notifications,
        'unread_notifications_count': unread_count,
        'notification_prefs': notification_prefs,
    }
    return context

@login_required
@csrf_exempt
def mark_all_notifications_read(request):
    if request.method == 'POST':
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
@require_POST
def mark_notification_read(request):
    try:
        notification_id = request.POST.get('notification_id')
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.is_read = True
        notification.save()
        return JsonResponse({'success': True})
    except Notification.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def save_notification_preferences(request):
    if request.method == 'POST':
        for notification_type, _ in NotificationPreference.NOTIFICATION_TYPES:
            enabled = request.POST.get(notification_type) == 'on'
            notify_via_email = request.POST.get(f"{notification_type}_email") == 'on'
            notify_via_push = request.POST.get(f"{notification_type}_push") == 'on'
            
            specific_collections = request.POST.get(f"{notification_type}_collections", '').split(',')
            specific_collections = [c.strip() for c in specific_collections if c.strip()]
            specific_traits = request.POST.get(f"{notification_type}_traits", '').split(',')
            specific_traits = [t.strip() for t in specific_traits if t.strip()]
            specific_wallets = request.POST.get(f"{notification_type}_wallets", '').split(',')
            specific_wallets = [w.strip() for w in specific_wallets if w.strip()]
            
            pref, created = NotificationPreference.objects.get_or_create(
                user=request.user,
                notification_type=notification_type,
                defaults={'enabled': enabled}
            )
            if not created:
                pref.enabled = enabled
                pref.notify_via_email = notify_via_email
                pref.notify_via_push = notify_via_push
                pref.specific_collections = specific_collections
                pref.specific_traits = specific_traits
                pref.specific_wallets = specific_wallets
                if notification_type == 'transaction':
                    min_value = request.POST.get(f"{notification_type}_min_value", '0')
                    try:
                        pref.transaction_min_value = float(min_value) if min_value else None
                    except ValueError:
                        pref.transaction_min_value = None
                pref.save()
        return redirect('index')
    return redirect('index')

@login_required
@require_POST
def save_push_subscription(request):
    try:
        subscription_data = json.loads(request.body)
        PushInformation.objects.create(
            user=request.user,
            subscription_json=subscription_data
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})