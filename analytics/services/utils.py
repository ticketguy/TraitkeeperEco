"""
Analytics Services Utilities

This module contains shared utility functions used across all analytics services.


Usage:
    from analytics.services.utils import (
        get_indexer_service,
        safe_decimal_conversion,
        get_metrics_cache,
        save_metrics_cache
    )
"""

import logging
import math
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from typing import Optional, Any, Dict, List

from django.utils import timezone
from django.core.cache import cache
from django.db.models import Q

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# SERVICE INITIALIZATION
# ============================================================================

_indexer_service_instance = None


def get_indexer_service():
    """
    Lazy load and return the IndexerService instance.
    
    This avoids circular import issues by only importing when needed.
    
    Returns:
        IndexerService: Singleton instance of the indexer service
    """
    global _indexer_service_instance
    
    if _indexer_service_instance is None:
        from indexer.services import IndexerService
        _indexer_service_instance = IndexerService()
        logger.debug("Initialized IndexerService instance")
    
    return _indexer_service_instance


# ============================================================================
# CACHE UTILITIES
# ============================================================================

async def get_metrics_cache(cache_key: str, cache_manager=None) -> Optional[Any]:
    """
    Get metrics from cache using cache manager with fallback to Django cache.
    
    Args:
        cache_key: The cache key to retrieve
        cache_manager: Optional CacheManager instance. If None, uses Django cache only.
    
    Returns:
        Cached data if found, None otherwise
    
    Example:
        >>> cached_metrics = await get_metrics_cache('collection:ABC123:metrics')
        >>> if cached_metrics:
        ...     logger.info("Cache hit!")
    """
    # Try cache manager first if available
    if cache_manager:
        try:
            cached_data = await cache_manager.get(cache_key)
            if cached_data is not None:
                logger.info(f"Metrics cache hit for {cache_key} (via cache manager)")
                return cached_data
        except Exception as e:
            logger.warning(f"Cache manager error for {cache_key}: {e}, falling back")
    
    # Fallback to Django cache
    try:
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"Metrics cache hit for {cache_key} (fallback)")
            return cached_data
    except Exception as e:
        logger.warning(f"Fallback cache error for {cache_key}: {e}")
    
    return None


async def save_metrics_cache(
    cache_key: str,
    data: Any,
    timeout: int = 3600,
    collection_address: Optional[str] = None,
    cache_manager=None
) -> bool:
    """
    Save metrics to cache using cache manager with fallback to Django cache.
    
    Args:
        cache_key: The cache key to store under
        data: The data to cache
        timeout: Cache TTL in seconds (default: 1 hour)
        collection_address: Optional collection address for cache invalidation
        cache_manager: Optional CacheManager instance
    
    Returns:
        True if cache was saved successfully, False otherwise
    
    Example:
        >>> metrics = {'floor_price': 5.5, 'volume': 1000}
        >>> await save_metrics_cache('collection:ABC:metrics', metrics, timeout=1800)
    """
    if not data:
        logger.warning(f"Attempted to cache empty data for {cache_key}")
        return False

    # Try cache manager first if available
    if cache_manager:
        try:
            from core.cache_manager import CacheType
            cache_type = CacheType.METRICS  # Metrics get their own TTL tier
            
            await cache_manager.set(
                cache_key,
                data,
                timeout=timeout,
                cache_type=cache_type,
                collection_address=collection_address
            )
            logger.debug(f"Cached metrics for {cache_key} (via cache manager, TTL: {timeout}s)")
            return True
        except Exception as e:
            logger.warning(f"Cache manager save error for {cache_key}: {e}, falling back")
    
    # Fallback to Django cache
    try:
        cache.set(cache_key, data, timeout)
        logger.debug(f"Cached metrics for {cache_key} (fallback, TTL: {timeout}s)")
        return True
    except Exception as e:
        logger.error(f"Failed to cache {cache_key}: {e}")
        return False


# ============================================================================
# DATA CONVERSION UTILITIES
# ============================================================================

def safe_decimal_conversion(value: Any, default: float = 0.0) -> Decimal:
    """
    Safely convert values to Decimal, handling edge cases like Infinity and NaN.
    
    This is critical for financial calculations where precision matters.
    
    Args:
        value: Value to convert (can be str, int, float, or None)
        default: Default value to return if conversion fails
    
    Returns:
        Decimal: Converted value or default
    
    Examples:
        >>> safe_decimal_conversion("5.5")
        Decimal('5.5')
        
        >>> safe_decimal_conversion("Infinity", default=0.0)
        Decimal('0.0')
        
        >>> safe_decimal_conversion(None, default=1.0)
        Decimal('1.0')
    """
    try:
        if value is None:
            return Decimal(str(default))
        
        # Handle string values
        if isinstance(value, str):
            if value.lower() in ['infinity', 'inf', '-infinity', '-inf', 'nan']:
                logger.warning(f"Invalid decimal value '{value}', using default {default}")
                return Decimal(str(default))
            return Decimal(value)
        
        # Handle numeric values
        if isinstance(value, (int, float)):
            if math.isinf(value) or math.isnan(value):
                logger.warning(f"Invalid numeric value {value}, using default {default}")
                return Decimal(str(default))
            return Decimal(str(value))
        
        # Handle Decimal values (pass through)
        if isinstance(value, Decimal):
            if value.is_infinite() or value.is_nan():
                logger.warning(f"Invalid Decimal value {value}, using default {default}")
                return Decimal(str(default))
            return value
        
        # Unknown type - use default
        logger.warning(f"Cannot convert {type(value)} to Decimal, using default {default}")
        return Decimal(str(default))
        
    except (InvalidOperation, ValueError, OverflowError) as e:
        logger.warning(f"Error converting {value} to Decimal: {e}, using default {default}")
        return Decimal(str(default))


# ============================================================================
# CONFIDENCE & QUALITY SCORING
# ============================================================================

def calculate_overall_confidence(
    successful_sources: List[Dict],
    source_attribution: Dict[str, Dict]
) -> float:
    """
    Calculate overall confidence in aggregated data based on source quality.
    
    Uses weighted average of field-specific confidence scores, with weights
    reflecting the importance of each metric for decision-making.
    
    Args:
        successful_sources: List of successful data sources
        source_attribution: Dict mapping fields to their source attribution
    
    Returns:
        float: Overall confidence score (0.0 to 1.0)
    
    Example:
        >>> attribution = {
        ...     'floor_price': {'confidence': 0.9},
        ...     'volume_24h': {'confidence': 0.85}
        ... }
        >>> calculate_overall_confidence(sources, attribution)
        0.875
    """
    if not source_attribution:
        return 0.0
    
    # Field importance weights (must sum to 1.0)
    field_weights = {
        'floor_price': 0.30,        # Most important - affects all valuations
        'volume_24h': 0.20,          # Market activity indicator
        'listed_count': 0.20,        # Supply-side metric
        'total_supply': 0.15,        # Collection size
        'highest_bid': 0.05,         # Demand indicator
        'price_change_24h': 0.05,    # Momentum indicator
        'bid_count': 0.05            # Market depth
    }
    
    weighted_confidence = 0.0
    total_weight = 0.0
    
    for field, weight in field_weights.items():
        if field in source_attribution:
            confidence = source_attribution[field].get('confidence', 0.0)
            weighted_confidence += confidence * weight
            total_weight += weight
    
    return weighted_confidence / total_weight if total_weight > 0 else 0.0


def get_calculated_metrics_attribution(
    calculated_changes: Dict,
    derived_metrics: Dict,
    analytics_metrics: Dict
) -> Dict[str, Dict]:
    """
    Create source attribution for calculated metrics.
    
    This helps track which metrics are calculated vs. sourced from APIs,
    and assigns appropriate confidence levels to each type.
    
    Args:
        calculated_changes: Historical change metrics
        derived_metrics: Mathematically derived metrics
        analytics_metrics: Advanced analytics scores
    
    Returns:
        Dict mapping metric names to attribution info
    
    Example:
        >>> attribution = get_calculated_metrics_attribution(
        ...     {'price_change_7d': 15.5},
        ...     {'market_cap': 50000},
        ...     {'efficiency_score': 0.85}
        ... )
        >>> attribution['price_change_7d']['confidence']
        0.9
    """
    attribution = {}
    
    # Historical change metrics - highest confidence (our own calculations)
    for metric in calculated_changes.keys():
        attribution[metric] = {
            'source': 'calculated_from_historical_data',
            'method': 'percentage_change_calculation',
            'confidence': 0.9  # High confidence - we control the calculation
        }
    
    # Derived metrics - slightly lower confidence (depends on input quality)
    for metric in derived_metrics.keys():
        attribution[metric] = {
            'source': 'calculated_from_aggregated_data',
            'method': 'mathematical_derivation',
            'confidence': 0.85  # Depends on quality of aggregated data
        }
    
    # Analytics metrics - lowest confidence (complex algorithms)
    for metric in analytics_metrics.keys():
        attribution[metric] = {
            'source': 'calculated_analytics_engine',
            'method': 'weighted_scoring_algorithm',
            'confidence': 0.8  # Complex scoring with more assumptions
        }
    
    return attribution


# ============================================================================
# RESULT TEMPLATES
# ============================================================================

def empty_aggregated_result() -> Dict:
    """
    Return an empty aggregated result template.
    
    Used when all data sources fail to provide any valid data.
    
    Returns:
        Dict with empty result structure
    
    Example:
        >>> result = empty_aggregated_result()
        >>> result['success']
        False
    """
    return {
        'source': 'aggregated',
        'success': False,
        'data': {},
        'metadata': {
            'error': 'No successful sources available',
            'aggregated_at': timezone.now(),
            'overall_confidence': 0.0
        }
    }


# ============================================================================
# NOTIFICATION UTILITIES
# ============================================================================

def send_notification(
    user_ids: List[int],
    event_type: str,
    message: str,
    data: Optional[Dict] = None
) -> bool:
    """
    Send notifications to specified users.
    
    This is a simplified implementation. In production, this should:
    - Queue notifications for async processing
    - Handle different notification channels (email, push, in-app)
    - Respect user notification preferences
    
    Args:
        user_ids: List of user IDs to notify
        event_type: Type of event (e.g., 'wallet_activity', 'price_alert')
        message: Notification message text
        data: Optional additional data payload
    
    Returns:
        bool: True if notifications were queued successfully
    
    Example:
        >>> send_notification(
        ...     user_ids=[1, 2, 3],
        ...     event_type='sweep_detected',
        ...     message='Collection sweep detected!',
        ...     data={'collection': 'ABC123', 'count': 15}
        ... )
    """
    try:
        logger.debug(
            f"Sending {event_type} notification to {len(user_ids)} users: {message}"
        )
        
        # TODO: Implement actual notification system
        # This could use:
        # - Django signals
        # - Celery tasks
        # - Message queue (RabbitMQ, Redis)
        # - Third-party services (SendGrid, Twilio)
        
        return True
        
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
        return False


# ============================================================================
# ANALYTICS SUMMARY
# ============================================================================

def get_analytics_summary() -> Dict:
    """
    Get summary statistics for all calculated analytics.
    
    Useful for monitoring, debugging, and displaying system health metrics.
    
    Returns:
        Dict containing counts and top performers across all analytics
    
    Example:
        >>> summary = get_analytics_summary()
        >>> print(f"Total trending traits: {summary['trending_traits']}")
        >>> print(f"Recent sweeps: {summary['recent_sweeps_7d']}")
    """
    try:
        from nft_data.models import (

            NFTCollection
        )

        
        # Try to import optional models 
        try:
            from analytics.models import (
                HighProfileTransfer,
                CollectionSweepEvent,
                WalletProminence,
                TraitPerformanceScore,
                TrendingTrait,
                TopTrait,
            )
            has_optional_models = True
        except ImportError:
            has_optional_models = False
            logger.warning("Some analytics models not available for summary")
        
        summary = {
            'trending_traits': TrendingTrait.objects.count(),
            'top_traits': TopTrait.objects.count(),
            'trait_performance_scores': TraitPerformanceScore.objects.count(),
            'featured_collections': NFTCollection.objects.filter(is_featured=True).count(),
            'last_calculated': timezone.now(),
        }
        
        # Add optional model counts if available
        if has_optional_models:
            summary.update({
                'high_profile_transfers': HighProfileTransfer.objects.count(),
                'collection_sweeps': CollectionSweepEvent.objects.count(),
                'wallet_prominence_records': WalletProminence.objects.count(),
                
                # Recent activity (last 7 days)
                'recent_sweeps_7d': CollectionSweepEvent.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).count(),
                'recent_high_profile_7d': HighProfileTransfer.objects.filter(
                    updated_at__gte=timezone.now() - timedelta(days=7)
                ).count(),
                
                # Top performers
                'top_trending_trait': TrendingTrait.objects.order_by('-trend_score').first(),
                'top_performing_trait': TopTrait.objects.order_by('-combined_score').first(),
                'biggest_recent_sweep': CollectionSweepEvent.objects.order_by(
                    '-significance_score'
                ).first(),
            })
        
        logger.info(
            f"📊 Analytics Summary: {summary['trending_traits']} trending traits, "
            f"{summary.get('collection_sweeps', 0)} sweeps, "
            f"{summary['featured_collections']} featured collections"
        )
        
        return summary
        
    except Exception as e:
        logger.error(f"📊 Error getting analytics summary: {str(e)}")
        return {
            'error': str(e),
            'last_calculated': timezone.now()
        }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Service initialization
    'get_indexer_service',
    
    # Cache utilities
    'get_metrics_cache',
    'save_metrics_cache',
    
    # Data conversion
    'safe_decimal_conversion',
    
    # Confidence & quality
    'calculate_overall_confidence',
    'get_calculated_metrics_attribution',
    
    # Result templates
    'empty_aggregated_result',
    
    # Notifications
    'send_notification',
    
    # Analytics summary
    'get_analytics_summary',
]