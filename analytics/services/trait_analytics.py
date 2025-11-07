# analytics/services/trait_analytics.py
"""
Trait Analytics Service
Handles all trait-related performance calculations, trending analysis, and top trait identification.

DATA FLOW:
- INPUT: NFTEvent (sales), NFT (trait relationships), TraitValue/TraitType (trait catalog)
- OUTPUT: TraitPerformanceScore, TrendingTrait, TopTrait

USAGE BY:
- Marketplace vitality system (reads TraitPerformanceScore for trait_performance component)
- Analytics dashboard (displays trending and top traits)
"""

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from django.db import transaction as db_transaction
from django.db.models import Sum, Count, Avg, Q, Max, Min, F
from django.utils import timezone
from django.core.cache import cache
from asgiref.sync import sync_to_async
from tenacity import retry, stop_after_attempt, wait_fixed

# Core catalog models
from nft_data.models import (
    NFTCollection,
    NFT
)

# Raw indexer data
from indexer.models import NFTEvent

# Analytics outputs
from ..models import TraitPerformanceScore, TraitType, TraitValue, TrendingTrait, TopTrait 
  
# Import utilities
from .utils import safe_decimal_conversion

# Configure logging
logger = logging.getLogger(__name__)


class TraitAnalyticsService:
    """
    Service for calculating trait performance, trending traits, and top traits.
    
    This service is responsible for:
    - Calculating trait performance scores based on sales data
    - Identifying trending traits (24h + 7d windows)
    - Determining top-performing traits
    - Managing trait rarity recalculations after burns
    """
    
    def __init__(self):
        """Initialize the service with caching configuration."""
        self._trait_update_cache = {}
        self._trait_update_cooldown = 300  # 5 minutes cooldown
    
    # ==================== MAIN TRAIT METRICS UPDATE ====================
    
    async def update_trait_metrics(
        self, 
        collection_address: str, 
        force_update: bool = False, 
        burn_event_data: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        🚀 OPTIMIZED: Update trait metrics for a specific collection with smart activity detection.
        
        Args:
            collection_address: Collection address to update
            force_update: Force update regardless of activity
            burn_event_data: Optional burn event data to process
            
        Returns:
            Dict with update results, or None if skipped
        """
        # Acquire lock to prevent race conditions
        lock_key = f"trait_metrics_lock:{collection_address}"
        if not cache.add(lock_key, "locked", timeout=300):
            logger.info(f"⏳ Skipping trait metrics for {collection_address}: update in progress")
            return None
        
        try:
            logger.info(f"🔥 Updating trait metrics for collection {collection_address}")
            
            # Get collection object
            collection = await sync_to_async(
                NFTCollection.objects.get
            )(address=collection_address)
            
            # Handle burn events first (they always force an update)
            if burn_event_data:
                logger.info(f"🔥 Processing burn event for NFT {burn_event_data.get('mint_address', 'unknown')}")
                force_update = True
                
                # Move burned NFT to memories and remove from main collection
                await self._move_burned_nft_to_memories(collection, burn_event_data)
                
                # Recalculate collection supply and trait rarities after removal
                await self._recalculate_trait_rarities_after_burn(collection)
            
            # Smart activity-based skipping (unless forced)
            if not force_update:
                should_skip = await self._should_skip_trait_calculations(collection)
                
                if should_skip:
                    logger.info(f"⚡ Skipped trait metrics for {collection.name} - no activity")
                    return None
                else:
                    logger.info(f"🎯 Running trait metrics for {collection.name} - activity detected")
                
                # Check cooldown
                last_update = self._trait_update_cache.get(collection_address)
                if last_update and (timezone.now() - last_update).total_seconds() < self._trait_update_cooldown:
                    logger.debug(f"⏳ Skipping trait update for {collection_address} - within cooldown")
                    return None
            
            # Calculate trait performance scores
            logger.info(f"📊 Calculating trait performance scores for {collection.name}")
            await sync_to_async(self.calculate_trait_performance_scores)(
                collection_address=collection_address
            )
            
            # Update cache
            self._trait_update_cache[collection_address] = timezone.now()
            
            logger.info(f"✅ Successfully updated trait metrics for {collection.name}")
            
            return {
                'success': True,
                'collection': collection.name,
                'timestamp': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"❌ Error updating trait metrics for {collection_address}: {str(e)}")
            raise
        finally:
            # Release the lock
            cache.delete(lock_key)
    
    # ==================== ACTIVITY DETECTION ====================
    
    async def _should_skip_trait_calculations(self, collection: NFTCollection) -> bool:
        """
        🎯 SMART ACTIVITY DETECTION: Check multiple signals to determine if calculations should run.
        
        Returns:
            True if should SKIP, False if should RUN calculations
        """
        try:
            now = timezone.now()
            
            # 1. Check recent blockchain transactions
            recent_db_activity = await sync_to_async(
                NFTEvent.objects.filter(
                    collection_address=collection.address,
                    timestamp__gte=now - timedelta(hours=6),
                    event_type__in=['SALE', 'MINT', 'BURN']
                ).exists
            )()
            
            if recent_db_activity:
                logger.debug(f"🎯 Activity detected: Recent blockchain transactions for {collection.name}")
                return False  # Don't skip
            
            # 2. Check if APIs show current market activity
            recent_market_activity = await self._check_api_market_activity(collection)
            
            if recent_market_activity:
                logger.debug(f"🎯 Activity detected: Live market data from APIs for {collection.name}")
                return False  # Don't skip
            
            # 3. Check time-based fallback (force calculation every 24 hours)
            last_calculation = await self._get_last_trait_calculation_time(collection)
            
            if last_calculation:
                hours_since_last = (now - last_calculation).total_seconds() / 3600
                if hours_since_last >= 24:
                    logger.debug(f"🎯 Fallback triggered: 24+ hours since last calculation for {collection.name}")
                    return False  # Don't skip
            else:
                # No previous calculation found
                logger.debug(f"🎯 First-time calculation for {collection.name}")
                return False  # Don't skip
            
            # No activity detected and within time window
            logger.debug(f"⚡ No activity signals detected for {collection.name} - safe to skip")
            return True  # Skip calculations
            
        except Exception as e:
            logger.error(f"Error in activity detection for {collection.address}: {str(e)}")
            # On error, err on the side of running calculations
            return False
    
    async def _check_api_market_activity(self, collection: NFTCollection) -> bool:
        """
        Check if recent market stats show API activity.
        
        Returns:
            True if recent activity detected, False otherwise
        """
        try:
            from indexer.models import CollectionMarketStats
            
            # Check for very recent market stats with meaningful data
            recent_cutoff = timezone.now() - timedelta(hours=2)
            
            recent_stats = await sync_to_async(list)(
                CollectionMarketStats.objects.filter(
                    collection=collection,
                    timestamp__gte=recent_cutoff
                ).exclude(source='aggregated').order_by('-timestamp')
            )
            
            for stat in recent_stats:
                # Check for signs of market activity
                has_floor_price = stat.floor_price and float(stat.floor_price) > 0
                has_volume = stat.volume_24h and float(stat.volume_24h) > 0
                has_listings = stat.listed_count and stat.listed_count > 0
                has_sales = stat.sales_count_24h and stat.sales_count_24h > 0
                
                if has_floor_price or has_volume or has_listings or has_sales:
                    logger.debug(
                        f"🎯 API activity found: {stat.source} shows floor={stat.floor_price}, "
                        f"volume={stat.volume_24h}, listings={stat.listed_count}"
                    )
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking API market activity: {str(e)}")
            return False
    
    async def _get_last_trait_calculation_time(self, collection: NFTCollection) -> Optional[timezone.datetime]:
        """
        Get the timestamp of the last trait performance calculation for this collection.
        
        Returns:
            Datetime of last calculation, or None if never calculated
        """
        try:
            last_calc = await sync_to_async(
                TraitPerformanceScore.objects.filter(
                    collection=collection
                ).order_by('-updated_at').first
            )()
            
            return last_calc.updated_at if last_calc else None
            
        except Exception as e:
            logger.error(f"Error getting last calculation time: {str(e)}")
            return None
    
    # ==================== BURN EVENT HANDLING ====================
    
    async def _move_burned_nft_to_memories(self, collection: NFTCollection, burn_event_data: Dict):
        """
        Handle burn event by moving NFT to memories and cleaning up relationships.
        
        Args:
            collection: Collection containing the burned NFT
            burn_event_data: Dict containing burn event details (must include 'mint_address')
        """
        try:
            mint_address = burn_event_data.get('mint_address')
            if not mint_address:
                logger.warning("🔥 No mint_address in burn event data")
                return
            
            logger.info(f"🔥 Moving burned NFT {mint_address} to memories")
            
            # Get the NFT before moving it
            burned_nft = await sync_to_async(
                NFT.objects.filter(mint_address=mint_address).first
            )()
            
            if not burned_nft:
                logger.warning(f"🔥 Burned NFT {mint_address} not found in collection")
                return
            
            # Get all trait values BEFORE deletion
            trait_values = await sync_to_async(list)(burned_nft.trait_values.all())
            
            logger.info(f"🔥 NFT has {len(trait_values)} traits to remove from calculations")
            
            # Decrease trait counts for each trait
            for trait_value in trait_values:
                if trait_value.count > 0:
                    trait_value.count -= 1
                    await sync_to_async(trait_value.save)(update_fields=['count'])
                    logger.debug(
                        f"🔥 Decreased count for {trait_value.trait_type.name}="
                        f"{trait_value.value} to {trait_value.count}"
                    )
            
            # Handle analytics relationships before deletion
            # Remove from trending traits
            trending_traits = await sync_to_async(list)(
                TrendingTrait.objects.filter(nfts=burned_nft)
            )
            for trending in trending_traits:
                await sync_to_async(trending.nfts.remove)(burned_nft)
                # If no NFTs left, delete the trending trait record
                if await sync_to_async(trending.nfts.count)() == 0:
                    await sync_to_async(trending.delete)()
            
            # Remove from top traits
            top_traits = await sync_to_async(list)(
                TopTrait.objects.filter(nfts=burned_nft)
            )
            for top in top_traits:
                await sync_to_async(top.nfts.remove)(burned_nft)
                # If no NFTs left, delete the top trait record
                if await sync_to_async(top.nfts.count)() == 0:
                    await sync_to_async(top.delete)()
            
            # Prepare NFT data for memories storage
            nft_memory_data = {
                'name': burned_nft.name,
                'description': '',
                'image_url': burned_nft.image_url,
                'number': burned_nft.number,
                'rarity': {
                    tv.trait_type.name: {
                        'value': tv.value,
                        'rarity': float(tv.rarity)
                    } for tv in trait_values
                }
            }
            
            # Get the BurnEvent object
            from indexer.models import BurnEvent
            burn_event = await sync_to_async(
                BurnEvent.objects.filter(mint_address=mint_address).first
            )()
            
            if not burn_event:
                logger.error(f"🔥 BurnEvent not found for {mint_address}")
                return
            
            # Create NFTBurn record in memories
            from nftmemories.models import NFTBurn
            nft_burn_memory = await sync_to_async(NFTBurn.objects.create)(
                burn_event=burn_event,
                **nft_memory_data
            )
            
            logger.info(f"🔥 Created NFTBurn memory record: {nft_burn_memory.id}")
            
            # Delete the NFT from the main collection
            await sync_to_async(burned_nft.delete)()
            
            logger.info(f"🔥 Successfully moved NFT {mint_address} to memories")
            
        except Exception as e:
            logger.error(f"🔥 Error moving burned NFT to memories: {str(e)}")
            raise
    
    async def _recalculate_trait_rarities_after_burn(self, collection: NFTCollection):
        """
        Recalculate all trait rarities after NFT removal (supply decreased).
        
        Args:
            collection: Collection to recalculate rarities for
        """
        try:
            logger.info(f"🔥 Recalculating trait rarities after burn for {collection.name}")
            
            # Get NEW total supply (after NFT deletion)
            total_supply = await sync_to_async(collection.nfts.count)()
            
            if total_supply == 0:
                logger.warning(f"🔥 No NFTs left in collection {collection.name}")
                return
            
            logger.info(f"🔥 New total supply after burn: {total_supply}")
            
            # Get all trait types for this collection
            trait_types = await sync_to_async(list)(
                TraitType.objects.filter(collection=collection)
            )
            
            # Recalculate rarity for each trait value
            for trait_type in trait_types:
                trait_values = await sync_to_async(list)(
                    TraitValue.objects.filter(trait_type=trait_type)
                )
                
                for trait_value in trait_values:
                    # Rarity is now count / new_total_supply
                    if total_supply > 0:
                        new_rarity = (trait_value.count / total_supply) * 100
                        old_rarity = trait_value.rarity
                        
                        trait_value.rarity = new_rarity
                        await sync_to_async(trait_value.save)(update_fields=['rarity'])
                        
                        logger.debug(
                            f"🔥 Updated rarity for {trait_type.name}={trait_value.value}: "
                            f"{old_rarity:.2f}% → {new_rarity:.2f}%"
                        )
            
            # Update collection supply in market stats
            await self._update_collection_supply_after_burn(collection, total_supply)
            
            logger.info(f"🔥 Successfully recalculated trait rarities for {collection.name}")
            
        except Exception as e:
            logger.error(f"🔥 Error recalculating trait rarities after burn: {str(e)}")
            raise
    
    async def _update_collection_supply_after_burn(self, collection: NFTCollection, new_total_supply: int):
        """
        Update collection market stats with new supply after burn.
        
        Args:
            collection: Collection to update
            new_total_supply: New supply count after burn
        """
        try:
            from indexer.models import CollectionMarketStats
            
            # Update the latest aggregated market stats
            latest_stats = await sync_to_async(
                CollectionMarketStats.objects.filter(
                    collection=collection,
                    source='aggregated'
                ).order_by('-timestamp').first
            )()
            
            if latest_stats:
                old_supply = latest_stats.total_supply
                latest_stats.total_supply = new_total_supply
                await sync_to_async(latest_stats.save)(update_fields=['total_supply'])
                
                logger.info(f"🔥 Updated collection supply: {old_supply} → {new_total_supply}")
                
                # Recalculate percentage listed with new supply
                if new_total_supply > 0:
                    new_percent_listed = (latest_stats.listed_count / new_total_supply) * 100
                    latest_stats.percent_listed = safe_decimal_conversion(new_percent_listed)
                    await sync_to_async(latest_stats.save)(update_fields=['percent_listed'])
                    
                    logger.info(f"🔥 Updated percent listed: {new_percent_listed:.2f}%")
            
        except Exception as e:
            logger.error(f"🔥 Error updating collection supply after burn: {str(e)}")
    
    # ==================== TRAIT PERFORMANCE CALCULATION ====================
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def calculate_trait_performance_scores(self, collection_address: Optional[str] = None) -> Dict:
        """
        🚀 FULLY OPTIMIZED: Calculate trait performance with bulk operations and no N+1 queries.
        
        This method analyzes sales data to determine trait performance scores including:
        - Premium score (how much traits sell above floor)
        - Velocity score (how quickly traits sell)
        - Momentum score (price trend over time)
        - Overall performance score (0-100)
        
        Args:
            collection_address: Optional specific collection to calculate for
            
        Returns:
            Dict with calculation results
        """
        try:
            with db_transaction.atomic():
                now = timezone.now()
                analysis_period = now - timedelta(days=14)
                
                # Determine collections to process
                if collection_address:
                    collections = NFTCollection.objects.filter(
                        address=collection_address
                    ).select_related()
                else:
                    # Only process collections with recent sales
                    active_collection_addresses = NFTEvent.objects.filter(
                        timestamp__gte=now - timedelta(days=7),
                        event_type='SALE'
                    ).values_list('collection_address', flat=True).distinct()
                    
                    collections = NFTCollection.objects.filter(
                        address__in=active_collection_addresses
                    ).select_related()
                
                logger.info(f"🚀 Processing {collections.count()} active collections for trait performance")
                
                trait_performance_bulk = []
                
                for collection in collections:
                    logger.debug(f"Processing collection: {collection.name}")

                    # 🎯 LEVEL 1: Use clean, multi-sourced aggregated stats for floor price and supply
                    from indexer.models import AggregatedCollectionStats

                    try:
                        aggregated_stats = AggregatedCollectionStats.objects.get(collection=collection)
                        floor_price = aggregated_stats.floor_price if aggregated_stats.floor_price else 0.01
                        total_nfts = aggregated_stats.total_supply if aggregated_stats.total_supply else 0
                        logger.debug(
                            f"📊 Using Level 1 aggregated stats for {collection.name}: "
                            f"floor={floor_price}, supply={total_nfts}"
                        )
                    except AggregatedCollectionStats.DoesNotExist:
                        # Fallback to get_latest_stats() if aggregated stats not available
                        latest_stats = collection.get_latest_stats()
                        floor_price = latest_stats.floor_price if latest_stats else 0.01
                        total_nfts = latest_stats.total_supply if latest_stats else 0
                        logger.warning(
                            f"⚠️ No aggregated stats for {collection.name}, using fallback: "
                            f"floor={floor_price}, supply={total_nfts}"
                        )
                    
                    # Get sales transactions for this collection
                    collection_txns = NFTEvent.objects.filter(
                        collection_address=collection.address,
                        event_type='SALE',
                        timestamp__gte=analysis_period
                    ).select_related(
                        'nft'
                    ).prefetch_related(
                        'nft__trait_values__trait_type'
                    )
                    
                    # Need minimum sales for meaningful analysis
                    if collection_txns.count() < 5:
                        continue
                    
                    # Build trait performance data
                    trait_premium_map = {}
                    trait_avg_sale_price_map = {}
                    
                    for transaction in collection_txns:
                        if not transaction.nft:
                            continue
                        
                        sale_price = float(transaction.amount)
                        price_ratio = sale_price / float(floor_price) if float(floor_price) > 0 else 1.0
                        
                        for trait_value in transaction.nft.trait_values.all():
                            trait_id = trait_value.id
                            
                            if trait_id not in trait_premium_map:
                                trait_premium_map[trait_id] = []
                                trait_avg_sale_price_map[trait_id] = []
                            
                            trait_premium_map[trait_id].append({
                                'price_ratio': price_ratio,
                                'timestamp': transaction.timestamp,
                                'marketplace': transaction.marketplace
                            })
                            trait_avg_sale_price_map[trait_id].append(sale_price)
                    
                    # Get all trait values for this collection
                    trait_values = TraitValue.objects.filter(
                        nfts__collection=collection
                    ).select_related('trait_type').prefetch_related('nfts').distinct()
                    
                    # Pre-fetch all trait counts in one query (no N+1)
                    trait_counts_qs = TraitValue.objects.filter(
                        trait_type__collection=collection
                    ).annotate(nft_count=Count('nfts')).values('id', 'nft_count')
                    trait_count_map = {item['id']: item['nft_count'] for item in trait_counts_qs}
                    
                    # Calculate performance for each trait
                    for trait_value in trait_values:
                        trait_id = trait_value.id
                        
                        # Count recent sales for this trait
                        recent_sales = sum(
                            1 for txn in collection_txns 
                            if txn.nft and trait_value in txn.nft.trait_values.all()
                        )
                        
                        # Use pre-fetched count
                        total_with_trait = trait_count_map.get(trait_id, 0)
                        
                        # Calculate velocity
                        velocity = recent_sales / total_with_trait if total_with_trait > 0 else 0
                        
                        # Calculate rarity
                        rarity = (total_with_trait / total_nfts * 100) if total_nfts > 0 else 0
                        
                        # Calculate momentum (price trend)
                        premium_data = trait_premium_map.get(trait_id, [])
                        momentum = 0
                        
                        if len(premium_data) >= 3:
                            premium_data.sort(key=lambda x: x['timestamp'])
                            mid_point = len(premium_data) // 2
                            early_avg = sum(p['price_ratio'] for p in premium_data[:mid_point]) / mid_point
                            recent_avg = sum(p['price_ratio'] for p in premium_data[mid_point:]) / (len(premium_data) - mid_point)
                            momentum = (recent_avg - early_avg) / early_avg if early_avg > 0 else 0
                        
                        # Calculate premium (average price ratio)
                        premium = sum(p['price_ratio'] for p in premium_data) / len(premium_data) if premium_data else 1.0
                        
                        # Calculate average sale price
                        avg_sale_price = (
                            sum(trait_avg_sale_price_map.get(trait_id, [])) / 
                            len(trait_avg_sale_price_map.get(trait_id, [1]))
                            if trait_avg_sale_price_map.get(trait_id) else 0
                        )
                        
                        # Calculate overall performance score
                        # Formula: (50% premium) + (30% velocity) + (20% momentum)
                        # Expected ranges: premium (0.8-2.0), velocity*10 (0-5), momentum+1 (0-2)
                        # Typical raw score: 0.5-4.0
                        performance_score = ((0.5 * premium) + (0.3 * velocity * 10) + (0.2 * (momentum + 1)))

                        # Normalize to 0-100 scale
                        # Using factor of 15 instead of 20 to utilize full range better
                        # Raw score of ~6.67 = 100 (very high performance trait)
                        normalized_score = min(100, max(0, performance_score * 15))
                        
                        # Create performance record
                        trait_performance_bulk.append(
                            TraitPerformanceScore(
                                trait_type=trait_value.trait_type,
                                trait_value=trait_value,
                                collection=collection,
                                rarity_score=rarity,
                                avg_sale_price=Decimal(str(avg_sale_price)),
                                premium_score=premium,
                                velocity_score=velocity,
                                momentum_score=momentum,
                                performance_score=normalized_score,
                                last_sale_date=now,
                                updated_at=now
                            )
                        )
                
                # Bulk create/update trait performance scores
                if trait_performance_bulk:
                    # Delete old scores for these collections
                    collection_addresses = [p.collection.address for p in trait_performance_bulk]
                    TraitPerformanceScore.objects.filter(
                        collection__address__in=collection_addresses
                    ).delete()
                    
                    # Bulk create new scores
                    TraitPerformanceScore.objects.bulk_create(
                        trait_performance_bulk,
                        batch_size=500
                    )
                    
                    logger.info(f"✅ Created {len(trait_performance_bulk)} trait performance scores")
                
                return {
                    'success': True,
                    'collections_processed': collections.count(),
                    'trait_scores_created': len(trait_performance_bulk),
                    'timestamp': now
                }
                
        except Exception as e:
            logger.error(f"Error calculating trait performance scores: {str(e)}")
            raise
    
    # ==================== TRENDING TRAITS ====================
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def calculate_and_store_trending_traits(self, collection_address: Optional[str] = None) -> Dict:
        """
        Calculate trending traits based on recent activity (24h + 7d windows).
        
        Trending score combines:
        - Activity score (sales frequency)
        - Volume score (total volume)
        - Performance score (existing performance metric)
        - Momentum score (price trend)
        
        Args:
            collection_address: Optional specific collection to calculate for
            
        Returns:
            Dict with calculation results
        """
        try:
            logger.info("📈 Calculating trending traits (24h + 7d)...")
            
            # Clear existing trending traits
            TrendingTrait.objects.all().delete()
            
            now = timezone.now()
            period_24h = now - timedelta(hours=24)
            period_7d = now - timedelta(days=7)
            
            # Get collections to analyze
            collections = NFTCollection.objects.all()
            if collection_address:
                collections = collections.filter(address=collection_address)
            
            trending_count = 0
            
            for collection in collections:
                try:
                    # Get trait performance scores for this collection
                    trait_performances = TraitPerformanceScore.objects.filter(
                        collection=collection
                    )
                    
                    if not trait_performances.exists():
                        continue
                    
                    for performance in trait_performances:
                        trait_type = performance.trait_type
                        trait_value = performance.trait_value
                        
                        # Calculate 24h trending score
                        trend_24h = self._calculate_trending_score(
                            trait_type, 
                            trait_value, 
                            period_24h, 
                            performance.performance_score
                        )
                        
                        # Calculate 7d trending score
                        trend_7d = self._calculate_trending_score(
                            trait_type, 
                            trait_value, 
                            period_7d, 
                            performance.performance_score
                        )
                        
                        # Combine scores (24h gets higher weight for "trending")
                        combined_trend_score = (trend_24h * 0.7) + (trend_7d * 0.3)
                        
                        # Get NFTs with this trait that had recent activity
                        trending_nfts = NFT.objects.filter(
                            trait_values=trait_value,
                            collection=collection,
                            is_burned=False,
                            events__event_type='SALE',
                            events__timestamp__gte=period_7d
                        ).distinct()
                        
                        trait_count = trending_nfts.count()
                        
                        # Store trending trait if score is significant
                        if combined_trend_score >= 10 and trait_count > 0:
                            trending_trait = TrendingTrait.objects.create(
                                trait_type=trait_type,
                                trait_value=trait_value,
                                collection=collection,
                                count=trait_count,
                                trend_score=combined_trend_score
                            )
                            
                            # Add NFT relationships
                            trending_trait.nfts.set(trending_nfts)
                            trending_count += 1
                    
                    logger.debug(f"📈 Processed trending traits for {collection.name}")
                    
                except Exception as e:
                    logger.error(f"📈 Error processing trending traits for {collection.name}: {str(e)}")
                    continue
            
            logger.info(f"📈 Successfully calculated {trending_count} trending traits")
            
            return {
                'success': True,
                'trending_traits_created': trending_count,
                'timestamp': now
            }
            
        except Exception as e:
            logger.error(f"📈 Error calculating trending traits: {str(e)}")
            raise
    
    def _calculate_trending_score(
        self, 
        trait_type: TraitType, 
        trait_value: TraitValue, 
        period_start: timezone.datetime, 
        base_performance_score: float
    ) -> float:
        """
        Calculate trending score for a specific time period.
        
        Args:
            trait_type: Trait type
            trait_value: Trait value
            period_start: Start of the period to analyze
            base_performance_score: Existing performance score (0-100)
            
        Returns:
            Trending score (0-100)
        """
        try:
            # Get sales for this trait in the period
            recent_sales = NFTEvent.objects.filter(
                nft__trait_values=trait_value,
                event_type='SALE',
                timestamp__gte=period_start
            )
            
            if not recent_sales.exists():
                return 0
            
            sales_count = recent_sales.count()
            total_volume = sum(float(sale.amount) for sale in recent_sales if sale.amount)
            
            # Calculate activity score (sales frequency)
            activity_score = min(30, sales_count * 3)  # Max 30
            
            # Calculate volume score
            volume_score = min(25, total_volume * 2)  # Max 25
            
            # Use existing performance score as base
            performance_component = min(45, base_performance_score * 0.45)  # Max 45
            
            # Calculate momentum (price trend within period)
            momentum_score = 0
            if sales_count >= 2:
                sales_list = list(recent_sales.order_by('timestamp'))
                early_sales = sales_list[:len(sales_list)//2]
                recent_sales_subset = sales_list[len(sales_list)//2:]
                
                early_avg = (
                    sum(float(s.amount) for s in early_sales if s.amount) / len(early_sales)
                    if early_sales else 0
                )
                recent_avg = (
                    sum(float(s.amount) for s in recent_sales_subset if s.amount) / len(recent_sales_subset)
                    if recent_sales_subset else 0
                )
                
                if early_avg > 0:
                    momentum = ((recent_avg - early_avg) / early_avg) * 100
                    momentum_score = max(0, min(20, momentum))  # Positive momentum only, max 20
            
            trending_score = activity_score + volume_score + performance_component + momentum_score
            return min(100, trending_score)
            
        except Exception as e:
            logger.error(f"📈 Error calculating trending score: {str(e)}")
            return 0
    
    # ==================== TOP TRAITS ====================
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def calculate_and_store_top_traits(self, collection_address: Optional[str] = None) -> Dict:
        """
        Calculate top traits based on overall performance.
        
        Top trait score combines:
        - Performance score (60% weight)
        - Rarity score (25% weight - inverse rarity)
        - Volume score (15% weight)
        
        Args:
            collection_address: Optional specific collection to calculate for
            
        Returns:
            Dict with calculation results
        """
        try:
            logger.info("🏆 Calculating top traits...")
            
            # Clear existing top traits
            TopTrait.objects.all().delete()
            
            # Get collections to analyze
            collections = NFTCollection.objects.all()
            if collection_address:
                collections = collections.filter(address=collection_address)
            
            top_traits_count = 0
            
            for collection in collections:
                try:
                    # Get trait performance scores for this collection
                    trait_performances = TraitPerformanceScore.objects.filter(
                        collection=collection
                    ).order_by('-performance_score')
                    
                    if not trait_performances.exists():
                        continue
                    
                    for performance in trait_performances:
                        trait_type = performance.trait_type
                        trait_value = performance.trait_value
                        
                        # Primary: Performance score (60% weight)
                        performance_component = performance.performance_score * 0.6
                        
                        # Secondary: Rarity score (25% weight - inverse rarity)
                        rarity_component = (
                            (100 - float(performance.rarity_score)) * 0.25
                            if performance.rarity_score else 0
                        )
                        
                        # Tertiary: Volume score (15% weight)
                        volume_component = min(100, float(performance.avg_sale_price) * 10) * 0.15
                        
                        # Combined score
                        combined_score = performance_component + rarity_component + volume_component
                        
                        # Get NFTs with this trait
                        trait_nfts = NFT.objects.filter(
                            trait_values=trait_value,
                            collection=collection,
                            is_burned=False
                        )
                        
                        if trait_nfts.exists():
                            top_trait = TopTrait.objects.create(
                                trait_type=trait_type,
                                trait_value=trait_value,
                                collection=collection,
                                rarity_score=100 - performance.rarity_score if performance.rarity_score else 0,
                                volume_score=min(100, float(performance.avg_sale_price * 10)),
                                count_score=performance.performance_score,
                                combined_score=combined_score
                            )
                            
                            # Add NFT relationships
                            top_trait.nfts.set(trait_nfts)
                            top_traits_count += 1
                    
                    logger.debug(f"🏆 Processed top traits for {collection.name}")
                    
                except Exception as e:
                    logger.error(f"🏆 Error processing top traits for {collection.name}: {str(e)}")
                    continue
            
            logger.info(f"🏆 Successfully calculated {top_traits_count} top traits")
            
            return {
                'success': True,
                'top_traits_created': top_traits_count,
                'timestamp': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"🏆 Error calculating top traits: {str(e)}")
            raise


# Export the service
__all__ = ['TraitAnalyticsService']