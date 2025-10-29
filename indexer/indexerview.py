"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from traitkeeper.permissions import HasValidToken  # New custom permission
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django_ratelimit.decorators import ratelimit
from django.utils import timezone
from datetime import datetime, timedelta
from .models import CollectionMarketStats, NFTEvent, TraitEvent, FailedTransaction, TraitPerformanceScore
from nft_data.models import NFT, CollectionSweepEvent, HighProfileTransfer, NFTCollection, TopTrait, TraitType, TraitValue, Creator, TrendingTrait, WalletProminence
from .services import IndexerService
import logging
from asgiref.sync import async_to_sync
from django.db.models.functions import Now
from django.db.models import (
    Q, Count, Avg, Sum, Case, When, Value,
    CharField, IntegerField, FloatField, BooleanField, DateTimeField,
    ForeignKey, OneToOneField, ManyToManyField
)
import pandas as pd
from django.db.models import Subquery, OuterRef

logger = logging.getLogger(__name__)

class StandardResultsSetPagination(PageNumberPagination):
    """Pagination class for API views."""
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000

# Throttling classes for specific views
class HighTrafficThrottle(UserRateThrottle):
    rate = '200/hour'  # Stricter rate limit for high-traffic endpoints

class AnonHighTrafficThrottle(AnonRateThrottle):
    rate = '50/hour'

# Existing views (updated to use HasValidToken)
class CollectionMarketStatsView(APIView):
    """
    Get market stats for a specific collection.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Address of the collection', type=str, required=True),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'collection_address': {'type': 'string'},
                    'floor_price': {'type': 'number'},
                    'volume_24h': {'type': 'number'},
                    'average_price_24h': {'type': 'number'},
                    'velocity_24h': {'type': 'number'},
                    'performance_score': {'type': 'number'},
                    'total_volume': {'type': 'number'},
                    'total_supply': {'type': 'integer'},
                    'listed_count': {'type': 'integer'},
                    'timestamp': {'type': 'string', 'format': 'date-time'},
                }
            }
        }
    )
    def get(self, request, collection_address):
        try:
            stats = CollectionMarketStats.objects.filter(
                collection_address=collection_address
            ).order_by('-timestamp').first()
            if not stats:
                return Response({'error': 'No stats found'}, status=status.HTTP_404_NOT_FOUND)

            response_data = {
                'collection_address': stats.collection_address,
                'floor_price': float(stats.floor_price),
                'volume_24h': float(stats.volume_24h),
                'average_price_24h': float(stats.average_price_24h),
                'velocity_24h': float(stats.velocity_24h),
                'performance_score': float(stats.performance_score),
                'total_volume': float(stats.total_volume),
                'total_supply': stats.total_supply,
                'listed_count': stats.listed_count,
                'timestamp': stats.timestamp.isoformat()
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in CollectionMarketStatsView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class NFTEventView(APIView):
    """
    Get NFT events with optional filters.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str),
            OpenApiParameter(name='mint_address', description='Filter by NFT mint address', type=str),
            OpenApiParameter(name='event_type', description='Filter by event type (e.g., SALE, LISTING)', type=str),
            OpenApiParameter(name='start_time', description='Filter events after this timestamp (ISO format)', type=str),
            OpenApiParameter(name='end_time', description='Filter events before this timestamp (ISO format)', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'event_id': {'type': 'string'},
                                'event_type': {'type': 'string'},
                                'mint_address': {'type': 'string'},
                                'amount': {'type': 'number', 'nullable': True},
                                'buyer': {'type': 'string', 'nullable': True},
                                'seller': {'type': 'string', 'nullable': True},
                                'timestamp': {'type': 'string', 'format': 'date-time'},
                                'collection_address': {'type': 'string'},
                                'marketplace': {'type': 'string', 'nullable': True},
                                'trait_values': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'trait_type': {'type': 'string'},
                                            'value': {'type': 'string'}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')
            mint_address = request.query_params.get('mint_address')
            event_type = request.query_params.get('event_type')
            start_time = request.query_params.get('start_time')
            end_time = request.query_params.get('end_time')

            query = Q()
            if collection_address:
                query &= Q(collection_address=collection_address)
            if mint_address:
                query &= Q(mint_address=mint_address)
            if event_type:
                query &= Q(event_type__iexact=event_type)
            if start_time:
                try:
                    start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    query &= Q(timestamp__gte=start_time)
                except ValueError:
                    return Response(
                        {'error': 'Invalid start_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            if end_time:
                try:
                    end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    query &= Q(timestamp__lte=end_time)
                except ValueError:
                    return Response(
                        {'error': 'Invalid end_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            events = NFTEvent.objects.filter(query).select_related('collection').prefetch_related('trait_values').order_by('-timestamp')

            paginator = self.pagination_class()
            paginated_events = paginator.paginate_queryset(events, request)

            response_data = {
                'count': events.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'event_id': event.event_id,
                        'event_type': event.event_type,
                        'mint_address': event.mint_address,
                        'amount': float(event.amount) if event.amount else None,
                        'buyer': event.buyer,
                        'seller': event.seller,
                        'timestamp': event.timestamp.isoformat(),
                        'collection_address': event.collection_address,
                        'marketplace': event.marketplace,
                        'trait_values': [
                            {'trait_type': tv.trait_type.name, 'value': tv.value}
                            for tv in event.trait_values.all()
                        ]
                    }
                    for event in paginated_events
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in NFTEventView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TraitEventView(APIView):
    """
    Get trait events with optional filters.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str),
            OpenApiParameter(name='mint_address', description='Filter by NFT mint address', type=str),
            OpenApiParameter(name='action', description='Filter by action type (e.g., ADDED, UPDATED, REMOVED)', type=str),
            OpenApiParameter(name='start_time', description='Filter events after this timestamp (ISO format)', type=str),
            OpenApiParameter(name='end_time', description='Filter events before this timestamp (ISO format)', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'event_id': {'type': 'string'},
                                'action': {'type': 'string'},
                                'mint_address': {'type': 'string'},
                                'trait_type': {'type': 'string'},
                                'trait_value': {'type': 'string'},
                                'timestamp': {'type': 'string', 'format': 'date-time'},
                                'collection_address': {'type': 'string'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')
            mint_address = request.query_params.get('mint_address')
            action = request.query_params.get('action')  # e.g., ADDED, UPDATED, REMOVED
            start_time = request.query_params.get('start_time')
            end_time = request.query_params.get('end_time')

            query = Q()
            if collection_address:
                query &= Q(collection__address=collection_address)
            if mint_address:
                query &= Q(mint_address=mint_address)
            if action:
                query &= Q(action__iexact=action)
            if start_time:
                try:
                    start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    query &= Q(timestamp__gte=start_time)
                except ValueError:
                    return Response(
                        {'error': 'Invalid start_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            if end_time:
                try:
                    end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    query &= Q(timestamp__lte=end_time)
                except ValueError:
                    return Response(
                        {'error': 'Invalid end_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            events = TraitEvent.objects.filter(query).select_related(
                'collection', 'nft', 'trait_type', 'trait_value'
            ).order_by('-timestamp')

            paginator = self.pagination_class()
            paginated_events = paginator.paginate_queryset(events, request)

            response_data = {
                'count': events.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'event_id': event.event_id,
                        'action': event.action,
                        'mint_address': event.mint_address,
                        'trait_type': event.trait_type.name,
                        'trait_value': event.trait_value.value,
                        'timestamp': event.timestamp.isoformat(),
                        'collection_address': event.collection.address,
                    }
                    for event in paginated_events
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in TraitEventView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class NFTCollectionView(APIView):
    """
    Get NFT collections with optional filters.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='name', description='Filter by collection name (case-insensitive)', type=str),
            OpenApiParameter(name='creator_address', description='Filter by creator address', type=str),
            OpenApiParameter(name='is_featured', description='Filter by featured status (true/false)', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'address': {'type': 'string'},
                                'name': {'type': 'string'},
                                'symbol': {'type': 'string'},
                                'image_url': {'type': 'string'},
                                'description': {'type': 'string'},
                                'creator_address': {'type': 'string'},
                                'is_featured': {'type': 'boolean'},
                                'created_at': {'type': 'string', 'format': 'date-time'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            name = request.query_params.get('name')
            creator_address = request.query_params.get('creator_address')
            is_featured = request.query_params.get('is_featured')

            query = Q()
            if name:
                query &= Q(name__icontains=name)
            if creator_address:
                query &= Q(creator_address=creator_address)
            if is_featured is not None:
                query &= Q(is_featured=(is_featured.lower() == 'true'))

            collections = NFTCollection.objects.filter(query).order_by('-created_at')

            paginator = self.pagination_class()
            paginated_collections = paginator.paginate_queryset(collections, request)

            response_data = {
                'count': collections.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'address': coll.address,
                        'name': coll.name,
                        'symbol': coll.symbol,
                        'image_url': coll.image_url,
                        'description': coll.description,
                        'creator_address': coll.creator_address,
                        'is_featured': coll.is_featured,
                        'created_at': coll.created_at.isoformat()
                    }
                    for coll in paginated_collections
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in NFTCollectionView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TraitTypeView(APIView):
    """
    Get trait types with optional filters.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str),
            OpenApiParameter(name='name', description='Filter by trait type name (case-insensitive)', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'id': {'type': 'integer'},
                                'name': {'type': 'string'},
                                'collection_address': {'type': 'string'},
                                'collection_name': {'type': 'string'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')
            name = request.query_params.get('name')

            query = Q()
            if collection_address:
                query &= Q(collection__address=collection_address)
            if name:
                query &= Q(name__icontains=name)

            trait_types = TraitType.objects.filter(query).select_related('collection').order_by('name')

            paginator = self.pagination_class()
            paginated_trait_types = paginator.paginate_queryset(trait_types, request)

            response_data = {
                'count': trait_types.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'id': tt.id,
                        'name': tt.name,
                        'collection_address': tt.collection.address,
                        'collection_name': tt.collection.name
                    }
                    for tt in paginated_trait_types
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in TraitTypeView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TraitValueView(APIView):
    """
    Get trait values with optional filters.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str),
            OpenApiParameter(name='trait_type', description='Filter by trait type name (case-insensitive)', type=str),
            OpenApiParameter(name='value', description='Filter by trait value (case-insensitive)', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'id': {'type': 'integer'},
                                'trait_type': {'type': 'string'},
                                'value': {'type': 'string'},
                                'rarity': {'type': 'number'},
                                'count': {'type': 'integer'},
                                'collection_address': {'type': 'string'},
                                'collection_name': {'type': 'string'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')
            trait_type = request.query_params.get('trait_type')
            value = request.query_params.get('value')

            query = Q()
            if collection_address:
                query &= Q(trait_type__collection__address=collection_address)
            if trait_type:
                query &= Q(trait_type__name__iexact=trait_type)
            if value:
                query &= Q(value__icontains=value)

            trait_values = TraitValue.objects.filter(query).select_related('trait_type', 'trait_type__collection').order_by('value')

            paginator = self.pagination_class()
            paginated_trait_values = paginator.paginate_queryset(trait_values, request)

            response_data = {
                'count': trait_values.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'id': tv.id,
                        'trait_type': tv.trait_type.name,
                        'value': tv.value,
                        'rarity': float(tv.rarity),
                        'count': tv.count,
                        'collection_address': tv.trait_type.collection.address,
                        'collection_name': tv.trait_type.collection.name
                    }
                    for tv in paginated_trait_values
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in TraitValueView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TraitFilteredEventView(APIView):
    """
    Get NFT events filtered by traits for a specific collection.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Address of the collection', type=str, required=True),
            OpenApiParameter(name='trait_type', description='Filter by trait type name', type=str),
            OpenApiParameter(name='trait_value', description='Filter by trait value', type=str),
            OpenApiParameter(name='event_type', description='Filter by event type (e.g., SALE, LISTING)', type=str),
            OpenApiParameter(name='start_time', description='Filter events after this timestamp (ISO format)', type=str),
            OpenApiParameter(name='end_time', description='Filter events before this timestamp (ISO format)', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'event_id': {'type': 'string'},
                                'event_type': {'type': 'string'},
                                'mint_address': {'type': 'string'},
                                'amount': {'type': 'number', 'nullable': True},
                                'buyer': {'type': 'string', 'nullable': True},
                                'seller': {'type': 'string', 'nullable': True},
                                'timestamp': {'type': 'string', 'format': 'date-time'},
                                'collection_address': {'type': 'string'},
                                'marketplace': {'type': 'string', 'nullable': True},
                                'trait_values': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'trait_type': {'type': 'string'},
                                            'value': {'type': 'string'}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request, collection_address):
        try:
            # Get query parameters
            trait_type = request.query_params.get('trait_type')
            trait_value = request.query_params.get('trait_value')
            event_type = request.query_params.get('event_type')
            start_time = request.query_params.get('start_time')
            end_time = request.query_params.get('end_time')

            # Build base query
            query = Q(collection_address=collection_address)

            # Add trait filters if provided
            if trait_type or trait_value:
                trait_query = Q()
                if trait_type:
                    trait_query &= Q(trait_values__trait_type__name__iexact=trait_type)
                if trait_value:
                    trait_query &= Q(trait_values__value__iexact=trait_value)
                query &= trait_query

            # Add event type filter if provided
            if event_type:
                query &= Q(event_type__iexact=event_type)

            # Add time range filters if provided
            if start_time:
                try:
                    start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    query &= Q(timestamp__gte=start_time)
                except ValueError:
                    return Response(
                        {'error': 'Invalid start_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            if end_time:
                try:
                    end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    query &= Q(timestamp__lte=end_time)
                except ValueError:
                    return Response(
                        {'error': 'Invalid end_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Get events with related trait data
            events = NFTEvent.objects.filter(query).select_related(
                'collection'
            ).prefetch_related('trait_values').order_by('-timestamp')

            # Apply pagination
            paginator = self.pagination_class()
            paginated_events = paginator.paginate_queryset(events, request)

            # Format response
            response_data = {
                'count': events.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'event_id': event.event_id,
                        'event_type': event.event_type,
                        'mint_address': event.mint_address,
                        'amount': float(event.amount) if event.amount else None,
                        'buyer': event.buyer,
                        'seller': event.seller,
                        'timestamp': event.timestamp.isoformat(),
                        'collection_address': event.collection_address,
                        'marketplace': event.marketplace,
                        'trait_values': [
                            {'trait_type': tv.trait_type.name, 'value': tv.value}
                            for tv in event.trait_values.all()
                        ]
                    }
                    for event in paginated_events
                ]
            }

            return Response(response_data)

        except Exception as e:
            logger.error(f"Error in TraitFilteredEventView: {str(e)}")
            return Response(
                {'error': 'An error occurred while fetching trait-filtered events'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class TraitPerformanceView(APIView):
    """
    Get trait performance scores for a collection or trait.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str),
            OpenApiParameter(name='trait_type', description='Filter by trait type name', type=str),
            OpenApiParameter(name='trait_value', description='Filter by trait value', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'collection_address': {'type': 'string'},
                                'trait_type': {'type': 'string'},
                                'trait_value': {'type': 'string'},
                                'rarity_score': {'type': 'number'},
                                'avg_sale_price': {'type': 'number'},
                                'performance_score': {'type': 'number'},
                                'timestamp': {'type': 'string', 'format': 'date-time'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')
            trait_type = request.query_params.get('trait_type')
            trait_value = request.query_params.get('trait_value')

            query = Q()
            if collection_address:
                query &= Q(collection__address=collection_address)
            if trait_type:
                query &= Q(trait_type__name__iexact=trait_type)
            if trait_value:
                query &= Q(trait_value__value__iexact=trait_value)

            scores = TraitPerformanceScore.objects.filter(query).select_related(
                'collection', 'trait_type', 'trait_value'
            ).order_by('-performance_score')

            paginator = self.pagination_class()
            paginated_scores = paginator.paginate_queryset(scores, request)

            response_data = {
                'count': scores.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'collection_address': score.collection.address,
                        'trait_type': score.trait_type.name,
                        'trait_value': score.trait_value.value,
                        'rarity_score': float(score.rarity_score),
                        'avg_sale_price': float(score.avg_sale_price),
                        'performance_score': float(score.performance_score),
                        'timestamp': score.updated_at.isoformat()
                    }
                    for score in paginated_scores
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in TraitPerformanceView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TrendingTraitsView(APIView):
    """
    Get trending traits.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'trait_type': {'type': 'string'},
                                'trait_value': {'type': 'string'},
                                'count': {'type': 'integer'},
                                'trend_score': {'type': 'number'},
                                'previous_count': {'type': 'integer'},
                                'updated_at': {'type': 'string', 'format': 'date-time'},
                                'collection_address': {'type': 'string'},
                                'collection_name': {'type': 'string'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')

            query = Q()
            if collection_address:
                query &= Q(trait_type__collection__address=collection_address)

            traits = TrendingTrait.objects.filter(query).select_related(
                'trait_type', 'trait_value', 'trait_type__collection'
            ).order_by('-trend_score')

            paginator = self.pagination_class()
            paginated_traits = paginator.paginate_queryset(traits, request)

            response_data = {
                'count': traits.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'trait_type': trait.trait_type.name,
                        'trait_value': trait.trait_value.value,
                        'count': trait.count,
                        'trend_score': float(trait.trend_score),
                        'previous_count': trait.previous_count,
                        'updated_at': trait.updated_at.isoformat(),
                        'collection_address': trait.trait_type.collection.address,
                        'collection_name': trait.trait_type.collection.name
                    }
                    for trait in paginated_traits
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in TrendingTraitsView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TopTraitsView(APIView):
    """
    Get top traits based on combined score.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'trait_type': {'type': 'string'},
                                'trait_value': {'type': 'string'},
                                'rarity_score': {'type': 'number'},
                                'volume_score': {'type': 'number'},
                                'count_score': {'type': 'number'},
                                'combined_score': {'type': 'number'},
                                'collection_address': {'type': 'string'},
                                'collection_name': {'type': 'string'},
                                'updated_at': {'type': 'string', 'format': 'date-time'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')

            query = Q()
            if collection_address:
                query &= Q(collection__address=collection_address)

            traits = TopTrait.objects.filter(query).select_related(
                'trait_type', 'trait_value', 'collection'
            ).order_by('-combined_score')

            paginator = self.pagination_class()
            paginated_traits = paginator.paginate_queryset(traits, request)

            response_data = {
                'count': traits.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'trait_type': trait.trait_type.name,
                        'trait_value': trait.trait_value.value,
                        'rarity_score': float(trait.rarity_score),
                        'volume_score': float(trait.volume_score),
                        'count_score': float(trait.count_score),
                        'combined_score': float(trait.combined_score),
                        'collection_address': trait.collection.address,
                        'collection_name': trait.collection.name,
                        'updated_at': trait.updated_at.isoformat()
                    }
                    for trait in paginated_traits
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in TopTraitsView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class HighProfileTransfersView(APIView):
    """
    Get high-profile transfers.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'event_id': {'type': 'string'},
                                'buyer': {'type': 'string'},
                                'seller': {'type': 'string'},
                                'mint_address': {'type': 'string'},
                                'price': {'type': 'number'},
                                'collection_address': {'type': 'string'},
                                'collection_name': {'type': 'string'},
                                'image_url': {'type': 'string'},
                                'traits': {'type': 'object'},
                                'high_profile_score': {'type': 'number'},
                                'updated_at': {'type': 'string', 'format': 'date-time'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')

            query = Q()
            if collection_address:
                query &= Q(event__collection__address=collection_address)

            transfers = HighProfileTransfer.objects.filter(query).select_related(
                'event', 'event__collection'
            ).order_by('rank')

            paginator = self.pagination_class()
            paginated_transfers = paginator.paginate_queryset(transfers, request)

            response_data = {
                'count': transfers.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'event_id': transfer.event.event_id,
                        'buyer': transfer.event.buyer,
                        'seller': transfer.event.seller,
                        'mint_address': transfer.event.mint_address,
                        'price': float(transfer.event.amount) if transfer.event.amount else 0.0,
                        'collection_address': transfer.event.collection.address,
                        'collection_name': transfer.event.collection.name,
                        'image_url': transfer.image_url,
                        'traits': transfer.traits,
                        'high_profile_score': float(transfer.high_profile_score),
                        'updated_at': transfer.updated_at.isoformat()
                    }
                    for transfer in paginated_transfers
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in HighProfileTransfersView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CollectionSweepsView(APIView):
    """
    Get collection sweeps.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str),
            OpenApiParameter(name='min_significance', description='Filter by minimum significance score', type=float),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'rank': {'type': 'integer'},
                                'collection_address': {'type': 'string'},
                                'collection_name': {'type': 'string'},
                                'buyer_address': {'type': 'string'},
                                'start_time': {'type': 'string', 'format': 'date-time'},
                                'end_time': {'type': 'string', 'format': 'date-time'},
                                'duration_minutes': {'type': 'number'},
                                'num_items': {'type': 'integer'},
                                'total_volume': {'type': 'number'},
                                'average_price': {'type': 'number'},
                                'pre_sweep_floor': {'type': 'number'},
                                'post_sweep_floor': {'type': 'number'},
                                'price_movement': {'type': 'number'},
                                'target_traits': {'type': 'object'},
                                'significance_score': {'type': 'number'},
                                'created_at': {'type': 'string', 'format': 'date-time'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')
            min_significance = float(request.query_params.get('min_significance', 0))

            query = Q()
            if collection_address:
                query &= Q(collection__address=collection_address)
            if min_significance:
                query &= Q(significance_score__gte=min_significance)

            sweeps = CollectionSweepEvent.objects.filter(query).select_related('collection').order_by('rank')

            paginator = self.pagination_class()
            paginated_sweeps = paginator.paginate_queryset(sweeps, request)

            response_data = {
                'count': sweeps.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'rank': sweep.rank,
                        'collection_address': sweep.collection.address,
                        'collection_name': sweep.collection.name,
                        'buyer_address': sweep.buyer_address,
                        'start_time': sweep.start_time.isoformat(),
                        'end_time': sweep.end_time.isoformat(),
                        'duration_minutes': float(sweep.duration_minutes),
                        'num_items': sweep.num_items,
                        'total_volume': float(sweep.total_volume),
                        'average_price': float(sweep.average_price),
                        'pre_sweep_floor': float(sweep.pre_sweep_floor),
                        'post_sweep_floor': float(sweep.post_sweep_floor),
                        'price_movement': float(sweep.price_movement),
                        'target_traits': sweep.target_traits,
                        'significance_score': float(sweep.significance_score),
                        'created_at': sweep.created_at.isoformat()
                    }
                    for sweep in paginated_sweeps
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in CollectionSweepsView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class WalletProminenceView(APIView):
    """
    Get wallet prominence scores.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='address', description='Filter by wallet address', type=str),
            OpenApiParameter(name='min_score', description='Filter by minimum prominence score', type=float),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'address': {'type': 'string'},
                                'transaction_count': {'type': 'integer'},
                                'transaction_volume': {'type': 'number'},
                                'collections_count': {'type': 'integer'},
                                'high_value_transactions': {'type': 'integer'},
                                'prominence_score': {'type': 'number'},
                                'last_updated': {'type': 'string', 'format': 'date-time'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            address = request.query_params.get('address')
            min_score = float(request.query_params.get('min_score', 0))

            query = Q()
            if address:
                query &= Q(address=address)
            if min_score:
                query &= Q(prominence_score__gte=min_score)

            wallets = WalletProminence.objects.filter(query).order_by('-prominence_score')

            paginator = self.pagination_class()
            paginated_wallets = paginator.paginate_queryset(wallets, request)

            response_data = {
                'count': wallets.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'address': wallet.address,
                        'transaction_count': wallet.transaction_count,
                        'transaction_volume': float(wallet.transaction_volume),
                        'collections_count': wallet.collections_count,
                        'high_value_transactions': wallet.high_value_transactions,
                        'prominence_score': float(wallet.prominence_score),
                        'last_updated': wallet.last_updated.isoformat()
                    }
                    for wallet in paginated_wallets
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in WalletProminenceView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class WalletEventView(APIView):
    """
    Get events associated with a wallet address.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='wallet_address', description='Wallet address to filter events (required)', type=str, required=True),
            OpenApiParameter(name='event_type', description='Filter by event type (e.g., SALE, LISTING)', type=str),
            OpenApiParameter(name='start_time', description='Filter events after this timestamp (ISO format)', type=str),
            OpenApiParameter(name='end_time', description='Filter events before this timestamp (ISO format)', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'event_id': {'type': 'string'},
                                'event_type': {'type': 'string'},
                                'mint_address': {'type': 'string'},
                                'amount': {'type': 'number', 'nullable': True},
                                'buyer': {'type': 'string', 'nullable': True},
                                'seller': {'type': 'string', 'nullable': True},
                                'timestamp': {'type': 'string', 'format': 'date-time'},
                                'collection_address': {'type': 'string'},
                                'marketplace': {'type': 'string', 'nullable': True},
                                'trait_values': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'trait_type': {'type': 'string'},
                                            'value': {'type': 'string'}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            wallet_address = request.query_params.get('wallet_address')
            event_type = request.query_params.get('event_type')
            start_time = request.query_params.get('start_time')
            end_time = request.query_params.get('end_time')

            if not wallet_address:
                return Response(
                    {'error': 'wallet_address is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            query = Q(buyer=wallet_address) | Q(seller=wallet_address)
            if event_type:
                query &= Q(event_type__iexact=event_type)
            if start_time:
                try:
                    start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    query &= Q(timestamp__gte=start_time)
                except ValueError:
                    return Response(
                        {'error': 'Invalid start_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            if end_time:
                try:
                    end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    query &= Q(timestamp__lte=end_time)
                except ValueError:
                    return Response(
                        {'error': 'Invalid end_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            events = NFTEvent.objects.filter(query).select_related(
                'collection'
            ).prefetch_related('trait_values').order_by('-timestamp')

            paginator = self.pagination_class()
            paginated_events = paginator.paginate_queryset(events, request)

            response_data = {
                'count': events.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'event_id': event.event_id,
                        'event_type': event.event_type,
                        'mint_address': event.mint_address,
                        'amount': float(event.amount) if event.amount else None,
                        'buyer': event.buyer,
                        'seller': event.seller,
                        'timestamp': event.timestamp.isoformat(),
                        'collection_address': event.collection_address,
                        'marketplace': event.marketplace,
                        'trait_values': [
                            {'trait_type': tv.trait_type.name, 'value': tv.value}
                            for tv in event.trait_values.all()
                        ]
                    }
                    for event in paginated_events
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in WalletEventView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FailedTransactionView(APIView):
    """
    Get failed transactions with optional filters.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str),
            OpenApiParameter(name='provider_name', description='Filter by provider name', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'event_id': {'type': 'string'},
                                'collection_address': {'type': 'string'},
                                'event_data': {'type': 'object'},
                                'error_message': {'type': 'string'},
                                'provider_name': {'type': 'string'},
                                'signature': {'type': 'string'},
                                'created_at': {'type': 'string', 'format': 'date-time'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')
            provider_name = request.query_params.get('provider_name')

            query = Q()
            if collection_address:
                query &= Q(collection_address=collection_address)
            if provider_name:
                query &= Q(provider_name__iexact=provider_name)

            transactions = FailedTransaction.objects.filter(query).order_by('-created_at')

            paginator = self.pagination_class()
            paginated_transactions = paginator.paginate_queryset(transactions, request)

            response_data = {
                'count': transactions.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'event_id': tx.event_id,
                        'collection_address': tx.collection_address,
                        'event_data': tx.event_data,
                        'error_message': tx.error_message,
                        'provider_name': tx.provider_name,
                        'signature': tx.signature,
                        'created_at': tx.created_at.isoformat()
                    }
                    for tx in paginated_transactions
                ]
            }
            return Response(response_data)
        except Exception as e:
            logger.error(f"Error in FailedTransactionView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class DynamicNFTEventView(APIView):
    """
    Fetch and process NFT events dynamically based on user input using IndexerService.
    Requires a valid token and the associated email in the X-Email header.
    For POST requests, the email can also be included in the request body.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [HighTrafficThrottle, AnonHighTrafficThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            # Added to document the X-Email header requirement
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        request={
            'type': 'object',
            'properties': {
                'type': {
                    'type': 'string',
                    'description': 'Type of input (e.g., mint_address, collection_name, trait_type)',
                    'enum': ['mint_address', 'collection_name', 'trait_type']
                },
                'value': {
                    'type': 'string',
                    'description': 'Value to filter by (e.g., a specific mint address or trait type name)'
                },
                'trait_value': {
                    'type': 'string',
                    'description': 'Trait value to filter by (required if type is trait_type)',
                    'nullable': True
                },
                'event_type': {
                    'type': 'string',
                    'description': 'Filter by event type (e.g., SALE, LISTING)',
                    'nullable': True
                },
                # Optionally allow email in the request body for POST requests
                'email': {
                    'type': 'string',
                    'description': 'Email associated with the token (optional in body if X-Email header is provided)',
                    'nullable': True
                },
            },
            'required': ['type', 'value']
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'event_id': {'type': 'string'},
                                'event_type': {'type': 'string'},
                                'mint_address': {'type': 'string'},
                                'amount': {'type': 'number', 'nullable': True},
                                'buyer': {'type': 'string', 'nullable': True},
                                'seller': {'type': 'string', 'nullable': True},
                                'timestamp': {'type': 'string', 'format': 'date-time'},
                                'collection_address': {'type': 'string'},
                                'marketplace': {'type': 'string', 'nullable': True},
                                'trait_values': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'trait_type': {'type': 'string'},
                                            'value': {'type': 'string'}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    )
    def post(self, request):
        """
        Fetch and process NFT events dynamically based on user input.
        
        Request Body:
        - type: Type of input (e.g., 'mint_address', 'collection_name', 'trait_type')
        - value: Value to filter by (e.g., a specific mint address or trait value)
        - additional params: Optional additional filters (e.g., trait_value if type is trait_type)

        Example:
        {
            "type": "mint_address",
            "value": "some_mint_address"
        }
        """
        try:
            # Expect input_data in the format: {'type': 'mint_address', 'value': 'some_address'}
            input_data = request.data
            if not isinstance(input_data, dict) or 'type' not in input_data or 'value' not in input_data:
                return Response(
                    {'error': 'Invalid input. Expected format: {"type": "mint_address", "value": "some_address"}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            service = IndexerService()
            # Call the async method synchronously
            events = async_to_sync(service.process_dynamic_nft_events)(input_data)

            # Apply pagination
            paginator = self.pagination_class()
            paginated_events = paginator.paginate_queryset(events, request)

            # Serialize the events for the response
            response_data = {
                'count': len(events),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'event_id': event.event_id,
                        'event_type': event.event_type,
                        'mint_address': event.mint_address,
                        'amount': float(event.amount) if event.amount else None,
                        'buyer': event.buyer,
                        'seller': event.seller,
                        'timestamp': event.timestamp.isoformat(),
                        'collection_address': event.collection_address,
                        'marketplace': event.marketplace,
                        'trait_values': [
                            {'trait_type': tv.trait_type.name, 'value': tv.value}
                            for tv in event.trait_values.all()
                        ]
                    }
                    for event in paginated_events
                ]
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in DynamicNFTEventView: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BatchEventView(APIView):
    """
    Process multiple event queries in batch.
    Requires a valid token and the associated email in the X-Email header.
    For POST requests, the email can also be included in the request body.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [HighTrafficThrottle, AnonHighTrafficThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        request={
            'type': 'object',
            'properties': {
                'queries': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'collection_address': {'type': 'string', 'nullable': True},
                            'trait_type': {'type': 'string', 'nullable': True},
                            'trait_value': {'type': 'string', 'nullable': True},
                            'creator_name': {'type': 'string', 'nullable': True},
                            'event_type': {'type': 'string', 'nullable': True}
                        }
                    }
                },
                'email': {
                    'type': 'string',
                    'description': 'Email associated with the token (optional in body if X-Email header is provided)',
                    'nullable': True
                },
            },
            'required': ['queries']
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'query': {'type': 'object'},
                                'count': {'type': 'integer'},
                                'next': {'type': 'string', 'nullable': True},
                                'previous': {'type': 'string', 'nullable': True},
                                'events': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'event_id': {'type': 'string'},
                                            'event_type': {'type': 'string'},
                                            'mint_address': {'type': 'string'},
                                            'amount': {'type': 'number', 'nullable': True},
                                            'buyer': {'type': 'string', 'nullable': True},
                                            'seller': {'type': 'string', 'nullable': True},
                                            'timestamp': {'type': 'string', 'format': 'date-time'},
                                            'collection_address': {'type': 'string'},
                                            'marketplace': {'type': 'string', 'nullable': True},
                                            'trait_values': {
                                                'type': 'array',
                                                'items': {
                                                    'type': 'object',
                                                    'properties': {
                                                        'trait_type': {'type': 'string'},
                                                        'value': {'type': 'string'}
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    )
    def post(self, request):
        try:
            queries = request.data.get('queries', [])
            results = []
            for query in queries:
                q = Q()
                if query.get('collection_address'):
                    q &= Q(collection_address=query['collection_address'])
                if query.get('trait_type') or query.get('trait_value'):
                    trait_query = Q()
                    if query.get('trait_type'):
                        trait_query &= Q(trait_values__trait_type__name__iexact=query['trait_type'])
                    if query.get('trait_value'):
                        trait_query &= Q(trait_values__value__iexact=query['trait_value'])
                    q &= trait_query
                if query.get('creator_name'):
                    creators = Creator.objects.filter(name__iexact=query['creator_name'])
                    q &= Q(nft__creators__in=creators)
                if query.get('event_type'):
                    q &= Q(event_type__iexact=query['event_type'])

                events = NFTEvent.objects.filter(q).select_related('collection').prefetch_related('trait_values')
                paginator = self.pagination_class()
                paginated_events = paginator.paginate_queryset(events, request)

                results.append({
                    'query': query,
                    'count': events.count(),
                    'next': paginator.get_next_link(),
                    'previous': paginator.get_previous_link(),
                    'events': [
                        {
                            'event_id': event.event_id,
                            'event_type': event.event_type,
                            'mint_address': event.mint_address,
                            'amount': float(event.amount) if event.amount else None,
                            'buyer': event.buyer,
                            'seller': event.seller,
                            'timestamp': event.timestamp.isoformat(),
                            'collection_address': event.collection_address,
                            'marketplace': event.marketplace,
                            'trait_values': [
                                {'trait_type': tv.trait_type.name, 'value': tv.value}
                                for tv in event.trait_values.all()
                            ]
                        }
                        for event in paginated_events
                    ]
                })
            return Response({'results': results})
        except Exception as e:
            logger.error(f"Error in BatchEventView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class HistoricalTrendView(APIView):
    """
    Get historical trends for a collection (e.g., volume, sales, floor price over time).
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Collection address to analyze', type=str, required=True),
            OpenApiParameter(name='start_time', description='Start timestamp for trend analysis (ISO format)', type=str, required=True),
            OpenApiParameter(name='end_time', description='End timestamp for trend analysis (ISO format)', type=str, required=True),
            OpenApiParameter(name='interval', description='Time interval for aggregation (e.g., hourly, daily)', type=str, enum=['hourly', 'daily'], default='daily'),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'collection_address': {'type': 'string'},
                    'trends': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'timestamp': {'type': 'string', 'format': 'date-time'},
                                'volume': {'type': 'number'},
                                'sales_count': {'type': 'integer'},
                                'floor_price': {'type': 'number'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        """
        Fetch historical trends for a specified collection within a given time range.
        Aggregates data by the specified interval (hourly or daily).

        Parameters:
        - collection_address: The address of the collection to analyze.
        - start_time: The start timestamp for the trend analysis in ISO format.
        - end_time: The end timestamp for the trend analysis in ISO format.
        - interval: The aggregation interval ('hourly' or 'daily').

        Returns:
        - A JSON object containing the collection address and a list of trend data points.
        """
        try:
            # Extract query parameters
            collection_address = request.query_params.get('collection_address')
            start_time = request.query_params.get('start_time')
            end_time = request.query_params.get('end_time')
            interval = request.query_params.get('interval', 'daily')

            # Validate required parameters
            if not all([collection_address, start_time, end_time]):
                return Response(
                    {'error': 'collection_address, start_time, and end_time are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Parse timestamps
            try:
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            except ValueError:
                return Response(
                    {'error': 'Invalid timestamp format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate time range
            if start_time >= end_time:
                return Response(
                    {'error': 'start_time must be earlier than end_time'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Fetch events and stats within the time range
            events = NFTEvent.objects.filter(
                collection_address=collection_address,
                event_type='SALE',
                timestamp__gte=start_time,
                timestamp__lte=end_time
            ).values('timestamp', 'amount')

            stats = CollectionMarketStats.objects.filter(
                collection_address=collection_address,
                timestamp__gte=start_time,
                timestamp__lte=end_time
            ).values('timestamp', 'floor_price')

            # Convert to pandas DataFrames for easier aggregation
            events_df = pd.DataFrame(list(events))
            stats_df = pd.DataFrame(list(stats))

            # Handle empty data case
            if events_df.empty and stats_df.empty:
                return Response({
                    'collection_address': collection_address,
                    'trends': []
                })

            # Set timestamp as index for events DataFrame
            if not events_df.empty:
                events_df['timestamp'] = pd.to_datetime(events_df['timestamp'])
                events_df.set_index('timestamp', inplace=True)
            else:
                # Create an empty DataFrame with the date range if no events
                events_df = pd.DataFrame(index=pd.date_range(start=start_time, end=end_time, freq='H'))

            # Set timestamp as index for stats DataFrame
            if not stats_df.empty:
                stats_df['timestamp'] = pd.to_datetime(stats_df['timestamp'])
                stats_df.set_index('timestamp', inplace=True)
            else:
                # Create an empty DataFrame with the date range if no stats
                stats_df = pd.DataFrame(index=pd.date_range(start=start_time, end=end_time, freq='H'))

            # Resample based on interval
            freq = 'D' if interval == 'daily' else 'H'

            # Resample events to calculate volume and sales count
            volume = events_df['amount'].resample(freq).sum().fillna(0) if 'amount' in events_df else pd.Series(0, index=pd.date_range(start=start_time, end=end_time, freq=freq))
            sales_count = events_df['amount'].resample(freq).count() if 'amount' in events_df else pd.Series(0, index=pd.date_range(start=start_time, end=end_time, freq=freq))

            # Resample stats to get floor price
            floor_price = stats_df['floor_price'].resample(freq).mean().fillna(method='ffill') if 'floor_price' in stats_df else pd.Series(0, index=pd.date_range(start=start_time, end=end_time, freq=freq))

            # Combine into trends
            trends = []
            for timestamp in pd.date_range(start=start_time, end=end_time, freq=freq):
                ts = timestamp.to_pydatetime().replace(tzinfo=timezone.utc)
                trends.append({
                    'timestamp': ts.isoformat(),
                    'volume': float(volume.get(ts, 0)),
                    'sales_count': int(sales_count.get(ts, 0)),
                    'floor_price': float(floor_price.get(ts, 0))
                })

            return Response({
                'collection_address': collection_address,
                'trends': trends
            })
        except Exception as e:
            logger.error(f"Error in HistoricalTrendView: {str(e)}")
            return Response({'error': 'An error occurred while fetching historical trends'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TraitAnalyticsView(APIView):
    """
    Get aggregated analytics for traits (e.g., average sale price, sales volume).
    Requires a valid token and the associated email in the X-Email header.
    Authentication:
    - Provide the token in the Authorization header as "Token <key>".
    - Provide the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str, required=True),
            OpenApiParameter(name='trait_type', description='Filter by trait type name (case-insensitive)', type=str),
            OpenApiParameter(name='trait_value', description='Filter by trait value (case-insensitive)', type=str),
            OpenApiParameter(name='start_time', description='Filter events after this timestamp (ISO format, e.g., 2024-03-20T00:00:00Z)', type=str),
            OpenApiParameter(name='end_time', description='Filter events before this timestamp (ISO format, e.g., 2024-03-20T00:00:00Z)', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the API token, must match the token\'s email (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'trait_type': {'type': 'string'},
                                'trait_value': {'type': 'string'},
                                'collection_address': {'type': 'string'},
                                'collection_name': {'type': 'string'},
                                'avg_sale_price': {'type': 'number'},
                                'total_volume': {'type': 'number'},
                                'sales_count': {'type': 'integer'},
                                'rarity': {'type': 'number'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
            try:
                collection_address = request.query_params.get('collection_address')
                trait_type = request.query_params.get('trait_type')
                trait_value = request.query_params.get('trait_value')
                start_time = request.query_params.get('start_time')
                end_time = request.query_params.get('end_time')

                if not collection_address:
                    return Response(
                        {'error': 'collection_address is required'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Build query for TraitValue objects
                query = Q(trait_type__collection__address=collection_address)
                if trait_type:
                    query &= Q(trait_type__name__iexact=trait_type)
                if trait_value:
                    query &= Q(value__iexact=trait_value)

                # Build event query for filtering sales
                event_query = Q(event_type='SALE', collection__address=collection_address)
                if start_time:
                    try:
                        start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                        event_query &= Q(timestamp__gte=start_time)
                    except ValueError:
                        return Response(
                            {'error': 'Invalid start_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                if end_time:
                    try:
                        end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                        event_query &= Q(timestamp__lte=end_time)
                    except ValueError:
                        return Response(
                            {'error': 'Invalid end_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                # Subquery to calculate aggregates for events associated with each TraitValue
                from django.db.models import Subquery, OuterRef
                events_subquery = NFTEvent.objects.filter(
                    event_query,
                    nft__trait_values=OuterRef('pk')
                )

                # Annotate TraitValue with aggregated analytics
                trait_values = TraitValue.objects.filter(query).select_related(
                    'trait_type', 'trait_type__collection'
                ).annotate(
                    avg_sale_price=Subquery(
                        events_subquery.values('amount').annotate(avg=Avg('amount')).values('avg')[:1],
                        output_field=FloatField()
                    ),
                    total_volume=Subquery(
                        events_subquery.values('amount').annotate(sum=Sum('amount')).values('sum')[:1],
                        output_field=FloatField()
                    ),
                    sales_count=Subquery(
                        events_subquery.values('id').annotate(count=Count('id')).values('count')[:1],
                        output_field=IntegerField()
                    )
                )

                results = []
                for tv in trait_values:
                    results.append({
                        'trait_type': tv.trait_type.name,
                        'trait_value': tv.value,
                        'collection_address': tv.trait_type.collection.address,
                        'collection_name': tv.trait_type.collection.name,
                        'avg_sale_price': float(tv.avg_sale_price or 0.0),
                        'total_volume': float(tv.total_volume or 0.0),
                        'sales_count': tv.sales_count or 0,
                        'rarity': float(tv.rarity)
                    })

                # Sort by total_volume descending
                results.sort(key=lambda x: x['total_volume'], reverse=True)

                # Apply pagination
                paginator = self.pagination_class()
                paginated_results = paginator.paginate_queryset(results, request)

                response_data = {
                    'count': len(results),
                    'next': paginator.get_next_link(),
                    'previous': paginator.get_previous_link(),
                    'results': paginated_results
                }
                return Response(response_data)
            except Exception as e:
                logger.error(f"Error in TraitAnalyticsView: {str(e)}")
                return Response({'error': 'An error occurred while fetching trait analytics'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RarityFilteredEventView(APIView):
    """
    Get NFT events filtered by rarity of the NFTs involved.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Filter by collection address', type=str, required=True),
            OpenApiParameter(name='min_rarity', description='Minimum rarity percentage (0-100)', type=float),
            OpenApiParameter(name='max_rarity', description='Maximum rarity percentage (0-100)', type=float),
            OpenApiParameter(name='event_type', description='Filter by event type (e.g., SALE, LISTING)', type=str),
            OpenApiParameter(name='start_time', description='Filter events after this timestamp (ISO format)', type=str),
            OpenApiParameter(name='end_time', description='Filter events before this timestamp (ISO format)', type=str),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'next': {'type': 'string', 'nullable': True},
                    'previous': {'type': 'string', 'nullable': True},
                    'results': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'event_id': {'type': 'string'},
                                'event_type': {'type': 'string'},
                                'mint_address': {'type': 'string'},
                                'amount': {'type': 'number', 'nullable': True},
                                'buyer': {'type': 'string', 'nullable': True},
                                'seller': {'type': 'string', 'nullable': True},
                                'timestamp': {'type': 'string', 'format': 'date-time'},
                                'collection_address': {'type': 'string'},
                                'marketplace': {'type': 'string', 'nullable': True},
                                'trait_values': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'trait_type': {'type': 'string'},
                                            'value': {'type': 'string'},
                                            'rarity': {'type': 'number'}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')
            min_rarity = request.query_params.get('min_rarity')
            max_rarity = request.query_params.get('max_rarity')
            event_type = request.query_params.get('event_type')
            start_time = request.query_params.get('start_time')
            end_time = request.query_params.get('end_time')

            if not collection_address:
                return Response(
                    {'error': 'collection_address is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Build base query
            query = Q(collection_address=collection_address)

            # Add rarity filters
            trait_values = TraitValue.objects.all()
            if min_rarity is not None:
                min_rarity = float(min_rarity)
                trait_values = trait_values.filter(rarity__gte=min_rarity)
            if max_rarity is not None:
                max_rarity = float(max_rarity)
                trait_values = trait_values.filter(rarity__lte=max_rarity)

            # Get NFTs with matching trait values
            nfts = NFT.objects.filter(
                trait_values__in=trait_values,
                collection__address=collection_address
            ).distinct()

            # Filter events by NFTs
            query &= Q(nft__in=nfts)

            # Add event type filter
            if event_type:
                query &= Q(event_type__iexact=event_type)

            # Add time range filters
            if start_time:
                try:
                    start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    query &= Q(timestamp__gte=start_time)
                except ValueError:
                    return Response(
                        {'error': 'Invalid start_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            if end_time:
                try:
                    end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    query &= Q(timestamp__lte=end_time)
                except ValueError:
                    return Response(
                        {'error': 'Invalid end_time format. Use ISO format (e.g., 2024-03-20T00:00:00Z)'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Fetch events
            events = NFTEvent.objects.filter(query).select_related(
                'collection', 'nft'
            ).prefetch_related('trait_values').order_by('-timestamp')

            # Apply pagination
            paginator = self.pagination_class()
            paginated_events = paginator.paginate_queryset(events, request)

            # Format response
            response_data = {
                'count': events.count(),
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': [
                    {
                        'event_id': event.event_id,
                        'event_type': event.event_type,
                        'mint_address': event.mint_address,
                        'amount': float(event.amount) if event.amount else None,
                        'buyer': event.buyer,
                        'seller': event.seller,
                        'timestamp': event.timestamp.isoformat(),
                        'collection_address': event.collection_address,
                        'marketplace': event.marketplace,
                        'trait_values': [
                            {
                                'trait_type': tv.trait_type.name,
                                'value': tv.value,
                                'rarity': float(tv.rarity)
                            }
                            for tv in event.trait_values.all()
                        ]
                    }
                    for event in paginated_events
                ]
            }

            return Response(response_data)

        except Exception as e:
            logger.error(f"Error in RarityFilteredEventView: {str(e)}")
            return Response(
                {'error': 'An error occurred while fetching rarity-filtered events'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CrossCollectionComparisonView(APIView):
    """
    Compare metrics across multiple collections.
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='collection_addresses',
                description='Comma-separated list of collection addresses to compare',
                type=str,
                required=True
            ),
            OpenApiParameter(
                name='metrics',
                description='Comma-separated list of metrics to compare (e.g., floor_price,volume_24h,total_volume)',
                type=str,
                default='floor_price,volume_24h,total_volume'
            ),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'comparisons': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'collection_address': {'type': 'string'},
                                'collection_name': {'type': 'string'},
                                'metrics': {'type': 'object'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_addresses = request.query_params.get('collection_addresses')
            metrics = request.query_params.get('metrics', 'floor_price,volume_24h,total_volume')

            if not collection_addresses:
                return Response(
                    {'error': 'collection_addresses is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            collection_addresses = collection_addresses.split(',')
            metrics = metrics.split(',')

            valid_metrics = {'floor_price', 'volume_24h', 'total_volume', 'total_supply', 'listed_count', 'performance_score'}
            metrics = [metric for metric in metrics if metric in valid_metrics]
            if not metrics:
                return Response(
                    {'error': f'Invalid metrics. Valid options are: {", ".join(valid_metrics)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            comparisons = []
            for address in collection_addresses:
                stats = CollectionMarketStats.objects.filter(
                    collection_address=address
                ).order_by('-timestamp').first()

                if not stats:
                    continue

                collection = NFTCollection.objects.filter(address=address).first()
                collection_name = collection.name if collection else "Unknown"

                metrics_data = {}
                for metric in metrics:
                    value = getattr(stats, metric, 0)
                    metrics_data[metric] = float(value) if metric != 'total_supply' else int(value)

                comparisons.append({
                    'collection_address': address,
                    'collection_name': collection_name,
                    'metrics': metrics_data
                })

            return Response({
                'comparisons': comparisons
            })
        except Exception as e:
            logger.error(f"Error in CrossCollectionComparisonView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class EventForecastView(APIView):
    """
    Predict future trends based on historical data (e.g., floor price prediction).
    Requires a valid token and the associated email in the X-Email header.
    """
    permission_classes = [HasValidToken]
    throttle_classes = [HighTrafficThrottle, AnonHighTrafficThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='collection_address', description='Collection address to forecast', type=str, required=True),
            OpenApiParameter(name='metric', description='Metric to forecast (e.g., floor_price, volume)', type=str, default='floor_price', enum=['floor_price', 'volume']),
            OpenApiParameter(name='days', description='Number of days to forecast into the future', type=int, default=7),
            OpenApiParameter(
                name='X-Email',
                description='Email associated with the token (required in header)',
                type=str,
                location='header',
                required=True
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'collection_address': {'type': 'string'},
                    'metric': {'type': 'string'},
                    'forecast': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'date': {'type': 'string', 'format': 'date'},
                                'value': {'type': 'number'}
                            }
                        }
                    }
                }
            }
        }
    )
    def get(self, request):
        try:
            collection_address = request.query_params.get('collection_address')
            metric = request.query_params.get('metric', 'floor_price')
            days = int(request.query_params.get('days', 7))

            if not collection_address:
                return Response(
                    {'error': 'collection_address is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if metric not in ['floor_price', 'volume']:
                return Response(
                    {'error': 'Invalid metric. Must be one of: floor_price, volume'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Fetch historical data (last 30 days)
            end_date = timezone.now()
            start_date = end_date - timedelta(days=30)

            if metric == 'floor_price':
                data = CollectionMarketStats.objects.filter(
                    collection_address=collection_address,
                    timestamp__gte=start_date,
                    timestamp__lte=end_date
                ).values('timestamp', 'floor_price').order_by('timestamp')
                df = pd.DataFrame(list(data))
                df['value'] = df['floor_price'].astype(float)
            else:  # volume
                data = NFTEvent.objects.filter(
                    collection_address=collection_address,
                    event_type='SALE',
                    timestamp__gte=start_date,
                    timestamp__lte=end_date
                ).values('timestamp', 'amount')
                df = pd.DataFrame(list(data))
                df['value'] = df['amount'].astype(float)

            if df.empty:
                return Response({
                    'collection_address': collection_address,
                    'metric': metric,
                    'forecast': []
                })

            # Prepare data for forecasting
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            daily_data = df['value'].resample('D').mean().fillna(0)

            # Simple moving average forecast (for demonstration; replace with a more sophisticated model in production)
            window = 7  # 7-day moving average
            forecast_values = daily_data.rolling(window=window, min_periods=1).mean()
            last_value = forecast_values[-1] if not forecast_values.empty else 0

            # Generate forecast for the next 'days'
            forecast = []
            current_date = end_date.date()
            for i in range(days):
                forecast_date = current_date + timedelta(days=i + 1)
                # Simple linear extrapolation based on the last value
                # In a production system, use a proper time-series model (e.g., ARIMA, Prophet)
                forecast_value = last_value * (1 + 0.01 * i)  # 1% daily growth assumption
                forecast.append({
                    'date': forecast_date.isoformat(),
                    'value': float(forecast_value)
                })

            return Response({
                'collection_address': collection_address,
                'metric': metric,
                'forecast': forecast
            })
        except Exception as e:
            logger.error(f"Error in EventForecastView: {str(e)}")
            return Response({'error': 'An error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            """