# /app/admin_panel/views.py

import logging
import time
import csv
from datetime import datetime, timedelta
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.db.models import Count, F, Q
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.contenttypes.models import ContentType

from notifications.services import NotificationService
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.admin.views.decorators import staff_member_required
from asgiref.sync import async_to_sync


from core.cache_manager import cache_manager, CacheType  # Correct import
from wallet.models import CustomUser, WalletProfile
from nft_data.models import NFTCollection, NFT, TraitType, TraitValue
# Models
from .models import AdminUser, AdminLoginAttempt, AdminLogEntry
from nft_data.models import NFTCollection, NFT, TraitType, TraitValue, PendingCollection
from indexer.models import NFTEvent
from wallet.models import CustomUser, WalletProfile

# Services
from nft_data.services import NFTDataService
from admin_panel.services import AdminAnalyticsService
from indexer.background_task_manager import task_manager, get_task_manager_status, Task, TaskPriority
from admin_secure.models import EncryptedSecret, SecretAccessLog

# Constants
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_TIME = 300
CACHE_PREFIX = 'login_attempts_'

logger = logging.getLogger(__name__)

# --- 2. CREATE A REUSABLE INSTANCE OF THE SERVICE ---

analytics_service = AdminAnalyticsService()
nft_data_service = NFTDataService()


# ============================================================================
# HELPER FUNCTIONS (Corrected to use cache_manager correctly)
# ============================================================================

def get_client_ip(request):
    """Extract the client's IP address from the request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def check_rate_limit(request):
    """
    Check if the requesting IP has exceeded the login attempt rate limit.
    Uses cache_manager for rate limiting.
    """
    ip = get_client_ip(request)
    # Use the correct CacheType to generate the key
    cache_key = cache_manager._get_key_with_prefix(CacheType.RATE_LIMIT, f"login_attempts_{ip}")
    lockout_key = cache_manager._get_key_with_prefix(CacheType.RATE_LIMIT, f"login_lockout_{ip}")
    
    # All cache_manager calls are async, so they MUST be wrapped
    attempts = async_to_sync(cache_manager.get)(cache_key) or 0
    
    if attempts >= MAX_LOGIN_ATTEMPTS:
        lockout_time = async_to_sync(cache_manager.get)(lockout_key)
        if lockout_time:
            time_left = int(lockout_time - time.time())
            if time_left > 0:
                return False, time_left
            else:
                # Clear the expired keys
                async_to_sync(cache_manager.delete)(cache_key)
                async_to_sync(cache_manager.delete)(lockout_key)
                return True, 0
        
        # If no lockout_time, set one now
        lockout_end_time = time.time() + LOCKOUT_TIME
        async_to_sync(cache_manager.set)(lockout_key, lockout_end_time, CacheType.RATE_LIMIT)
        return False, LOCKOUT_TIME
    
    return True, 0


def increment_failed_attempt(request):
    """
    Increment the failed login attempt counter for an IP.
    Triggers a security notification if the threshold is exceeded.
    """
    ip = get_client_ip(request)
    cache_key = cache_manager._get_key_with_prefix(CacheType.RATE_LIMIT, f"login_attempts_{ip}")
    lockout_key = cache_manager._get_key_with_prefix(CacheType.RATE_LIMIT, f"login_lockout_{ip}")
    
    # Get current attempts and increment
    attempts = (async_to_sync(cache_manager.get)(cache_key) or 0) + 1
    
    # ✅ CORRECTED CALL: Pass CacheType.RATE_LIMIT, not ttl
    async_to_sync(cache_manager.set)(cache_key, attempts, CacheType.RATE_LIMIT)
    
    if attempts >= MAX_LOGIN_ATTEMPTS:
        lockout_end_time = time.time() + LOCKOUT_TIME
        # ✅ CORRECTED CALL: Pass CacheType.RATE_LIMIT, not ttl
        async_to_sync(cache_manager.set)(
            lockout_key, 
            lockout_end_time, 
            CacheType.RATE_LIMIT
        )
        
        # This service is synchronous
        NotificationService.create_admin_notification(
            subject="Security Alert: Brute-Force Attempt Detected",
            message=f"The system has locked out IP address {ip} after multiple failed login attempts.",
            notification_type='failed_login',
            severity='warning'
        )

def reset_failed_attempts(request):
    """Clear any failed login attempts for the requesting IP."""
    ip = get_client_ip(request)
    cache_key = cache_manager._get_key_with_prefix(CacheType.RATE_LIMIT, f"login_attempts_{ip}")
    lockout_key = cache_manager._get_key_with_prefix(CacheType.RATE_LIMIT, f"login_lockout_{ip}")
    
    # All cache_manager calls must be wrapped
    async_to_sync(cache_manager.delete)(cache_key)
    async_to_sync(cache_manager.delete)(lockout_key)

# ============================================================================
# AUTHENTICATION VIEWS
# ============================================================================

@require_http_methods(["GET", "POST"])
def login_view(request):
    """Handle admin login with rate limiting and attempt tracking."""
    logger.info(f"Accessing login_view for user: {request.user} with method: {request.method}")

    if request.user.is_authenticated and isinstance(request.user, AdminUser):
        logger.info("User is authenticated, redirecting to admin:index")
        return redirect('admin:index')

    allowed, time_left = check_rate_limit(request)
    if not allowed:
        messages.error(request, f'Too many failed attempts. Please try again in {time_left//60} minutes.')
        logger.info(f"Rate limit exceeded for IP {get_client_ip(request)}. Time left: {time_left // 60} minutes.")
        return render(request, 'admin/login.html')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember') == 'on'
        ip_address = get_client_ip(request)

        login_attempt = AdminLoginAttempt(
            ip_address=ip_address,
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        logger.info(f"Attempting to authenticate user: {username}")
        user = authenticate(request, username=username, password=password)

        if user is not None and isinstance(user, AdminUser):
            logger.info(f"Authentication successful for user: {username}")
            reset_failed_attempts(request)
            login_attempt.set_user(user)
            login_attempt.success = True
            login_attempt.save()
            login(request, user)
            if not remember_me:
                request.session.set_expiry(0)
            logger.info(f"User logged in: {request.user.is_authenticated}")
            return redirect('admin:index')
        else:
            logger.warning(f"Authentication failed for user: {username}")
            increment_failed_attempt(request)
            login_attempt.success = False
            login_attempt.save()
            
            try:
                query = Q(username=username) | Q(email=username)
                user = AdminUser.objects.filter(query).first()
                if not user:
                    error_message = 'Invalid username or email.'
                elif not user.check_password(password):
                    error_message = 'Invalid password.'
                elif not user.is_active:
                    error_message = 'User account is inactive.'
                elif not user.is_staff:
                    error_message = 'Only staff users can log in to the admin panel.'
                else:
                    error_message = 'An unexpected error occurred during login.'
            except Exception:
                error_message = 'Invalid username or email.'
            
            messages.error(request, error_message)
            logger.info(f"Set error message: {error_message}")
            return render(request, 'admin/login.html')

    logger.info("Rendering login page for GET request")
    return render(request, 'admin/login.html')


@login_required
def admin_logout(request):
    """Log out the current admin user."""
    if isinstance(request.user, AdminUser):
        logout(request)
        messages.success(request, 'You have been successfully logged out.')
    return redirect('admin_panel:login')


def password_reset_request(request):
    """Handle password reset request via email."""
    if request.method == 'POST':
        email = request.POST.get('email')
        user = AdminUser.objects.filter(email=email).first()
        if user:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_link = request.build_absolute_uri(
                reverse('admin_panel:password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
            )
            subject = 'Password Reset Request - TraitKeeper Admin'
            message = render_to_string('admin/password_reset_email.html', {
                'user': user,
                'reset_link': reset_link,
            })
            send_mail(subject, message, 'from@example.com', [email], fail_silently=False)
        return render(request, 'admin/password_reset_done.html', {
            'message': 'If an account with that email exists, a password reset link has been sent.'
        })
    return redirect('admin_panel:login')


def password_reset_confirm(request, uidb64, token):
    """Confirm password reset with token validation."""
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = AdminUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, AdminUser.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                return render(request, 'admin/password_reset_complete.html', {
                    'message': 'Your password has been reset. You can now log in.'
                })
        else:
            form = SetPasswordForm(user)
        return render(request, 'admin/password_reset_confirm.html', {
            'form': form, 'uidb64': uidb64, 'token': token
        })
    else:
        return render(request, 'admin/password_reset_confirm.html', {
            'error': 'Invalid or expired reset link.'
        })


# ============================================================================
# ADMIN USER MANAGEMENT
# ============================================================================

@login_required
def select_admin_user(request):
    """Display admin user management dashboard."""
    yesterday = timezone.now() - timedelta(days=1)
    recent_logins = AdminLoginAttempt.objects.filter(
        timestamp__gte=yesterday, 
        success=True
    ).count()
    active_admins = AdminUser.objects.filter(is_active=True).count()
    superusers = AdminUser.objects.filter(is_superuser=True).count()
    twofa_enabled = AdminUser.objects.filter(two_factor_enabled=True).count()
    admin_users = AdminUser.objects.all().order_by('-date_joined')
    recent_attempts = AdminLoginAttempt.objects.filter(
        timestamp__gte=yesterday
    ).order_by('-timestamp')[:10]
    
    context = {
        'title': 'Admin Users',
        'subtitle': 'Manage Administrator Accounts',
        'recent_logins': recent_logins,
        'active_admins': active_admins,
        'superusers': superusers,
        'twofa_count': twofa_enabled,
        'admin_users': admin_users,
        'all_admin_users': admin_users,
        'recent_attempts': recent_attempts,
        'opts': AdminUser._meta,
        'cl': {'queryset': admin_users},
        'has_add_permission': request.user.is_superuser,
    }
    return render(request, 'admin/admin_panel/adminuser/select_form.html', context)


@login_required
def admin_log_export(request):
    """Export admin log entries to CSV with filtering support."""
    format_type = request.GET.get('format', '')
    queryset = AdminLogEntry.objects.all()

    # Apply filters
    user_id = request.GET.get('user__id__exact')
    if user_id:
        queryset = queryset.filter(user__id=user_id)

    action_flag = request.GET.get('action_flag__exact')
    if action_flag:
        queryset = queryset.filter(action_flag=action_flag)

    content_type_id = request.GET.get('content_type__id__exact')
    if content_type_id:
        queryset = queryset.filter(content_type__id=content_type_id)

    date_from = request.GET.get('date_from')
    if date_from:
        queryset = queryset.filter(action_time__gte=date_from)

    date_to = request.GET.get('date_to')
    if date_to:
        queryset = queryset.filter(action_time__lte=date_to)

    search_query = request.GET.get('q')
    if search_query:
        queryset = queryset.filter(
            Q(object_repr__icontains=search_query) |
            Q(change_message__icontains=search_query)
        )

    if format_type == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="admin_log_entries.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'User', 'Action', 'Content Type', 'Object', 'Change Message'])
        
        for entry in queryset:
            writer.writerow([
                entry.action_time.strftime('%Y-%m-%d %H:%M:%S'),
                entry.user.username if entry.user else '-',
                entry.get_action_flag_display(),
                str(entry.content_type) if entry.content_type else '-',
                entry.object_repr,
                entry.change_message
            ])
        
        return response
    
    return redirect('admin:admin_panel_adminlogentry_changelist')


# ============================================================================
# NFT DATA VIEWS
# ============================================================================

@login_required
def nft_data_models(request):
    """Display overview of all NFT-related data models."""
    nft_models = [
        {'name': 'NFT Collections', 'app_label': 'nft_data', 'model': 'nftcollection', 
         'count': NFTCollection.objects.count()},
        {'name': 'NFTs', 'app_label': 'nft_data', 'model': 'nft', 
         'count': NFT.objects.count()},
        {'name': 'NFT Events', 'app_label': 'indexer', 'model': 'nftevent', 
         'count': NFTEvent.objects.count()},
        {'name': 'Trait Types', 'app_label': 'nft_data', 'model': 'traittype', 
         'count': TraitType.objects.count()},
        {'name': 'Trait Values', 'app_label': 'nft_data', 'model': 'traitvalue', 
         'count': TraitValue.objects.count()},
        {'name': 'Pending Collections', 'app_label': 'nft_data', 'model': 'pendingcollection', 
         'count': PendingCollection.objects.count()},
    ]
    context = {
        'title': 'NFT Data Models',
        'subtitle': 'Manage NFT-related data models.',
        'nft_models': nft_models,
    }
    return render(request, 'admin/nft_data/models.html', context)


@login_required
def nft_collections(request):
    """List all NFT collections with pagination."""
    collections = NFTCollection.objects.all().order_by('-updated_at')
    paginator = Paginator(collections, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'page_obj': page_obj,
        'page_title': 'NFT Collections',
    }
    return render(request, 'admin/nft_data/collections.html', context)


@login_required
def nft_collection_detail(request, collection_address):
    """Display detailed information about a specific NFT collection."""
    collection = get_object_or_404(NFTCollection, address=collection_address)
    nfts = NFT.objects.filter(collection=collection).order_by('name')
    paginator = Paginator(nfts, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    trait_types = TraitType.objects.filter(collection=collection)
    context = {
        'collection': collection,
        'page_obj': page_obj,
        'trait_types': trait_types,
        'page_title': f'Collection: {collection.name}',
    }
    return render(request, 'admin/nft_data/collection_detail.html', context)


@login_required
def trait_types(request):
    """Display all trait types organized by collection."""
    trait_types = TraitType.objects.select_related('collection').all()
    collections = {}
    for trait_type in trait_types:
        collection = trait_type.collection
        if collection.address not in collections:
            collections[collection.address] = {
                'collection': collection,
                'trait_types': []
            }
        collections[collection.address]['trait_types'].append(trait_type)
    context = {
        'collections': collections,
        'page_title': 'NFT Trait Types',
    }
    return render(request, 'admin/nft_data/trait_types.html', context)


@login_required
def trait_values(request, trait_type_id):
    """Display all values for a specific trait type with rarity information."""
    trait_type = get_object_or_404(TraitType, id=trait_type_id)
    values = TraitValue.objects.with_count_and_rarity(trait_type)
    values = sorted(values, key=lambda x: x.rarity or 0)
    paginator = Paginator(values, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'trait_type': trait_type,
        'page_obj': page_obj,
        'page_title': f'Trait: {trait_type.name}',
    }
    return render(request, 'admin/nft_data/trait_values.html', context)


@login_required
def nft_transactions(request):
    """Display NFT transaction history (sale events)."""
    events = NFTEvent.objects.filter(event_type='SALE').select_related(
        'nft', 'collection'
    ).order_by('-timestamp')
    paginator = Paginator(events, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'page_obj': page_obj,
        'page_title': 'NFT Transactions',
    }
    return render(request, 'admin/nft_data/transactions.html', context)


# ============================================================================
# PENDING COLLECTION MANAGEMENT
# ============================================================================

@login_required
@require_http_methods(["GET", "POST"])
def pending_collections(request):
    """
    Handle pending collection approvals, rejections, and deletions.
    Business logic is delegated to NFTDataService.
    """
    if request.method == 'POST':
        action = request.POST.get('action')
        collection_ids = request.POST.getlist('collection_ids')

        if not collection_ids:
            messages.error(request, "Please select at least one collection to perform this action.")
            return redirect('admin:index')

        if not action:
            messages.error(request, "Please select an action to perform.")
            return redirect('admin:index')

        collections = list(
            PendingCollection.objects.filter(id__in=collection_ids)
        )

        if action == 'approve':
            if not request.user.has_perm('nft_data.approve_pendingcollection'):
                messages.error(request, "You do not have permission to approve collections.")
                return redirect('admin:index')
            
            for collection in collections:
                result = async_to_sync(nft_data_service.approve_pending_collection)(
                    pending_collection_id=collection.id,
                    approved_by_user=request.user
                )
                if result.get("success"):
                    messages.success(request, f"Collection '{collection.name}' approved successfully.")
                else:
                    messages.error(request, f"Failed to approve '{collection.name}': {result.get('error')}")
        
        elif action == 'reject':
            if not request.user.has_perm('nft_data.reject_pendingcollection'):
                messages.error(request, "You do not have permission to reject collections.")
                return redirect('admin:index')
            
            for collection in collections:
                result = async_to_sync(nft_data_service.reject_pending_collection)(
                    pending_collection_id=collection.id,
                    rejected_by_user=request.user
                )
                if result.get("success"):
                    messages.success(request, f"Collection '{collection.name}' rejected successfully.")
                else:
                    messages.error(request, f"Failed to reject '{collection.name}': {result.get('error')}")
        
        elif action == 'delete':
            if not request.user.has_perm('nft_data.delete_pendingcollection'):
                messages.error(request, "You do not have permission to delete collections.")
                return redirect('admin:index')
            
            for collection in collections:
                collection_name = collection.name
                collection.delete()
                messages.success(request, f"Collection '{collection_name}' deleted successfully.")
        
        else:
            messages.error(request, "Invalid action selected.")

        return redirect('admin:index')

    # GET request - display pending collections
    collections = PendingCollection.objects.all().order_by('-created_at')
    paginator = Paginator(collections, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'page_title': 'Pending Collections',
    }
    return render(request, 'admin/pending_collections.html', context)


# ============================================================================
# NFT COLLECTION ACTIONS
# ============================================================================

@login_required
@require_http_methods(["GET"])
def nft_collection_action(request, address, action):
    """
    Handle NFT collection actions (list/delist/delete).
    Delegates to NFTDataService.
    """
    try:
        collection = NFTCollection.objects.get(address=address)
    except NFTCollection.DoesNotExist:
        messages.error(request, "Collection not found.")
        return redirect('admin:index')

    notification_base = (
        f"NFT collection '{collection.name}' "
        f"(Address: {collection.address}) "
    )

    if action == 'list':
        if not request.user.has_perm('nft_data.change_nftcollection'):
            messages.error(request, "You do not have permission to list collections.")
            return redirect('admin:index')
        
        result = nft_data_service.list_collection(collection.address)
        
        if result["success"]:
            messages.success(request, f"Collection '{collection.name}' has been listed.")
            notification_message = notification_base + f"was listed by {request.user.username}."
            severity = 'info'
        else:
            messages.error(request, f"Error listing collection: {result['error']}")
            notification_message = notification_base + f"listing failed. Error: {result['error']}"
            severity = 'error'
    
    elif action == 'delist':
        if not request.user.has_perm('nft_data.change_nftcollection'):
            messages.error(request, "You do not have permission to delist collections.")
            return redirect('admin:index')
        
        result = nft_data_service.delist_collection(collection.address)
        
        if result["success"]:
            messages.success(request, f"Collection '{collection.name}' has been delisted.")
            notification_message = notification_base + f"was delisted by {request.user.username}."
            severity = 'info'
        else:
            messages.error(request, f"Error delisting collection: {result['error']}")
            notification_message = notification_base + f"delisting failed. Error: {result['error']}"
            severity = 'error'
    elif action == 'delete':
        if not request.user.has_perm('nft_data.delete_nftcollection'):
            messages.error(request, "You do not have permission to delete collections.")
            return redirect('admin:index')
        
        collection_name = collection.name
        
        AdminLogEntry.objects.log_action(
            user_id=request.user.id,
            content_type_id=(ContentType.objects.get_for_model(NFTCollection)).pk,
            object_id=collection.address,
            object_repr=str(collection),
            action_flag=3,
            change_message=f"Deleted collection: {collection_name}"
        )
        
        collection.delete()
        messages.success(request, f"Collection '{collection_name}' has been deleted.")
        notification_message = notification_base + f"was deleted by {request.user.username}."
        severity = 'info'
    
    else:
        messages.error(request, "Invalid action.")
        notification_message = notification_base + f"action failed. Invalid action: {action}"
        severity = 'error'

    # Send notifications to all admin users
    admin_users = list(
        AdminUser.objects.filter(is_active=True, is_staff=True)
    )
    for admin_user in admin_users:
        NotificationService.create_admin_notification(
            subject=f"Collection Action: {action.capitalize()}",
            message=notification_message,
            notification_type='collection_action',
            severity=severity,
            admin_user=admin_user
        )

    return redirect('admin:index')


# ============================================================================
# STATISTICS & ANALYTICS (Corrected)
# ============================================================================

@login_required
def statistics(request):
    """
    Renders the main statistics dashboard by calling the AnalyticsService.
    All business logic and caching is handled by the service layer.
    """
    if not request.user.is_staff:
        return render(request, 'admin/permission_denied.html', status=403)

    user_stats = analytics_service.get_user_stats()
    nft_stats = analytics_service.get_nft_stats()
    
    context = {
        'title': 'Statistics Dashboard',
        'user_stats': user_stats,
        'nft_stats': nft_stats,
    }
    return render(request, 'admin/statistics.html', context)


@login_required
def export_statistics(request):
    """Export all statistics to CSV format."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="traitkeeper_statistics.csv"'
    
    end_date = timezone.now()
    start_date = end_date - timedelta(days=7)
    
    # Exclude admin users from regular user counts
    admin_user_ids = list(AdminUser.objects.values_list('id', flat=True))

    user_stats = {
        'total_users': CustomUser.objects.exclude(id__in=admin_user_ids).count(),
        'active_users': CustomUser.objects.exclude(id__in=admin_user_ids).filter(last_login__gte=start_date).count(),
        'wallet_connections': WalletProfile.objects.count(),
        'admin_users': AdminUser.objects.count(),
    }
    
    nft_stats = {
        'collections': NFTCollection.objects.count(),
        'nfts': NFT.objects.count(),
        'transactions': NFTEvent.objects.filter(event_type='SALE').count(),
    }
    
    writer = csv.writer(response)
    writer.writerow(['Category', 'Metric', 'Value'])
    
    for key, value in user_stats.items():
        writer.writerow(['User Stats', key.replace('_', ' ').title(), value])
    
    for key, value in nft_stats.items():
        writer.writerow(['NFT Stats', key.title(), value])
    
    return response


@login_required
def user_activity_data(request):
    """
    Returns JSON data for user login activity chart (last 7 days).
    Uses the core cache_manager correctly.
    """
    logger.info(f"Fetching user activity data for request by user: {request.user.username}")
    
    cache_key = cache_manager._get_key_with_prefix(CacheType.METRICS, "user_activity_7days")
    
    # ✅ CORRECTED: Use async_to_sync for the async 'get' method
    chart_data = async_to_sync(cache_manager.get)(cache_key)
    
    if chart_data:
        logger.debug("Cache hit for user activity data.")
        return JsonResponse(chart_data)
    
    logger.info("Cache miss for user activity data, calculating...")
    
    end_date = timezone.now()
    start_date = end_date - timedelta(days=7)
    login_activity = {}
    
    for i in range(7):
        day = start_date + timedelta(days=i)
        day_str = day.strftime('%b %d')
        login_activity[day_str] = 0
    
    login_attempts = list(
        AdminLoginAttempt.objects.filter(
            timestamp__gte=start_date,
            timestamp__lt=end_date + timedelta(days=1), # Use '<' for next day
            success=True
        ).extra(
            select={'day': "date(timestamp)"}
        ).values('day').annotate(count=Count('id'))
    )
    
    for attempt in login_attempts:
        day_obj = attempt['day']
        if isinstance(day_obj, str):
            day_obj = datetime.strptime(attempt['day'], '%Y-%m-%d').date()
        day_str = day_obj.strftime('%b %d')
        if day_str in login_activity:
            login_activity[day_str] = attempt['count']
    
    chart_data = {
        'labels': list(login_activity.keys()),
        'data': list(login_activity.values())
    }

    # Pass CacheType.METRICS, not ttl
    async_to_sync(cache_manager.set)(
        cache_key, 
        chart_data, 
        CacheType.METRICS
    )
    
    logger.info(f"Returning user activity data: {chart_data}")
    return JsonResponse(chart_data)


@login_required
def signup_activity_data(request):
    """
    Returns JSON data for signup activity chart (last 7 days).
    Uses the core cache_manager correctly.
    """
    logger.info(f"Fetching signup activity data for request by user: {request.user.username}")
    
    cache_key = cache_manager._get_key_with_prefix(CacheType.METRICS, "signup_activity_7days")

    # Use async_to_sync for the async 'get' method
    signup_data = async_to_sync(cache_manager.get)(cache_key)
    
    if signup_data:
        logger.debug("Cache hit for signup activity data.")
        return JsonResponse(signup_data)
    
    logger.info("Cache miss for signup activity data, calculating...")
    
    end_date = timezone.now()
    start_date = end_date - timedelta(days=7)
    signup_activity = {}
    
    for i in range(7):
        day = start_date + timedelta(days=i)
        day_str = day.strftime('%b %d')
        signup_activity[day_str] = 0
    
    signups = list(
        CustomUser.objects.filter(
            date_joined__gte=start_date,
            date_joined__lt=end_date + timedelta(days=1) # Use '<' for next day
        ).extra(
            select={'day': "date(date_joined)"}
        ).values('day').annotate(count=Count('id'))
    )
    
    for signup in signups:
        day_obj = signup['day']
        if isinstance(day_obj, str):
            day_obj = datetime.strptime(signup['day'], '%Y-%m-%d').date()
        day_str = day_obj.strftime('%b %d')
        if day_str in signup_activity:
            signup_activity[day_str] = signup['count']
    
    signup_data = {
        'labels': list(signup_activity.keys()),
        'data': list(signup_activity.values())
    }
    
    # Pass CacheType.METRICS, not ttl
    async_to_sync(cache_manager.set)(
        cache_key, 
        signup_data, 
        CacheType.METRICS
    )
    
    logger.info(f"Returning signup activity data: {signup_data}")
    return JsonResponse(signup_data)


@login_required
def nft_stats_data(request):
    """
    Returns JSON data for NFT statistics chart.
    Delegates to AnalyticsService.
    """
    logger.info(f"Fetching NFT stats data for request by user: {request.user.username}")
    
    stats = analytics_service.get_nft_stats()
    
    response_data = {
        'labels': ['Collections', 'NFTs', 'Transactions'],
        'data': [stats['collections'], stats['nfts'], stats['transactions']]
    }
    
    logger.info(f"Returning NFT stats data: {response_data}")
    return JsonResponse(response_data)


@login_required
def user_stats_data(request):
    """
    Returns JSON data for user statistics chart.
    Delegates to AnalyticsService.
    """
    logger.info(f"Fetching user stats data for request by user: {request.user.username}")
    
    user_stats = analytics_service.get_user_stats()
    
    response_data = {
        'labels': ['Users', 'Active Users', 'Wallet Connections', 'Admin Users'],
        'data': [
            user_stats['total_users'],
            user_stats['active_users'],
            user_stats['wallet_connections'],
            user_stats['admin_users']
        ],
        'retention_rate': user_stats['retention_rate']
    }
    
    logger.info(f"Returning user stats data: {response_data}")
    return JsonResponse(response_data)


# ============================================================================
# BACKGROUND TASK MANAGEMENT API
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def task_manager_status(request):
    """Get current status of the background task manager."""
    try:
        status_data = get_task_manager_status()
        return Response(status_data)
    except Exception as e:
        logger.error(f"Error getting task manager status: {e}", exc_info=True)
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@staff_member_required
def trigger_collection_indexing(request):
    """Manually trigger collection indexing."""
    try:
        collection_address = request.data.get('collection_address')
        priority = request.data.get('priority', 'medium').upper()
        
        if not collection_address:
            return Response(
                {'error': 'collection_address is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        task_priority = getattr(TaskPriority, priority, TaskPriority.MEDIUM)
        
        task = Task(
            id=f"manual_index_{collection_address}_{int(timezone.now().timestamp())}",
            name=f"Manual Index Collection {collection_address}",
            function=task_manager.indexer_service.process_nft_events,
            kwargs={
                'collection_address': collection_address, 
                'limit': 100, 
                'use_db': True
            },
            priority=task_priority
        )
        
        task_manager.add_task(task)
        
        logger.info(f"Manual indexing task queued for collection {collection_address} by {request.user.username}")
        
        return Response({
            'message': f'Indexing task queued for collection {collection_address}',
            'task_id': task.id,
            'priority': priority
        })
        
    except Exception as e:
        logger.error(f"Error triggering collection indexing: {e}", exc_info=True)
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@staff_member_required  
def trigger_stats_update(request):
    """Manually trigger collection stats update."""
    try:
        collection_address = request.data.get('collection_address')
        
        if collection_address:
            # Update specific collection
            task = Task(
                id=f"manual_stats_{collection_address}_{int(timezone.now().timestamp())}",
                name=f"Manual Stats Update {collection_address}",
                function=task_manager.indexer_service.update_collection_stats,
                args=(collection_address,),
                priority=TaskPriority.HIGH
            )
        else:
            # Update all collections
            task = Task(
                id=f"manual_stats_all_{int(timezone.now().timestamp())}",
                name="Manual Stats Update All Collections",
                function=task_manager._run_collection_stats_update,
                priority=TaskPriority.HIGH
            )
        
        task_manager.add_task(task)
        
        logger.info(f"Manual stats update task queued by {request.user.username}")
        
        return Response({
            'message': 'Stats update task queued',
            'task_id': task.id
        })
        
    except Exception as e:
        logger.error(f"Error triggering stats update: {e}", exc_info=True)
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@staff_member_required
def task_history(request):
    """Get recent task execution history."""
    try:
        # Get last 50 tasks from history
        history = list(task_manager.task_history)[-50:]
        return Response({
            'task_history': history,
            'total_tasks': len(task_manager.task_history)
        })
    except Exception as e:
        logger.error(f"Error getting task history: {e}", exc_info=True)
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@staff_member_required
def restart_task_manager(request):
    """Restart the background task manager."""
    try:
        task_manager.stop()
        import asyncio
        from asgiref.sync import async_to_sync
        async_to_sync(task_manager.start)()
        
        logger.info(f"Task manager restarted by {request.user.username}")
        
        return Response({'message': 'Task manager restarted successfully'})
    except Exception as e:
        logger.error(f"Error restarting task manager: {e}", exc_info=True)
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@login_required
def task_dashboard(request):
    """Render the task management dashboard."""
    # Check if user is admin
    from admin_panel.models import AdminUser
    if not isinstance(request.user, AdminUser) and not request.user.is_staff:
        raise Http404("Page not found")
    return render(request, 'admin_panel/task_dashboard.html')


@login_required
def secrets_management(request):
    """
    Secrets Management Dashboard for admin panel.
    Shows encrypted secrets, access logs, and statistics.
    Only accessible to superusers.
    """
    from admin_panel.models import AdminUser
    from django.http import Http404
    from django.core.exceptions import PermissionDenied
    from django.db.models import Count, Max

    # Check if user is admin
    if not isinstance(request.user, AdminUser) and not request.user.is_staff:
        raise Http404("Page not found")

    # Only superusers can access secrets
    if not request.user.is_superuser:
        raise PermissionDenied("Only superusers can access secret management")

    # Get all secrets with access counts
    secrets = EncryptedSecret.objects.annotate(
        total_accesses=Count('access_logs'),
        last_access=Max('access_logs__timestamp')
    ).order_by('-created_at')

    # Get recent access logs (last 50)
    recent_logs = SecretAccessLog.objects.select_related(
        'secret', 'user'
    ).order_by('-timestamp')[:50]

    # Access statistics by action type (last 30 days)
    from datetime import timedelta
    cutoff_date = timezone.now() - timedelta(days=30)
    access_by_action = SecretAccessLog.objects.filter(
        timestamp__gte=cutoff_date
    ).values('action').annotate(count=Count('id'))

    # Secret type distribution
    secret_type_stats = EncryptedSecret.objects.filter(
        is_active=True
    ).values('secret_type').annotate(count=Count('id'))

    # Calculate total stats
    total_secrets = secrets.count()
    active_secrets = secrets.filter(is_active=True).count()
    total_accesses = SecretAccessLog.objects.count()
    failed_attempts = SecretAccessLog.objects.filter(success=False).count()

    context = {
        'secrets': secrets,
        'recent_logs': recent_logs,
        'access_by_action': list(access_by_action),
        'secret_type_stats': list(secret_type_stats),
        'total_secrets': total_secrets,
        'active_secrets': active_secrets,
        'total_accesses': total_accesses,
        'failed_attempts': failed_attempts,
    }

    return render(request, 'admin_panel/secrets_management.html', context)