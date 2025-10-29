from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import Http404
from django.contrib import messages
from django.db import transaction
from decimal import Decimal
import logging

# Import your Profile model
from .models import Profile
from .forms import ProfileUpdateForm
# Import other models needed (NFTs, Wallets, Notifications etc.) later
# Import notification models
from notifications.models import NotificationPreference
# Import wallet models
from wallet.models import WalletProfile
# Import NFT models
from nft_data.models import NFT

# Get the CustomUser model defined in settings.py
User = get_user_model()

# Initialize logger
logger = logging.getLogger(__name__) 

def profile_view(request, username):
    """
    Displays the user profile page with NFTs, marketplace data, watchlist, and achievements.
    """
    try:
        # Fetch the user whose profile is being viewed
        profile_user = User.objects.select_related('profile').get(username=username)
    except User.DoesNotExist:
        raise Http404("User not found")

    # Determine if the logged-in user is viewing their own profile
    is_owner = request.user.is_authenticated and (request.user.pk == profile_user.pk)

    # Get user's wallets (now supports multiple)
    user_wallets = profile_user.wallets.all() if hasattr(profile_user, 'wallets') else []
    primary_wallet = WalletProfile.get_primary_wallet(profile_user) if user_wallets.exists() else None

    # Get wallet addresses for querying
    wallet_addresses = list(user_wallets.values_list('public_key', flat=True)) if user_wallets.exists() else []

    # Fetch NFTs owned by all user's wallets with pagination
    from django.core.paginator import Paginator
    user_nfts = []
    nfts_page = None
    if wallet_addresses:
        all_nfts = NFT.objects.filter(
            owner__in=wallet_addresses
        ).select_related('collection').order_by('-collection__created_at')

        # Paginate NFTs (24 per page)
        paginator = Paginator(all_nfts, 24)
        page_number = request.GET.get('page', 1)
        nfts_page = paginator.get_page(page_number)
        user_nfts = nfts_page.object_list

    # Group NFTs by collection for better display
    from collections import defaultdict
    nfts_by_collection = defaultdict(list)
    for nft in user_nfts:
        collection_name = nft.collection.name if nft.collection else 'Uncategorized'
        nfts_by_collection[collection_name].append(nft)

    # Fetch marketplace data - Active Listings
    from marketplace.models import NFTListing, Bid
    active_listings = []
    if wallet_addresses:
        active_listings = NFTListing.objects.filter(
            seller__in=wallet_addresses,
            is_active=True
        ).select_related('nft', 'nft__collection').order_by('-listed_at')[:20]

    # Fetch marketplace data - Active Bids (Bids user placed)
    bids_placed = []
    if wallet_addresses:
        bids_placed = Bid.objects.filter(
            bidder__in=wallet_addresses,
            status='ACTIVE'
        ).select_related('nft', 'nft__collection').order_by('-bid_placed_at')[:20]

    # Fetch marketplace data - Bids Received (on user's NFTs)
    bids_received = []
    if wallet_addresses:
        user_nft_mints = NFT.objects.filter(owner__in=wallet_addresses).values_list('mint_address', flat=True)
        bids_received = Bid.objects.filter(
            nft__mint_address__in=user_nft_mints,
            status='ACTIVE'
        ).select_related('nft', 'bidder').order_by('-bid_placed_at')[:20]

    # Fetch Watchlist Items
    from .models import WatchlistItem
    watchlist_items = []
    if is_owner:  # Only show watchlist to profile owner
        watchlist_items = WatchlistItem.objects.filter(
            user=profile_user
        ).select_related('nft', 'collection').order_by('-added_at')[:20]

    # Fetch Achievements
    from .models import UserAchievement
    from .utils import get_user_achievement_stats, get_next_achievements

    user_achievements = UserAchievement.objects.filter(
        user=profile_user
    ).select_related('achievement', 'achievement__category').order_by('-earned_at')[:10]

    achievement_stats = get_user_achievement_stats(profile_user)
    next_achievements = get_next_achievements(profile_user, limit=3)

    # Fetch NFT Memories Stats
    from nftmemories.utils import get_user_memories_stats, get_user_most_interacted_memories

    memories_stats = get_user_memories_stats(profile_user)
    most_interacted_memories = get_user_most_interacted_memories(profile_user, limit=5)

    # Calculate basic stats
    stats = {
        'total_nfts': len(user_nfts) if not nfts_page else nfts_page.paginator.count,
        'unique_collections': len(nfts_by_collection),
        'active_listings_count': len(active_listings),
        'active_bids_count': len(bids_placed),
    }

    context = {
        'profile_user': profile_user,
        'is_owner': is_owner,
        'user_wallets': user_wallets,
        'primary_wallet': primary_wallet,
        'user_nfts': user_nfts,
        'nfts_page': nfts_page,
        'nfts_by_collection': dict(nfts_by_collection),
        'active_listings': active_listings,
        'bids_placed': bids_placed,
        'bids_received': bids_received,
        'watchlist_items': watchlist_items,
        'user_achievements': user_achievements,
        'achievement_stats': achievement_stats,
        'next_achievements': next_achievements,
        'memories_stats': memories_stats,
        'most_interacted_memories': most_interacted_memories,
        'stats': stats,
    }
    return render(request, 'profiles/user_profile.html', context)

# --- Settings Views ---

@login_required
def settings_view_router(request):
    """
    Optional: A single entry point that redirects or renders based on a section.
    Or you can keep separate views/URLs as initially planned.
    This example assumes separate views.
    """
    # This function isn't strictly necessary if you have separate URLs/views
    # for each settings tab, which is often cleaner.
    # If used, it would redirect to the specific view based on '#hash' or a query param.
    return redirect('profiles:settings_profile') # Redirect to the default settings tab

@login_required
def settings_profile_view(request):
    """
    Handles displaying and updating profile information.
    """
    profile = request.user.profile

    if request.method == 'POST':
        # Pass request.POST and request.FILES (if using ImageField for avatar)
        form = ProfileUpdateForm(request.POST, request.FILES or None, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profiles:settings_profile') # Redirect back to profile settings
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # Create form instance for GET request, pre-filled with current profile data
        form = ProfileUpdateForm(instance=profile)

    context = {
        'active_tab': 'profile',
        'form': form, # Pass the form to the template
    }
    return render(request, 'profiles/settings.html', context)

@login_required
def settings_wallets_view(request):
    """
    Handles displaying linked wallets (now supports multiple wallets).
    """
    # Fetch all wallets linked to the user
    user_wallets = request.user.wallets.all() if hasattr(request.user, 'wallets') else []

    context = {
        'active_tab': 'wallets',
        'user_wallets': user_wallets,
    }
    return render(request, 'profiles/settings.html', context)


@login_required
def remove_wallet_view(request, wallet_id):
    """
    Handles wallet removal via POST request.
    """
    if request.method == 'POST':
        try:
            wallet = WalletProfile.objects.get(id=wallet_id, user=request.user)
            wallet_address = wallet.short_public_key

            # Check if it's the only wallet
            wallet_count = WalletProfile.objects.filter(user=request.user).count()
            if wallet_count == 1:
                messages.error(request, 'Cannot remove your only wallet. Please link another wallet first.')
                return redirect('profiles:settings_wallets')

            # If removing primary wallet, set another wallet as primary
            if wallet.is_primary:
                other_wallet = WalletProfile.objects.filter(user=request.user).exclude(id=wallet_id).first()
                if other_wallet:
                    other_wallet.is_primary = True
                    other_wallet.save()

            wallet.delete()
            messages.success(request, f'Wallet {wallet_address} removed successfully.')
        except WalletProfile.DoesNotExist:
            messages.error(request, 'Wallet not found or does not belong to you.')
        except Exception as e:
            logger.error(f"Error removing wallet: {e}", exc_info=True)
            messages.error(request, f'Error removing wallet: {e}')

    return redirect('profiles:settings_wallets')


@login_required
def set_primary_wallet_view(request, wallet_id):
    """
    Sets a wallet as the primary wallet for the user.
    """
    if request.method == 'POST':
        try:
            wallet = WalletProfile.objects.get(id=wallet_id, user=request.user)

            # Unset other primary wallets
            WalletProfile.objects.filter(user=request.user, is_primary=True).update(is_primary=False)

            # Set this wallet as primary
            wallet.is_primary = True
            wallet.save()

            messages.success(request, f'Wallet {wallet.short_public_key} set as primary.')
        except WalletProfile.DoesNotExist:
            messages.error(request, 'Wallet not found or does not belong to you.')
        except Exception as e:
            logger.error(f"Error setting primary wallet: {e}", exc_info=True)
            messages.error(request, f'Error setting primary wallet: {e}')

    return redirect('profiles:settings_wallets')


@login_required
def settings_notifications_view(request):
    """
    Handles displaying and updating notification preferences.
    Uses direct POST data handling.
    """
    if request.method == 'POST':
        try:
            with transaction.atomic(): # Ensure all updates succeed or fail together
                for pref_type, _ in NotificationPreference.NOTIFICATION_TYPES:
                    enabled = request.POST.get(f'{pref_type}_enabled') == 'on'
                    notify_email = request.POST.get(f'{pref_type}_email') == 'on' if enabled else False
                    notify_push = request.POST.get(f'{pref_type}_push') == 'on' if enabled else False
                    min_value_str = request.POST.get(f'{pref_type}_min_value', '0')
                    collections_str = request.POST.get(f'{pref_type}_collections', '')
                    wallets_str = request.POST.get(f'{pref_type}_wallets', '')

                    # Validate min_value
                    min_value = None
                    try:
                        min_val_decimal = Decimal(min_value_str)
                        if min_val_decimal >= 0:
                            min_value = min_val_decimal
                    except (ValueError, TypeError):
                        pass # Keep min_value as None or 0

                    # Process comma-separated strings into lists (simple split, no validation here)
                    collections_list = [addr.strip() for addr in collections_str.split(',') if addr.strip()]
                    wallets_list = [addr.strip() for addr in wallets_str.split(',') if addr.strip()]

                    # Get or create the preference object for the user and type
                    preference, created = NotificationPreference.objects.update_or_create(
                        user=request.user,
                        notification_type=pref_type,
                        defaults={
                            'enabled': enabled,
                            'notify_via_email': notify_email,
                            'notify_via_push': notify_push,
                            'transaction_min_value': min_value,
                            'specific_collections': collections_list,
                            'specific_wallets': wallets_list,
                        }
                    )
            messages.success(request, 'Notification preferences saved successfully!')
        except Exception as e:
            logger.error(f"Error saving notification preferences for user {request.user.id}: {e}", exc_info=True)
            messages.error(request, 'An error occurred while saving notification preferences.')

        return redirect('profiles:settings_notifications') # Redirect back

    # --- GET Request ---
    # Fetch existing preferences to display in the template
    existing_prefs = NotificationPreference.objects.filter(user=request.user)
    prefs_dict = {pref.notification_type: pref for pref in existing_prefs}

    # Prepare context data structured for the template loop
    notification_prefs_context = {}
    for pref_type, label in NotificationPreference.NOTIFICATION_TYPES:
        pref = prefs_dict.get(pref_type)
        notification_prefs_context[pref_type] = {
            'label': label,
            'enabled': getattr(pref, 'enabled', True), # Default to True if not set? Or False?
            'notify_via_email': getattr(pref, 'notify_via_email', False),
            'notify_via_push': getattr(pref, 'notify_via_push', False),
            'transaction_min_value': getattr(pref, 'transaction_min_value', None),
            'specific_collections': getattr(pref, 'specific_collections',),
            'specific_wallets': getattr(pref, 'specific_wallets',),
        }

    context = {
        'active_tab': 'notifications',
        'notification_prefs_context': notification_prefs_context,
        # Pass the choices for the loop in the template if not using the context dict approach
        'NOTIFICATION_TYPES': NotificationPreference.NOTIFICATION_TYPES
    }
    return render(request, 'profiles/settings.html', context)


@login_required
def settings_visibility_view(request):
    """
    Handles updating profile visibility.
    """
    profile = request.user.profile
    if request.method == 'POST':
         is_public_value = request.POST.get('profile_public') == 'on' # Checkbox value
         profile.is_public = is_public_value
         profile.save(update_fields=['is_public'])
         messages.success(request, f'Profile visibility updated to {"Public" if is_public_value else "Private"}.')
         return redirect('profiles:settings_visibility') # Redirect back

    context = {
        'active_tab': 'visibility',
        # Pass profile object to check current state in template
        'profile': profile
    }
    return render(request, 'profiles/settings.html', context)

@login_required
def settings_account_view(request):
    """
    Displays account settings (placeholder for email/password, links to Danger Zone).
    """
    # --- TODO: Add forms/logic for email/password change if you implement standard auth ---
    account_management_enabled = False # Set to True if you have email/password forms

    context = {
        'active_tab': 'account',
        'account_management_enabled': account_management_enabled,
    }
    return render(request, 'profiles/settings.html', context)

@login_required
def delete_account_view(request):
    """
    Handles the actual account deletion after confirmation.
    Accessed via POST from the settings_account_view's confirmation JS.
    """
    if request.method == 'POST':
        user_to_delete = request.user
        try:
            # --- Implement SAFE Deletion ---
            # 1. (Optional) Verify password if applicable
            # 2. Perform deletion (consider soft delete: user_to_delete.is_active = False)
            logger.warning(f"Deleting account for user: {user_to_delete.username} (ID: {user_to_delete.id})")
            # user_to_delete.delete() # Hard delete - BE CAREFUL

            # --- Soft Delete Example ---
            user_to_delete.is_active = False
            user_to_delete.save(update_fields=['is_active'])
            # You might want to also anonymize profile data here if needed
            # user_to_delete.profile.display_name = "Deleted User"... etc.

            # 3. Log the user out
            from django.contrib.auth import logout
            logout(request)

            # 4. Add message and redirect
            messages.success(request, 'Your account has been successfully deleted.')
            return redirect('index') # Redirect to home
        except Exception as e:
            logger.error(f"Error deleting account for user {user_to_delete.id}: {e}", exc_info=True)
            messages.error(request, 'An error occurred while deleting your account. Please contact support.')
            return redirect('profiles:settings_account')
    else:
        # Redirect GET requests away
        return redirect('profiles:settings_account')


# --- Watchlist Management Views ---

@login_required
def add_to_watchlist(request):
    """
    Add an NFT or Collection to user's watchlist.
    Accepts POST with item_type, item_id, and optional notes.
    """
    if request.method == 'POST':
        from .models import WatchlistItem
        from nft_data.models import NFTCollection

        item_type = request.POST.get('item_type')  # 'NFT' or 'COLLECTION'
        item_id = request.POST.get('item_id')
        notes = request.POST.get('notes', '')

        if not item_type or not item_id:
            messages.error(request, 'Invalid watchlist item data.')
            return redirect(request.META.get('HTTP_REFERER', 'index'))

        try:
            # Check if already watching
            if item_type == 'NFT':
                nft = get_object_or_404(NFT, mint_address=item_id)
                existing = WatchlistItem.objects.filter(user=request.user, nft=nft).first()
                if existing:
                    messages.info(request, f'You are already watching "{nft.name}".')
                    return redirect(request.META.get('HTTP_REFERER', 'index'))

                WatchlistItem.objects.create(
                    user=request.user,
                    item_type=WatchlistItem.ItemType.NFT,
                    nft=nft,
                    notes=notes
                )
                messages.success(request, f'Added "{nft.name}" to your watchlist.')

            elif item_type == 'COLLECTION':
                collection = get_object_or_404(NFTCollection, id=item_id)
                existing = WatchlistItem.objects.filter(user=request.user, collection=collection).first()
                if existing:
                    messages.info(request, f'You are already watching "{collection.name}".')
                    return redirect(request.META.get('HTTP_REFERER', 'index'))

                WatchlistItem.objects.create(
                    user=request.user,
                    item_type=WatchlistItem.ItemType.COLLECTION,
                    collection=collection,
                    notes=notes
                )
                messages.success(request, f'Added "{collection.name}" to your watchlist.')

            else:
                messages.error(request, 'Invalid item type.')

        except Exception as e:
            logger.error(f"Error adding to watchlist: {e}", exc_info=True)
            messages.error(request, 'An error occurred while adding to watchlist.')

    return redirect(request.META.get('HTTP_REFERER', 'index'))


@login_required
def remove_from_watchlist(request, watchlist_id):
    """
    Remove an item from user's watchlist.
    """
    if request.method == 'POST':
        from .models import WatchlistItem

        try:
            watchlist_item = WatchlistItem.objects.get(id=watchlist_id, user=request.user)
            item_name = watchlist_item.get_item.name if hasattr(watchlist_item.get_item, 'name') else 'Item'
            watchlist_item.delete()
            messages.success(request, f'Removed "{item_name}" from your watchlist.')
        except WatchlistItem.DoesNotExist:
            messages.error(request, 'Watchlist item not found or does not belong to you.')
        except Exception as e:
            logger.error(f"Error removing from watchlist: {e}", exc_info=True)
            messages.error(request, 'An error occurred while removing from watchlist.')

    return redirect(request.META.get('HTTP_REFERER', 'profiles:profile'))


@login_required
def update_watchlist_notes(request, watchlist_id):
    """
    Update notes for a watchlist item.
    """
    if request.method == 'POST':
        from .models import WatchlistItem

        try:
            watchlist_item = WatchlistItem.objects.get(id=watchlist_id, user=request.user)
            new_notes = request.POST.get('notes', '')
            watchlist_item.notes = new_notes
            watchlist_item.save(update_fields=['notes'])
            messages.success(request, 'Watchlist notes updated.')
        except WatchlistItem.DoesNotExist:
            messages.error(request, 'Watchlist item not found or does not belong to you.')
        except Exception as e:
            logger.error(f"Error updating watchlist notes: {e}", exc_info=True)
            messages.error(request, 'An error occurred while updating notes.')

    return redirect(request.META.get('HTTP_REFERER', 'profiles:profile'))