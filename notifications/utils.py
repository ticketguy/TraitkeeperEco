# notifications/utils.py
"""
Utility functions for creating and managing user notifications.
"""
from django.contrib.auth import get_user_model
from .models import Notification, NotificationPreference

User = get_user_model()


def create_notification(user, event_type, message, data=None, related_nft=None, related_listing=None, related_bid=None):
    """
    Create a notification for a user if they have it enabled in preferences.

    Args:
        user: User instance to notify
        event_type: String event type (must match Notification.EVENT_TYPES)
        message: String message for the notification
        data: Optional dict of additional data
        related_nft: Optional NFT instance
        related_listing: Optional NFTListing instance
        related_bid: Optional Bid instance

    Returns:
        Notification instance or None if user has disabled this notification type
    """
    # Check if user has this notification type enabled
    preference = NotificationPreference.objects.filter(
        user=user,
        notification_type=event_type
    ).first()

    if preference and not preference.enabled:
        return None

    notification = Notification.objects.create(
        user=user,
        event_type=event_type,
        message=message,
        data=data or {},
        related_nft=related_nft,
        related_listing=related_listing,
        related_bid=related_bid
    )

    return notification


def create_listing_notification(seller_user, nft, listing):
    """
    Notify seller when their NFT is listed.
    """
    message = f"Your NFT '{nft.name}' has been listed for {listing.price} SOL"
    return create_notification(
        user=seller_user,
        event_type='nft_listed',
        message=message,
        data={
            'nft_mint': nft.mint_address,
            'price': str(listing.price),
            'listing_id': listing.listing_id,
        },
        related_nft=nft,
        related_listing=listing
    )


def create_sale_notification(seller_user, buyer_user, nft, listing, sale_price):
    """
    Notify both seller and buyer when NFT is sold.
    """
    # Notify seller
    seller_message = f"Your NFT '{nft.name}' sold for {sale_price} SOL"
    create_notification(
        user=seller_user,
        event_type='nft_sold',
        message=seller_message,
        data={
            'nft_mint': nft.mint_address,
            'price': str(sale_price),
            'buyer': buyer_user.username if buyer_user else 'Unknown',
        },
        related_nft=nft,
        related_listing=listing
    )

    # Notify buyer
    if buyer_user:
        buyer_message = f"You purchased '{nft.name}' for {sale_price} SOL"
        create_notification(
            user=buyer_user,
            event_type='nft_sold',
            message=buyer_message,
            data={
                'nft_mint': nft.mint_address,
                'price': str(sale_price),
                'seller': seller_user.username if seller_user else 'Unknown',
            },
            related_nft=nft,
            related_listing=listing
        )


def create_bid_notification(seller_user, bid, nft):
    """
    Notify NFT owner when they receive a bid.
    """
    message = f"You received a bid of {bid.amount} SOL on '{nft.name}'"
    return create_notification(
        user=seller_user,
        event_type='bid_received',
        message=message,
        data={
            'nft_mint': nft.mint_address,
            'bid_amount': str(bid.amount),
            'bid_id': bid.bid_id,
            'bidder': bid.bidder,
        },
        related_nft=nft,
        related_bid=bid
    )


def create_bid_accepted_notification(bidder_user, bid, nft):
    """
    Notify bidder when their bid is accepted.
    """
    message = f"Your bid of {bid.amount} SOL on '{nft.name}' was accepted!"
    return create_notification(
        user=bidder_user,
        event_type='bid_accepted',
        message=message,
        data={
            'nft_mint': nft.mint_address,
            'bid_amount': str(bid.amount),
            'bid_id': bid.bid_id,
        },
        related_nft=nft,
        related_bid=bid
    )


def create_bid_rejected_notification(bidder_user, bid, nft):
    """
    Notify bidder when their bid is rejected.
    """
    message = f"Your bid of {bid.amount} SOL on '{nft.name}' was rejected"
    return create_notification(
        user=bidder_user,
        event_type='bid_rejected',
        message=message,
        data={
            'nft_mint': nft.mint_address,
            'bid_amount': str(bid.amount),
            'bid_id': bid.bid_id,
        },
        related_nft=nft,
        related_bid=bid
    )


def create_outbid_notification(bidder_user, nft, old_bid_amount, new_bid_amount):
    """
    Notify user when they've been outbid.
    """
    message = f"You've been outbid on '{nft.name}'. New highest bid: {new_bid_amount} SOL"
    return create_notification(
        user=bidder_user,
        event_type='bid_outbid',
        message=message,
        data={
            'nft_mint': nft.mint_address,
            'your_bid': str(old_bid_amount),
            'new_bid': str(new_bid_amount),
        },
        related_nft=nft
    )


def create_watchlist_listing_notification(watcher_user, watchlist_item, listing):
    """
    Notify user when a watched NFT/collection item is listed.
    """
    item = watchlist_item.get_item
    item_name = getattr(item, 'name', 'Item')

    message = f"Watched item '{item_name}' has been listed for {listing.price} SOL"
    return create_notification(
        user=watcher_user,
        event_type='watchlist_listed',
        message=message,
        data={
            'item_type': watchlist_item.item_type,
            'price': str(listing.price),
            'listing_id': listing.listing_id,
        },
        related_nft=listing.nft if listing.nft else None,
        related_listing=listing
    )


def create_watchlist_price_change_notification(watcher_user, watchlist_item, old_price, new_price):
    """
    Notify user when a watched item's price changes significantly.
    """
    item = watchlist_item.get_item
    item_name = getattr(item, 'name', 'Item')

    percentage_change = ((new_price - old_price) / old_price * 100) if old_price > 0 else 0
    direction = "increased" if new_price > old_price else "decreased"

    message = f"Price {direction} for watched item '{item_name}': {old_price} SOL → {new_price} SOL ({abs(percentage_change):.1f}%)"
    return create_notification(
        user=watcher_user,
        event_type='watchlist_price_change',
        message=message,
        data={
            'item_type': watchlist_item.item_type,
            'old_price': str(old_price),
            'new_price': str(new_price),
            'percentage_change': round(percentage_change, 2),
        }
    )


def create_achievement_notification(user, achievement):
    """
    Notify user when they earn an achievement.
    """
    message = f"Achievement unlocked: {achievement.name}! (+{achievement.points} points)"
    return create_notification(
        user=user,
        event_type='achievement_earned',
        message=message,
        data={
            'achievement_key': achievement.key,
            'achievement_name': achievement.name,
            'points': achievement.points,
            'rarity': achievement.rarity,
        }
    )


def bulk_mark_as_read(user, notification_ids=None):
    """
    Mark multiple notifications as read for a user.

    Args:
        user: User instance
        notification_ids: Optional list of specific notification IDs to mark as read.
                         If None, marks all unread notifications as read.
    """
    queryset = Notification.objects.filter(user=user, is_read=False)

    if notification_ids:
        queryset = queryset.filter(id__in=notification_ids)

    return queryset.update(is_read=True)


def get_unread_count(user):
    """
    Get count of unread notifications for a user.
    """
    return Notification.objects.filter(user=user, is_read=False).count()


def get_notifications_summary(user, limit=5):
    """
    Get recent notifications summary for a user.

    Returns:
        Dict with unread count and recent notifications
    """
    unread_count = get_unread_count(user)
    recent_notifications = Notification.objects.filter(user=user).select_related(
        'related_nft',
        'related_listing',
        'related_bid'
    )[:limit]

    return {
        'unread_count': unread_count,
        'recent_notifications': recent_notifications,
    }


def ensure_default_preferences(user):
    """
    Ensure user has default notification preferences for all types.
    Called when user signs up or when new notification types are added.
    """
    created_count = 0

    for notification_type, _ in NotificationPreference.NOTIFICATION_TYPES:
        _, created = NotificationPreference.objects.get_or_create(
            user=user,
            notification_type=notification_type,
            defaults={
                'enabled': True,
                'notify_via_email': False,
                'notify_via_push': False,
            }
        )
        if created:
            created_count += 1

    return created_count
