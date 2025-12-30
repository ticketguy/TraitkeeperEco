# traitkeeper/admin_site.py
import json
import re
from . import settings
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.contrib.admin import AdminSite
from django.apps import apps
from django.template.response import TemplateResponse
from django.http import Http404
from nft_data.models import NFT, NFTCollection, PendingCollection
from wallet.models import CustomUser, WalletProfile
from admin_panel.models import AdminUser, AdminLogEntry, AdminLoginAttempt, PrimaryProviderSetting
from notifications.models import AdminNotification
from indexer.models import NFTEvent, CollectionMarketStats
from django.utils import timezone
from django.db.models.functions import TruncDate  
from django.contrib import messages
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.db.models import Count, F
from django.core.cache import cache
import psutil
from django.shortcuts import redirect
from traitkeeper.admin_utils import AdvancedFilterAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.urls import reverse, path, include, re_path
from django.shortcuts import HttpResponseRedirect
from nft_data.services import NFTDataService
from django.contrib.contenttypes.models import ContentType
from asgiref.sync import async_to_sync
import logging
from traitkeeper.models import Token  # Use the custom Token model

# Configure logging for the admin site
logger = logging.getLogger('nft_data.services')
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class CustomAdminSite(AdminSite):
    """
    Custom AdminSite for TraitKeeper with extended functionality.
    Extends Django's default AdminSite to add custom views, URLs, and behavior tailored for TraitKeeper's admin panel.
    """
    # Customize the admin site's branding
    site_header = 'TraitKeeper Admin'  # Header displayed on all admin pages
    site_title = 'TraitKeeper Admin Portal'  # Title tag for admin pages
    index_title = 'Welcome to TraitKeeper Admin Portal'  # Title on the admin index page
    login_url = 'admin_panel:login'  # URL name for the custom login view

    def __init__(self, *args, **kwargs):
        """
        Initialize the CustomAdminSite.
        Unregisters CustomUser and WalletProfile models to prevent them from being managed directly
        through this admin site, as they may be handled elsewhere (e.g., via a custom UserAdmin).
        """
        super().__init__(*args, **kwargs)
        # Unregister models that should not be managed directly in this admin site
        for model in [CustomUser, WalletProfile]:
            if self._registry.get(model):
                self.unregister(model)

    def get_urls(self):
        """
        Add custom URLs for admin views and override the default app_list URL pattern.
        The app_list pattern is customized to include only specific apps (including traitkeeper)
        to control which apps are accessible in the admin interface.

        Returns:
            list: A list of URL patterns combining custom URLs with the parent's URLs.
        """
        from django.urls import re_path  # Import re_path for regex-based URL patterns

        # Get the default URLs from the parent AdminSite class
        urls = super().get_urls()

        # Filter out the default app_list URL pattern to replace it with our own
        # Use hasattr to safely check for the 'name' attribute, as urls contains both URLPattern
        # (which have a 'name') and URLResolver objects (which do not)
        filtered_urls = []
        for url in urls:
            if hasattr(url, 'name') and url.name == 'app_list':
                continue  # Skip the default app_list pattern
            filtered_urls.append(url)

        # Define custom URLs for the admin site
        custom_urls = [
            # Custom app_list URL pattern to include only specific apps
            # This pattern ensures that only allowed apps can be accessed via /admin/<app_label>/
            # Added traitkeeper to fix NoReverseMatch error when traitkeeper appeared in admin logs
            re_path(
                r'^(?P<app_label>wallet|admin_panel|auth|nft_data|advertisement|indexer|traitkeeper|analytics|marketplace|learn|nftmemories|notifications|axplorer|system_health|admin_secure)/$',
                self.admin_view(self.app_index),
                name='app_list'
            ), 
            # URL for manually populating NFT collections
            path('populate-collections/', self.admin_view(self.populate_collections_view), name='populate_collections'),
            # URL for refreshing existing NFT collections
            path('refresh-collections/', self.admin_view(self.refresh_collections_view), name='refresh_collections'),  
            # URL for viewing and managing admin notifications
            path('notifications/', self.admin_view(self.notifications_view), name='notifications_view'),  
            # URL for marking a notification as read
            path('notifications/mark-read/<int:notification_id>/', self.admin_view(self.mark_notification_read), name='mark_notification_read'),
            # URL for marking a notification as unread (all notification view page)
            path('notifications/mark-unread/<int:notification_id>/', self.admin_view(self.mark_notification_unread), name='mark_notification_unread'),
            # URL for viewing single admin notifications
            path('notifications/view/<int:notification_id>/', self.admin_view(self.view_notification), name='view_notification'),  
            # URL for marking all notifications as read (for header bar)
            path('notifications/mark-all-read/', self.admin_view(self.mark_all_notifications_read), name='mark_all_notifications_read'),
            # URL for setting the primary RPC provider for the indexer
            path('set-primary-provider/', self.admin_view(self.set_primary_provider_view), name='set_primary_provider'),
            # URL for listing all API tokens
            path('tokens/', self.admin_view(self.token_list_view), name='token_list_view'),
            # URL for generating new API tokens for external users
            path('generate-tokens/', self.admin_view(self.generate_tokens_view), name='generate_tokens'),
        ]

        # Combine custom URLs with the filtered parent URLs
        return custom_urls + filtered_urls

    @staticmethod
    def validate_websocket_url(url):
        """
        Validate that a WebSocket URL is in the correct format (ws:// or wss://).
        Used when adding new RPC providers in set_primary_provider_view.

        Args:
            url (str): The WebSocket URL to validate.

        Returns:
            bool: True if the URL is valid or empty (optional field), False otherwise.
        """
        if not url:
            return True  # Optional field
        
        # Regex pattern for validating WebSocket URLs
        websocket_pattern = re.compile(
            r'^wss?://'  # ws:// or wss://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        return bool(websocket_pattern.match(url))

    def set_primary_provider_view(self, request):
        """
        View to set the primary RPC provider or add a new one for the indexer.
        Allows admins to manage RPC providers used for blockchain data fetching.

        Args:
            request (HttpRequest): The HTTP request object.

        Returns:
            TemplateResponse: Renders the set_primary_provider.html template with the provider management form.
        """
        # Fetch all active providers and the current primary provider
        available_providers = list(PrimaryProviderSetting.objects.filter(is_active=True).values_list('name', flat=True))
        current_provider = PrimaryProviderSetting.objects.filter(is_primary=True).first()
        # Fallback to settings if no primary provider is set
        current_provider_name = current_provider.name if current_provider else getattr(settings, 'PRIMARY_RPC_PROVIDER', 'helius')
        all_providers = PrimaryProviderSetting.objects.all()
        
        # Prepare context for the template
        context = dict(
            self.each_context(request),
            title="Set Primary RPC Provider",
            available_providers=available_providers,
            current_provider=current_provider_name,
            all_providers=all_providers
        )

        if request.method == "POST":
            # Check if the user has permission to change the primary provider
            if not request.user.has_perm('admin_panel.change_primaryprovidersetting'):
                messages.error(request, "You do not have permission to change the primary provider.")
                return self.template_response(request, 'admin/set_primary_provider.html', context)

            action = request.POST.get('action')
            if action == 'set_provider':
                # Handle setting a new primary provider
                provider_name = request.POST.get('provider')
                if provider_name not in available_providers:
                    messages.error(request, "Invalid provider selected.")
                    return self.template_response(request, 'admin/set_primary_provider.html', context)

                try:
                    provider = PrimaryProviderSetting.objects.get(name=provider_name)
                    provider.is_primary = True
                    provider.save()

                    # Log the action in AdminLogEntry
                    AdminLogEntry.objects.log_action(
                        user_id=request.user.id,
                        content_type_id=ContentType.objects.get_for_model(PrimaryProviderSetting).pk,
                        object_id=provider.pk,
                        object_repr=f"Primary Provider: {provider_name}",
                        action_flag=2,
                        change_message=f"Changed primary provider to {provider_name}"
                    )

                    # Notify all admin users of the change
                    admin_users = AdminUser.objects.filter(is_active=True, is_staff=True)
                    notification_message = (
                        f"Primary provider changed by {request.user.username}:\n"
                        f"New Provider: {provider_name}\n"
                        f"Previous Provider: {current_provider_name}"
                    )
                    for admin_user in admin_users:
                        AdminNotification.objects.create(
                            type='provider_changed',
                            message=notification_message,
                            admin_user=admin_user,
                        )
                        logger.info(f"Sent notification to admin {admin_user.username}")

                    messages.success(request, f"Primary provider successfully set to {provider_name}.")
                except PrimaryProviderSetting.DoesNotExist:
                    messages.error(request, "Selected provider does not exist.")
                except Exception as e:
                    logger.error(f"Error setting primary provider: {str(e)}")
                    messages.error(request, f"Error setting primary provider: {str(e)}")

            elif action == 'add_provider':
                # Handle adding a new provider
                new_provider_name = request.POST.get('new_provider_name').strip().lower()
                rpc_url = request.POST.get('rpc_url').strip()
                ws_url = request.POST.get('ws_url').strip() or None
                api_key = request.POST.get('api_key').strip() or None

                # Basic validation for required fields
                if not new_provider_name or not rpc_url:
                    messages.error(request, "Provider name and RPC URL are required.")
                    return self.template_response(request, 'admin/set_primary_provider.html', context)

                if new_provider_name in available_providers:
                    messages.error(request, "A provider with this name already exists.")
                    return self.template_response(request, 'admin/set_primary_provider.html', context)

                # Validate RPC URL format
                url_validator = URLValidator()
                try:
                    url_validator(rpc_url)
                except ValidationError:
                    messages.error(request, "Please enter a valid RPC URL.")
                    return self.template_response(request, 'admin/set_primary_provider.html', context)

                # Validate WebSocket URL format if provided
                if ws_url and not self.validate_websocket_url(ws_url):
                    messages.error(request, "Please enter a valid WebSocket URL starting with ws:// or wss://")
                    return self.template_response(request, 'admin/set_primary_provider.html', context)

                # QuickNode-specific validation for RPC and WebSocket URLs
                if 'quiknode.pro' in rpc_url:
                    if not re.match(r'^https://[a-zA-Z0-9-]+\.quiknode\.pro(/[a-zA-Z0-9-]+/?)?$', rpc_url):
                        messages.error(request, "Invalid QuickNode RPC URL format. Expected: https://<endpoint>.quiknode.pro/<api-key>/")
                        return self.template_response(request, 'admin/set_primary_provider.html', context)
                    if not api_key and '/' in rpc_url.split('quiknode.pro')[1]:
                        api_key = rpc_url.split('quiknode.pro')[1].strip('/')
                
                if ws_url and 'quiknode.pro' in ws_url:
                    if not re.match(r'^wss://[a-zA-Z0-9-]+\.solana-mainnet\.quiknode\.pro(/[a-zA-Z0-9-]+/?)?$', ws_url):
                        messages.error(request, "Invalid QuickNode WebSocket URL format. Expected: wss://<endpoint>.solana-mainnet.quiknode.pro/<api-key>/")
                        return self.template_response(request, 'admin/set_primary_provider.html', context)

                try:
                    # Create the new provider
                    new_provider = PrimaryProviderSetting.objects.create(
                        name=new_provider_name,
                        rpc_url=rpc_url,
                        ws_url=ws_url,
                        api_key=api_key,
                        is_active=True,
                        is_primary=False
                    )

                    # Log the action in AdminLogEntry
                    AdminLogEntry.objects.log_action(
                        user_id=request.user.id,
                        content_type_id=ContentType.objects.get_for_model(PrimaryProviderSetting).pk,
                        object_id=new_provider.pk,
                        object_repr=f"Provider: {new_provider_name}",
                        action_flag=1,
                        change_message=f"Added new provider: {new_provider_name}"
                    )

                    # Notify all admin users of the new provider
                    admin_users = AdminUser.objects.filter(is_active=True, is_staff=True)
                    notification_message = (
                        f"New RPC provider added by {request.user.username}:\n"
                        f"Provider Name: {new_provider_name}\n"
                        f"RPC URL: {rpc_url}\n"
                        f"WebSocket URL: {ws_url or 'Not Provided'}\n"
                        f"API Key: {'Provided' if api_key else 'Not Provided'}"
                    )
                    for admin_user in admin_users:
                        AdminNotification.objects.create(
                            type='provider_added',
                            message=notification_message,
                            admin_user=admin_user,
                        )
                        logger.info(f"Sent notification to admin {admin_user.username}")

                    messages.success(request, f"New provider '{new_provider_name}' added successfully.")
                    available_providers.append(new_provider_name)
                    context['available_providers'] = available_providers
                except Exception as e:
                    logger.error(f"Error adding new provider: {str(e)}")
                    messages.error(request, f"Error adding new provider: {str(e)}")

        return self.template_response(request, 'admin/set_primary_provider.html', context)

    def refresh_collections_view(self, request):
        """
        View to manually refresh NFT collection data.
        Triggers a refresh of existing collections and logs the results.

        Args:
            request (HttpRequest): The HTTP request object.

        Returns:
            TemplateResponse: Renders the refresh_collections.html template with refresh results.
        """
        context = dict(
            self.each_context(request),
            title="Refresh Collections",
        )

        if request.method == "POST":
            logger.info("=== Starting Manual Collection Refresh ===")
            service = NFTDataService()
            
            try:
                # Trigger immediate refresh of collections (days_old=0, minutes_old=0)
                # Use asyncio.run to handle async operations in a synchronous context
                import asyncio
                result = asyncio.run(asyncio.coroutine(lambda: service.schedule_collection_refresh(days_old=0, minutes_old=0))())
                logger.info("=== Manual Collection Refresh Completed ===")

                # Extract results for display
                results = result["details"]
                success_count = result["success"]
                failed_count = result["failed"]
                total_count = result["total"]

                # Notify all admin users of the refresh results
                admin_users = AdminUser.objects.filter(is_active=True, is_staff=True)
                notification_message = (
                    f"Manual collection refresh triggered by {request.user.username}:\n"
                    f"Total Collections Processed: {total_count}\n"
                    f"Successful: {success_count}\n"
                    f"Failed: {failed_count}\n"
                    "Details:\n"
                )
                for detail in results:
                    # Build the main result line without nested f-strings to avoid syntax/indent issues
                    if detail.get('success'):
                        notification_message += f"- {detail.get('collection_address')} ({detail.get('collection_name')}): Success\n"
                    else:
                        error_text = detail.get('error', 'Unknown error')
                        notification_message += f"- {detail.get('collection_address')} ({detail.get('collection_name')}): Failed - {error_text}\n"

                    # Append any detected changes
                    if "changes_detected" in detail:
                        changes = detail["changes_detected"]
                        if isinstance(changes, dict):
                            notification_message += "  Changes Detected:\n"
                            if changes.get("metadata_changed"):
                                notification_message += "    - Metadata updated\n"
                            if changes.get("nfts_added", 0) > 0:
                                notification_message += f"    - {changes['nfts_added']} new NFTs added\n"
                            if changes.get("nfts_burned", 0) > 0:
                                notification_message += f"    - {changes['nfts_burned']} NFTs burned\n"
                            if changes.get("nfts_updated", 0) > 0:
                                notification_message += f"    - {changes['nfts_updated']} NFTs updated\n"
                        else:
                            notification_message += f"  Changes: {changes}\n"

                for admin_user in admin_users:
                    AdminNotification.objects.create(
                        type='collection_refreshed',
                        message=notification_message,
                        admin_user=admin_user,
                    )
                    logger.info(f"Sent notification to admin {admin_user.username}")

                # Update context with refresh results
                context['results'] = results
                context['success_count'] = success_count
                context['failed_count'] = failed_count
                context['total_count'] = total_count

            except Exception as e:
                logger.error(f"Error during manual collection refresh: {str(e)}")
                context['error'] = f"Error during refresh: {str(e)}"

            return self.template_response(request, 'admin/refresh_collections.html', context)

        return self.template_response(request, 'admin/refresh_collections.html', context)

    def populate_collections_view(self, request):
        """
        View to manually populate NFT collections from provided addresses.
        Admins can input collection addresses to fetch and store their data.

        Args:
            request (HttpRequest): The HTTP request object.

        Returns:
            TemplateResponse: Renders the populate_collections.html template with population results.
        """
        # Initialize metrics for tracking the population process
        metrics = {
            "total_attempted": 0,
            "successful": 0,
            "failed": 0,
            "errors_encountered": [],
            "collection_details": [],
        }

        context = dict(
            self.each_context(request),
            title="Populate Collections",
        )

        if request.method == "POST":
            logger.info("=== Starting Collection Population ===")
            # Get the collection addresses from the form input
            collection_addresses = request.POST.get('collection_addresses', '').strip()
            if not collection_addresses:
                logger.warning("No collection addresses provided for population.")
                context['error'] = "Please provide at least one collection address."
                logger.info("=== Collection Population Aborted ===")
                return self.template_response(request, 'admin/populate_collections.html', context)

            # Parse the addresses into a list
            addresses = [addr.strip() for addr in collection_addresses.splitlines() if addr.strip()]
            if not addresses:
                logger.warning("No valid collection addresses provided after parsing.")
                context['error'] = "Please provide at least one valid collection address."
                logger.info("=== Collection Population Aborted ===")
                return self.template_response(request, 'admin/populate_collections.html', context)

            metrics["total_attempted"] = len(addresses)
            logger.info(f"Total collections to populate: {metrics['total_attempted']}")

            # Use NFTDataService to populate each collection
            service = NFTDataService()
            results = []
            successful_addresses = []
            for address in addresses:
                logger.info(f"Processing collection: {address}")
                try:
                    # Call the async populate_collection method using asyncio.run
                    import asyncio
                    result = asyncio.run(service.populate_collection(address))
                    if result["success"]:
                        metrics["successful"] += 1
                        successful_addresses.append(address)
                        results.append({
                            'address': address,
                            'success': True,
                            'message': f"Successfully populated collection {address}",
                        })
                        metrics["collection_details"].append({
                            "address": address,
                            "status": "Success",
                            "error": None,
                        })
                        logger.info(f"Successfully populated collection {address}")
                    else:
                        metrics["failed"] += 1
                        results.append({
                            'address': address,
                            'success': False,
                            'message': f"Failed to populate collection {address}: {result['error']}",
                        })
                        metrics["collection_details"].append({
                            "address": address,
                            "status": "Failed",
                            "error": result['error'],
                        })
                        metrics["errors_encountered"].append(f"{address}: {result['error']}")
                        logger.error(f"Failed to populate collection {address}: {result['error']}")
                    # Log the action in AdminLogEntry
                    if result.get('success'):
                        change_message = f"Populated collection {address} via admin panel: Success"
                    else:
                        change_message = f"Populated collection {address} via admin panel: Failed - {result.get('error', 'Unknown')}"
                    AdminLogEntry.objects.log_action(
                        user_id=request.user.id,
                        content_type_id=ContentType.objects.get_for_model(NFTCollection).pk,
                        object_id=address,
                        object_repr=address,
                        action_flag=1,
                        change_message=change_message
                    )

                except Exception as e:
                    metrics["failed"] += 1
                    results.append({
                        'address': address,
                        'success': False,
                        'message': f"Error populating collection {address}: {str(e)}",
                    })
                    metrics["collection_details"].append({
                        "address": address,
                        "status": "Failed",
                        "error": str(e),
                    })
                    metrics["errors_encountered"].append(f"{address}: {str(e)}")
                    logger.error(f"Error populating collection {address}: {str(e)}")
                    # Log the error in AdminLogEntry
                    AdminLogEntry.objects.log_action(
                        user_id=request.user.id,
                        content_type_id=ContentType.objects.get_for_model(NFTCollection).pk,
                        object_id=address,
                        object_repr=address,
                        action_flag=1,
                        change_message=f"Failed to populate collection {address}: {str(e)}"
                    )

            # Log the population metrics
            logger.info("=== Collection Population Metrics ===")
            logger.info(f"Total Attempted: {metrics['total_attempted']}")
            logger.info(f"Successful: {metrics['successful']}")
            logger.info(f"Failed: {metrics['failed']}")
            logger.info(f"Errors Encountered: {', '.join(metrics['errors_encountered']) if metrics['errors_encountered'] else 'None'}")
            logger.info("Collection Details:")
            for detail in metrics["collection_details"]:
                logger.info(f"  - Address: {detail['address']}, Status: {detail['status']}, Error: {detail['error'] or 'None'}")
            logger.info("=============================")
            logger.info("Collection population completed")

            # Notify all admin users of the population results
            admin_users = AdminUser.objects.filter(is_active=True, is_staff=True)
            notification_message = (
                f"Collections populated by {request.user.username}:\n"
                f"Total Attempted: {metrics['total_attempted']}\n"
                f"Successful: {metrics['successful']}\n"
                f"Failed: {metrics['failed']}\n"
                "Details:\n"
            )
            for detail in metrics["collection_details"]:
                notification_message += f"- {detail['address']}: {detail['status']}"
                if detail["error"]:
                    notification_message += f" (Error: {detail['error']})"
                notification_message += "\n"
            if metrics["errors_encountered"]:
                notification_message += f"Errors Encountered: {', '.join(metrics['errors_encountered'])}"

            for admin_user in admin_users:
                AdminNotification.objects.create(
                    type='collection_populated',
                    message=notification_message,
                    admin_user=admin_user,
                )
                logger.info(f"Sent notification to admin {admin_user.username}")

            # Update context with population results
            context['results'] = results
            context['collection_addresses'] = ''
            return self.template_response(request, 'admin/populate_collections.html', context)

        context['collection_addresses'] = ''
        return self.template_response(request, 'admin/populate_collections.html', context)
    
    def notifications_view(self, request):
        """
        View to display and manage admin notifications.
        Admins can view their notifications and mark them as read or unread.

        Args:
            request (HttpRequest): The HTTP request object.

        Returns:
            TemplateResponse: Renders the notifications.html template with the user's notifications.
        """
        context = dict(
            self.each_context(request),
            title="Notifications",
        )

        # Get notifications for the current user, ordered by most recent first
        notifications = AdminNotification.objects.filter(admin_user=request.user).order_by('-created_at')
        
        # Handle marking notifications as read or unread via POST request
        if request.method == "POST":
            action = request.POST.get('action')
            notification_ids = request.POST.getlist('notification_ids')
            
            if not notification_ids:
                context['error'] = "Please select at least one notification."
                context['notifications'] = notifications
                return self.template_response(request, 'admin/notifications.html', context)

            if action == 'mark_read':
                updated = notifications.filter(id__in=notification_ids).update(is_read=True)
                for notification_id in notification_ids:
                    AdminLogEntry.objects.log_action(
                        user_id=request.user.id,
                        content_type_id=ContentType.objects.get_for_model(AdminNotification).pk,
                        object_id=notification_id,
                        object_repr=str(notifications.get(id=notification_id)),
                        action_flag=2,
                        change_message=f"Marked notification as read via full view"
                    )
                context['message'] = f"Marked {updated} notification(s) as read."
            elif action == 'mark_unread':
                updated = notifications.filter(id__in=notification_ids).update(is_read=False)
                for notification_id in notification_ids:
                    AdminLogEntry.objects.log_action(
                        user_id=request.user.id,
                        content_type_id=ContentType.objects.get_for_model(AdminNotification).pk,
                        object_id=notification_id,
                        object_repr=str(notifications.get(id=notification_id)),
                        action_flag=2,
                        change_message=f"Marked notification as unread via full view"
                    )
                context['message'] = f"Marked {updated} notification(s) as unread."
            else:
                context['error'] = "Invalid action selected."

        context['notifications'] = notifications
        return self.template_response(request, 'admin/notifications.html', context)

    def mark_notification_read(self, request, notification_id):
        """
        Mark a specific notification as read and redirect back to the previous page.

        Args:
            request (HttpRequest): The HTTP request object.
            notification_id (int): The ID of the notification to mark as read.

        Returns:
            HttpResponseRedirect: Redirects to the previous page or the admin index.
        """
        try:
            # Fetch the notification for the current user
            notification = AdminNotification.objects.get(id=notification_id, admin_user=request.user)
            notification.is_read = True
            notification.save()
            # Log the action in AdminLogEntry
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminNotification).pk,
                object_id=notification.id,
                object_repr=str(notification),
                action_flag=2,
                change_message=f"Marked notification as read: {notification.message[:50]}..."
            )
            messages.success(request, "Notification marked as read.")
        except AdminNotification.DoesNotExist:
            messages.error(request, "Notification not found or you do not have permission to modify it.")
        # Redirect to the previous page or the admin index if no referrer
        return redirect(request.META.get('HTTP_REFERER', 'admin:index'))

    def mark_notification_unread(self, request, notification_id):
        """
        Mark a specific notification as unread and redirect back to the previous page.

        Args:
            request (HttpRequest): The HTTP request object.
            notification_id (int): The ID of the notification to mark as unread.

        Returns:
            HttpResponseRedirect: Redirects to the previous page or the admin index.
        """
        try:
            # Fetch the notification for the current user
            notification = AdminNotification.objects.get(id=notification_id, admin_user=request.user)
            notification.is_read = False
            notification.save()
            # Log the action in AdminLogEntry
            AdminLogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(AdminNotification).pk,
                object_id=notification.id,
                object_repr=str(notification),
                action_flag=2,
                change_message=f"Marked notification as unread: {notification.message[:50]}..."
            )
            messages.success(request, "Notification marked as unread.")
        except AdminNotification.DoesNotExist:
            messages.error(request, "Notification not found or you do not have permission to modify it.")
        # Redirect to the previous page or the admin index if no referrer
        return redirect(request.META.get('HTTP_REFERER', 'admin:index'))
    
    def view_notification(self, request, notification_id):
        """
        View to display a single notification in detail.

        Args:
            request (HttpRequest): The HTTP request object.
            notification_id (int): The ID of the notification to view.

        Returns:
            TemplateResponse: Renders the notification_detail.html template with the notification details.
        """
        try:
            notification = AdminNotification.objects.get(id=notification_id, admin_user=request.user)
            # Mark as read when viewed
            if not notification.is_read:
                notification.is_read = True
                notification.save()
                AdminLogEntry.objects.log_action(
                    user_id=request.user.id,
                    content_type_id=ContentType.objects.get_for_model(AdminNotification).pk,
                    object_id=notification.id,
                    object_repr=str(notification),
                    action_flag=2,
                    change_message=f"Marked notification as read via detailed view: {notification.message[:50]}..."
                )
        except AdminNotification.DoesNotExist:
            messages.error(request, "Notification not found or you do not have permission to view it.")
            return redirect('admin:notifications_view')

        context = dict(
            self.each_context(request),
            title=f"Notification: {notification.get_type_display()}",
            notification=notification,
        )
        return self.template_response(request, 'admin/notification_detail.html', context)

    def mark_all_notifications_read(self, request):
        """
        View to mark all notifications for the current user as read.

        Args:
            request (HttpRequest): The HTTP request object.

        Returns:
            HttpResponseRedirect: Redirects back to the previous page or the notifications view.
        """
        if request.method == "POST":
            notifications = AdminNotification.objects.filter(admin_user=request.user, is_read=False)
            updated = notifications.update(is_read=True)
            for notification in notifications:
                AdminLogEntry.objects.log_action(
                    user_id=request.user.id,
                    content_type_id=ContentType.objects.get_for_model(AdminNotification).pk,
                    object_id=notification.id,
                    object_repr=str(notification),
                    action_flag=2,
                    change_message=f"Marked notification as read via mark all: {notification.message[:50]}..."
                )
            messages.success(request, f"Marked {updated} notification(s) as read.")
        else:
            messages.error(request, "Invalid request method.")
        return redirect(request.META.get('HTTP_REFERER', 'admin:notifications_view'))

    def login(self, request, extra_context=None):
        """
        Handle admin login by redirecting to the custom login view.
        If the user is already authenticated and has staff privileges, redirect to the admin index.

        Args:
            request (HttpRequest): The HTTP request object.
            extra_context (dict, optional): Additional context for the login view.

        Returns:
            HttpResponseRedirect: Redirects to the custom login view or admin index.
        """
        # If the request is for the login page, use the custom login view
        if request.path == reverse('admin_panel:login'):
            from admin_panel.views import login_view
            return login_view(request)
        # If the user is already authenticated and has staff privileges, redirect to the admin index
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            return HttpResponseRedirect(reverse('admin:index'))
        # Otherwise, redirect to the custom login page
        return redirect('admin_panel:login')

    def get_login_url(self):
        """
        Return the URL for the admin login page.

        Returns:
            str: The URL name for the custom login view.
        """
        return reverse('admin_panel:login')

    def template_response(self, request, template, context=None):
        """
        Render a template response with additional admin context.
        Adds common admin context variables to all templates.

        Args:
            request (HttpRequest): The HTTP request object.
            template (str): The path to the template to render.
            context (dict, optional): The context dictionary for the template.

        Returns:
            TemplateResponse: The rendered template response.
        """
        if context is None:
            context = {}
        # Add common admin context variables
        context.update({
            'site_header': self.site_header,
            'site_title': self.site_title,
            'title': self.index_title,
            'available_apps': self.get_app_list(request),
            'is_popup': False,
            'is_nav_sidebar_enabled': True,
            'has_permission': self.has_permission(request),
            'is_admin': True,
        })
        return TemplateResponse(request, template, context)

    def log_action(self, user, content_type, object_id, object_repr, action_flag, change_message=''):
        """
        Log an admin action using only our custom AdminLogEntry system.
        Never use Django's default logging.
        """
        try:
            # Always try to use AdminLogEntry, regardless of user type
            if hasattr(user, 'id'):
                AdminLogEntry.objects.log_action(
                    user_id=user.id,
                    content_type_id=content_type.id if content_type else None,
                    object_id=str(object_id),
                    object_repr=object_repr,
                    action_flag=action_flag,
                    change_message=change_message
                )
        except Exception as e:
            # Log the error but don't break the admin operation
            logger.error(f"Failed to log admin action: {str(e)}")
            # DO NOT call super().log_action() here - that's what's causing the error


    def index(self, request, extra_context=None):
        """
        Render the admin index page with dashboard statistics.
        Displays an overview of apps, user stats, server metrics, admin logs, and pending collections.

        Args:
            request (HttpRequest): The HTTP request object.
            extra_context (dict, optional): Additional context for the template.

        Returns:
            TemplateResponse: Renders the admin/index.html template with dashboard data.
        """
        # Get the list of apps for the admin interface
        app_list = self.get_app_list(request)
        # Filter out the wallet app to prevent it from appearing in the dashboard
        app_list = [app for app in app_list if app.get('app_label') != 'wallet']

        for app in app_list:
            if not app.get('app_label'):
                continue
            app['app_url'] = f"/admin/{app['app_label']}/"
            app['detailed_models'] = []
            # Add model counts for each app
            for model in app['models']:
                if not model.get('object_name'):
                    continue
                try:
                    model_class = apps.get_model(app['app_label'], model['object_name'])
                    model_count = model_class.objects.count()
                    app['detailed_models'].append({
                        'name': model_class._meta.verbose_name_plural.title(),
                        'app_label': app['app_label'],
                        'model': model['object_name'].lower(),
                        'count': model_count,
                    })
                except LookupError:
                    continue

        # Fetch the 10 most recent admin log entries, excluding wallet entries
        admin_log = (
            AdminLogEntry.objects.select_related('content_type', 'user')
            .exclude(content_type__app_label='wallet')  # Exclude wallet entries to prevent NoReverseMatch
            .order_by('-action_time')[:10]
        )
        # Debug: Log the app labels in the admin log
        app_labels = [entry.content_type.app_label for entry in admin_log if entry.content_type]
        logger.info(f"Admin log app labels: {app_labels}")

        admin_user_count = AdminUser.objects.count()

        # Cache and fetch total user count
        cache_key = 'total_user_count'
        user_count = cache.get(cache_key)
        if user_count is None:
            user_count = CustomUser.objects.count()
            cache.set(cache_key, user_count, 3600)

        # Cache and fetch user statistics
        user_stats_cache_key = 'user_stats'
        user_stats = cache.get(user_stats_cache_key)
        if user_stats is None:
            end_date = timezone.now()
            # Exclude admin users (is_staff=True) from regular user counts
            regular_users = CustomUser.objects.filter(is_staff=False)
            user_stats = {
                'total_users': regular_users.count(),
                'active_users': regular_users.filter(
                    last_login__gte=end_date - timedelta(days=30)
                ).count(),
                'wallet_connections': WalletProfile.objects.count(),
                'admin_users': AdminUser.objects.count(),
            }
            signup_start = end_date - timedelta(days=7)
            new_users = regular_users.filter(date_joined__gte=signup_start)
            new_user_count = new_users.count()
            retained_users = new_users.filter(
                last_login__gt=F('date_joined')
            ).count()
            user_stats['retention_rate'] = (retained_users / new_user_count * 100) if new_user_count > 0 else 0
            cache.set(user_stats_cache_key, user_stats, 3600)

        # Fetch server metrics
        server_load = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        memory_usage = memory.percent
        disk = psutil.disk_usage('/')
        disk_usage = disk.percent

        # Prepare login activity data for the last 7 days
        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)
        login_activity = {}
        for i in range(7):
            day = start_date + timedelta(days=i)
            day_str = day.strftime('%b %d')
            login_activity[day_str] = 0


        login_attempts = AdminLoginAttempt.objects.filter(
            timestamp__gte=start_date,
            timestamp__lte=end_date,
            success=True
        ).annotate(day=TruncDate("timestamp")).values('day').annotate(count=Count('id'))
        for attempt in login_attempts:
            day_str = attempt['day'].strftime('%b %d')
            login_activity[day_str] = attempt['count']
        login_activity_labels = json.dumps(list(login_activity.keys()))
        login_activity_data = json.dumps(list(login_activity.values()))

        # Prepare signup activity data for the last 7 days
        signup_activity_labels = []
        signup_activity_data = []
        for i in range(7):
            day = start_date + timedelta(days=i)
            day_str = day.strftime('%b %d')
            signup_activity_labels.append(day_str)
            count = CustomUser.objects.filter(date_joined__date=day).count()
            signup_activity_data.append(count)
        signup_activity_labels = json.dumps(signup_activity_labels)
        signup_activity_data = json.dumps(signup_activity_data)

        # Fetch NFT statistics
        nft_stats = {
            'collections': NFTCollection.objects.count(),
            'nfts': NFT.objects.count(),
            'transactions': NFTEvent.objects.filter(event_type='SALE').count(),
        }

        # Paginate pending collections
        # traitkeeper/admin_site.py

        pending_collections = PendingCollection.objects.filter(status='pending').order_by('-created_at')    
        paginator = Paginator(pending_collections, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # Define the list of allowed apps for the app_list URL pattern
        allowed_apps = ['admin_panel', 'auth', 'nft_data', 'advertisement', 'indexer', 'traitkeeper']
        # Debug: Log the allowed_apps to confirm it's set correctly
        logger.info(f"Allowed apps in context: {allowed_apps}")

        # Prepare context for the template
        context = {
            **self.each_context(request),
            'title': self.index_title,
            'subtitle': None,
            'app_list': app_list,
            'admin_log': admin_log,
            'user_count': user_count,
            'user_stats': user_stats,
            'admin_user_count': admin_user_count,
            'server_load': server_load,
            'memory_usage': memory_usage,
            'disk_usage': disk_usage,
            'login_activity_labels': login_activity_labels,
            'login_activity_data': login_activity_data,
            'signup_activity_labels': signup_activity_labels,
            'signup_activity_data': signup_activity_data,
            'nft_stats': nft_stats,
            'page_obj': page_obj,
            'allowed_apps': allowed_apps,  # Add allowed_apps to context for template use
            **(extra_context or {}),
        }

        request.current_app = self.name
        return self.template_response(request, 'admin/index.html', context)

    def app_index(self, request, app_label, extra_context=None):
        """
        Render the app-specific admin page (e.g., /admin/traitkeeper/) with app statistics.
        Displays models, their counts, and recent actions for the specified app with modern
        features like filtering, search, pagination, and sorting.

        Args:
            request (HttpRequest): The HTTP request object.
            app_label (str): The label of the app (e.g., 'traitkeeper').
            extra_context (dict, optional): Additional context for the template.

        Returns:
            TemplateResponse: Renders the admin/app_index.html template with app data.
            Raises Http404 if the app is not found.
        """
        # Fetch the list of apps and find the requested app
        app_list = self.get_app_list(request)
        # Filter out the wallet app to prevent it from appearing
        app_list = [app for app in app_list if app.get('app_label') != 'wallet']
        app = None
        for app_dict in app_list:
            if app_dict['app_label'] == app_label:
                app = app_dict
                break
        if not app:
            raise Http404('The requested admin app does not exist.')

        # Get query parameters for filtering and search
        search_query = request.GET.get('q', '').strip()
        sort_by = request.GET.get('sort', 'name')  # name, count, -count
        view_mode = request.GET.get('view', 'grid')  # grid or table
        per_page = int(request.GET.get('per_page', '12'))

        # Calculate total objects and model details for the app
        total_objects = 0
        detailed_models = []
        for model in app['models']:
            if not model.get('object_name'):
                continue
            try:
                model_class = apps.get_model(app_label, model['object_name'])
                model_count = model_class.objects.count()
                total_objects += model_count

                model_name = model_class._meta.verbose_name_plural.title()

                detailed_models.append({
                    'name': model_name,
                    'app_label': app_label,
                    'model': model['object_name'].lower(),
                    'count': model_count,
                    'model_class_name': model['object_name'],
                    'verbose_name': model_class._meta.verbose_name,
                })
            except LookupError:
                continue

        # Apply search filter
        if search_query:
            detailed_models = [
                m for m in detailed_models
                if search_query.lower() in m['name'].lower() or
                   search_query.lower() in m['model'].lower()
            ]

        # Apply sorting
        if sort_by == 'name':
            detailed_models.sort(key=lambda x: x['name'].lower())
        elif sort_by == '-name':
            detailed_models.sort(key=lambda x: x['name'].lower(), reverse=True)
        elif sort_by == 'count':
            detailed_models.sort(key=lambda x: x['count'])
        elif sort_by == '-count':
            detailed_models.sort(key=lambda x: x['count'], reverse=True)

        # Pagination
        paginator = Paginator(detailed_models, per_page)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # Fetch the 10 most recent admin log entries for this app
        admin_log = (
            AdminLogEntry.objects.select_related('content_type', 'user')
            .filter(content_type__app_label=app_label)
            .order_by('-action_time')[:10]
        )

        # Prepare context for the template
        context = {
            **self.each_context(request),
            'title': f'{app["name"]} Administration',
            'subtitle': None,
            'app_list': app_list,
            'app_label': app_label,
            'app_name': app["name"],
            'total_objects': total_objects,
            'total_models': len(app['models']),
            'filtered_count': len(detailed_models),
            'admin_log': admin_log,
            'detailed_models': detailed_models,  # Keep all for stats
            'page_obj': page_obj,
            'search_query': search_query,
            'sort_by': sort_by,
            'view_mode': view_mode,
            'per_page': per_page,
            **(extra_context or {}),
        }
        return self.template_response(request, 'admin/app_index.html', context)

    def token_list_view(self, request):
        """
        Custom view to list all API tokens with their associated emails and expiry dates.
        Provides a paginated list of tokens for admin management.

        Args:
            request (HttpRequest): The HTTP request object.

        Returns:
            TemplateResponse: Renders the admin/token_list.html template with the token list.
        """
        # Fetch all tokens, ordered by creation date (most recent first)
        tokens = Token.objects.all().select_related('created_by').order_by('-created_at')
        # Paginate the tokens (20 per page)
        paginator = Paginator(tokens, 20)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # Prepare context for the template
        context = {
            'title': 'API Token Management',
            'page_obj': page_obj,
            'tokens': page_obj.object_list,
        }
        return self.template_response(request, 'admin/token_list.html', context)

    def generate_tokens_view(self, request):
        """
        Custom view to generate API tokens for external users.
        Admins can specify an email and optional expiry date for the token.
        Only accessible to AdminUser instances with staff or superuser privileges.

        Args:
            request (HttpRequest): The HTTP request object.

        Returns:
            TemplateResponse: Renders the admin/token_generation.html template with the token generation form.
        """
        # Check if the requesting user is an admin with appropriate privileges
        if not isinstance(request.user, AdminUser) or not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, "Only admin users can generate tokens.")
            return redirect('admin:index')

        context = {
            'title': 'Generate API Tokens',
        }

        # Handle form submission to generate a token
        if request.method == "POST":
            email = request.POST.get('email')
            expiry_option = request.POST.get('expiry_option')
            expiry_date_str = request.POST.get('expiry_date')

            # Validate the email address
            from django.core.validators import validate_email
            try:
                validate_email(email)
            except ValidationError:
                messages.error(request, "Please provide a valid email address.")
                return self.template_response(request, 'admin/token_generation.html', context)

            # Validate and parse the expiry date if provided
            expires_at = None
            if expiry_option == 'custom':
                if not expiry_date_str:
                    messages.error(request, "Please provide an expiry date and time.")
                    return self.template_response(request, 'admin/token_generation.html', context)
                try:
                    expires_at = datetime.strptime(expiry_date_str, '%Y-%m-%dT%H:%M')
                    expires_at = timezone.make_aware(expires_at)
                    if expires_at <= timezone.now():
                        messages.error(request, "Expiry date must be in the future.")
                        return self.template_response(request, 'admin/token_generation.html', context)
                except ValueError:
                    messages.error(request, "Invalid expiry date format. Use YYYY-MM-DDThh:mm.")
                    return self.template_response(request, 'admin/token_generation.html', context)

            # Generate a new token for the external user
            try:
                token = Token.objects.create(
                    email=email,
                    expires_at=expires_at,
                    created_by=request.user  # Set the AdminUser who created the token
                )
                token_list = [{
                    'message': f"External user with email {email}",
                    'token': token.key
                }]
                # Log the token generation action
                expiry_info = f"Expires at {expires_at}" if expires_at else "No expiry"
                AdminLogEntry.objects.log_action(
                    user_id=request.user.id,
                    content_type_id=ContentType.objects.get_for_model(Token).pk,
                    object_id=token.key,
                    object_repr=f"Token for {email}",
                    action_flag=1,  # Addition action
                    change_message=f"Generated API token for external user (email: {email}, {expiry_info}): {token.key}"
                )
                success_message = f"Successfully generated token for external user (email: {email}):"
            except Exception as e:
                logger.error(f"Error generating token: {str(e)}")
                messages.error(request, f"Error generating token: {str(e)}")
                return self.template_response(request, 'admin/token_generation.html', context)

            # Update context with the generated token details
            context.update({
                'success_message': success_message,
                'token_list': token_list
            })
            return self.template_response(request, 'admin/token_generation.html', context)

        return self.template_response(request, 'admin/token_generation.html', context)

# Create an instance of CustomAdminSite
admin_site = CustomAdminSite(name='admin')

class UserAdmin(BaseUserAdmin, AdvancedFilterAdmin):
    """
    Custom UserAdmin for managing CustomUser instances.
    Adds a custom action to revoke API tokens for selected users.
    """
    change_list_template = "admin/change_list.html"

    # Add custom action for token revocation
    actions = ['revoke_api_token']

    def revoke_api_token(self, request, queryset):
        """
        Action to revoke API tokens for selected CustomUser instances.
        Deletes any tokens associated with the selected users.
        Only accessible to admin users with staff or superuser privileges.

        Args:
            request (HttpRequest): The HTTP request object.
            queryset (QuerySet): The selected CustomUser instances.
        """
        # Check if the requesting user is an admin with appropriate privileges
        if not isinstance(request.user, AdminUser) or not (request.user.is_staff or request.user.is_superuser):
            self.message_user(request, "Only admin users can revoke tokens.", level=messages.ERROR)
            return

        # Note: This action is kept for CustomUser instances that might still have old tokens
        # from the previous Token model. It can be removed if no such tokens exist.
        tokens_revoked = 0
        for user in queryset:
            try:
                tokens = Token.objects.filter(email=user.email)  # Match by email if applicable
                token_count = tokens.count()
                if token_count > 0:
                    tokens.delete()
                    tokens_revoked += token_count
                    # Log the action
                    AdminLogEntry.objects.log_action(
                        user_id=request.user.id,
                        content_type_id=ContentType.objects.get_for_model(CustomUser).pk,
                        object_id=user.id,
                        object_repr=str(user),
                        action_flag=2,  # Change action
                        change_message=f"Revoked {token_count} API token(s) for user {user.username}"
                    )
            except Exception as e:
                logger.error(f"Error revoking token for user {user.username}: {str(e)}")
                self.message_user(request, f"Error revoking token for {user.username}: {str(e)}", level=messages.ERROR)
                continue

        # Provide feedback to the admin
        if tokens_revoked > 0:
            self.message_user(request, f"Successfully revoked {tokens_revoked} token(s).", level=messages.SUCCESS)
        else:
            self.message_user(request, "No tokens were found to revoke.", level=messages.WARNING)

    # Customize the action description in the admin panel
    revoke_api_token.short_description = "Revoke API token for selected users"

# Register CustomUser with the admin site using UserAdmin
admin_site.register(CustomUser, UserAdmin)

# Register the Token model with the admin site to manage API tokens
from traitkeeper.models import Token
from django.contrib import admin

class TokenAdmin(admin.ModelAdmin):
    """
    Admin interface for managing Token instances.
    Allows admins to view and manage API tokens for external users.
    """
    list_display = ('key', 'email', 'created_at', 'expires_at', 'created_by')  # Columns to display in the list view
    list_filter = ('created_at', 'expires_at')  # Filters for the list view
    search_fields = ('email', 'key')  # Fields to search in the list view
    readonly_fields = ('key', 'created_at')  # Fields that cannot be edited
    fieldsets = (
        (None, {
            'fields': ('email', 'key', 'created_at', 'expires_at', 'created_by')
        }),
    )

# Register the Token model if not already registered
if not admin_site._registry.get(Token):
    admin_site.register(Token, TokenAdmin)