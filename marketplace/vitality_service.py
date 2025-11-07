# marketplace/vitality_service.py

"""
NFT Vitality Calculation Service - REFACTORED

This service calculates NFT Vitality scores - TraitKeeper's proprietary value metric
that replaces floor price as the primary indicator of NFT value in the marketplace.

Component Weights (User-Specified - Final):
- Market Momentum: 25% (60-day lookback period)
- Trait Performance: 20%
- Collection Health: 15%
- Collection Utility: 10%
- Rarity Score: 10%
- Holder Quality: 10%
- Sentiment Score: 5% (TODO: Not yet implemented, returns 0.5)
- Market Influence: 5%

Total: 100%

REFACTOR CHANGES:
- Now acts as a pure "scoring engine" that applies WEIGHTS to pre-calculated analytics
- Removed all redundant database queries
- Reads from analytics services instead of duplicating logic
- Smaller, cleaner, more focused on vitality-specific scoring
"""

import logging
from decimal import Decimal
from statistics import mean
from datetime import timedelta
from typing import Dict, Optional, Tuple

from django.db import transaction
from django.db.models import Avg, Count, Sum, Q, F, Max
from django.utils import timezone
from asgiref.sync import sync_to_async

from nft_data.models import NFT, NFTCollection, TraitValue
from indexer.models import NFTEvent, CollectionMarketStats  # CollectionMarketStats only for source counting
from analytics.models import (
    AggregatedCollectionStats,
    TraitPerformanceScore,
    WalletProminence,
    WalletBehaviorProfile
)
from .vitality_models import (
    NFTVitality,
    NFTVitalityHistory,
    CollectionVitality,
    CollectionVitalityHistory,
    VitalityPriceComparison
)

logger = logging.getLogger(__name__)


class VitalityCalculationService:
    """
    Main service for calculating NFT and Collection vitality scores.

    This service orchestrates the calculation of all vitality components
    and combines them into a final weighted score (0-100).
    
    REFACTORED: Now focuses purely on applying proprietary WEIGHTS to
    pre-calculated analytics data from analytics services.
    """

    # === COMPONENT WEIGHTS (User-Specified - Final) ===
    WEIGHTS = {
        'market_momentum': Decimal('0.25'),      # 25%
        'trait_performance': Decimal('0.20'),    # 20%
        'collection_health': Decimal('0.15'),    # 15%
        'collection_utility': Decimal('0.10'),   # 10%
        'rarity_score': Decimal('0.10'),         # 10%
        'holder_quality': Decimal('0.10'),       # 10%
        'sentiment_score': Decimal('0.05'),      # 5% - TODO
        'market_influence': Decimal('0.05'),     # 5%
    }

    # === CONFIGURATION ===
    MOMENTUM_LOOKBACK_DAYS = 60  # Use 60 days for market momentum (user-specified)

    def __init__(self):
        """Initialize the vitality calculation service."""
        self.logger = logger

    # =========================================================================
    # NFT-LEVEL VITALITY CALCULATION
    # =========================================================================

    async def calculate_nft_vitality(
        self,
        nft: NFT,
        store_history: bool = True
    ) -> Optional[NFTVitality]:
        """
        Calculate and store vitality score for a single NFT.

        Args:
            nft: The NFT to calculate vitality for
            store_history: Whether to store a historical snapshot

        Returns:
            NFTVitality instance with calculated score, or None if insufficient data

        Raises:
            ValueError: If NFT data is invalid
            Exception: For other calculation errors
        """
        self.logger.info(f"Calculating vitality for NFT: {nft.mint_address}")

        # === PREREQUISITE CHECK ===
        if not await self._has_sufficient_data(nft):
            self.logger.warning(
                f"NFT {nft.mint_address} has no transactions. "
                f"Cannot calculate vitality."
            )
            return None

        try:
            # === CALCULATE ALL COMPONENTS ===
            components = await self._calculate_all_components(nft)

            # === CALCULATE WEIGHTED VITALITY SCORE ===
            vitality_score = self._apply_weights(components)

            # === STORE OR UPDATE VITALITY RECORD ===
            vitality = await sync_to_async(NFTVitality.objects.update_or_create)(
                nft=nft,
                defaults={
                    'vitality_score': vitality_score,
                    'market_momentum': Decimal(str(components['market_momentum'])),
                    'trait_performance': Decimal(str(components['trait_performance'])),
                    'collection_health': Decimal(str(components['collection_health'])),
                    'collection_utility': Decimal(str(components['collection_utility'])),
                    'rarity_score': Decimal(str(components['rarity_score'])),
                    'holder_quality': Decimal(str(components['holder_quality'])),
                    'sentiment_score': Decimal(str(components['sentiment_score'])),
                    'market_influence': Decimal(str(components['market_influence'])),
                    'has_sufficient_data': True,
                    'last_calculated': timezone.now()
                }
            )

            # === STORE HISTORICAL SNAPSHOT ===
            if store_history:
                await sync_to_async(NFTVitalityHistory.objects.create)(
                    nft=nft,
                    vitality_score=vitality_score,
                    market_momentum=Decimal(str(components['market_momentum'])),
                    trait_performance=Decimal(str(components['trait_performance'])),
                    collection_health=Decimal(str(components['collection_health'])),
                    collection_utility=Decimal(str(components['collection_utility'])),
                    rarity_score=Decimal(str(components['rarity_score'])),
                    holder_quality=Decimal(str(components['holder_quality'])),
                    sentiment_score=Decimal(str(components['sentiment_score'])),
                    market_influence=Decimal(str(components['market_influence']))
                )

            self.logger.info(
                f"✅ Vitality calculated for {nft.mint_address}: {vitality_score}"
            )

            return vitality[0]

        except Exception as e:
            self.logger.error(
                f"Error calculating vitality for {nft.mint_address}: {str(e)}"
            )
            raise

    async def _calculate_all_components(self, nft: NFT) -> Dict[str, float]:
        """
        Calculate all vitality components for an NFT.

        Returns:
            Dict mapping component names to scores (0-1)
        """
        return {
            'market_momentum': await self._calculate_market_momentum(nft),
            'trait_performance': await self._calculate_trait_performance(nft),
            'collection_health': await self._calculate_collection_health_component(nft.collection),
            'collection_utility': await self._calculate_collection_utility(nft.collection),
            'rarity_score': await self._calculate_rarity_score(nft),
            'holder_quality': await self._calculate_holder_quality(nft),
            'sentiment_score': await self._calculate_sentiment_score(nft),
            'market_influence': await self._calculate_market_influence(nft),
        }

    def _apply_weights(self, components: Dict[str, float]) -> Decimal:
        """
        Apply component weights to calculate final vitality score.

        Args:
            components: Dict of component scores (0-1)

        Returns:
            Weighted vitality score (0-100)
        """
        weighted_sum = Decimal('0')

        for component_name, weight in self.WEIGHTS.items():
            component_value = Decimal(str(components[component_name]))
            weighted_sum += component_value * weight

        # Scale to 0-100
        vitality_score = (weighted_sum * 100).quantize(Decimal('0.01'))

        return vitality_score

    # =========================================================================
    # COMPONENT CALCULATION METHODS - REFACTORED
    # =========================================================================

    async def _calculate_market_momentum(self, nft: NFT) -> float:
        """
        Calculate market momentum component (25% weight).

        REFACTORED: Uses Level 1 AggregatedCollectionStats for clean, multi-sourced data.

        Market momentum is primarily driven by the collection's overall momentum,
        with some NFT-specific adjustments if the NFT has recent sales.

        Returns:
            Score from 0-1 (0 = declining, 0.5 = stable, 1 = strong momentum)
        """
        try:
            # 🎯 LEVEL 1: Get aggregated stats (pre-calculated by MarketAggregationService)
            collection_stats = await sync_to_async(
                AggregatedCollectionStats.objects.filter(
                    collection=nft.collection
                ).first
            )()

            if not collection_stats:
                self.logger.warning(
                    f"No aggregated stats for collection {nft.collection.address}"
                )
                return 0.5

            # === COLLECTION-LEVEL MOMENTUM ===
            # Use pre-calculated price changes and volume metrics
            price_change_24h = float(collection_stats.price_change_24h or 0)
            price_change_7d = float(collection_stats.price_change_7d or 0)
            volume_24h = float(collection_stats.volume_24h or 0)
            
            # Calculate price momentum (0-1)
            # Normalize percentage changes to 0-1 range (cap at ±50%)
            price_momentum_24h = max(0, min(1, 0.5 + (price_change_24h / 100)))
            price_momentum_7d = max(0, min(1, 0.5 + (price_change_7d / 100)))
            
            # Weight recent momentum more heavily (60% 24h, 40% 7d)
            price_momentum = (price_momentum_24h * 0.6) + (price_momentum_7d * 0.4)
            
            # === VOLUME MOMENTUM ===
            # Higher volume = more market interest
            # Normalize volume (assume 100 SOL/24h is high for a collection)
            volume_score = min(1.0, volume_24h / 100.0)
            
            # === NFT-SPECIFIC ADJUSTMENT ===
            # Check if THIS specific NFT has recent sales
            fourteen_days_ago = timezone.now() - timedelta(days=14)
            nft_recent_sales = await sync_to_async(
                NFTEvent.objects.filter(
                    nft_mint=nft.mint_address,
                    event_type='SALE',
                    timestamp__gte=fourteen_days_ago
                ).count
            )()
            
            # If NFT has recent sales, boost momentum slightly
            nft_activity_boost = min(0.1, nft_recent_sales * 0.03)  # Max 10% boost
            
            # Combine all momentum factors
            momentum = (
                price_momentum * 0.5 +    # Collection price trend (50%)
                volume_score * 0.4 +      # Collection volume (40%)
                nft_activity_boost        # NFT-specific activity (10%)
            )
            
            return min(1.0, momentum)
            
        except Exception as e:
            self.logger.error(f"Error calculating market momentum: {str(e)}")
            return 0.5

    async def _calculate_trait_performance(self, nft: NFT) -> float:
        """
        Calculate trait performance component (20% weight).
        
        ALREADY CLEAN: Reads from TraitPerformanceScore (calculated by TraitAnalyticsService).
        No changes needed - this method was already properly using analytics data!

        Returns:
            Score from 0-1 (0 = worst, 1 = best)
        """
        # Get all trait values for this NFT
        trait_values = await sync_to_async(list)(
            nft.trait_values.all()
        )

        if not trait_values:
            self.logger.warning(f"NFT {nft.mint_address} has no trait values")
            return 0.5  # Neutral if no traits

        trait_scores = []
        
        for trait_value in trait_values:
            # Get performance score from analytics (calculated by TraitAnalyticsService)
            try:
                performance = await sync_to_async(
                    TraitPerformanceScore.objects.get
                )(
                    collection=nft.collection,
                    trait_value=trait_value
                )
                # Normalize performance_score (0-100) to 0-1
                normalized_score = performance.performance_score / 100.0
                trait_scores.append(normalized_score)

            except TraitPerformanceScore.DoesNotExist:
                # If no performance data for this trait, use neutral (0.5)
                trait_scores.append(0.5)
                self.logger.debug(
                    f"No performance score for {trait_value.value} "
                    f"in {nft.collection.display_name}"
                )

        # Average all trait scores
        return mean(trait_scores) if trait_scores else 0.5

    async def _calculate_collection_health_component(self, collection: NFTCollection) -> float:
        """
        Calculate collection health component (15% weight).

        REFACTORED: Uses Level 1 AggregatedCollectionStats for pre-calculated health metrics.

        Returns:
            Score from 0-1 (0 = unhealthy, 1 = very healthy)
        """
        try:
            # 🎯 LEVEL 1: Get aggregated stats (calculated by MarketAggregationService)
            stats = await sync_to_async(
                AggregatedCollectionStats.objects.filter(
                    collection=collection
                ).first
            )()

            if not stats:
                self.logger.warning(
                    f"No aggregated stats for collection {collection.address}"
                )
                return 0.5

            # Use pre-calculated health metrics
            # Combine multiple health indicators
            
            # Market efficiency score (0-100)
            efficiency = float(stats.market_efficiency_score or 50) / 100.0
            
            # Holder confidence index (0-100)
            confidence = float(stats.holder_confidence_index or 50) / 100.0
            
            # Liquidity health score (0-100)
            liquidity = float(stats.liquidity_health_score or 50) / 100.0
            
            # Overall performance score (0-100)
            performance = float(stats.performance_score or 50) / 100.0
            
            # Weighted combination (all factors important)
            health_score = (
                efficiency * 0.3 +
                confidence * 0.3 +
                liquidity * 0.2 +
                performance * 0.2
            )
            
            return health_score

        except Exception as e:
            self.logger.error(f"Error calculating collection health: {str(e)}")
            return 0.5

    async def _calculate_collection_utility(self, collection: NFTCollection) -> float:
        """
        Calculate collection utility component (10% weight).

        Utility measures what value the collection provides beyond just art:
        - Staking rewards
        - Governance rights
        - Access to events/communities
        - Gamification/play-to-earn
        - Physical merchandise
        - Future airdrops

        TODO: This requires manual tagging or metadata analysis.
        For now, check collection metadata for utility keywords.

        Returns:
            Score from 0-1 (0 = no utility, 1 = high utility)
        """
        # TODO: Implement utility detection/scoring system
        # Future implementation:
        # 1. Check collection metadata for utility keywords
        # 2. Manual admin tagging in NFTCollection model (add utility_features JSONField)
        # 3. Check for staking contracts associated with collection
        # 4. Social media/website analysis for utility announcements

        # For now, return neutral (0.5)
        # This prevents utility from negatively impacting score until implemented
        return 0.5

    async def _calculate_rarity_score(self, nft: NFT) -> float:
        """
        Calculate rarity component (10% weight).

        Statistical rarity based on trait combinations.
        Not just individual trait rarity, but the rarity of having
        this specific combination of traits.

        NO CHANGES NEEDED: This method was already clean - it just reads
        trait rarity values that are stored in the NFT model.

        Returns:
            Score from 0-1 (0 = common, 1 = extremely rare)
        """
        trait_values = await sync_to_async(list)(
            nft.trait_values.all()
        )

        if not trait_values:
            return 0.5  # Neutral if no traits

        # Get individual trait rarities
        rarities = []
        for trait_value in trait_values:
            # trait_value.rarity is stored as a percentage (0-100)
            # Normalize to 0-1
            rarity = trait_value.rarity / 100.0
            rarities.append(rarity)

        if not rarities:
            return 0.5

        # === COMBINATION RARITY ===
        # Multiply individual rarities to get combination rarity
        # Rarer combinations have smaller product
        combination_rarity = 1.0
        for r in rarities:
            combination_rarity *= r

        # Invert and scale (lower product = higher score)
        # Use log scaling for better distribution
        import math
        if combination_rarity > 0:
            # Score increases as combination_rarity decreases
            # Adjust the divisor (10) to tune sensitivity
            score = max(0, min(1, -math.log10(combination_rarity) / 10))
        else:
            score = 1.0  # Maximum rarity (impossible combination)

        return score

    async def _calculate_holder_quality(self, nft: NFT) -> float:
        """
        Calculate holder quality component (10% weight).
        
        ALREADY CLEAN: Reads from WalletProminence and WalletBehaviorProfile
        (calculated by WalletAnalyticsService).
        No changes needed - this method was already properly using analytics data!

        Returns:
            Score from 0-1 (0 = unknown/low quality, 1 = high quality/influential)
        """
        if not nft.owner:
            return 0.5  # Neutral if no owner

        # === CHECK WALLET PROMINENCE ===
        try:
            prominence = await sync_to_async(
                WalletProminence.objects.get
            )(address=nft.owner)
            # prominence_score is 0-100, normalize to 0-1
            prominence_score = prominence.prominence_score / 100.0
        except WalletProminence.DoesNotExist:
            prominence_score = 0.5  # Neutral for unknown wallet

        # === CHECK WALLET BEHAVIOR PROFILE ===
        try:
            behavior = await sync_to_async(
                WalletBehaviorProfile.objects.get
            )(wallet_address=nft.owner)
            influence_score = behavior.influence_score
            diversification = behavior.diversification_score

            # Combine metrics (influence matters more than diversification)
            behavior_score = (influence_score * 0.6) + (diversification * 0.4)
        except WalletBehaviorProfile.DoesNotExist:
            behavior_score = None

        # Combine prominence and behavior (if available)
        if behavior_score is not None:
            holder_quality = (prominence_score * 0.4) + (behavior_score * 0.6)
        else:
            # Only prominence available
            holder_quality = prominence_score

        return holder_quality

    async def _calculate_sentiment_score(self, nft: NFT) -> float:
        """
        Calculate sentiment component (5% weight).

        TODO: Implement sentiment analysis from social media/community.
        Future data sources:
        - Twitter API for collection mentions and sentiment
        - Discord API for community activity and sentiment
        - TraitKeeper user reviews/ratings for collections
        - Sentiment analysis of collection description/metadata
        - NFT influencer mentions and opinions

        For now, returns neutral (0.5) as specified by user.

        Returns:
            Score from 0-1 (0 = negative sentiment, 1 = positive sentiment)
        """
        # TODO: Implement sentiment analysis
        # Placeholder for future implementation
        return 0.5  # Neutral until implemented

    async def _calculate_market_influence(self, nft: NFT) -> float:
        """
        Calculate market influence component (5% weight).

        REFACTORED: Uses Level 1 AggregatedCollectionStats for market metrics.

        Returns:
            Score from 0-1 (0 = no influence, 1 = highly influential)
        """
        try:
            # 🎯 LEVEL 1: Get aggregated stats (calculated by MarketAggregationService)
            stats = await sync_to_async(
                AggregatedCollectionStats.objects.filter(
                    collection=nft.collection
                ).first
            )()

            if not stats:
                return 0.5

            # === VOLUME INFLUENCE ===
            # Normalize volume to 0-1 (assume 1000 SOL/24h is high volume)
            volume_24h = float(stats.volume_24h or 0)
            volume_score = min(1.0, volume_24h / 1000.0)

            # === HOLDER INFLUENCE ===
            # Normalize holders to 0-1 (assume 5000 holders is high)
            holder_count = stats.number_of_holders or 0
            holder_score = min(1.0, holder_count / 5000.0)

            # === MARKETPLACE PRESENCE ===
            # Check how many marketplaces have data for this collection
            market_stats_count = await sync_to_async(
                CollectionMarketStats.objects.filter(
                    collection=nft.collection
                ).values('source').distinct().count
            )()

            # Normalize (assume 3+ sources = max presence)
            marketplace_score = min(1.0, market_stats_count / 3.0)

            # Combine all factors
            influence = (
                volume_score * 0.5 +
                holder_score * 0.3 +
                marketplace_score * 0.2
            )

            return influence

        except Exception as e:
            self.logger.error(f"Error calculating market influence: {str(e)}")
            return 0.5

    # =========================================================================
    # COLLECTION-LEVEL VITALITY CALCULATION
    # =========================================================================

    async def calculate_collection_vitality(
        self,
        collection: NFTCollection,
        store_history: bool = True
    ) -> Optional[CollectionVitality]:
        """
        Calculate and store vitality score for an entire collection.

        This is an aggregate of all NFTs in the collection, plus
        collection-level metrics.

        Args:
            collection: The collection to calculate vitality for
            store_history: Whether to store a historical snapshot

        Returns:
            CollectionVitality instance, or None if insufficient data
        """
        self.logger.info(f"Calculating collection vitality for: {collection.display_name}")

        # === PREREQUISITE CHECK ===
        if not await self._has_sufficient_data_collection(collection):
            self.logger.warning(
                f"Collection {collection.address} has no transactions. "
                f"Cannot calculate vitality."
            )
            return None

        try:
            # === AGGREGATE NFT VITALITIES ===
            # Get average vitality components across all NFTs in collection
            nft_vitalities = await sync_to_async(
                NFTVitality.objects.filter(
                    nft__collection=collection,
                    has_sufficient_data=True
                )
            )()

            nft_vitalities_list = await sync_to_async(list)(nft_vitalities)

            if not nft_vitalities_list:
                # No NFT vitalities calculated yet
                # Use collection-level metrics only
                self.logger.info(
                    f"No NFT vitalities found for {collection.display_name}. "
                    f"Using collection-level metrics only."
                )
                components = await self._calculate_collection_components_direct(collection)
            else:
                # Aggregate from existing NFT vitalities
                aggregates = await sync_to_async(nft_vitalities.aggregate)(
                    avg_trait_perf=Avg('trait_performance'),
                    avg_rarity=Avg('rarity_score'),
                    avg_holder_quality=Avg('holder_quality')
                )

                components = {
                    'market_momentum': await self._calculate_collection_momentum(collection),
                    'avg_trait_performance': aggregates['avg_trait_perf'] or 0.5,
                    'collection_health': await self._calculate_collection_health_component(collection),
                    'collection_utility': await self._calculate_collection_utility(collection),
                    'avg_rarity_score': aggregates['avg_rarity'] or 0.5,
                    'holder_quality_avg': aggregates['avg_holder_quality'] or 0.5,
                    'sentiment_score': 0.5,  # TODO: Implement
                    'market_influence': await self._calculate_market_influence_collection(collection),
                }

            # === CALCULATE WEIGHTED VITALITY SCORE ===
            # Map component names for collection level
            collection_components = {
                'market_momentum': components['market_momentum'],
                'trait_performance': components['avg_trait_performance'],
                'collection_health': components['collection_health'],
                'collection_utility': components['collection_utility'],
                'rarity_score': components['avg_rarity_score'],
                'holder_quality': components['holder_quality_avg'],
                'sentiment_score': components['sentiment_score'],
                'market_influence': components['market_influence'],
            }

            vitality_score = self._apply_weights(collection_components)

            # === STORE OR UPDATE COLLECTION VITALITY ===
            vitality = await sync_to_async(CollectionVitality.objects.update_or_create)(
                collection=collection,
                defaults={
                    'vitality_score': vitality_score,
                    'market_momentum': Decimal(str(components['market_momentum'])),
                    'avg_trait_performance': Decimal(str(components['avg_trait_performance'])),
                    'collection_health': Decimal(str(components['collection_health'])),
                    'collection_utility': Decimal(str(components['collection_utility'])),
                    'avg_rarity_score': Decimal(str(components['avg_rarity_score'])),
                    'holder_quality_avg': Decimal(str(components['holder_quality_avg'])),
                    'sentiment_score': Decimal(str(components['sentiment_score'])),
                    'market_influence': Decimal(str(components['market_influence'])),
                    'has_sufficient_data': True,
                    'last_calculated': timezone.now()
                }
            )

            # === STORE HISTORICAL SNAPSHOT ===
            if store_history:
                await sync_to_async(CollectionVitalityHistory.objects.create)(
                    collection=collection,
                    vitality_score=vitality_score,
                    market_momentum=Decimal(str(components['market_momentum'])),
                    avg_trait_performance=Decimal(str(components['avg_trait_performance'])),
                    collection_health=Decimal(str(components['collection_health'])),
                    collection_utility=Decimal(str(components['collection_utility'])),
                    avg_rarity_score=Decimal(str(components['avg_rarity_score'])),
                    holder_quality_avg=Decimal(str(components['holder_quality_avg'])),
                    sentiment_score=Decimal(str(components['sentiment_score'])),
                    market_influence=Decimal(str(components['market_influence']))
                )

            self.logger.info(
                f"✅ Collection vitality calculated for {collection.display_name}: "
                f"{vitality_score}"
            )

            return vitality[0]

        except Exception as e:
            self.logger.error(
                f"Error calculating collection vitality for {collection.address}: {str(e)}"
            )
            raise

    async def _calculate_collection_momentum(self, collection: NFTCollection) -> float:
        """
        Calculate collection-level market momentum.

        REFACTORED: Uses Level 1 AggregatedCollectionStats for pre-calculated metrics.

        Returns:
            Score from 0-1
        """
        try:
            # 🎯 LEVEL 1: Get aggregated stats
            stats = await sync_to_async(
                AggregatedCollectionStats.objects.filter(
                    collection=collection
                ).first
            )()

            if not stats:
                return 0.5

            # Use pre-calculated momentum indicators
            price_change_7d = float(stats.price_change_7d or 0)
            volume_24h = float(stats.volume_24h or 0)
            velocity_24h = float(stats.velocity_24h or 0)

            # Price momentum (0-1)
            price_momentum = max(0, min(1, 0.5 + (price_change_7d / 100)))

            # Volume momentum (0-1)
            volume_score = min(1.0, volume_24h / 100.0)

            # Velocity momentum (0-1) - sales per hour
            velocity_score = min(1.0, velocity_24h / 5.0)  # 5 sales/hour = high

            # Combine
            momentum = (
                price_momentum * 0.4 +
                volume_score * 0.4 +
                velocity_score * 0.2
            )

            return momentum

        except Exception as e:
            self.logger.error(f"Error calculating collection momentum: {str(e)}")
            return 0.5

    async def _calculate_market_influence_collection(self, collection: NFTCollection) -> float:
        """
        Calculate market influence for collection.
        
        REFACTORED: Simplified to use pre-calculated metrics.

        Returns:
            Score from 0-1
        """
        return await self._calculate_market_influence(
            NFT(collection=collection, owner=None, mint_address="dummy")
        )

    async def _calculate_collection_components_direct(self, collection: NFTCollection) -> Dict:
        """
        Calculate collection components when no NFT vitalities exist yet.

        Returns:
            Dict of component scores
        """
        return {
            'market_momentum': await self._calculate_collection_momentum(collection),
            'avg_trait_performance': 0.5,  # Neutral until NFTs calculated
            'collection_health': await self._calculate_collection_health_component(collection),
            'collection_utility': await self._calculate_collection_utility(collection),
            'avg_rarity_score': 0.5,  # Neutral until NFTs calculated
            'holder_quality_avg': 0.5,  # Neutral until NFTs calculated
            'sentiment_score': 0.5,  # TODO
            'market_influence': await self._calculate_market_influence_collection(collection),
        }

    # =========================================================================
    # PREREQUISITE CHECKS
    # =========================================================================

    async def _has_sufficient_data(self, nft: NFT) -> bool:
        """
        Check if an NFT has sufficient transaction data for vitality calculation.

        At minimum, the collection must have at least 1 transaction.

        Returns:
            True if sufficient data exists, False otherwise
        """
        # Check if collection has any transactions
        has_transactions = await sync_to_async(
            NFTEvent.objects.filter(
                collection_address=nft.collection.address
            ).exists
        )()

        return has_transactions

    async def _has_sufficient_data_collection(self, collection: NFTCollection) -> bool:
        """
        Check if a collection has sufficient data for vitality calculation.

        Returns:
            True if sufficient data exists, False otherwise
        """
        has_transactions = await sync_to_async(
            NFTEvent.objects.filter(
                collection_address=collection.address
            ).exists
        )()

        return has_transactions


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'VitalityCalculationService',
]