"""
Wallet Analytics Service

This service analyzes wallet behavior and calculates prominence scores based on
trading activity, volume, and market influence.


Usage:
    from analytics.services.wallet_analytics import WalletAnalyticsService
    
    service = WalletAnalyticsService()
    await service.calculate_wallet_prominence()
"""

import logging
from datetime import timedelta
from typing import Optional, Dict, List
from decimal import Decimal

from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.contrib.auth import get_user_model
from asgiref.sync import sync_to_async

# Import models from correct sources
from indexer.models import NFTEvent
from analytics.models import WalletProminence, WalletBehaviorProfile
from nft_data.models import NFTCollection

# Import utilities
from .utils import send_notification

# Configure logging
logger = logging.getLogger(__name__)

User = get_user_model()


class WalletAnalyticsService:
    """
    Service for analyzing wallet trading behavior and calculating prominence scores.
    
    This service processes NFTEvent data to:
    - Calculate wallet prominence scores (0-100)
    - Classify wallet behavior types (whale, flipper, holder, etc.)
    - Track trading patterns and risk profiles
    - Identify influential wallets
    
    The results are stored in WalletProminence and WalletBehaviorProfile models,
    which can be consumed by other services (e.g., marketplace vitality system).
    """
    
    def __init__(self, analysis_period_days: int = 30):
        """
        Initialize the wallet analytics service.
        
        Args:
            analysis_period_days: Number of days to analyze for wallet activity (default: 30)
        """
        self.analysis_period_days = analysis_period_days
        logger.info(f"Initialized WalletAnalyticsService (analysis period: {analysis_period_days} days)")
    
    async def calculate_wallet_prominence(self) -> Dict[str, int]:
        """
        Calculate prominence scores for all active wallets.
        
        This is the main method that analyzes wallet behavior across the marketplace
        and creates/updates WalletProminence and WalletBehaviorProfile records.
        
        Prominence is calculated based on:
        - Transaction volume (40% weight)
        - Activity/transaction count (30% weight)
        - Portfolio diversity (20% weight)
        - High-value transactions (10% weight)
        
        Returns:
            Dict with counts of processed wallets
            {
                'total_wallets': int,
                'prominent_wallets': int,  # Score > 80
                'behavior_profiles_created': int
            }
        
        Example:
            >>> service = WalletAnalyticsService()
            >>> results = await service.calculate_wallet_prominence()
            >>> print(f"Analyzed {results['total_wallets']} wallets")
        """
        try:
            now = timezone.now()
            analysis_period = now - timedelta(days=self.analysis_period_days)
            
            logger.info(f"🔍 Starting wallet prominence calculation (period: {self.analysis_period_days} days)")
            
            # Fetch unique buyer and seller addresses from NFTEvent
            buyer_addresses = await sync_to_async(list)(
                NFTEvent.objects.filter(
                    event_type__in=['SALE', 'BID'],
                    timestamp__gte=analysis_period
                ).values_list('buyer', flat=True).distinct()
            )
            
            seller_addresses = await sync_to_async(list)(
                NFTEvent.objects.filter(
                    event_type='SALE',
                    timestamp__gte=analysis_period
                ).values_list('seller', flat=True).distinct()
            )
            
            all_addresses = set(buyer_addresses + seller_addresses)
            all_addresses.discard(None)  # Remove None values
            all_addresses.discard('')    # Remove empty strings
            
            logger.info(f"📊 Found {len(all_addresses)} unique wallet addresses to analyze")
            
            prominent_count = 0
            behavior_profiles_created = 0
            
            for address in all_addresses:
                if not address:
                    continue
                
                # Calculate transaction metrics for the wallet using NFTEvent
                buy_txns_query = NFTEvent.objects.filter(
                    buyer=address,
                    event_type__in=['SALE', 'BID'],
                    timestamp__gte=analysis_period
                )
                
                sell_txns_query = NFTEvent.objects.filter(
                    seller=address,
                    event_type='SALE',
                    timestamp__gte=analysis_period
                )
                
                # Get counts
                buy_count = await sync_to_async(buy_txns_query.count)()
                sell_count = await sync_to_async(sell_txns_query.count)()
                total_txns = buy_count + sell_count
                
                # Calculate volumes
                buy_volume_result = await sync_to_async(buy_txns_query.aggregate)(sum=Sum('amount'))
                sell_volume_result = await sync_to_async(sell_txns_query.aggregate)(sum=Sum('amount'))
                
                buy_volume = buy_volume_result['sum'] or Decimal('0')
                sell_volume = sell_volume_result['sum'] or Decimal('0')
                total_volume = float(buy_volume) + float(sell_volume)
                
                # Count unique collections traded
                collections_interacted = await sync_to_async(
                    NFTEvent.objects.filter(
                        Q(buyer=address) | Q(seller=address),
                        timestamp__gte=analysis_period
                    ).values('collection_address').distinct().count
                )()
                
                # Count high-value transactions (> 5 SOL)
                high_value_threshold = 5  # SOL
                high_value_txns = await sync_to_async(
                    NFTEvent.objects.filter(
                        Q(buyer=address) | Q(seller=address),
                        event_type='SALE',
                        amount__gte=high_value_threshold,
                        timestamp__gte=analysis_period
                    ).count
                )()
                
                # Calculate prominence score (0-100)
                volume_score = min(1.0, total_volume / 100)      # Cap at 100 SOL
                activity_score = min(1.0, total_txns / 50)       # Cap at 50 transactions
                diversity_score = min(1.0, collections_interacted / 10)  # Cap at 10 collections
                high_value_score = min(1.0, high_value_txns / 5)  # Cap at 5 high-value txns
                
                prominence_score = (
                    (volume_score * 0.4) +
                    (activity_score * 0.3) +
                    (diversity_score * 0.2) +
                    (high_value_score * 0.1)
                ) * 100
                
                # Store or update basic wallet prominence
                await sync_to_async(WalletProminence.objects.update_or_create)(
                    address=address,
                    defaults={
                        'transaction_count': total_txns,
                        'transaction_volume': total_volume,
                        'collections_count': collections_interacted,
                        'prominence_score': prominence_score,
                        'last_updated': now
                    }
                )
                
                # Track prominent wallets
                if prominence_score > 80:
                    prominent_count += 1
                
                # Create advanced wallet behavior profile
                behavior_profile = await self._analyze_wallet_behavior(address, analysis_period)
                if behavior_profile:
                    await sync_to_async(WalletBehaviorProfile.objects.update_or_create)(
                        wallet_address=address,
                        defaults=behavior_profile
                    )
                    behavior_profiles_created += 1
            
            logger.info(
                f"✅ Wallet prominence calculation complete: "
                f"{len(all_addresses)} wallets analyzed, "
                f"{prominent_count} prominent (>80 score), "
                f"{behavior_profiles_created} behavior profiles created"
            )
            
            # Send notification if prominent wallets detected
            if prominent_count > 0:
                admin_users = await sync_to_async(list)(
                    User.objects.filter(is_staff=True).values_list('id', flat=True)
                )
                if admin_users:
                    send_notification(
                        user_ids=admin_users,
                        event_type='wallet_prominence_updated',
                        message=f"Identified {prominent_count} prominent wallets in the marketplace",
                        data={
                            'prominent_count': prominent_count,
                            'total_wallets': len(all_addresses)
                        }
                    )
            
            return {
                'total_wallets': len(all_addresses),
                'prominent_wallets': prominent_count,
                'behavior_profiles_created': behavior_profiles_created
            }
            
        except Exception as e:
            logger.error(f"Error calculating wallet prominence: {str(e)}")
            raise
    
    async def _analyze_wallet_behavior(
        self,
        address: str,
        analysis_period: timezone.datetime
    ) -> Optional[Dict]:
        """
        Analyze detailed wallet behavior patterns.
        
        This creates a comprehensive behavior profile including:
        - Behavior type classification (whale, flipper, holder, etc.)
        - Hold time patterns
        - Trading frequency
        - Risk tolerance
        - Diversification metrics
        - Influence score
        
        Args:
            address: Wallet address to analyze
            analysis_period: Start of analysis period
            
        Returns:
            Dict with behavior profile data, or None if insufficient data
            {
                'behavior_type': str,
                'confidence_score': float,
                'avg_hold_time_hours': float,
                'trade_frequency_per_day': float,
                'risk_tolerance': str,
                'max_single_purchase': Decimal,
                'diversification_score': float,
                'influence_score': float,
                'first_seen': datetime,
                'behavior_features': dict
            }
        """
        try:
            # Get all transactions for this wallet
            all_txns = await sync_to_async(list)(
                NFTEvent.objects.filter(
                    Q(buyer=address) | Q(seller=address),
                    timestamp__gte=analysis_period
                ).order_by('timestamp')
            )
            
            if not all_txns:
                return None
            
            # Calculate hold times
            hold_times = []
            wallet_nfts = {}  # Track NFTs owned by this wallet: {nft_mint: purchase_timestamp}
            
            for txn in all_txns:
                if txn.buyer == address:  # Buying
                    wallet_nfts[txn.nft_mint] = txn.timestamp
                elif txn.seller == address and txn.nft_mint in wallet_nfts:  # Selling
                    buy_time = wallet_nfts[txn.nft_mint]
                    hold_time = (txn.timestamp - buy_time).total_seconds() / 3600  # hours
                    hold_times.append(hold_time)
                    del wallet_nfts[txn.nft_mint]
            
            avg_hold_time = sum(hold_times) / len(hold_times) if hold_times else 0
            
            # Calculate trading frequency
            days_active = (timezone.now() - all_txns[0].timestamp).days or 1
            trade_frequency = len(all_txns) / days_active
            
            # Determine behavior type based on patterns
            behavior_type = self._classify_behavior_type(avg_hold_time, trade_frequency, all_txns)
            
            # Calculate risk tolerance based on transaction values
            transaction_values = [float(txn.amount) for txn in all_txns if txn.amount]
            max_purchase = max(transaction_values) if transaction_values else 0
            avg_purchase = sum(transaction_values) / len(transaction_values) if transaction_values else 0
            
            # Risk tolerance: high variance in purchase amounts = higher risk tolerance
            if len(transaction_values) > 1:
                variance = sum((x - avg_purchase) ** 2 for x in transaction_values) / len(transaction_values)
                risk_tolerance = min(variance / avg_purchase, 5.0) if avg_purchase > 0 else 0
            else:
                risk_tolerance = 0
            
            risk_level = (
                'very_high' if risk_tolerance > 3 else
                'high' if risk_tolerance > 2 else
                'medium' if risk_tolerance > 1 else
                'low'
            )
            
            # Calculate diversification score (0-1)
            unique_collections = len(set(txn.collection_address for txn in all_txns))
            diversification_score = min(1.0, unique_collections / 10.0)
            
            # Calculate influence metrics (placeholder - can be enhanced with network analysis)
            # TODO: Implement network analysis for true influence scoring
            influence_score = min(1.0, len(all_txns) / 100.0)
            
            return {
                'behavior_type': behavior_type,
                'confidence_score': 0.8,  # TODO: Implement ML confidence scoring
                'avg_hold_time_hours': avg_hold_time,
                'trade_frequency_per_day': trade_frequency,
                'risk_tolerance': risk_level,
                'max_single_purchase': Decimal(str(max_purchase)),
                'diversification_score': diversification_score,
                'influence_score': influence_score,
                'first_seen': all_txns[0].timestamp,
                # ML preparation fields
                'behavior_features': {
                    'hold_time': avg_hold_time,
                    'frequency': trade_frequency,
                    'max_purchase': max_purchase,
                    'diversification': diversification_score,
                    'total_volume': sum(transaction_values),
                    'transaction_count': len(all_txns)
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing wallet behavior for {address[:8]}: {str(e)}")
            return None
    
    def _classify_behavior_type(
        self,
        avg_hold_time: float,
        trade_frequency: float,
        transactions: List
    ) -> str:
        """
        Classify wallet behavior based on trading patterns.
        
        Current implementation uses rule-based classification.
        ML PREPARATION: This logic will be replaced with ML classification models.
        
        Args:
            avg_hold_time: Average hold time in hours
            trade_frequency: Trades per day
            transactions: List of NFTEvent transactions
        
        Returns:
            str: Behavior type classification
            - 'whale': High volume trader (>1000 SOL)
            - 'scalper': Very short hold times (<24 hours)
            - 'holder': Long-term holder (>30 days)
            - 'flipper': Frequent trader (>2 trades/day)
            - 'casual': Default classification
        """
        # Calculate total volume
        total_volume = sum(float(txn.amount) for txn in transactions if txn.amount)
        
        # Rule-based classification (will be enhanced with ML)
        if total_volume > 1000:  # High volume threshold
            return 'whale'
        elif avg_hold_time < 24:  # Less than 24 hours
            return 'scalper'
        elif avg_hold_time > 720:  # More than 30 days
            return 'holder'
        elif trade_frequency > 2:  # More than 2 trades per day
            return 'flipper'
        else:
            return 'casual'
    
    @staticmethod
    async def get_wallet_prominence_factor(buyer: Optional[str], seller: Optional[str]) -> float:
        """
        Calculate wallet prominence factor for a transaction.
        
        This is a utility method used by other services (e.g., MarketEventService)
        to factor wallet prominence into their calculations.
        
        Args:
            buyer: Buyer wallet address (can be None)
            seller: Seller wallet address (can be None)
        
        Returns:
            float: Prominence factor (1.0 to 3.0)
            - 1.0: No prominent wallets involved
            - 3.0: Maximum prominence (capped)
        
        Example:
            >>> factor = await WalletAnalyticsService.get_wallet_prominence_factor(
            ...     buyer='ABC123...',
            ...     seller='XYZ789...'
            ... )
            >>> high_profile_score = base_score * factor
        """
        try:
            wallet_factor = 1.0
            
            if buyer:
                buyer_prominence = await sync_to_async(
                    WalletProminence.objects.filter(address=buyer).first
                )()
                if buyer_prominence:
                    # Scale 0-100 prominence to 0-0.5 bonus
                    wallet_factor += (buyer_prominence.prominence_score / 200)
            
            if seller:
                seller_prominence = await sync_to_async(
                    WalletProminence.objects.filter(address=seller).first
                )()
                if seller_prominence:
                    # Scale 0-100 prominence to 0-0.5 bonus
                    wallet_factor += (seller_prominence.prominence_score / 200)
            
            return min(3.0, wallet_factor)  # Cap at 3x multiplier
            
        except Exception as e:
            logger.error(f"Error calculating wallet prominence factor: {str(e)}")
            return 1.0


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'WalletAnalyticsService',
]