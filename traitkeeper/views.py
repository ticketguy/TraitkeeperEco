# traitkeeper/views.py

# --- Django Imports ---
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import StreamingHttpResponse, JsonResponse
# Import necessary aggregation functions and Q objects
from django.db.models import Sum, Count, Q, Prefetch, Avg, OuterRef, Subquery, FloatField, F
from django.db.models.functions import Coalesce  # To handle null averages
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.decorators import login_required
from decimal import Decimal

# --- Third-Party Imports ---
# Some dev environments may not have DRF available to the static analyzer; provide safe runtime fallbacks.
try:
    from rest_framework.decorators import api_view, permission_classes  # Add permission_classes if needed for API
    from rest_framework.permissions import AllowAny  # Example permission
    from rest_framework.response import Response
except Exception:
    # Minimal stubs so code can run (or be statically analyzed) in environments without DRF.
    def api_view(methods):
        def _decorator(fn):
            return fn
        return _decorator

    def permission_classes(classes):
        def _decorator(fn):
            return fn
        return _decorator

    class AllowAny:
        pass

    # Use Django's JsonResponse as a simple Response fallback
    Response = JsonResponse
# --- App Imports ---
from traitkeeper.network_services import SolanaNetworkService
# Import models correctly
from nft_data.models import NFT, NFTCollection, TraitValue, TraitType
from indexer.models import NFTEvent
from marketplace.models import AuctionEvent
from marketplace.vitality_models import NFTVitality, CollectionVitality
# Ad models
from advertisement.models import HeroSlide

# Analytics models
from analytics.models import (
    CollectionSweepEvent, 
    HighProfileTransfer, 
    TrendingTrait, 
    TraitPerformanceScore,  # Using this for Top Traits
    TopTrait,               # This model exists but TraitPerformanceScore has more data
    AggregatedCollectionStats
)





# --- Standard Library Imports ---
import json
import time
import logging
from decimal import Decimal # Import Decimal

# --- Logger Setup ---
logger = logging.getLogger(__name__)


# ============================================================================
# == UTILITY & HEALTH CHECK VIEWS 🩺
# ============================================================================

def health_check(request):
    """Health check endpoint."""
    return JsonResponse({'status': 'healthy', 'timestamp': timezone.now().isoformat()})


@api_view(['GET'])
@permission_classes([AllowAny])
def search_collections(request):
    """
    Search collections by name or display_name.
    Returns JSON with matching collections.
    """
    query = request.GET.get('q', '').strip()

    if not query or len(query) < 2:
        return Response({'results': []})

    # Search collections by name or display_name (case-insensitive)
    collections = NFTCollection.objects.filter(
        Q(name__icontains=query) |
        Q(display_name__icontains=query)
    ).only(
        'address', 'name', 'display_name', 'image_url'
    )[:10]  # Limit to 10 results

    results = [{
        'address': col.address,
        'name': col.display_name or col.name,
        'image_url': col.image_url or '',
        'url': f'/collection/{col.address}/'
    } for col in collections]

    return Response({'results': results})


@api_view(['GET'])
@permission_classes([AllowAny]) # Allow anyone to get stats
def solana_network_stats(request):
    """API endpoint for Solana network statistics."""
    # Consider caching this response
    service = SolanaNetworkService()
    stats = service.get_network_stats()
    return Response(stats)
    # Use a plain dict and populate on error/path to avoid narrow inferred typing
    context = {}

# ============================================================================
# == CORE PAGE VIEWS 🖥️
# ============================================================================

def index(request):
    """
    Renders the main index (homepage).
    (Optimized data fetching remains similar, but ensure models are available)
    """
    # Dynamic Imports (keep this pattern)
    from nft_data.models import NFTCollection, NFT, TraitValue
    from analytics.models import HighProfileTransfer, CollectionSweepEvent, TrendingTrait, TraitPerformanceScore
    from marketplace.models import AuctionEvent
    from indexer.models import CollectionMarketStats, NFTEvent
    from advertisement.models import HeroSlide

    context = {'error': None}
    try:
        # Fetch collections
        collections_qs = NFTCollection.objects.filter(is_listed=True).only(
            'address', 'name', 'display_name', 'image_url', 'is_featured', 'social_media_links'
        )
        
        collections_data = []
        for coll in collections_qs:
            try:
                # Get vitality score
                vitality_score = None
                if hasattr(coll, 'vitality') and getattr(coll, 'vitality') is not None:
                    vitality_score = getattr(coll, 'vitality').vitality_score
                else:
                    vit_obj = CollectionVitality.objects.filter(collection=coll).first()
                    if vit_obj and vit_obj.vitality_score is not None:
                        vitality_score = vit_obj.vitality_score

                vitality = float(vitality_score) if vitality_score is not None else 50.0
            except (AttributeError, TypeError, ValueError, CollectionVitality.DoesNotExist):
                vitality = 50.0

            collections_data.append({
                'name': coll.display_name or coll.name,
                'address': coll.address,
                'image_url': coll.image_url,
                'is_featured': coll.is_featured,
                'social_media_links': coll.social_media_links or {},
                'vitality_score': vitality,
            })
        
        collection_addresses = [coll.address for coll in collections_qs]

        # Fetch Aggregated Stats
        agg_stats_qs = AggregatedCollectionStats.objects.filter(
            collection__address__in=collection_addresses
        ).select_related('collection')

        # Create mapping from collection address to aggregated stat
        agg_stats_dict = {}
        for stat in agg_stats_qs:
            try:
                addr = stat.collection.address
            except Exception:
                continue
            agg_stats_dict[addr] = stat

        # Initialize totals
        total_volume_24h = Decimal('0.0')
        market_cap = Decimal('0.0')
        total_sales = 0

        # Attach aggregated stats to collection data
        for coll_dict in collections_data:
            agg_stat = agg_stats_dict.get(coll_dict['address'])
            if not agg_stat:
                coll_dict.setdefault('floor_price', 0.0)
                coll_dict.setdefault('volume_24h', 0.0)
                coll_dict.setdefault('total_volume', 0.0)
                coll_dict.setdefault('market_cap', 0.0)
                coll_dict.setdefault('price_change_24h', 0.0)
                coll_dict.setdefault('performance_score', 50.0)
                coll_dict.setdefault('number_of_holders', 0)
                coll_dict.setdefault('total_supply', 0)
                coll_dict.setdefault('listed_count', 0)
                continue

            coll_dict['floor_price'] = float(getattr(agg_stat, 'floor_price', 0) or 0.0)
            coll_dict['volume_24h'] = float(getattr(agg_stat, 'volume_24h', 0) or 0.0)
            coll_dict['total_volume'] = float(getattr(agg_stat, 'total_volume', 0) or 0.0)
            coll_dict['market_cap'] = float(getattr(agg_stat, 'market_cap', 0) or 0.0)
            coll_dict['price_change_24h'] = float(getattr(agg_stat, 'floor_change_24h', 0) or 0.0)
            coll_dict['performance_score'] = float(getattr(agg_stat, 'performance_score', 50) or 50.0)
            coll_dict['number_of_holders'] = int(getattr(agg_stat, 'unique_holders', getattr(agg_stat, 'unique_holder_count', 0)) or 0)
            coll_dict['total_supply'] = int(getattr(agg_stat, 'total_supply', 0) or 0)
            coll_dict['listed_count'] = int(getattr(agg_stat, 'listed_count', 0) or 0)

            # Accumulate totals
            try:
                total_volume_24h += Decimal(str(getattr(agg_stat, 'volume_24h', 0) or 0))
            except Exception:
                pass
            try:
                market_cap += Decimal(str(getattr(agg_stat, 'market_cap', 0) or 0))
            except Exception:
                pass
            try:
                total_sales += int(getattr(agg_stat, 'sales_count_24h', 0) or 0)
            except Exception:
                pass

        # Get top collections (filter out empty addresses)
        top_collections = sorted(
            [c for c in collections_data if c.get('address')],
            key=lambda x: x.get('performance_score', 0),
            reverse=True
        )[:10]
        
        top_performing_nfts = []

        # Fetch Hero Slides
        hero_slides = list(HeroSlide.objects.filter(is_active=True).order_by('id'))
        hero_slides_data = [
            {
                'title': s.title,
                'description': s.description,
                'button_text': s.button_text,
                'button_url': s.button_url,
                'image_url': s.image_url or "/static/img/certificate-preview.png",
                'url': s.url or ""
            } 
            for s in hero_slides
        ]

        # Fetch Collection Sweeps
        sweep_window = timezone.now() - timedelta(hours=12)
        collection_sweeps = list(
            CollectionSweepEvent.objects.select_related('collection')
            .filter(start_time__gte=sweep_window)
            .order_by('-significance_score')[:10]
        )
        collection_sweeps_list = [
            {
                "rank": index + 1,
                "collection": sweep.collection.display_name or sweep.collection.name,
            }
            for index, sweep in enumerate(collection_sweeps)
        ]

        # Fetch High Profile Transfers
        high_profile_threshold = 50  # SOL threshold
        recent_high_profile = HighProfileTransfer.objects.filter(
            event__amount__gte=high_profile_threshold,  # ✅ Access through event relation
            event__timestamp__gte=timezone.now() - timedelta(hours=24)  # ✅ Use event timestamp
        ).select_related('nft', 'nft__collection', 'event').prefetch_related(
            'nft__trait_values__trait_type'
        ).order_by('-event__amount')[:10]  # ✅ Order by event amount

        recent_transfers_list = []
        for index, transfer in enumerate(recent_high_profile):
            # Calculate time since
            time_diff = timezone.now() - transfer.event.timestamp
            
            if time_diff.total_seconds() < 3600:
                time_since = f"{int(time_diff.total_seconds() // 60)} mins ago"
            elif time_diff.total_seconds() < 86400:
                time_since = f"{int(time_diff.total_seconds() // 3600)} hours ago"
            else:
                time_since = f"{time_diff.days} days ago"
            
            # Get trait summary
            traits_summary = "None"
            if transfer.nft:
                traits = transfer.nft.trait_values.all()[:3]
                if traits:
                    traits_summary = ", ".join([f"{t.trait_type.name}: {t.value}" for t in traits])
            
            recent_transfers_list.append({
                'image_url': transfer.nft.image_url if transfer.nft else None,
                'buyer': transfer.event.buyer,  # ✅ Access through event
                'mint_address': transfer.nft.mint_address if transfer.nft else "Unknown",
                'seller': transfer.event.seller,  # ✅ Access through event
                'price': float(transfer.event.amount) if transfer.event.amount else 0.0,  # ✅ Access through event
                'collection': transfer.nft.collection.display_name or transfer.nft.collection.name if transfer.nft and transfer.nft.collection else "Unknown",
                'traits': traits_summary,
                'delay': index * 100,
            })

        # Calculate average price
        avg_price = float(total_volume_24h / total_sales) if total_sales > 0 else 0.0

        # ============================================================================
        # TRENDING TRAITS (NFTs) - Level 2A + Level 3
        # ============================================================================
        # Goal: Display NFTs ranked by their highest-performing trending trait
        # Strategy:
        # 1. Get top 5 trending traits from TrendingTrait model
        # 2. Find all NFTs that have ANY of these trending traits
        # 3. Annotate each NFT with the MAX performance_score from their trending traits
        # 4. Sort NFTs by this max score and display with the signifying trait

        trending_nfts = []
        try:
            # Step 1: Get top 5 trending trait_values
            trending_traits_qs = TrendingTrait.objects.select_related(
                'trait_value', 'trait_value__trait_type'
            ).order_by('-trend_score')[:5]

            trending_trait_value_ids = [tt.trait_value.id for tt in trending_traits_qs if tt.trait_value]

            if trending_trait_value_ids:
                # Step 2: Get TraitPerformanceScore for these traits to use for ranking
                trending_trait_scores = TraitPerformanceScore.objects.filter(
                    trait_value_id__in=trending_trait_value_ids
                ).select_related('trait_value', 'trait_type')

                # Create a map of trait_value_id -> performance_score
                trait_score_map = {
                    tps.trait_value_id: tps.performance_score
                    for tps in trending_trait_scores
                }

                # Step 3: Find NFTs with these trending traits
                # Use subquery to get max performance score for each NFT
                nfts_with_trending_traits = NFT.objects.filter(
                    trait_values__id__in=trending_trait_value_ids
                ).select_related('collection').prefetch_related(
                    Prefetch(
                        'trait_values',
                        queryset=TraitValue.objects.filter(
                            id__in=trending_trait_value_ids
                        ).select_related('trait_type')
                    )
                ).distinct()

                # Step 4: Annotate and rank
                nft_scores = []
                for nft in nfts_with_trending_traits:
                    # Find the max score from this NFT's trending traits
                    nft_trending_traits = [tv for tv in nft.trait_values.all() if tv.id in trending_trait_value_ids]

                    if nft_trending_traits:
                        # Get scores for all trending traits on this NFT
                        scores_with_traits = [
                            (trait_score_map.get(tv.id, 0), tv)
                            for tv in nft_trending_traits
                        ]

                        # Find the trait with max score (the signifying trait)
                        max_score, signifying_trait = max(scores_with_traits, key=lambda x: x[0])

                        nft_scores.append({
                            'nft': nft,
                            'max_score': max_score,
                            'signifying_trait': signifying_trait,
                        })

                # Sort by max score descending
                nft_scores.sort(key=lambda x: x['max_score'], reverse=True)

                # Take top 10 and format for template
                for index, item in enumerate(nft_scores[:10]):
                    nft = item['nft']
                    trait = item['signifying_trait']

                    trending_nfts.append({
                        'mint_address': nft.mint_address,
                        'name': nft.name or f"{nft.collection.name} #{nft.mint_address[:8]}",
                        'image_url': nft.image_url or '/static/img/nft-default.png',
                        'collection': nft.collection.display_name or nft.collection.name,
                        'collection_address': nft.collection.address,
                        'trait_type': trait.trait_type.name,
                        'trait_value': trait.value,
                        'performance_score': float(item['max_score']),
                        'delay': index * 100,
                    })

        except Exception as e:
            logger.error(f"Error fetching trending traits NFTs: {e}", exc_info=True)

        # ============================================================================
        # TOP 100 TRAITS - Level 2A Direct Query
        # ============================================================================
        # Goal: Display traits sorted by performance_score from TraitPerformanceScore
        # This is straightforward - just query and sort

        # Get search and pagination params
        search_query = request.GET.get('q', '').strip()
        page_number = request.GET.get('page', 1)

        # Base queryset
        top_traits_qs = TraitPerformanceScore.objects.select_related(
            'trait_type', 'trait_value', 'collection'
        ).order_by('-performance_score')

        # Apply search filter if provided
        if search_query:
            top_traits_qs = top_traits_qs.filter(
                Q(trait_type__name__icontains=search_query) |
                Q(trait_value__value__icontains=search_query) |
                Q(collection__name__icontains=search_query)
            )

        # Paginate (100 per page)
        paginator = Paginator(top_traits_qs, 100)

        try:
            top_traits_page = paginator.page(page_number)
        except PageNotAnInteger:
            top_traits_page = paginator.page(1)
        except EmptyPage:
            top_traits_page = paginator.page(paginator.num_pages)

        # Format traits for template
        top_traits_list = []
        for trait_perf in top_traits_page:
            # Get a sample NFT with this trait for the image
            sample_nft = NFT.objects.filter(
                trait_values=trait_perf.trait_value
            ).select_related('collection').first()

            # Get collection market stats for modal
            collection_stats = CollectionMarketStats.objects.filter(
                collection=trait_perf.collection
            ).order_by('-timestamp').first()

            # Get collection vitality for performance score
            collection_vitality = None
            if hasattr(trait_perf.collection, 'vitality'):
                collection_vitality = trait_perf.collection.vitality
            else:
                try:
                    collection_vitality = CollectionVitality.objects.filter(
                        collection=trait_perf.collection
                    ).first()
                except:
                    pass

            top_traits_list.append({
                'trait_name': trait_perf.trait_type.name,
                'trait_value': trait_perf.trait_value.value,
                'collection': trait_perf.collection.display_name or trait_perf.collection.name,
                'collection_address': trait_perf.collection.address,
                'performance_score': float(trait_perf.performance_score),
                'rarity_score': float(trait_perf.rarity_score),
                'avg_sale_price': float(trait_perf.avg_sale_price),
                'premium_score': float(trait_perf.premium_score),
                'velocity_score': float(trait_perf.velocity_score),
                'momentum_score': float(trait_perf.momentum_score),
                'image_url': sample_nft.image_url if sample_nft else '/static/img/nft-default.png',
                'mint_address': sample_nft.mint_address if sample_nft else None,
                # Collection-level data for modal
                'collection_image_url': trait_perf.collection.image_url,
                'collection_floor_price': float(collection_stats.floor_price) if collection_stats and collection_stats.floor_price else 0.0,
                'collection_volume': float(collection_stats.volume_24h) if collection_stats and collection_stats.volume_24h else 0.0,
                'collection_market_cap': float(collection_stats.market_cap) if collection_stats and collection_stats.market_cap else 0.0,
                'collection_price_change': float(collection_stats.price_change_24h) if collection_stats and collection_stats.price_change_24h else 0.0,
                'collection_holders': collection_stats.num_holders if collection_stats and collection_stats.num_holders else 0,
                'collection_supply': trait_perf.collection.total_supply if hasattr(trait_perf.collection, 'total_supply') else 0,
                'collection_listed': collection_stats.num_listed if collection_stats and collection_stats.num_listed else 0,
                'collection_performance': float(collection_vitality.vitality_score) if collection_vitality and collection_vitality.vitality_score else 0.0,
            })

        # Build context
        context = {
            **context,
            'collection_stats': {
                'total_volume_24h': float(total_volume_24h),
                'market_cap': float(market_cap),
                'total_sales': total_sales,
                'avg_price_24h': avg_price,
            },
            'hero_slides': hero_slides_data,
            'collection_sweeps': collection_sweeps_list,
            'featured_collections': sorted(
                [c for c in collections_data 
                 if c.get('vitality_score') is not None 
                 and c.get('address')
                ],
                key=lambda x: x.get('vitality_score', 0),
                reverse=True
            )[:10],
            'top_collections': top_collections,
            'top_performing_nfts': top_performing_nfts,
            'recent_transfers': recent_transfers_list,
            'trending_traits': trending_nfts,  # NFTs ranked by trending trait performance
            'top_traits': top_traits_page,  # Paginated TraitPerformanceScore objects
            'search_query': search_query,  # For search persistence
            'vapid_public_key': settings.VAPID_PUBLIC_KEY,
            'initial_data_json': json.dumps({
                'collections': collections_data,
            })
        }
        
    except Exception as e:
        logger.error(f"Error in index view: {str(e)}", exc_info=True)
        context['error'] = 'An error occurred while loading homepage data.'

    return render(request, 'index page/index.html', context)




@api_view(['GET'])
@permission_classes([AllowAny]) # Allow anyone to get details
def get_nft_details_api(request, mint_address):
    """
    API endpoint to fetch detailed data for a SINGLE NFT for the modal view.
    Includes listing status, asking price, and vitality score.
    """
    try:
        # Fetch NFT with related collection and traits efficiently
        nft = NFT.objects.select_related('collection').prefetch_related(
             Prefetch('trait_values', queryset=TraitValue.objects.select_related('trait_type'))
        ).get(mint_address=mint_address)

        traits_list = [{"trait_type": trait.trait_type.name, "value": trait.value} for trait in nft.trait_values.all()] # Use prefetched

        # Fetch recent events
        events = NFTEvent.objects.filter(nft_mint=nft.mint_address).order_by('-timestamp')[:20]
        events_list = [
            {
                'event_type': event.get_event_type_display(),
                'amount': float(event.amount) if event.amount else None,
                'timestamp': event.timestamp.isoformat(),
                'buyer': event.buyer,
                'seller': event.seller
            }
            for event in events
        ]

        # Fetch Vitality Score
        vitality_score = None
        try:
            # No need for sync_to_async here as the view itself isn't async
            vitality = NFTVitality.objects.get(nft=nft)
            vitality_score = float(vitality.vitality_score) if vitality.vitality_score is not None else None
        except NFTVitality.DoesNotExist:
            logger.warning(f"No vitality score found for NFT {mint_address}")
        except Exception as e:
            logger.error(f"Error fetching vitality for {mint_address}: {e}")

        # --- TODO: Fetch Trait Performance Score(s) for this NFT ---
        # Calculate average or max score based on its traits
        nft_trait_value_ids = [tv.id for tv in nft.trait_values.all()]
        trait_scores = TraitPerformanceScore.objects.filter(trait_value_id__in=nft_trait_value_ids)
        avg_trait_perf_score = trait_scores.aggregate(avg_score=Avg('performance_score'))['avg_score']
        trait_performance_score = float(avg_trait_perf_score) if avg_trait_perf_score is not None else None

        # Prepare the detailed data dictionary
        nft_details_data = {
            'mint_address': nft.mint_address,
            'name': nft.name or 'Unknown NFT',
            'image_url': nft.image_url or "/static/img/nft-default.png",
            'owner': nft.owner,
            'collection_name': nft.collection.display_name or nft.collection.name,
            'collection_address': nft.collection.address,
            'has_buy_price': nft.has_buy_price,
            'buy_price': float(nft.buy_price) if nft.has_buy_price and nft.buy_price is not None else None,
            'has_sell_intent': nft.has_sell_intent,
            'asking_price': float(nft.asking_price) if nft.has_sell_intent and nft.asking_price is not None else None,
            'vitality_score': vitality_score,
            'trait_performance_score': trait_performance_score, # Add trait performance score
            'traits': traits_list,
            'onchain_details': {
                 "Token Address": nft.mint_address,
                 "Token Standard": "SPL",
                 "Collection": nft.collection.display_name or nft.collection.name
                 },
            'journey': events_list
        }

        return Response({'success': True, 'details': nft_details_data})

    except NFT.DoesNotExist:
        return Response({'success': False, 'error': 'NFT not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_nft_details_api for {mint_address}: {e}", exc_info=True)
        return Response({'success': False, 'error': 'An internal error occurred'}, status=500)



# ============================================================================
#  COLLECTION DETAIL VIEW - Shows Collection with Vitality and Advanced Sorting/Filtering
# ============================================================================


def collection_detail(request, address):
    """
    Enhanced collection detail view with:
    - Collection vitality score from your vitality models
    - 9 sort options: Trait Performance, Vitality, Rarity, Price, Recent
    - Working filters and search
    - Pagination
    """
    
    # --- 1. Get Collection ---
    collection = get_object_or_404(NFTCollection, address=address)
    
# --- 2. Get Collection Stats with Vitality ---
    collection_stats_data = {}
    agg_stat = None # Initialize agg_stat to None

    try:
        # Use filter().first() - returns None if not found, doesn't raise DoesNotExist
        agg_stat = AggregatedCollectionStats.objects.filter(collection_id=address).first()

        if agg_stat:
            # Safely resolve owners count
            owners_raw = None
            for attr in ('number_of_holders', 'unique_holders', 'unique_holder_count', 'unique_owner_count', 'owners', 'holders_count', 'holders'):
                owners_raw = getattr(agg_stat, attr, None)
                if owners_raw is not None:
                    break
            owners_count = int(owners_raw or 0)

            collection_stats_data = {
                'floor_price': float(getattr(agg_stat, 'floor_price', 0) or 0),
                'floor_change_24h': float(getattr(agg_stat, 'price_change_24h', 0) or 0), # Match model field
                'volume_24h': float(getattr(agg_stat, 'volume_24h', 0) or 0),
                'velocity_24h': float(getattr(agg_stat, 'velocity_24h', 0) or 0), # Now safe to access
                'total_volume': float(getattr(agg_stat, 'total_volume', 0) or 0), # Check if this field exists
                'market_cap': float(getattr(agg_stat, 'market_cap', 0) or 0),
                'owners': owners_count,
                'owners_change_24h': float(getattr(agg_stat, 'holder_change_24h', 0) or 0), # Check if this field exists
                'listed_count': int(getattr(agg_stat, 'listed_count', 0) or 0),
                'total_supply': int(getattr(agg_stat, 'total_supply', 0) or 0), # Get total supply
                 # Add other stats you need from agg_stat here, using getattr for safety
            }
        else:
            # agg_stat is None (record doesn't exist) - set all defaults
            logger.warning(f"No AggregatedCollectionStats found for {address}. Using defaults.")
            collection_stats_data = {
                'floor_price': 0.0, 'floor_change_24h': 0.0, 'volume_24h': 0.0,
                'velocity_24h': 0.0, 'total_volume': 0.0, 'market_cap': 0.0,
                'owners': 0, 'owners_change_24h': 0.0, 'listed_count': 0,
                'total_supply': 0, # Default to 0 when no stats available
                # Add any other default values needed
            }

        # --- Now handle Vitality ---
        # (This part seems okay, but ensure CollectionVitality exists)
        try:
             vitality_obj = collection.vitality # Access related object directly
             if vitality_obj and vitality_obj.vitality_score is not None:
                 collection_stats_data['vitality_score'] = float(vitality_obj.vitality_score)
             else:
                 # Fallback needed if collection.vitality doesn't exist or score is null
                 vit_fallback = CollectionVitality.objects.filter(collection=collection).first()
                 collection_stats_data['vitality_score'] = float(vit_fallback.vitality_score) if vit_fallback and vit_fallback.vitality_score is not None else 50.0
        except CollectionVitality.DoesNotExist:
             logger.warning(f"No CollectionVitality object linked for {address}")
             collection_stats_data['vitality_score'] = 50.0 # Default neutral score
        except AttributeError: # Handles case where collection.vitality doesn't exist
             logger.warning(f"No 'vitality' attribute on collection {address}")
             collection_stats_data['vitality_score'] = 50.0 # Default neutral score


    except Exception as e:
        # Catch any other unexpected errors during stat/vitality fetching
        logger.error(f"Error fetching stats or vitality for {address}: {e}", exc_info=True)
        # Ensure safe defaults are set even if another error occurs
        collection_stats_data.setdefault('floor_price', 0.0)
        collection_stats_data.setdefault('volume_24h', 0.0)
        collection_stats_data.setdefault('market_cap', 0.0)
        collection_stats_data.setdefault('owners', 0)
        collection_stats_data.setdefault('listed_count', 0)
        collection_stats_data.setdefault('total_supply', 0)
        collection_stats_data.setdefault('vitality_score', 50.0)
        collection_stats_data['error'] = "Could not load collection statistics."
    
    # --- 3. Get Collection Vitality Score (Using Your Models) ---
    try:
        # Direct access via OneToOne relationship
        collection_stats_data['vitality_score'] = float(collection.vitality.vitality_score)
    except (CollectionVitality.DoesNotExist, AttributeError) as e:
        logger.warning(f"No vitality data for collection {address}: {e}")
        collection_stats_data['vitality_score'] = 50.0  # Default neutral score
    
    # --- 4. Get NFTs with Filtering and Sorting ---
    nfts_queryset = NFT.objects.filter(collection=collection, is_burned=False)
    
    # Get filter parameters
    search_query = request.GET.get('q', '')
    sort_by = request.GET.get('sort_by', 'trait_perf_desc')  # Default sort
    selected_traits = request.GET.getlist('trait')
    
    # Apply search filter
    if search_query:
        nfts_queryset = nfts_queryset.filter(
            Q(name__icontains=search_query) | Q(mint_address__icontains=search_query)
        )
    
    # Apply trait filters
    if selected_traits:
        for trait_pair in selected_traits:
            try:
                type_name, value_name = trait_pair.split(':', 1)
                nfts_queryset = nfts_queryset.filter(
                    trait_values__trait_type__name=type_name,
                    trait_values__value=value_name
                )
            except ValueError:
                logger.warning(f"Invalid trait filter format: {trait_pair}")
        nfts_queryset = nfts_queryset.distinct()
    
    # --- 5. Apply Sorting ---
    # OPTIMIZATION: Only calculate expensive annotations when needed for sorting

    # For trait performance sorting
    if sort_by in ['trait_perf_desc', 'trait_perf_asc']:
        avg_trait_score_subquery = TraitPerformanceScore.objects.filter(
            trait_value__nfts=OuterRef('pk')
        ).values('trait_value__nfts').annotate(
            avg_score=Avg('performance_score')
        ).values('avg_score')

        nfts_queryset = nfts_queryset.annotate(
            avg_trait_performance=Coalesce(
                Subquery(avg_trait_score_subquery, output_field=FloatField()),
                0.0
            )
        )

    # For vitality sorting, use select_related (OneToOne relationship)
    if sort_by in ['vitality_desc', 'vitality_asc']:
        nfts_queryset = nfts_queryset.select_related('vitality')

    # For rarity sorting, calculate rarity score
    if sort_by in ['rarity_desc', 'rarity_asc']:
        nfts_queryset = nfts_queryset.annotate(
            rarity_score=Coalesce(
                Sum('trait_values__rarity'),
                100.0  # Default for NFTs with no traits
            )
        )
    
    # Apply the appropriate ordering
    if sort_by == 'trait_perf_desc':
        nfts_queryset = nfts_queryset.order_by('-avg_trait_performance')
    elif sort_by == 'trait_perf_asc':
        nfts_queryset = nfts_queryset.order_by('avg_trait_performance')
    elif sort_by == 'vitality_desc':
        nfts_queryset = nfts_queryset.order_by(
            F('vitality__vitality_score').desc(nulls_last=True)
        )
    elif sort_by == 'vitality_asc':
        nfts_queryset = nfts_queryset.order_by(
            F('vitality__vitality_score').asc(nulls_last=True)
        )
    elif sort_by == 'rarity_desc':
        # Lower rarity_score = more rare
        nfts_queryset = nfts_queryset.order_by('rarity_score')
    elif sort_by == 'rarity_asc':
        # Higher rarity_score = more common
        nfts_queryset = nfts_queryset.order_by('-rarity_score')
    elif sort_by == 'price_desc':
        nfts_queryset = nfts_queryset.annotate(
            effective_price=Coalesce('buy_price', 'asking_price', 0.0)
        ).order_by('-effective_price')
    elif sort_by == 'price_asc':
        nfts_queryset = nfts_queryset.annotate(
            effective_price=Coalesce('buy_price', 'asking_price', 999999.0)
        ).order_by('effective_price')
    elif sort_by == 'recent':
        nfts_queryset = nfts_queryset.order_by('-created_at')
    else:
        # Default to trait performance
        nfts_queryset = nfts_queryset.order_by('-avg_trait_performance')
    
    # Prefetch related objects AFTER sorting/filtering
    nfts_queryset = nfts_queryset.prefetch_related(
        Prefetch('trait_values', queryset=TraitValue.objects.select_related('trait_type'))
    )

    # --- 6. Pagination ---
    # Use 50 NFTs per page for optimal performance with Load More button
    paginator = Paginator(nfts_queryset, 50)
    page_number = request.GET.get('page')
    
    try:
        nfts_page = paginator.page(page_number)
    except PageNotAnInteger:
        nfts_page = paginator.page(1)
    except EmptyPage:
        nfts_page = paginator.page(paginator.num_pages)
    
    # --- 7. Prepare NFT Data with Vitality ---
    nfts_list = []
    for nft in nfts_page.object_list:
        nft_data = {
            'mint_address': nft.mint_address,
            'name': nft.name,
            'image_url': nft.image_url,
            'buy_price': nft.buy_price,
            'asking_price': nft.asking_price,
            'performance_score': getattr(nft, 'avg_trait_performance', 50.0),  # Only set if sorting by performance
        }

        # Add vitality score from OneToOne relationship
        try:
            nft_data['vitality_score'] = float(nft.vitality.vitality_score)
        except (AttributeError, NFTVitality.DoesNotExist):
            nft_data['vitality_score'] = 50.0  # Default for NFTs without vitality

        # Add rarity score if it was calculated
        if hasattr(nft, 'rarity_score'):
            nft_data['rarity_score'] = nft.rarity_score

        nfts_list.append(nft_data)
    
    # --- 8. Get Traits for Filter ---
    traits_queryset = TraitValue.objects.filter(
        trait_type__collection=collection
    ).select_related('trait_type').values(
        'trait_type__name', 'value', 'count', 'rarity'
    ).order_by('trait_type__name', 'value')
    
    traits_list_for_template = [
        {
            'trait_name': t['trait_type__name'],
            'trait_value': t['value'],
            'count': t['count'],
            'rarity': t['rarity']
        }
        for t in traits_queryset
    ]
    
    # --- 9. Get Activity Events ---
    try:
        # Use a stable filter for recent events for this collection if available, otherwise global recent
        events_queryset = NFTEvent.objects.filter(
            collection_address=collection.address
        ).order_by('-timestamp')[:20]
    except Exception:
        events_queryset = NFTEvent.objects.order_by('-timestamp')[:20]

    # Get NFT info for events in a single query
    event_mint_addresses = {e.nft_mint for e in events_queryset if e.nft_mint}
    nfts_for_events = NFT.objects.filter(
        mint_address__in=event_mint_addresses
    ).values('mint_address', 'name', 'image_url')
    nft_info_map = {nft['mint_address']: nft for nft in nfts_for_events}

    events_list = []
    for event in events_queryset:
        nft_info = nft_info_map.get(event.nft_mint)
        nft_name = nft_info.get('name') if nft_info else (event.nft_mint[:8] if event.nft_mint else 'Unknown')
        nft_image = nft_info.get('image_url') if nft_info else '/static/img/nft-default.png'

        events_list.append({
            'event_id': getattr(event, 'event_id', None),
            'nft_mint': getattr(event, 'nft_mint', None),
            'nft_name': nft_name,
            'nft_image_url': nft_image,
            'event_type': getattr(event, 'get_event_type_display', lambda: str(getattr(event, 'event_type', '')))(),
            'amount': float(event.amount) if getattr(event, 'amount', None) is not None else None,
            'timestamp': getattr(event, 'timestamp', None),
            'buyer': getattr(event, 'buyer', None),
            'seller': getattr(event, 'seller', None)
        })

    # --- 10. Final Context ---
    try:
        from django.core.serializers.json import DjangoJSONEncoder
    except Exception:
        DjangoJSONEncoder = json.JSONEncoder

    # Prepare data for JSON script tag
    initial_data_for_script = {
        'collection_stats': collection_stats_data,
        'nfts': nfts_list,
        'events': events_list,
        'search_query': search_query,
        'sort_by': sort_by,
        'selected_traits_json': json.dumps(selected_traits),
        'address': address,
    }

    context = {
        'collection': collection,
        'collection_stats': collection_stats_data,
        'nfts': nfts_list,
        'nfts_page': nfts_page,  # For pagination/Load More button
        'traits': traits_list_for_template,
        'events': events_list,
        'search_query': search_query,
        'sort_by': sort_by,
        'selected_traits': selected_traits,
        'address': address,
        'vapid_public_key': settings.VAPID_PUBLIC_KEY,
        'initial_data_json': json.dumps(initial_data_for_script, cls=DjangoJSONEncoder)
    }

    return render(request, 'index page/collection_detail.html', context) 

# ============================================================================
# SSE VIEW 1: Main Site Updates (Sweeps, Traits, Transfers, etc.)
# URL: /stream-site-updates/
# ============================================================================

def stream_site_updates(request):
    """
    Server-Sent Events (SSE) stream for live data updates.
    Handles 'index' page data and 'collection_detail' page data.
    """
    page = request.GET.get('page', 'index')
    address = request.GET.get('address', None)

    # If the client requested collection detail stream but didn't provide address, return an error SSE payload.
    if page == 'collection_detail' and not address:
        error_msg = json.dumps({'error': "'address' parameter is required for the collection detail page."})
        return StreamingHttpResponse([f"data: {error_msg}\n\n".encode()], content_type='text/event-stream')

    def event_stream():
        """Generator function that yields SSE data periodically."""
        
        # Import models needed for the loop here, inside the generator
        # Note: We only import models needed for THIS stream
        from analytics.models import (
            CollectionSweepEvent, HighProfileTransfer, TrendingTrait, 
            TraitPerformanceScore, AggregatedCollectionStats
        )
        from nft_data.models import NFTCollection, NFT
        
        while True:
            # Use a generic update_data dict
            update_data = {}
            
            try:
                # ========================================================
                # COLLECTION DETAIL PAGE UPDATES
                # ========================================================
                if page == 'collection_detail' and address:
                    update_data['timestamp'] = timezone.now().isoformat()
                    update_data['page'] = page
                    try:
                        collection = NFTCollection.objects.filter(address=address).first()
                        if collection:
                            try:
                                agg_stat = AggregatedCollectionStats.objects.filter(
                                    collection__address=address
                                ).select_related('collection').first()
                            except Exception:
                                agg_stat = None

                            collection_stats = {}
                            if agg_stat:
                                collection_stats = {
                                    'floor_price': float(getattr(agg_stat, 'floor_price', 0) or 0),
                                    'volume_24h': float(getattr(agg_stat, 'volume_24h', 0) or 0),
                                    'market_cap': float(getattr(agg_stat, 'market_cap', 0) or 0),
                                    'performance_score': float(getattr(agg_stat, 'performance_score', 50) or 50),
                                }
                            else:
                                collection_stats = {
                                    'floor_price': 0.0, 'volume_24h': 0.0,
                                    'market_cap': 0.0, 'performance_score': 50.0
                                }

                            try:
                                avg_trait_score_subquery = TraitPerformanceScore.objects.filter(
                                    trait_value__nfts=OuterRef('pk')
                                ).values('trait_value__nfts').annotate(
                                    avg_score=Avg('performance_score')
                                ).values('avg_score')

                                nfts_qs = NFT.objects.filter(
                                    collection=collection, 
                                    is_burned=False
                                ).annotate(
                                    avg_trait_performance=Coalesce(
                                        Subquery(avg_trait_score_subquery, output_field=FloatField()), 0.0
                                    )
                                ).order_by('-avg_trait_performance')[:12]

                                nfts_sample = [
                                    {
                                        'mint_address': nft.mint_address,
                                        'name': nft.name,
                                        'image_url': nft.image_url,
                                        'performance_score': float(getattr(nft, 'avg_trait_performance', 0.0))
                                    } for nft in nfts_qs
                                ]
                            except Exception:
                                nfts_sample = []

                            update_data['collection'] = {
                                'address': address,
                                'name': getattr(collection, 'display_name', None) or getattr(collection, 'name', None),
                                'stats': collection_stats,
                                'nfts_sample': nfts_sample
                            }
                        else:
                            update_data['collection'] = {'address': address, 'error': 'not found'}
                    except Exception as e:
                        logger.exception("Error preparing collection update for SSE: %s", e)
                        update_data['collection'] = {'address': address, 'error': 'internal'}

                # ========================================================
                # INDEX PAGE UPDATES (Homepage)
                # ========================================================
                elif page == 'index':
                    # Note: Hero Slides and Vitality Collections are REMOVED from this view.
                    
                    # --- 1. Get Top Collections (for the Table) ---
                    top_collections_data = []  # <<< FIX 1: Initialize list *outside* the try block
                    try:
                        top_collections_stats = AggregatedCollectionStats.objects.filter(
                            collection__is_listed=True
                        ).select_related('collection', 'collection__vitality').order_by('-performance_score')[:8]
                        
                        for stat in top_collections_stats:
                            try:
                                # This inner try/except skips individual bad records
                                try:
                                    vitality = float(stat.collection.vitality.vitality_score)
                                except Exception:
                                    vitality = 50.0 # Default if vitality record is missing
                                
                                top_collections_data.append({
                                    'address': stat.collection.address,
                                    'name': stat.collection.display_name or stat.collection.name,
                                    'image_url': stat.collection.image_url,
                                    'volume': float(stat.volume_24h or 0), 
                                    'vitality_score': vitality,
                                    'floor_price': float(stat.floor_price or 0),
                                    'sales': int(getattr(stat, 'sales_count_24h', 0) or 0), # Note: This field is not on the model, will be 0
                                    'trend': float(stat.price_change_24h or 0), 
                                })
                            except Exception as inner_e:
                                logger.warning(f"Skipping bad collection record during SSE serialization: {inner_e}", exc_info=False)

                    except Exception as e:
                        logger.error(f"Error fetching top collections for SSE: {e}", exc_info=True)
                    
                    update_data['top_collections'] = top_collections_data

                    # --- 2. Get Collection Sweeps ---
                    try:
                        sweep_window = timezone.now() - timedelta(hours=12)
                        collection_sweeps = list(
                            CollectionSweepEvent.objects.select_related('collection')
                            .filter(start_time__gte=sweep_window)
                            .order_by('-significance_score')[:10]
                        )
                        collection_sweeps_list = [
                            {
                                "rank": index + 1,
                                "collection": sweep.collection.display_name or sweep.collection.name,
                                "buyer_address": sweep.buyer_address,
                                "num_items": sweep.num_items,
                                "total_volume": float(sweep.total_volume),
                                "significance_score": float(sweep.significance_score),
                                "image_url": sweep.collection.image_url or "/static/img/collection-default.png",
                                # JS expects these fields, keep getattr for safety
                                "price_movement": float(getattr(sweep, 'price_movement', 0.0)),
                                "target_traits": getattr(sweep, 'target_traits', []) 
                            }
                            for index, sweep in enumerate(collection_sweeps)
                        ]
                        update_data['collection_sweeps'] = collection_sweeps_list
                    except Exception as e:
                        logger.error(f"Error fetching collection sweeps for SSE: {e}", exc_info=True)

                    # --- 3. Get Recent High-Profile Transfers ---
                    try:
                        high_profile_threshold = 50  # SOL threshold
                        recent_high_profile = HighProfileTransfer.objects.filter(
                            event__amount__gte=high_profile_threshold,
                            event__timestamp__gte=timezone.now() - timedelta(hours=24)
                        ).select_related('nft', 'nft__collection', 'event').prefetch_related(
                            'nft__trait_values__trait_type'
                        ).order_by('-event__amount')[:10]

                        recent_transfers_list = []
                        for index, transfer in enumerate(recent_high_profile):
                            traits_summary = "None"
                            if transfer.nft:
                                traits = transfer.nft.trait_values.all()[:3]
                                if traits:
                                    traits_summary = ", ".join([f"{t.trait_type.name}: {t.value}" for t in traits])
                            
                            recent_transfers_list.append({
                                'image_url': transfer.nft.image_url if transfer.nft else None,
                                'buyer': transfer.event.buyer,
                                'mint_address': transfer.nft.mint_address if transfer.nft else "Unknown",
                                'seller': transfer.event.seller,
                                'price': float(transfer.event.amount) if transfer.event.amount else 0.0,
                                'collection': transfer.nft.collection.display_name or transfer.nft.collection.name if transfer.nft and transfer.nft.collection else "Unknown",
                                'traits': traits_summary,
                            })
                        update_data['recent_transfers'] = recent_transfers_list
                    except Exception as e:
                        logger.error(f"Error fetching high profile transfers for SSE: {e}", exc_info=True)

                    # --- 4. Get Trending Traits ---
                    try:
                        # FIX: Model uses 'trend_score', not 'trending_score'
                        trending_traits_qs = TrendingTrait.objects.select_related(
                            'trait_value__trait_type', 'collection'
                        ).order_by('-trend_score')[:5]

                        trending_traits_list = []
                        for index, trait in enumerate(trending_traits_qs):
                            trending_traits_list.append({
                                'trait_name': trait.trait_value.trait_type.name,
                                'trait_value': trait.trait_value.value,
                                # NOTE: TraitValue model has no image_url, using placeholder
                                'image_url': "/static/img/nft-default.png", 
                                'count': trait.trait_value.count,
                                'delay': index * 100,
                            })
                        update_data['trending_traits'] = trending_traits_list
                    except Exception as e:
                        logger.error(f"Error fetching trending traits for SSE: {e}", exc_info=True)

                    # --- 5. [NEW] Get Top Traits ---
                    # Your JS expects 'top_traits'. We'll use TraitPerformanceScore for this.
                    try:
                        top_traits_qs = TraitPerformanceScore.objects.select_related(
                            'trait_value', 'trait_value__trait_type', 'collection'
                        ).order_by('-performance_score')[:10] # Get top 10

                        top_traits_list = []
                        for tt in top_traits_qs:
                            top_traits_list.append({
                                'trait_name': tt.trait_value.trait_type.name,
                                'trait_value': tt.trait_value.value,
                                'collection': tt.collection.display_name or tt.collection.name,
                                'floor_price': float(tt.avg_sale_price or 0),
                                'trend_percentage': float(tt.momentum_score or 0),
                                'count': tt.trait_value.count,
                                # NOTE: TraitValue model has no image_url, using placeholder
                                'image_url': "/static/img/nft-default.png",
                                # Fields JS expects but model doesn't have:
                                'volume': 0.0, 
                                'sales': 0,
                                'market_cap': 0.0,
                            })
                        update_data['top_traits'] = top_traits_list
                    except Exception as e:
                        logger.error(f"Error fetching top traits for SSE: {e}", exc_info=True)
                    
                    # --- 6. [NEW] Get X Feed (Placeholder) ---
                    # No models were provided for this, so here is a hard-coded placeholder
                    try:
                        update_data['x_feed'] = [
                            {
                                'username': 'traitkeeper',
                                'content': 'Welcome to the TraitKeeper alpha! 🚀 Follow us for live Solana NFT analytics.',
                                'time': '1m ago',
                                'avatar_url': '/static/img/trait-keeper-logo-purple-combination-mark.png'
                            },
                            {
                                'username': 'sol_whale',
                                'content': 'Just swept 10 @SomeCollection NFTs using @traitkeeper, the analytics are insane!',
                                'time': '5m ago',
                                'avatar_url': 'https://ui-avatars.com/api/?name=SW&background=9333ea&color=fff'
                            }
                        ]
                    except Exception as e:
                        logger.error(f"Error fetching x_feed for SSE: {e}", exc_info=True)

                
                # --- Final Send ---
                if not update_data:
                    # If page is not 'index' or 'collection_detail', send a simple ping
                    update_data = {'timestamp': timezone.now().isoformat(), 'page': page, 'status': 'ping'}

            except Exception as e:
                logger.error(
                    f"General error in stream_site_updates for page '{page}': {str(e)}",
                    exc_info=True
                )
                update_data['error'] = 'An error occurred during the stream.'

            # SSE expects bytes; send JSON-encoded payload
            try:
                yield f"data: {json.dumps(update_data)}\n\n".encode()
            except Exception:
                yield f"data: {json.dumps({'error': 'encoding error'})}\n\n".encode()

            # Wait 30 seconds before next update for this stream
            time.sleep(30)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # Disable buffering for nginx
    return response


# ============================================================================
# SSE VIEW 2: Hero Slides
# URL: /stream-hero-slides/
# ============================================================================

def stream_hero_slides(request):
    """
    A dedicated SSE stream just for the hero slides.
    This can update on a much slower interval.
    """
    def event_stream():
        from advertisement.models import HeroSlide
        while True:
            update_data = {}
            try:
                hero_slides_qs = HeroSlide.objects.filter(is_active=True).order_by('id')
                hero_slides_data = [
                    {'title': s.title, 'description': s.description, 'button_text': s.button_text, 'button_url': s.button_url, 'image_url': s.image_url}
                    for s in hero_slides_qs
                ]
                update_data['hero_slides'] = hero_slides_data
            
            except Exception as e:
                logger.error(f"Error fetching hero slides for SSE: {e}", exc_info=True)
                update_data['error'] = 'Could not fetch hero slides.'
            
            try:
                yield f"data: {json.dumps(update_data)}\n\n".encode()
            except Exception:
                yield f"data: {json.dumps({'error': 'encoding error'})}\n\n".encode()

            # Wait 5 minutes (300 seconds) before next update
            time.sleep(300)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# ============================================================================
# SSE VIEW 3: Highest Vitality Collections
# URL: /stream-highest-vitality-collections/
# ============================================================================

def stream_highest_vitality_collections(request):
    """
    A dedicated SSE stream for the highest vitality collections carousel.
    """
    def event_stream():
        from nft_data.models import NFTCollection
        from analytics.models import AggregatedCollectionStats
        
        while True:
            update_data = {}
            try:
                vitality_collections_qs = NFTCollection.objects.filter(
                    is_listed=True
                ).select_related('vitality').order_by('-vitality__vitality_score')[:10]

                vitality_data = []
                stats_dict = {s.collection_id: s for s in AggregatedCollectionStats.objects.filter(collection__in=vitality_collections_qs)}

                # Get latest market stats for floor price and 24h volume
                from indexer.models import CollectionMarketStats
                market_stats_dict = {}
                for coll in vitality_collections_qs:
                    latest_market = CollectionMarketStats.objects.filter(
                        collection=coll
                    ).order_by('-timestamp').first()
                    if latest_market:
                        market_stats_dict[coll.pk] = latest_market

                for coll in vitality_collections_qs:
                    stat = stats_dict.get(coll.pk)
                    market_stat = market_stats_dict.get(coll.pk)

                    # Calculate market cap from floor_price * total_supply
                    floor_price = float(market_stat.floor_price) if market_stat and market_stat.floor_price else 0.0
                    total_supply = stat.total_supply if stat else (market_stat.total_supply if market_stat and hasattr(market_stat, 'total_supply') else (coll.total_supply if hasattr(coll, 'total_supply') else 0))
                    calculated_market_cap = floor_price * total_supply if floor_price and total_supply else 0.0

                    # Fallback to AggregatedCollectionStats market_cap if available
                    market_cap = calculated_market_cap if calculated_market_cap > 0 else (float(stat.market_cap) if stat and hasattr(stat, 'market_cap') and stat.market_cap else 0.0)

                    vitality_data.append({
                        'name': coll.display_name or coll.name,
                        'address': coll.address,
                        'image_url': coll.image_url,
                        'number_of_holders': stat.number_of_holders if stat else (market_stat.num_holders if market_stat else 0),
                        'total_supply': total_supply,
                        'listed_count': stat.listed_count if stat else (market_stat.num_listed if market_stat else 0),
                        'volume_24h': float(market_stat.volume_24h) if market_stat and market_stat.volume_24h else 0.0,
                        'floor_price': floor_price,
                        'market_cap': market_cap,
                        'price_change_24h': float(market_stat.price_change_24h) if market_stat and market_stat.price_change_24h else (float(stat.price_change_24h) if stat and stat.price_change_24h else 0.0),
                        'performance_score': float(coll.vitality.vitality_score) if hasattr(coll, 'vitality') and coll.vitality else (float(stat.performance_score) if stat and stat.performance_score else 50.0),
                    })
                update_data['highest_vitality_collections'] = vitality_data
            
            except Exception as e:
                logger.error(f"Error fetching highest vitality collections for SSE: {e}", exc_info=True)
                update_data['error'] = 'Could not fetch vitality collections.'

            try:
                yield f"data: {json.dumps(update_data)}\n\n".encode()
            except Exception:
                yield f"data: {json.dumps({'error': 'encoding error'})}\n\n".encode()

            # Wait 60 seconds before next update
            time.sleep(60)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response