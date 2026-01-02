# nftmemories/utils.py
"""
Utility functions for NFT Memories app.
"""

from typing import Dict, List
from django.contrib.auth import get_user_model
from .models import NFTBurn, CollectionEvent

User = get_user_model()


def get_user_memories_stats(user: User) -> Dict:
    """
    Get comprehensive NFT Memories statistics for a user.

    Returns:
        Dict with keys:
        - burn_reasons_contributed: Number of approved burn reasons added by user
        - burn_reasons_pending: Number of pending burn reasons
        - total_interactions: Total comments + tributes by user
        - comments_count: Number of comments user has made
        - tributes_count: Number of tributes user has given
        - recent_contributions: QuerySet of recent NFTBurn contributions
    """
    stats = {
        'burn_reasons_contributed': 0,
        'burn_reasons_pending': 0,
        'total_interactions': 0,
        'comments_count': 0,
        'tributes_count': 0,
        'recent_contributions': []
    }

    if not user or not user.is_authenticated:
        return stats

    # Count burn reasons
    approved_burns = NFTBurn.objects.filter(
        added_by_user=user,
        reason_is_approved=True
    )
    pending_burns = NFTBurn.objects.filter(
        added_by_user=user,
        reason_is_approved=False,
        reason__isnull=False
    ).exclude(reason='')

    stats['burn_reasons_contributed'] = approved_burns.count()
    stats['burn_reasons_pending'] = pending_burns.count()

    # Get recent contributions (last 5)
    stats['recent_contributions'] = NFTBurn.objects.filter(
        added_by_user=user
    ).select_related('burn_event').order_by('-created_at')[:5]

    # Count user's interactions across all events and burns
    # This is expensive but necessary since interactions are in JSON fields
    total_comments = 0
    total_tributes = 0

    # Count from CollectionEvents (limit to reduce query time)
    for event in CollectionEvent.objects.only('user_interactions').iterator(chunk_size=100):
        interactions = event.user_interactions
        comments = interactions.get('comments', [])
        tributes = interactions.get('tributes', [])

        # Count user's comments
        total_comments += sum(1 for c in comments if c.get('user') == user.username)

        # Count user's tributes
        total_tributes += sum(1 for t in tributes if t.get('user') == user.username)

    # Count from NFTBurns
    for burn in NFTBurn.objects.only('user_interactions').iterator(chunk_size=100):
        interactions = burn.user_interactions
        comments = interactions.get('comments', [])
        tributes = interactions.get('tributes', [])

        # Count user's comments
        total_comments += sum(1 for c in comments if c.get('user') == user.username)

        # Count user's tributes
        total_tributes += sum(1 for t in tributes if t.get('user') == user.username)

    stats['comments_count'] = total_comments
    stats['tributes_count'] = total_tributes
    stats['total_interactions'] = total_comments + total_tributes

    return stats


def get_user_most_interacted_memories(user: User, limit: int = 5) -> List[Dict]:
    """
    Get the memories (events/burns) that the user has interacted with most.

    Returns list of dicts with:
    - type: 'event' or 'burn'
    - object: The CollectionEvent or NFTBurn instance
    - interaction_count: Number of user's interactions on this memory
    """
    if not user or not user.is_authenticated:
        return []

    memories = []

    # Check CollectionEvents
    for event in CollectionEvent.objects.select_related('event').iterator(chunk_size=100):
        interactions = event.user_interactions
        comments = interactions.get('comments', [])
        tributes = interactions.get('tributes', [])

        user_comment_count = sum(1 for c in comments if c.get('user') == user.username)
        user_tribute_count = sum(1 for t in tributes if t.get('user') == user.username)
        total_count = user_comment_count + user_tribute_count

        if total_count > 0:
            memories.append({
                'type': 'event',
                'object': event,
                'interaction_count': total_count,
                'event_type': event.event.event_type,
                'collection': event.event.collection,
                'timestamp': event.event.timestamp
            })

    # Check NFTBurns
    for burn in NFTBurn.objects.select_related('burn_event').iterator(chunk_size=100):
        interactions = burn.user_interactions
        comments = interactions.get('comments', [])
        tributes = interactions.get('tributes', [])

        user_comment_count = sum(1 for c in comments if c.get('user') == user.username)
        user_tribute_count = sum(1 for t in tributes if t.get('user') == user.username)
        total_count = user_comment_count + user_tribute_count

        if total_count > 0:
            # Get collection object from collection_address
            from nft_data.models import NFTCollection
            collection = NFTCollection.objects.filter(address=burn.burn_event.collection_address).first()

            memories.append({
                'type': 'burn',
                'object': burn,
                'interaction_count': total_count,
                'nft_name': burn.name,
                'collection': collection,
                'timestamp': burn.burn_event.timestamp
            })

    # Sort by interaction count and return top N
    memories.sort(key=lambda x: x['interaction_count'], reverse=True)
    return memories[:limit]


def get_collection_memory_summary(collection_address: str) -> Dict:
    """
    Get summary statistics for a collection's memories.

    Returns:
        Dict with total events, burns, interactions, etc.
    """
    from nft_data.models import NFTCollection

    try:
        collection = NFTCollection.objects.get(address=collection_address)
    except NFTCollection.DoesNotExist:
        return {}

    # Count events
    events_count = CollectionEvent.objects.filter(
        event__collection_address=collection_address
    ).count()

    # Count burns
    burns_count = NFTBurn.objects.filter(
        burn_event__collection_address=collection_address
    ).count()

    # Count total interactions
    total_likes = 0
    total_comments = 0
    total_tributes = 0

    for event in CollectionEvent.objects.filter(event__collection_address=collection_address):
        interactions = event.user_interactions
        total_likes += interactions.get('likes', 0)
        total_comments += len(interactions.get('comments', []))
        total_tributes += len(interactions.get('tributes', []))

    for burn in NFTBurn.objects.filter(burn_event__collection_address=collection_address):
        interactions = burn.user_interactions
        total_likes += interactions.get('likes', 0)
        total_comments += len(interactions.get('comments', []))
        total_tributes += len(interactions.get('tributes', []))

    return {
        'total_events': events_count,
        'total_burns': burns_count,
        'total_likes': total_likes,
        'total_comments': total_comments,
        'total_tributes': total_tributes,
        'total_interactions': total_likes + total_comments + total_tributes,
    }
