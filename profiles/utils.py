# profiles/utils.py
"""
Utility functions for profile-related features including achievements.
"""
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from .models import Achievement, UserAchievement

User = get_user_model()


def award_achievement(user, achievement_key, create_notification=True):
    """
    Award an achievement to a user if they haven't already earned it.

    Args:
        user: User instance
        achievement_key: String key of the achievement (e.g., 'FIRST_BID')
        create_notification: Whether to create a notification (default: True)

    Returns:
        Tuple (UserAchievement or None, bool indicating if newly created)
    """
    try:
        achievement = Achievement.objects.get(key=achievement_key, is_active=True)
    except Achievement.DoesNotExist:
        return None, False

    user_achievement, created = UserAchievement.objects.get_or_create(
        user=user,
        achievement=achievement
    )

    if created and create_notification:
        from notifications.utils import create_achievement_notification
        create_achievement_notification(user, achievement)

    return user_achievement, created


def check_and_award_trading_achievements(user):
    """
    Check and award trading-related achievements based on user activity.
    Called after marketplace transactions.
    """
    from marketplace.models import NFTListing, Bid

    achievements_to_check = []

    # Check first listing
    listings_count = NFTListing.objects.filter(seller=user.wallets.values_list('public_key', flat=True)).count()
    if listings_count == 1:
        achievements_to_check.append('FIRST_LISTING')
    elif listings_count >= 10:
        achievements_to_check.append('ACTIVE_SELLER')
    elif listings_count >= 100:
        achievements_to_check.append('MARKETPLACE_VETERAN')

    # Check first bid
    bids_count = Bid.objects.filter(bidder__in=user.wallets.values_list('public_key', flat=True)).count()
    if bids_count == 1:
        achievements_to_check.append('FIRST_BID')
    elif bids_count >= 10:
        achievements_to_check.append('ACTIVE_BIDDER')

    # Check accepted bids (successful purchases)
    accepted_bids = Bid.objects.filter(
        bidder__in=user.wallets.values_list('public_key', flat=True),
        status='ACCEPTED'
    ).count()
    if accepted_bids >= 5:
        achievements_to_check.append('SAVVY_BUYER')
    elif accepted_bids >= 50:
        achievements_to_check.append('MASTER_COLLECTOR')

    # Award achievements
    awarded = []
    for achievement_key in achievements_to_check:
        user_achievement, created = award_achievement(user, achievement_key)
        if created:
            awarded.append(achievement_key)

    return awarded


def check_and_award_collection_achievements(user):
    """
    Check and award collection-related achievements based on NFT holdings.
    """
    from nft_data.models import NFT

    wallet_addresses = user.wallets.values_list('public_key', flat=True)
    user_nfts = NFT.objects.filter(owner__in=wallet_addresses)

    achievements_to_check = []

    # Check total NFT count
    nft_count = user_nfts.count()
    if nft_count >= 1:
        achievements_to_check.append('FIRST_NFT')
    if nft_count >= 10:
        achievements_to_check.append('GROWING_COLLECTION')
    if nft_count >= 100:
        achievements_to_check.append('SERIOUS_COLLECTOR')
    if nft_count >= 500:
        achievements_to_check.append('WHALE')

    # Check unique collections
    unique_collections = user_nfts.values('collection').distinct().count()
    if unique_collections >= 5:
        achievements_to_check.append('DIVERSE_PORTFOLIO')
    if unique_collections >= 20:
        achievements_to_check.append('COLLECTION_CONNOISSEUR')

    # Award achievements
    awarded = []
    for achievement_key in achievements_to_check:
        user_achievement, created = award_achievement(user, achievement_key)
        if created:
            awarded.append(achievement_key)

    return awarded


def check_and_award_social_achievements(user):
    """
    Check and award social/engagement achievements.
    """
    from .models import WatchlistItem

    achievements_to_check = []

    # Check watchlist size
    watchlist_count = WatchlistItem.objects.filter(user=user).count()
    if watchlist_count >= 1:
        achievements_to_check.append('FIRST_WATCH')
    if watchlist_count >= 10:
        achievements_to_check.append('VIGILANT_WATCHER')

    # Check profile completion
    profile = user.profile
    completion_score = 0
    if profile.display_name:
        completion_score += 1
    if profile.bio:
        completion_score += 1
    if profile.get_avatar_url != '/static/img/user-avatar-default.jpg':
        completion_score += 1
    if profile.social_x or profile.social_discord or profile.website_url:
        completion_score += 1

    if completion_score >= 3:
        achievements_to_check.append('PROFILE_COMPLETE')

    # Award achievements
    awarded = []
    for achievement_key in achievements_to_check:
        user_achievement, created = award_achievement(user, achievement_key)
        if created:
            awarded.append(achievement_key)

    return awarded


def get_user_achievement_stats(user):
    """
    Get statistics about user's achievements.

    Returns:
        Dict with achievement statistics
    """
    total_achievements = Achievement.objects.filter(is_active=True).count()
    earned_achievements = UserAchievement.objects.filter(user=user).count()

    # Points calculation
    total_points = UserAchievement.objects.filter(user=user).aggregate(
        total=Count('achievement__points')
    )['total'] or 0

    # Rarity breakdown
    rarity_counts = {}
    for rarity_choice in Achievement.Rarity.choices:
        rarity_key = rarity_choice[0]
        count = UserAchievement.objects.filter(
            user=user,
            achievement__rarity=rarity_key
        ).count()
        rarity_counts[rarity_key.lower()] = count

    return {
        'total_earned': earned_achievements,
        'total_available': total_achievements,
        'completion_percentage': round((earned_achievements / total_achievements * 100) if total_achievements > 0 else 0, 1),
        'total_points': total_points,
        'rarity_breakdown': rarity_counts,
    }


def get_next_achievements(user, limit=3):
    """
    Get suggested next achievements user can work towards.

    Returns:
        QuerySet of Achievement objects
    """
    earned_achievement_ids = UserAchievement.objects.filter(user=user).values_list('achievement_id', flat=True)

    return Achievement.objects.filter(
        is_active=True,
        is_hidden=False
    ).exclude(
        id__in=earned_achievement_ids
    ).order_by('rarity', 'display_order')[:limit]
