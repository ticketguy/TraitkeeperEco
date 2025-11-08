# traitkeeper/api/views.py
from django.http import JsonResponse
from django.db.models import Q
from nft_data.models import NFTCollection


def search_collections(request):
    """
    API endpoint for real-time collection search.
    Returns JSON with matching collections.
    """
    query = request.GET.get('q', '').strip()

    if len(query) < 2:
        return JsonResponse({'results': []})

    # Search collections by name or display name
    collections = NFTCollection.objects.filter(
        Q(name__icontains=query) | Q(display_name__icontains=query),
        is_active=True
    ).select_related('creator').only(
        'address', 'name', 'display_name', 'slug', 'image_url',
        'verified', 'total_supply'
    )[:10]  # Limit to 10 results

    results = []
    for collection in collections:
        # Try to get floor price from aggregated stats
        floor_price = None
        try:
            from analytics.models import AggregatedCollectionStats
            stats = AggregatedCollectionStats.objects.filter(
                collection=collection
            ).only('floor_price_sol').first()
            if stats:
                floor_price = float(stats.floor_price_sol) if stats.floor_price_sol else None
        except Exception:
            pass

        results.append({
            'address': collection.address,
            'name': collection.display_name or collection.name,
            'slug': collection.slug,
            'image_url': collection.image_url,
            'verified': collection.verified,
            'nft_count': collection.total_supply or 0,
            'floor_price': floor_price
        })

    return JsonResponse({'results': results})
