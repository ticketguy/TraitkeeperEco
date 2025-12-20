# analytics/services/market_aggregation.py
"""
Market Aggregation Service

Handles multi-source market data aggregation, validation, and calculation.

DATA FLOW:
- INPUT: CollectionMarketStats (from various providers: MagicEden, Tensor, blockchain, etc.)
- PROCESSING: Validation, intelligent aggregation, historical calculations
- OUTPUT: Aggregated CollectionMarketStats with comprehensive metrics

CORE RESPONSIBILITIES:
1. Read pre-fetched data from multiple sources (APIs + blockchain)
2. Validate and score data quality
3. Intelligently aggregate fields using source-specific rules
4. Calculate historical changes (24h, 7d, 30d)
5. Derive advanced metrics and analytics scores
6. Store aggregated results back to CollectionMarketStats

USAGE:
    from analytics.services.market_aggregation import MarketAggregationService
    
    service = MarketAggregationService()
    await service.update_collection_metrics(collection)
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
from nft_data.models import NFTCollection, NFT

# Raw indexer data
from indexer.models import (
    CollectionMarketStats,
    NFTEvent,
    NFTListing
)

# Import utilities
from .utils import (
    get_metrics_cache,
    save_metrics_cache,
    safe_decimal_conversion,
    calculate_overall_confidence,
    get_calculated_metrics_attribution,
    empty_aggregated_result
)

# Configure logging
logger = logging.getLogger(__name__)


class MarketAggregationService:
    """
    Service for aggregating market data from multiple sources and calculating
    comprehensive collection metrics.
    
    This service is the CORE of the analytics pipeline. It:
    1. Reads pre-fetched data from CollectionMarketStats (various sources)
    2. Enriches incomplete data with calculated fields
    3. Validates and scores data quality
    4. Intelligently aggregates fields using source-specific rules
    5. Calculates historical changes and derived metrics
    6. Stores the final aggregated record
    
    The aggregated data is then consumed by:
    - Marketplace vitality system (reads aggregated CollectionMarketStats)
    - Frontend dashboards (displays aggregated metrics)
    - Trait analytics (uses market context for trait performance)
    """
    
    def __init__(self):
        """Initialize the service."""
        logger.info("Initialized MarketAggregationService")
    
    # ==================== MAIN AGGREGATION METHOD ====================
    
    async def update_collection_metrics(self, collection: NFTCollection) -> Optional[Dict]:
        """
        MAIN METHOD: Aggregate market metrics for a collection from multiple sources.
        
        This method orchestrates the entire aggregation pipeline:
        1. Read pre-fetched data from database
        2. Enrich incomplete sources with calculations
        3. Process and validate all source data
        4. Create intelligent aggregations
        5. Calculate analytics and derived metrics
        6. Store aggregated record
        7. Cache results
        
        Args:
            collection: NFTCollection instance to update
            
        Returns:
            Dict with aggregated metrics and metadata, or None if failed
            
        Example:
            >>> service = MarketAggregationService()
            >>> result = await service.update_collection_metrics(collection)
            >>> print(f"Floor: {result['data']['floor_price']}")
        """
        logger.info(
            f"AnalyticsService: Received request to update metrics for collection "
            f"'{collection.name}' ({collection.address})"
        )
        
        try:
            cache_key = f"collection_metrics:{collection.address}"
            
            # Check cache first
            cached_metrics = await get_metrics_cache(cache_key)
            if cached_metrics:
                logger.info(f"Using cached metrics for {collection.address}")
                return cached_metrics

            # Step 1: READ pre-fetched data from the database
            logger.info(f"📖 [STEP 1/7] Reading pre-fetched market stats from DB for {collection.name}")
            latest_stats_records = await sync_to_async(list)(
                CollectionMarketStats.objects.filter(
                    collection=collection
                ).order_by('source', '-timestamp').distinct('source')
            )

            if not latest_stats_records:
                logger.warning(
                    f"⚠️  No market stats found in DB for {collection.address}. "
                    f"Cannot calculate metrics."
                )
                return None

            logger.info(f"✅ Found {len(latest_stats_records)} market stat sources: {[r.source for r in latest_stats_records]}")

            # Convert DB records to raw data sources format
            raw_data_sources = {}
            for record in latest_stats_records:
                raw_data_sources[record.source] = {
                    'source': record.source,
                    'success': True,
                    'data': record.raw_data,
                    'metadata': {
                        'data_freshness': record.timestamp,
                        'source_authority': 'high'
                    }
                }

            # Step 2: ENRICH data for sources with incomplete info
            logger.info(f"🔧 [STEP 2/7] Enriching data sources with derived metrics for {collection.name}")
            providers_needing_derivation = ['magic_eden']  # Add others as needed
            enriched_count = 0
            for provider_name in providers_needing_derivation:
                if provider_name in raw_data_sources and raw_data_sources[provider_name]['success']:
                    logger.info(f"   → Deriving missing fields for '{provider_name}'")
                    base_data = raw_data_sources[provider_name]['data']
                    derived_data = await self._derive_missing_fields(
                        collection,
                        base_data,
                        provider_name
                    )
                    # Add the newly calculated fields back into the data dictionary
                    raw_data_sources[provider_name]['data'].update(derived_data)
                    enriched_count += 1
                    logger.info(f"   ✅ Derived {len(derived_data)} fields: {list(derived_data.keys())}")

            if enriched_count == 0:
                logger.info(f"   ⊘ No sources required enrichment")

            # Step 3: Process and validate all source data
            logger.info(f"✔️  [STEP 3/7] Validating and scoring data quality for {collection.name}")
            processed_sources = await self._process_and_validate_source_data(raw_data_sources)
            successful_count = sum(1 for s in processed_sources.values() if s.get('success', False))
            logger.info(f"✅ Validated {successful_count}/{len(processed_sources)} sources successfully")
            
            # Step 4: Create aggregated metrics with source attribution
            logger.info(f"🔀 [STEP 4/7] Aggregating metrics from multiple sources for {collection.name}")
            aggregated_metrics = await self._create_intelligent_aggregated_metrics(
                processed_sources
            )
            if aggregated_metrics.get('success'):
                sources_used = aggregated_metrics['metadata']['sources_used']
                logger.info(f"✅ Aggregated data from {len(sources_used)} sources: {sources_used}")
                logger.info(f"   → Floor: {aggregated_metrics['data'].get('floor_price', 0)}, "
                           f"Volume 24h: {aggregated_metrics['data'].get('volume_24h', 0)}, "
                           f"Listed: {aggregated_metrics['data'].get('listed_count', 0)}")
            else:
                logger.warning(f"⚠️  Aggregation failed for {collection.name}")

            # Step 5: Calculate final analytics and derived metrics
            logger.info(f"📊 [STEP 5/7] Calculating analytics and derived metrics for {collection.name}")
            enhanced_metrics = await self._calculate_analytics_and_derived_metrics(
                collection,
                aggregated_metrics,
                processed_sources
            )
            if enhanced_metrics.get('success'):
                logger.info(f"✅ Calculated derived metrics:")
                logger.info(f"   → Market Efficiency: {enhanced_metrics['data'].get('market_efficiency_score', 0):.1f}")
                logger.info(f"   → Holder Confidence: {enhanced_metrics['data'].get('holder_confidence_index', 0):.1f}")
                logger.info(f"   → Liquidity Health: {enhanced_metrics['data'].get('liquidity_health_score', 0):.1f}")
                logger.info(f"   → Overall Health: {enhanced_metrics['data'].get('overall_health_score', 0):.1f}")

            # Step 6: Store the final aggregated record
            logger.info(f"💾 [STEP 6/7] Storing aggregated record to database for {collection.name}")
            await self._store_aggregated_record(collection, enhanced_metrics)
            logger.info(f"✅ Database record updated successfully")

            # Step 7: Cache the final result
            logger.info(f"🗂️  [STEP 7/7] Caching final metrics for {collection.name}")
            await save_metrics_cache(
                cache_key,
                enhanced_metrics,
                timeout=3600,
                collection_address=collection.address
            )
            logger.info(f"✅ Metrics cached for 1 hour")

            logger.info(f"🎉 Successfully completed all 7 steps for {collection.name}")
            return enhanced_metrics
            
        except Exception as e:
            logger.error(f"Error in update_collection_metrics for {collection.address}: {str(e)}")
            raise
    
    # ==================== DATA ENRICHMENT ====================
    
    async def _derive_missing_fields(
        self,
        collection: NFTCollection,
        base_data: dict,
        source_name: str
    ) -> dict:
        """
        Derive missing metrics for sources with incomplete data.
        
        Uses historical stats from the database to calculate percentage changes
        and estimates other missing fields using heuristics.
        
        Args:
            collection: Collection to calculate for
            base_data: Base data from the source
            source_name: Name of the source (e.g., 'magic_eden')
            
        Returns:
            Dict of derived fields to merge with base_data
            
        Example:
            >>> base = {'floor_price': 5.5, 'listed_count': 100}
            >>> derived = await service._derive_missing_fields(collection, base, 'magic_eden')
            >>> # derived = {'price_change_24h': 10.5, 'highest_bid': 4.95, ...}
        """
        try:
            cutoff_24h = timezone.now() - timedelta(hours=24)
            cutoff_7d = timezone.now() - timedelta(days=7)
            
            # Get previous stats for the specific source to calculate price changes
            prev_stats_24h = await sync_to_async(
                CollectionMarketStats.objects.filter(
                    collection=collection,
                    source=source_name,
                    timestamp__lt=cutoff_24h
                ).order_by('-timestamp').first
            )()
            
            prev_stats_7d = await sync_to_async(
                CollectionMarketStats.objects.filter(
                    collection=collection,
                    source=source_name,
                    timestamp__lt=cutoff_7d
                ).order_by('-timestamp').first
            )()
            
            current_floor = base_data.get('floor_price', 0)
            
            # Calculate price changes
            price_change_24h = 0.0
            if prev_stats_24h and prev_stats_24h.floor_price and float(prev_stats_24h.floor_price) > 0:
                price_change_24h = (
                    (current_floor - float(prev_stats_24h.floor_price)) 
                    / float(prev_stats_24h.floor_price)
                ) * 100
            
            price_change_7d = 0.0
            if prev_stats_7d and prev_stats_7d.floor_price and float(prev_stats_7d.floor_price) > 0:
                price_change_7d = (
                    (current_floor - float(prev_stats_7d.floor_price)) 
                    / float(prev_stats_7d.floor_price)
                ) * 100
            
            # Estimate fields that are commonly missing from simpler APIs
            highest_bid = current_floor * 0.9 if current_floor > 0 else 0.0
            
            total_supply = await sync_to_async(collection.nfts.count)()
            percent_listed = (
                (base_data.get('listed_count', 0) / total_supply * 100) 
                if total_supply > 0 else 0.0
            )
            
            bid_count = int(base_data.get('listed_count', 0) * 0.2)  # Simple estimation
            
            market_cap = current_floor * total_supply if total_supply > 0 else 0.0
            
            return {
                'highest_bid': highest_bid,
                'price_change_24h': price_change_24h,
                'price_change_7d': price_change_7d,
                'percent_listed': percent_listed,
                'bid_count': bid_count,
                'market_cap': market_cap,
            }
            
        except Exception as e:
            logger.warning(f"Failed to derive missing fields for source '{source_name}': {str(e)}")
            return {
                'highest_bid': 0.0,
                'price_change_24h': 0.0,
                'price_change_7d': 0.0,
                'percent_listed': 0.0,
                'bid_count': 0,
                'market_cap': 0.0,
            }
    
    # ==================== DATA PROCESSING AND VALIDATION ====================
    
    async def _process_and_validate_source_data(
        self,
        raw_data_sources: Dict
    ) -> Dict:
        """
        Process and validate data from each source, assign quality scores.
        
        Each source is:
        1. Validated for data completeness
        2. Cleaned of invalid values
        3. Scored for data quality
        4. Classified by reliability tier
        
        Args:
            raw_data_sources: Dict of source_name -> source data
            
        Returns:
            Dict of source_name -> processed and scored data
        """
        processed_sources = {}
        
        for source_name, source_result in raw_data_sources.items():
            try:
                if not source_result.get('success', False):
                    processed_sources[source_name] = source_result
                    continue
                
                data = source_result['data']
                metadata = source_result.get('metadata', {})
                
                # Validate and clean the data
                validated_data = self._validate_and_clean_data(data, source_name)
                
                # Calculate data quality score
                quality_score = self._calculate_data_quality_score(
                    validated_data,
                    source_name,
                    metadata
                )
                
                processed_sources[source_name] = {
                    'source': source_name,
                    'success': True,
                    'data': validated_data,
                    'quality_score': quality_score,
                    'metadata': metadata
                }
                
                logger.debug(
                    f"Processed {source_name}: "
                    f"quality={quality_score:.2f}"
                )
                
            except Exception as e:
                logger.error(f"Error processing {source_name}: {str(e)}")
                processed_sources[source_name] = {
                    'source': source_name,
                    'success': False,
                    'error': str(e)
                }
        
        return processed_sources
    
    def _validate_and_clean_data(self, data: dict, source_name: str) -> dict:
        """
        Validate and clean data from a source.
        
        Removes:
        - Negative values (prices, volumes, counts)
        - Infinity and NaN values
        - Unrealistic outliers
        
        Args:
            data: Raw data dict
            source_name: Name of the source
            
        Returns:
            Cleaned data dict
        """
        cleaned = {}
        
        # Numeric fields that should be >= 0
        numeric_fields = [
            'floor_price', 'volume_24h', 'volume_7d', 'volume_30d', 'total_volume',
            'listed_count', 'total_supply', 'number_of_holders', 'highest_bid',
            'bid_count', 'market_cap', 'sales_count_24h', 'sales_count_7d',
            'sales_count_all'
        ]
        
        for field in numeric_fields:
            if field in data:
                value = safe_decimal_conversion(data[field])
                # Ensure non-negative
                cleaned[field] = max(0, float(value))
        
        # Percentage fields (-100% to +infinity, but realistically cap at ±1000%)
        percentage_fields = [
            'price_change_24h', 'price_change_7d', 'percent_listed',
            'listing_change_24h', 'listing_change_7d'
        ]
        
        for field in percentage_fields:
            if field in data:
                value = safe_decimal_conversion(data[field])
                # Cap at reasonable range
                cleaned[field] = max(-100, min(1000, float(value)))
        
        # Pass through other fields
        for key, value in data.items():
            if key not in cleaned:
                cleaned[key] = value
        
        return cleaned
    
    def _calculate_data_quality_score(
        self,
        data: dict,
        source_name: str,
        metadata: dict
    ) -> float:
        """
        Calculate quality score for source data (0.0 to 1.0).
        
        Quality factors:
        - Data completeness (how many fields are present)
        - Data freshness (how recent is the data)
        - Source reliability tier
        - Data consistency (realistic values)
        
        Args:
            data: Validated data dict
            source_name: Name of the source
            metadata: Source metadata
            
        Returns:
            Quality score between 0.0 and 1.0
        """
        score_components = []
        
        # 1. Completeness score (40% weight)
        required_fields = ['floor_price', 'volume_24h', 'listed_count', 'total_supply']
        optional_fields = [
            'volume_7d', 'highest_bid', 'price_change_24h',
            'bid_count', 'number_of_holders'
        ]
        
        required_present = sum(1 for f in required_fields if data.get(f, 0) > 0)
        optional_present = sum(1 for f in optional_fields if data.get(f, 0) > 0)
        
        completeness = (
            (required_present / len(required_fields)) * 0.7 +
            (optional_present / len(optional_fields)) * 0.3
        )
        score_components.append(('completeness', completeness, 0.4))
        
        # 2. Freshness score (30% weight)
        data_freshness = metadata.get('data_freshness')
        if data_freshness:
            age_minutes = (timezone.now() - data_freshness).total_seconds() / 60
            # Decay: 1.0 if fresh (<5 min), 0.5 if old (>60 min)
            freshness = max(0.5, 1.0 - (age_minutes / 120))
        else:
            freshness = 0.7  # Assume reasonably fresh if unknown
        score_components.append(('freshness', freshness, 0.3))
        
        # 3. Source reliability tier (30% weight)
        source_tiers = {
            'blockchain': 1.0,      # Most authoritative
            'tensor': 0.95,         # High quality API
            'magic_eden': 0.9,      # Good quality API
            'traitkeeper': 0.85,    # Reliable aggregator
        }
        reliability = source_tiers.get(source_name, 0.7)
        score_components.append(('reliability', reliability, 0.3))
        
        # Calculate weighted score
        total_score = sum(score * weight for _, score, weight in score_components)
        
        logger.debug(
            f"Quality score for {source_name}: {total_score:.2f} "
            f"(completeness={completeness:.2f}, freshness={freshness:.2f}, "
            f"reliability={reliability:.2f})"
        )
        
        return total_score
    
    # ==================== INTELLIGENT AGGREGATION ====================
    
    async def _create_intelligent_aggregated_metrics(
        self,
        processed_sources: Dict
    ) -> Dict:
        """
        Create aggregated metrics using intelligent source-specific rules.
        
        Different fields use different aggregation strategies:
        - Floor price: Minimum across marketplaces (true market floor)
        - Volume: Sum from unique sources (avoid double-counting)
        - Listed count: Maximum (most comprehensive view)
        - Supply: Prefer blockchain source (most authoritative)
        - Shared fields: Best quality source or average if tied
        
        Args:
            processed_sources: Dict of validated source data
            
        Returns:
            Dict with aggregated data and source attribution metadata
        """
        successful_sources = {
            name: data for name, data in processed_sources.items()
            if data.get('success', False)
        }
        
        if not successful_sources:
            logger.warning("No successful sources for aggregation")
            return empty_aggregated_result()
        
        # Apply intelligent aggregation rules
        aggregated_data, source_attribution = self._aggregate_fields_intelligently(
            successful_sources
        )
        
        logger.info(
            f"Aggregated metrics from {len(successful_sources)} sources: "
            f"{list(successful_sources.keys())}"
        )
        
        return {
            'source': 'aggregated',
            'success': True,
            'data': aggregated_data,
            'metadata': {
                'aggregation_method': 'intelligent_multi_source',
                'sources_used': list(successful_sources.keys()),
                'source_attribution': source_attribution,
                'aggregated_at': timezone.now(),
                'overall_confidence': calculate_overall_confidence(
                    list(successful_sources.values()),
                    source_attribution
                )
            }
        }
    
    def _aggregate_fields_intelligently(
        self,
        successful_sources: Dict
    ) -> Tuple[Dict, Dict]:
        """
        Apply intelligent aggregation rules for each field.
        
        Returns:
            Tuple of (aggregated_data, source_attribution)
        """
        aggregated_data = {}
        source_attribution = {}
        
        # Floor price: Use minimum across marketplaces (true market floor) - no blockchain
        floor_prices = {}
        for name, source in successful_sources.items():
            if name in ['magic_eden', 'tensor', 'traitkeeper']:
                floor = source['data'].get('floor_price', 0)
                if floor > 0:
                    floor_prices[name] = floor
        
        if floor_prices:
            min_floor = min(floor_prices.values())
            floor_source = min(floor_prices.items(), key=lambda x: x[1])[0]
            aggregated_data['floor_price'] = min_floor
            source_attribution['floor_price'] = {
                'value': min_floor,
                'source': floor_source,
                'method': 'minimum_across_marketplaces',
                'all_sources': floor_prices,
                'confidence': successful_sources[floor_source]['quality_score']
            }
        
        # Volume: Use blockchain + traitkeeper (avoid double counting marketplace volumes)
        volume_24h = 0
        volume_sources = []
        for name in ['blockchain', 'traitkeeper']:
            if name in successful_sources:
                vol = successful_sources[name]['data'].get('volume_24h', 0)
                if vol > 0:
                    volume_24h += vol
                    volume_sources.append(name)
        
        aggregated_data['volume_24h'] = volume_24h
        source_attribution['volume_24h'] = {
            'value': volume_24h,
            'source': '+'.join(volume_sources) if volume_sources else 'none',
            'method': 'sum_unique_transactions',
            'confidence': 0.8 if volume_sources else 0.0
        }
        
        # Listed count: Use maximum (most comprehensive view)
        listed_counts = {}
        for name, source in successful_sources.items():
            listed_count = source['data'].get('listed_count', 0)
            if listed_count > 0:
                listed_counts[name] = listed_count
        
        if listed_counts:
            max_listed = max(listed_counts.values())
            listed_source = max(listed_counts.items(), key=lambda x: x[1])[0]
            aggregated_data['listed_count'] = max_listed
            source_attribution['listed_count'] = {
                'value': max_listed,
                'source': listed_source,
                'method': 'maximum_across_sources',
                'all_sources': listed_counts,
                'confidence': successful_sources[listed_source]['quality_score']
            }
        
        # Total supply: Prefer blockchain (most authoritative)
        total_supply = 0
        supply_source = 'none'
        
        priority_sources = ['blockchain', 'tensor', 'magic_eden']
        for name in priority_sources:
            if name in successful_sources:
                supply = successful_sources[name]['data'].get('total_supply', 0)
                if supply > 0:
                    total_supply = supply
                    supply_source = name
                    break
        
        aggregated_data['total_supply'] = total_supply
        source_attribution['total_supply'] = {
            'value': total_supply,
            'source': supply_source,
            'method': 'authoritative_source_priority',
            'confidence': (
                successful_sources[supply_source]['quality_score'] 
                if supply_source != 'none' else 0.0
            )
        }
        
        # Shared fields: Select best quality source or average if both available
        shared_fields = {
            'highest_bid': ['tensor', 'magic_eden'],
            'price_change_24h': ['tensor', 'magic_eden'],
            'price_change_7d': ['tensor', 'magic_eden'],
            'percent_listed': ['tensor', 'magic_eden'],
            'bid_count': ['tensor', 'magic_eden'],
            'market_cap': ['tensor', 'magic_eden'],
        }
        
        for field, possible_sources in shared_fields.items():
            candidates = {}
            for source_name in possible_sources:
                if source_name in successful_sources:
                    field_value = successful_sources[source_name]['data'].get(field, None)
                    if field_value is not None:
                        candidates[source_name] = {
                            'value': field_value,
                            'quality': successful_sources[source_name]['quality_score']
                        }
            
            if candidates:
                # Select best quality or average if tie/difference < 0.1
                best_source = max(candidates, key=lambda s: candidates[s]['quality'])
                best_value = candidates[best_source]['value']
                best_quality = candidates[best_source]['quality']
                
                if len(candidates) > 1:
                    other_sources = [s for s in candidates if s != best_source]
                    for other in other_sources:
                        if abs(candidates[other]['quality'] - best_quality) < 0.1:
                            best_value = (best_value + candidates[other]['value']) / 2
                            best_source = f"{best_source}+{other}"
                            break
                
                aggregated_data[field] = best_value
                source_attribution[field] = {
                    'value': best_value,
                    'source': best_source,
                    'method': 'best_quality_or_average',
                    'all_sources': {s: c['value'] for s, c in candidates.items()},
                    'confidence': best_quality
                }
            else:
                aggregated_data[field] = 0
                source_attribution[field] = {
                    'value': 0,
                    'source': 'none',
                    'method': 'unavailable',
                    'confidence': 0.0
                }
        
        return aggregated_data, source_attribution
    
    # ==================== CALCULATION ENGINE ====================
    
    async def _calculate_analytics_and_derived_metrics(
        self,
        collection: NFTCollection,
        aggregated_metrics: Dict,
        processed_sources: Dict
    ) -> Dict:
        """
        Calculate analytics and derived metrics using the calculation engine.
        
        This adds three layers of calculated metrics:
        1. Historical changes (24h, 7d, 30d percentage changes)
        2. Derived metrics (averages, ratios, velocity)
        3. Advanced analytics (efficiency, confidence, liquidity scores)
        
        Args:
            collection: Collection to calculate for
            aggregated_metrics: Base aggregated data
            processed_sources: Original source data
            
        Returns:
            Enhanced metrics dict with all calculated fields
        """
        logger.info(f"Calculating analytics for {collection.address}")
        
        if not aggregated_metrics.get('success'):
            logger.warning("Cannot calculate analytics - no valid aggregated data")
            return aggregated_metrics
        
        base_data = aggregated_metrics['data']
        
        # Step 1: Calculate historical change metrics (always calculated)
        calculated_changes = await self._calculate_historical_changes(collection, base_data)
        
        # Step 2: Calculate derived metrics and averages
        derived_metrics = self._calculate_derived_metrics(base_data, calculated_changes)
        
        # Step 3: Calculate advanced analytics
        analytics_metrics = self._calculate_advanced_analytics(
            base_data,
            calculated_changes,
            derived_metrics
        )
        
        # Step 4: Merge all calculated metrics with base data
        enhanced_data = {
            **base_data,
            **calculated_changes,
            **derived_metrics,
            **analytics_metrics
        }
        
        # Step 5: Update source attribution to include calculated metrics
        enhanced_source_attribution = {
            **aggregated_metrics['metadata']['source_attribution'],
            **get_calculated_metrics_attribution(
                calculated_changes,
                derived_metrics,
                analytics_metrics
            )
        }
        
        return {
            'source': 'aggregated',
            'success': True,
            'data': enhanced_data,
            'metadata': {
                **aggregated_metrics['metadata'],
                'source_attribution': enhanced_source_attribution,
                'calculation_methods': {
                    'historical_changes': 'percentage_change_from_historical_data',
                    'derived_metrics': 'mathematical_derivation',
                    'analytics': 'weighted_scoring_algorithms'
                }
            }
        }
    
    async def _calculate_historical_changes(
        self,
        collection: NFTCollection,
        base_data: Dict
    ) -> Dict:
        """
        Calculate all historical change metrics using our own methodology.
        
        Looks back at historical CollectionMarketStats records to calculate
        percentage changes over different time periods.
        
        Args:
            collection: Collection to calculate for
            base_data: Current aggregated data
            
        Returns:
            Dict of historical change metrics
        """
        logger.debug("Calculating historical change metrics")
        
        try:
            now = timezone.now()
            changes = {}
            
            # Get historical data points
            historical_data = {}
            time_periods = {
                '24h': now - timedelta(hours=24),
                '7d': now - timedelta(days=7),
                '30d': now - timedelta(days=30)
            }
            
            for period, cutoff_time in time_periods.items():
                # Get the closest historical record to the cutoff time
                historical_record = await sync_to_async(
                    CollectionMarketStats.objects.filter(
                        collection=collection,  # ForeignKey, not collection_address
                        source='aggregated',  # Use aggregated historical data
                        timestamp__lte=cutoff_time
                    ).order_by('-timestamp').first
                )()
                
                if historical_record:
                    historical_data[period] = {
                        'floor_price': float(historical_record.floor_price),
                        'volume_24h': float(historical_record.volume_24h),
                        'listed_count': historical_record.listed_count,
                        'total_supply': historical_record.total_supply,
                    }
            
            # Calculate price changes
            current_floor = base_data.get('floor_price', 0)
            
            if current_floor > 0:
                for period in ['24h', '7d', '30d']:
                    if period in historical_data and historical_data[period]['floor_price'] > 0:
                        historical_floor = historical_data[period]['floor_price']
                        price_change = ((current_floor - historical_floor) / historical_floor) * 100
                        changes[f'price_change_{period}'] = price_change
                        
                        logger.debug(
                            f"Price change {period}: {price_change:.2f}% "
                            f"(current: {current_floor}, historical: {historical_floor})"
                        )
                    else:
                        changes[f'price_change_{period}'] = 0.0
            else:
                for period in ['24h', '7d', '30d']:
                    changes[f'price_change_{period}'] = 0.0
            
            # Calculate volume changes
            current_volume_24h = base_data.get('volume_24h', 0)
            
            if '24h' in historical_data and historical_data['24h']['volume_24h'] > 0:
                historical_volume = historical_data['24h']['volume_24h']
                volume_change = ((current_volume_24h - historical_volume) / historical_volume) * 100
                changes['volume_change_24h'] = volume_change
            else:
                changes['volume_change_24h'] = 0.0
            
            # Calculate listing count changes
            current_listed = base_data.get('listed_count', 0)
            
            for period in ['24h', '7d']:
                if period in historical_data:
                    historical_listed = historical_data[period]['listed_count']
                    if historical_listed > 0:
                        listing_change = ((current_listed - historical_listed) / historical_listed) * 100
                        changes[f'listing_change_{period}'] = listing_change
                    else:
                        changes[f'listing_change_{period}'] = 0.0
                else:
                    changes[f'listing_change_{period}'] = 0.0
            
            # Calculate supply changes (rare, but possible with burns/mints)
            current_supply = base_data.get('total_supply', 0)
            if '7d' in historical_data and current_supply > 0:
                historical_supply = historical_data['7d']['total_supply']
                if historical_supply > 0:
                    supply_change = ((current_supply - historical_supply) / historical_supply) * 100
                    changes['supply_change_7d'] = supply_change
                else:
                    changes['supply_change_7d'] = 0.0
            else:
                changes['supply_change_7d'] = 0.0
            
            logger.debug(f"Calculated {len(changes)} historical change metrics")
            return changes
            
        except Exception as e:
            logger.error(f"Error calculating historical changes: {str(e)}")
            return {
                'price_change_24h': 0.0,
                'price_change_7d': 0.0,
                'price_change_30d': 0.0,
                'volume_change_24h': 0.0,
                'listing_change_24h': 0.0,
                'listing_change_7d': 0.0,
                'supply_change_7d': 0.0,
            }
    
    def _calculate_derived_metrics(
        self,
        base_data: Dict,
        calculated_changes: Dict
    ) -> Dict:
        """
        Calculate derived metrics (averages, ratios, velocity).
        
        These are mathematical derivations from base data:
        - Average sale price (volume / sales count)
        - Sales velocity (sales per hour)
        - Bid-to-floor ratio
        - Market cap
        
        Args:
            base_data: Base aggregated data
            calculated_changes: Historical change metrics
            
        Returns:
            Dict of derived metrics
        """
        derived = {}
        
        # Average sale price (24h)
        volume_24h = base_data.get('volume_24h', 0)
        sales_count_24h = base_data.get('sales_count_24h', 0)
        if sales_count_24h > 0:
            derived['average_sale_price_24h'] = volume_24h / sales_count_24h
        else:
            derived['average_sale_price_24h'] = 0.0
        
        # Sales velocity (sales per hour over 24h)
        if sales_count_24h > 0:
            derived['sales_velocity'] = sales_count_24h / 24.0
        else:
            derived['sales_velocity'] = 0.0
        
        # Bid-to-floor ratio
        floor_price = base_data.get('floor_price', 0)
        highest_bid = base_data.get('highest_bid', 0)
        if floor_price > 0:
            derived['bid_floor_ratio'] = highest_bid / floor_price
        else:
            derived['bid_floor_ratio'] = 0.0
        
        # Market cap (if not already calculated)
        if 'market_cap' not in base_data or base_data['market_cap'] == 0:
            total_supply = base_data.get('total_supply', 0)
            derived['market_cap'] = floor_price * total_supply
        
        # Listing percentage (if not already calculated)
        if 'percent_listed' not in base_data or base_data['percent_listed'] == 0:
            total_supply = base_data.get('total_supply', 0)
            listed_count = base_data.get('listed_count', 0)
            if total_supply > 0:
                derived['percent_listed'] = (listed_count / total_supply) * 100
            else:
                derived['percent_listed'] = 0.0
        
        return derived
    
    def _calculate_advanced_analytics(
        self,
        base_data: Dict,
        calculated_changes: Dict,
        derived_metrics: Dict
    ) -> Dict:
        """
        Calculate advanced analytics scores.
        
        These are composite scores combining multiple signals:
        - Market efficiency score
        - Holder confidence index
        - Liquidity health score
        - Overall health score
        - Trend direction classification
        - Market condition classification
        
        Args:
            base_data: Base aggregated data
            calculated_changes: Historical changes
            derived_metrics: Derived metrics
            
        Returns:
            Dict of analytics scores
        """
        analytics = {}
        
        # Market Efficiency Score (0-100)
        # Factors: bid-floor ratio, sales velocity, listing percentage
        bid_floor_ratio = derived_metrics.get('bid_floor_ratio', 0)
        sales_velocity = derived_metrics.get('sales_velocity', 0)
        percent_listed = base_data.get('percent_listed', derived_metrics.get('percent_listed', 0))
        
        efficiency_score = (
            (bid_floor_ratio * 40) +  # High bids = efficient price discovery
            (min(sales_velocity / 2, 1.0) * 30) +  # Active trading = efficient
            ((percent_listed / 100) * 30)  # Healthy listings = liquidity
        )
        analytics['market_efficiency_score'] = min(100, efficiency_score)
        
        # Holder Confidence Index (0-100)
        # Factors: listing decrease, price increase, low volatility
        price_change_24h = calculated_changes.get('price_change_24h', 0)
        listing_change_24h = calculated_changes.get('listing_change_24h', 0)
        
        confidence_score = 50  # Base confidence
        
        # Price trending up = confidence boost
        if price_change_24h > 0:
            confidence_score += min(price_change_24h * 0.5, 25)
        
        # Listings decreasing = holders confident (not panic selling)
        if listing_change_24h < 0:
            confidence_score += min(abs(listing_change_24h) * 0.3, 25)
        
        analytics['holder_confidence_index'] = max(0, min(100, confidence_score))
        
        # Liquidity Health Score (0-100)
        # Factors: volume, listings, bid depth
        volume_24h = base_data.get('volume_24h', 0)
        listed_count = base_data.get('listed_count', 0)
        bid_count = base_data.get('bid_count', 0)
        floor_price = base_data.get('floor_price', 0)

        # Calculate volume depth (protect against division by zero)
        if floor_price > 0:
            volume_depth_score = min(volume_24h / (floor_price * 10), 1.0) * 40
        else:
            volume_depth_score = 0

        liquidity_score = (
            volume_depth_score +  # Volume depth
            (min(listed_count / 50, 1.0) * 35) +  # Listing depth
            (min(bid_count / 20, 1.0) * 25)  # Bid depth
        )
        analytics['liquidity_health_score'] = min(100, liquidity_score)
        
        # Overall Health Score (weighted average of all scores)
        analytics['overall_health_score'] = (
            analytics['market_efficiency_score'] * 0.4 +
            analytics['holder_confidence_index'] * 0.3 +
            analytics['liquidity_health_score'] * 0.3
        )
        
        # Trend Direction (categorical)
        if price_change_24h > 5:
            analytics['trend_direction'] = 'strong_uptrend'
        elif price_change_24h > 1:
            analytics['trend_direction'] = 'uptrend'
        elif price_change_24h > -1:
            analytics['trend_direction'] = 'sideways'
        elif price_change_24h > -5:
            analytics['trend_direction'] = 'downtrend'
        else:
            analytics['trend_direction'] = 'strong_downtrend'
        
        # Market Condition (categorical)
        if analytics['overall_health_score'] > 80:
            analytics['market_condition'] = 'excellent'
        elif analytics['overall_health_score'] > 60:
            analytics['market_condition'] = 'healthy'
        elif analytics['overall_health_score'] > 40:
            analytics['market_condition'] = 'moderate'
        elif analytics['overall_health_score'] > 20:
            analytics['market_condition'] = 'weak'
        else:
            analytics['market_condition'] = 'poor'
        
        return analytics
    
    # ==================== STORAGE ====================
    async def _store_aggregated_record(
            self,
            collection: NFTCollection,
            enhanced_metrics: Dict
        ) -> None:
            """
            Store the final aggregated record into the AggregatedCollectionStats model.

            This updates the single source of truth for collection analytics.

            Args:
                collection: Collection to store for
                enhanced_metrics: Complete metrics dict with all calculations
            """
            if not enhanced_metrics.get('success', False):
                logger.warning(f"Cannot store aggregated record - no valid data for {collection.address}")
                return

            # --- Import the correct model ---
            from analytics.models import AggregatedCollectionStats
            # --------------------------------

            try:
                data = enhanced_metrics['data']
                metadata = enhanced_metrics['metadata']

                # --- Map fields from 'data' to AggregatedCollectionStats fields ---
                defaults_for_agg_stats = {
                    # Base Metrics
                    'floor_price': safe_decimal_conversion(data.get('floor_price', 0)),
                    'volume_24h': safe_decimal_conversion(data.get('volume_24h', 0)),
                    'listed_count': data.get('listed_count', 0),
                    'total_supply': data.get('total_supply', 0),
                    'number_of_holders': data.get('number_of_holders', 0), # Field name assumed, check model

                    # Calculated Analytics (Map based on your model's field names)
                    # 'vitality_score': data.get('vitality_score', 0.0), # Example if you have it
                    'holder_quality_score': data.get('holder_confidence_index', 0.0), # Map confidence index here? Check model
                    # 'sentiment_score': data.get('sentiment_score', 0.0), # Example
                    # 'market_influence_score': data.get('market_influence_score', 0.0), # Example
                    'performance_score': data.get('overall_health_score', 0.0), # Map overall health here
                    'market_cap': safe_decimal_conversion(data.get('market_cap', 0)),
                    'price_change_24h': safe_decimal_conversion(data.get('price_change_24h', 0)),
                    'price_change_7d': safe_decimal_conversion(data.get('price_change_7d', 0)), # Assumes field exists
                    'percent_listed': safe_decimal_conversion(data.get('percent_listed', 0)),
                    'velocity_24h': safe_decimal_conversion(data.get('sales_velocity', 0)), # Map sales velocity here
                    'market_efficiency_score': data.get('market_efficiency_score', 0.0),
                    'holder_confidence_index': data.get('holder_confidence_index', 0.0),
                    'liquidity_health_score': data.get('liquidity_health_score', 0.0),


                    # Metadata (Store relevant metadata if needed)
                    'source_attribution': metadata.get('source_attribution', {}), # Store attribution JSON
                    'updated_at': timezone.now() # Model handles this automatically via auto_now=True
                }

                # Use update_or_create on the correct model (AggregatedCollectionStats)
                # It uses a OneToOneField, so 'collection' is the unique identifier
                agg_stats_obj, created = await sync_to_async(
                    AggregatedCollectionStats.objects.update_or_create,
                    thread_sensitive=False # Keep this for safety
                )(
                    collection=collection,
                    defaults=defaults_for_agg_stats
                )

                action = "Created" if created else "Updated"
                logger.info(f"✓ {action} AggregatedCollectionStats record for {collection.address}")

            except Exception as e:
                logger.error(f"Error storing AggregatedCollectionStats record: {str(e)}", exc_info=True)
    
    # ==================== UTILITY METHODS ====================
    
    async def _calculate_blockchain_floor_price(
        self,
        collection: NFTCollection
    ) -> float:
        """
        Calculate floor price from blockchain/marketplace listings.
        
        Args:
            collection: Collection to calculate for
            
        Returns:
            Floor price from blockchain data
        """
        try:
            # Method 1: Get from active marketplace listings (most accurate)
            marketplace_floor = await sync_to_async(
                NFTListing.objects.filter(
                    collection=collection,
                    status='ACTIVE',
                    lifecycle_stage='ACTIVE'
                ).aggregate
            )(min_price=Min('price'))
            
            marketplace_price = float(marketplace_floor['min_price'] or 0)
            
            # Method 2: Fallback to blockchain events
            if marketplace_price == 0:
                blockchain_floor = await sync_to_async(
                    NFTEvent.objects.filter(
                        collection_address=collection.address,
                        event_type='NFT_LISTING',
                        status='active'
                    ).aggregate
                )(min_price=Min('amount'))
                
                marketplace_price = float(blockchain_floor['min_price'] or 0)
            
            return marketplace_price
                
        except Exception as e:
            logger.error(f"Error calculating blockchain floor price: {str(e)}")
            return 0.0
    
    async def _count_blockchain_listings(
        self,
        collection: NFTCollection
    ) -> int:
        """
        Count active listings from blockchain/marketplace data.
        
        Args:
            collection: Collection to count for
            
        Returns:
            Count of active listings
        """
        try:
            # Method 1: Count from marketplace listings (most accurate)
            marketplace_count = await sync_to_async(
                NFTListing.objects.filter(
                    collection=collection,
                    status='ACTIVE',
                    lifecycle_stage='ACTIVE'
                ).count
            )()
            
            # Method 2: Fallback to blockchain events
            if marketplace_count == 0:
                blockchain_count = await sync_to_async(
                    NFTEvent.objects.filter(
                        collection_address=collection.address,
                        event_type='NFT_LISTING',
                        status='active'
                    ).count
                )()
                
                marketplace_count = blockchain_count
            
            return marketplace_count
                
        except Exception as e:
            logger.error(f"Error counting blockchain listings: {str(e)}")
            return 0


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'MarketAggregationService',
]