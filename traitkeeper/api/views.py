# traitkeeper/api/views.py
from django.http import JsonResponse
from django.db.models import Q
from nft_data.models import NFTCollection


def search_collections(request):
    """
    API endpoint for real-time collection search.
    Returns JSON with matching collections.
    """
    try:
        query = request.GET.get('q', '').strip()

        if len(query) < 2:
            return JsonResponse({'results': []})

        # Search collections by name or display name
        # Show both active and inactive collections, prioritize active ones
        collections = NFTCollection.objects.filter(
            Q(name__icontains=query) | Q(display_name__icontains=query)
        ).only(
            'address', 'name', 'display_name', 'slug', 'image_url',
            'verified', 'total_supply', 'is_active'
        ).order_by('-is_active', '-verified', 'name')[:10]  # Limit to 10 results

        results = []
        for collection in collections:
            # Try to get floor price from aggregated stats
            floor_price = None
            try:
                from analytics.models import AggregatedCollectionStats
                stats = AggregatedCollectionStats.objects.filter(
                    collection=collection
                ).only('floor_price_sol').first()
                if stats and stats.floor_price_sol:
                    floor_price = float(stats.floor_price_sol)
            except Exception:
                pass

            results.append({
                'address': collection.address,
                'name': collection.display_name or collection.name,
                'slug': collection.slug,
                'image_url': collection.image_url or '',
                'verified': collection.verified,
                'nft_count': collection.total_supply or 0,
                'floor_price': floor_price
            })

        return JsonResponse({'results': results})

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Search collections error: {str(e)}")
        return JsonResponse({'error': 'Search failed', 'results': []}, status=500)
