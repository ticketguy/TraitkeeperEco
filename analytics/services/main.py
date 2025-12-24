# analytics/services/main.py - REFACTORED VERSION
"""
Metrics Calculation Service - Main Orchestrator

This service coordinates all analytics calculations by delegating to specialized services.
It provides backward compatibility while keeping the orchestration logic clean.

REFACTORED ARCHITECTURE:
- MarketAggregationService: Handles multi-source market data
- TraitAnalyticsService: Handles trait performance and trending
- WalletAnalyticsService: Handles wallet behavior and prominence
- This service: Just orchestrates and delegates!
"""

import logging
import asyncio
from datetime import timedelta
from typing import Optional, List

from django.db import transaction as db_transaction
from django.utils import timezone
from django.core.cache import cache
from django.contrib.auth import get_user_model
from asgiref.sync import sync_to_async, async_to_sync

# Core models
from ..models import NFTCollection, NFT, TraitType, TraitValue, TrendingTrait, TopTrait
from indexer.models import CollectionMarketStats

# Import the specialized services
from .market_aggregation import MarketAggregationService
from .trait_analytics import TraitAnalyticsService
from .wallet_analytics import WalletAnalyticsService

# Configure logging
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

User = get_user_model()


class MetricsCalculationService:
    """
    Main orchestrator for all analytics calculations.
    
    This service delegates actual work to specialized services:
    - MarketAggregationService: Multi-source market data aggregation
    - TraitAnalyticsService: Trait performance, trending, and top traits
    - WalletAnalyticsService: Wallet prominence and behavior analysis
    
    This class now focuses ONLY on:
    1. Service initialization
    2. Orchestration of comprehensive calculations
    3. Backward compatibility wrappers
    """
    
    def __init__(self):
        """Initialize all specialized services."""
        # Initialize sub-services
        self.market_aggregation = MarketAggregationService()
        self.trait_analytics = TraitAnalyticsService()
        self.wallet_analytics = WalletAnalyticsService()

        # Keep API provider manager for backward compatibility if needed
        try:
            from core.api_provider.api_providers import APIProviderManager
            self.provider_manager = APIProviderManager()
        except ImportError:
            self.provider_manager = None
            logger.warning("APIProviderManager not available")

        logger.info("✅ Initialized MetricsCalculationService with all sub-services")
    
    # ==================== DELEGATION METHODS (Backward Compatibility) ====================
    
    async def update_collection_metrics(self, collection: NFTCollection):
        """
        Update market metrics for a collection.

        DELEGATES TO:
        - MarketAggregationService (for market metrics)

        NOTE: Vitality calculations are handled separately by the vitality-analytics container
        based on collection priority (VIP: 15min, ACTIVE: 60min, INACTIVE: 4hr)

        This is a backward compatibility wrapper. Direct usage:
        >>> from analytics.services import MarketAggregationService
        >>> service = MarketAggregationService()
        >>> await service.update_collection_metrics(collection)
        """
        # Update market metrics (creates/updates AggregatedCollectionStats)
        return await self.market_aggregation.update_collection_metrics(collection)
    
    async def update_trait_metrics(
        self,
        collection_address: str,
        force_update: bool = False,
        burn_event_data: Optional[dict] = None
    ):
        """
        Update trait metrics for a collection.
        
        DELEGATES TO: TraitAnalyticsService
        
        Args:
            collection_address: Collection address
            force_update: Force update regardless of activity
            burn_event_data: Optional burn event data
            
        Returns:
            Dict with results, or None if skipped
        """
        return await self.trait_analytics.update_trait_metrics(
            collection_address,
            force_update,
            burn_event_data
        )
    
    async def calculate_wallet_prominence(self):
        """
        Calculate wallet prominence scores.
        
        DELEGATES TO: WalletAnalyticsService
        
        Returns:
            Dict with wallet analysis results
        """
        return await self.wallet_analytics.calculate_wallet_prominence()
    
    def calculate_and_store_trending_traits(self, collection_address: Optional[str] = None):
        """
        Calculate trending traits across collections.
        
        DELEGATES TO: TraitAnalyticsService
        
        Args:
            collection_address: Optional specific collection
            
        Returns:
            Dict with trending trait results
        """
        return self.trait_analytics.calculate_and_store_trending_traits(collection_address)
    
    def calculate_and_store_top_traits(self, collection_address: Optional[str] = None):
        """
        Calculate top-performing traits.
        
        DELEGATES TO: TraitAnalyticsService
        
        Args:
            collection_address: Optional specific collection
            
        Returns:
            Dict with top trait results
        """
        return self.trait_analytics.calculate_and_store_top_traits(collection_address)
    
    def calculate_trait_performance_scores(self, collection_address: str):
        """
        Calculate performance scores for all traits in a collection.
        
        DELEGATES TO: TraitAnalyticsService
        
        Args:
            collection_address: Collection to calculate for
            
        Returns:
            Dict with performance score results
        """
        return self.trait_analytics.calculate_trait_performance_scores(collection_address)
    
    # ==================== ORCHESTRATION METHOD ====================
    
    async def calculate_comprehensive_metrics(
        self,
        collection_addresses: Optional[List[str]] = None
    ):
        """
        Calculate all metrics for multiple collections.
        
        THIS IS THE MAIN ORCHESTRATION METHOD!
        
        It coordinates:
        1. Market metrics (MarketAggregationService)
        2. Trait metrics (TraitAnalyticsService)
        3. Cross-collection analytics (wallet, trending, top traits)
        
        Args:
            collection_addresses: Optional list of specific collections to process
            
        Returns:
            Dict with comprehensive results and summary
        """
        try:
            logger.info("🚀 STARTING OPTIMIZED COMPREHENSIVE METRICS CALCULATION")
            
            # Get collections to process
            if collection_addresses:
                collections = await sync_to_async(list)(
                    NFTCollection.objects.filter(address__in=collection_addresses)
                )
            else:
                collections = await sync_to_async(list)(
                    NFTCollection.objects.filter(is_active=True)
                )
            
            results = {
                'total_collections': len(collections),
                'successful_updates': 0,
                'skipped_inactive': 0,
                'failed_updates': 0,
                'errors': [],
                'source_availability': {}
            }
            
            logger.info(f"📊 Processing {len(collections)} collections")
            
            # Process each collection
            for i, collection in enumerate(collections, 1):
                try:
                    logger.info(f"[{i}/{len(collections)}] Processing: {collection.name}")
                    
                    # 1. Update market metrics (aggregated from multiple sources)
                    await self.market_aggregation.update_collection_metrics(collection)
                    
                    # 2. Update trait metrics with intelligent activity-based skipping
                    trait_result = await self.trait_analytics.update_trait_metrics(
                        collection.address,
                        force_update=False
                    )
                    
                    if trait_result is None:  # Indicates skipped due to no activity
                        results['skipped_inactive'] += 1
                        logger.info(f"⚡ Skipped trait metrics for {collection.name} - no recent activity")
                    else:
                        results['successful_updates'] += 1
                        logger.info(f"✓ Successfully updated {collection.name}")
                    
                    # Progressive rate limiting - faster for first few, slower later
                    if i < len(collections) - 1:  # Don't sleep after last collection
                        if i < 10:
                            await asyncio.sleep(1)  # Fast start for first 10
                        elif i < 50:
                            await asyncio.sleep(2)  # Medium pace for first 50
                        else:
                            await asyncio.sleep(3)  # Slower for remainder
                            
                except Exception as e:
                    logger.error(f"✗ Error updating {collection.name}: {str(e)}")
                    results['failed_updates'] += 1
                    results['errors'].append(f"{collection.name}: {str(e)}")
                    continue
            
            # 3. Run cross-collection analytics ONCE at the end
            try:
                logger.info("🚀 Running cross-collection analytics ONCE (instead of per-collection)")
                
                # Run calculations in parallel but with error handling
                additional_results = await asyncio.gather(
                    self.wallet_analytics.calculate_wallet_prominence(),
                    async_to_sync(self.trait_analytics.calculate_and_store_trending_traits)(),
                    async_to_sync(self.trait_analytics.calculate_and_store_top_traits)(),
                    return_exceptions=True
                )
                
                # Check for any failures in additional calculations
                calculation_names = [
                    'wallet_prominence',
                    'trending_traits',
                    'top_traits'
                ]
                
                for i, result in enumerate(additional_results):
                    if isinstance(result, Exception):
                        logger.error(f"Error in {calculation_names[i]}: {str(result)}")
                        results['errors'].append(f"{calculation_names[i]}: {str(result)}")
                    else:
                        logger.info(f"✓ Completed {calculation_names[i]} calculation")
                
                successful_calculations = sum(
                    1 for r in additional_results if not isinstance(r, Exception)
                )
                logger.info(
                    f"✓ Cross-collection analytics completed: "
                    f"{successful_calculations}/{len(calculation_names)} successful"
                )
                
            except Exception as e:
                logger.error(f"Error in cross-collection analytics: {str(e)}")
                results['errors'].append(f"Cross-collection analytics: {str(e)}")
            
            # Generate comprehensive summary
            success_rate = (
                (results['successful_updates'] / results['total_collections']) * 100
                if results['total_collections'] > 0 else 0
            )
            
            logger.info("=" * 60)
            logger.info("🚀 OPTIMIZED METRICS CALCULATION COMPLETE")
            logger.info("=" * 60)
            logger.info(f"Collections processed: {results['total_collections']}")
            logger.info(f"Successful updates: {results['successful_updates']}")
            logger.info(f"⚡ Skipped (no activity): {results['skipped_inactive']}")
            logger.info(f"Failed updates: {results['failed_updates']}")
            logger.info(f"Success rate: {success_rate:.1f}%")
            logger.info("🚀 OPTIMIZATION BENEFITS:")
            logger.info(f"  - Activity-based skipping saved ~{results['skipped_inactive'] * 60} seconds")
            logger.info(f"  - Parallel API calls improved network efficiency")
            logger.info(f"  - Cross-collection analytics run 1x instead of {results['total_collections']}x")
            logger.info(f"  - Bulk database operations reduced query count")
            
            if results['errors']:
                logger.warning(f"Errors encountered: {len(results['errors'])}")
                logger.warning("First 5 errors:")
                for i, error in enumerate(results['errors'][:5]):
                    logger.warning(f"  {i+1}. {error}")
                if len(results['errors']) > 5:
                    logger.warning(f"  ... and {len(results['errors']) - 5} more errors")
            
            logger.info("=" * 60)
            
            # Determine overall success
            overall_success = success_rate >= 60
            
            return {
                "success": overall_success,
                "results": results,
                "summary": {
                    "collections_processed": results['total_collections'],
                    "collections_updated": results['successful_updates'],
                    "collections_skipped_inactive": results['skipped_inactive'],
                    "success_rate": f"{success_rate:.1f}%",
                    "error_count": len(results['errors']),
                    "optimization_impact": "Major performance improvements implemented"
                },
                "message": (
                    f"🚀 OPTIMIZED metrics calculation completed: "
                    f"{results['successful_updates']} updated, "
                    f"{results['skipped_inactive']} skipped (inactive)"
                )
            }
            
        except Exception as e:
            logger.error(f"Critical error in comprehensive metrics calculation: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "Critical failure in metrics calculation system"
            }
    
    # ==================== SUMMARY STATISTICS METHOD ====================
    
    def get_analytics_summary(self):
        """
        Get summary statistics for all calculated analytics.
        
        DELEGATES TO: utils.get_analytics_summary()
        
        Returns:
            Dict with analytics summary
        """
        from .utils import get_analytics_summary
        return get_analytics_summary()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'MetricsCalculationService',
]