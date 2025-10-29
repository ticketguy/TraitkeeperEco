# marketplace/safety_validation.py
"""
Safety Validation Service for TraitKeeper Marketplace

Provides two types of checks:
1. CRITICAL SAFETY CHECKS - Block transactions (ownership, spam)
2. QUEST ELIGIBILITY CHECKS - Don't block, just determine quest credit
"""

from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from typing import Tuple, Optional
import logging
from asgiref.sync import sync_to_async

from nft_data.models import NFT
from .models import PrivateBid, MarketplaceTransaction
from indexer.models import NFTEvent

logger = logging.getLogger(__name__)


class SafetyValidationService:
    """
    Provides safety checks for marketplace transactions.

    CRITICAL CHECKS (Block Actions):
    - Ownership verification
    - Bid spam prevention

    QUEST ELIGIBILITY CHECKS (Don't Block):
    - Ownership duration
    - Sale velocity
    """

    # Quest eligibility thresholds (NOT blocking)
    MIN_OWNERSHIP_DURATION_MINUTES_FOR_QUEST = 5  # For quest credit only
    MAX_SALES_PER_HOUR_FOR_QUEST = 5             # For quest credit only
    MAX_BIDS_PER_HOUR_SPAM = 3                   # For blocking spam

    # --- CRITICAL SAFETY CHECKS (Block Action if False) ---

    def verify_ownership(
        self,
        nft: NFT,
        seller_wallet: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify that the seller actually owns the NFT. BLOCK action if False.

        This is critical to prevent unauthorized sales.
        """
        if nft.owner != seller_wallet:
            logger.warning(
                f"Ownership verification failed: {seller_wallet} tried to sell "
                f"{nft.mint_address} owned by {nft.owner}"
            )
            return False, "You do not own this NFT. Only the current owner can list or sell."
        return True, None

    async def validate_bid_placement_safety(
        self,
        bidder_wallet: str,
        nft: NFT,
        bid_amount: Decimal
    ) -> Tuple[bool, Optional[str]]:
        """
        Critical safety checks for placing bids. BLOCK action if False.
        Checks: Owner bidding, Bid spam.
        """
        # Check 1: Can't bid on own NFT
        if bidder_wallet == nft.owner:
            return False, "You cannot bid on your own NFT."

        # Check 2: Check for bid spam
        @sync_to_async
        def count_recent_bids():
            one_hour_ago = timezone.now() - timedelta(hours=1)
            return PrivateBid.objects.filter(
                bidder=bidder_wallet,
                nft=nft,
                created_at__gte=one_hour_ago
            ).count()

        recent_bids = await count_recent_bids()

        if recent_bids >= self.MAX_BIDS_PER_HOUR_SPAM:
            return False, (
                f"You have placed {recent_bids} bids on this NFT in the past hour. "
                f"Please wait before placing another bid."
            )

        return True, None

    # --- QUEST ELIGIBILITY CHECKS (Do NOT Block Action) ---

    async def check_quest_eligibility(
        self,
        nft: NFT,
        actor_wallet: str,
        action_type: str  # 'sale', 'list', 'bid'
    ) -> bool:
        """
        Checks conditions ONLY affecting quest eligibility. Does NOT block the action.
        Checks: Ownership duration, Sale velocity.

        Returns:
            bool: True if eligible for quest credit, False otherwise.
        """
        try:
            # Check 1: Ownership duration (only for sales/listings by owner)
            if action_type in ['sale', 'list']:
                is_eligible, _ = await self._check_ownership_duration_for_quest(nft, actor_wallet)
                if not is_eligible:
                    logger.info(f"Quest eligibility failed for {nft.mint_address} by {actor_wallet}: Ownership duration too short.")
                    return False  # Not eligible

            # Check 2: Sale velocity (relevant for sales and listings)
            if action_type in ['sale', 'list']:
                is_eligible, _ = await self._check_sale_velocity_for_quest(nft)
                if not is_eligible:
                    logger.info(f"Quest eligibility failed for {nft.mint_address}: Sale velocity too high.")
                    return False  # Not eligible

            # If all checks pass
            logger.info(f"Quest eligibility passed for {nft.mint_address} action by {actor_wallet}.")
            return True

        except Exception as e:
            logger.error(f"Error during quest eligibility check for {nft.mint_address}: {e}", exc_info=True)
            return False  # Default to not eligible on error

    async def _check_ownership_duration_for_quest(
        self,
        nft: NFT,
        seller_wallet: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Ensure owner has held NFT for minimum duration FOR QUESTS ONLY.
        Does NOT block the transaction.
        """
        @sync_to_async
        def get_last_transfer():
            return NFTEvent.objects.filter(
                nft=nft,
                buyer=seller_wallet,
                event_type='SALE'
            ).order_by('-timestamp').first()

        last_transfer = await get_last_transfer()

        if last_transfer:
            time_held = timezone.now() - last_transfer.timestamp
            min_duration = timedelta(minutes=self.MIN_OWNERSHIP_DURATION_MINUTES_FOR_QUEST)

            if time_held < min_duration:
                return False, "Ownership duration too short for quest eligibility."

        return True, None  # Eligible

    async def _check_sale_velocity_for_quest(
        self,
        nft: NFT
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if NFT is being flipped too rapidly FOR QUESTS ONLY.
        Does NOT block the transaction.
        """
        @sync_to_async
        def count_recent_sales():
            one_hour_ago = timezone.now() - timedelta(hours=1)
            return NFTEvent.objects.filter(
                nft=nft,
                event_type='SALE',
                timestamp__gte=one_hour_ago
            ).count()

        recent_sales = await count_recent_sales()

        if recent_sales >= self.MAX_SALES_PER_HOUR_FOR_QUEST:
            return False, "Sale velocity too high for quest eligibility."

        return True, None  # Eligible

    # --- HELPER/DISPLAY FUNCTION (Optional) ---

    async def get_safety_score(self, nft: NFT) -> dict:
        """
        Generate a safety score for an NFT (for UI display).
        This reflects potential quest eligibility issues, not critical risk.
        """
        score = 100
        flags = []
        indicators = {}

        # Check ownership duration
        @sync_to_async
        def get_ownership_duration():
            last_transfer = NFTEvent.objects.filter(
                nft=nft,
                buyer=nft.owner,
                event_type='SALE'
            ).order_by('-timestamp').first()

            if last_transfer:
                return (timezone.now() - last_transfer.timestamp).days
            return 999  # Old ownership

        ownership_days = await get_ownership_duration()

        if ownership_days < 1:
            indicators['ownership_duration'] = 'New (<1 day)'
            score -= 20
            flags.append('Recently acquired')
        elif ownership_days < 7:
            indicators['ownership_duration'] = f'Recent ({ownership_days} days)'
            score -= 10
        else:
            indicators['ownership_duration'] = 'Established'

        # Check trade frequency
        @sync_to_async
        def get_trade_count():
            thirty_days_ago = timezone.now() - timedelta(days=30)
            return NFTEvent.objects.filter(
                nft=nft,
                event_type='SALE',
                timestamp__gte=thirty_days_ago
            ).count()

        recent_trades = await get_trade_count()

        if recent_trades > 10:
            indicators['trade_frequency'] = 'Very High'
            score -= 30
            flags.append('Frequently traded')
        elif recent_trades > 5:
            indicators['trade_frequency'] = 'High'
            score -= 15
        else:
            indicators['trade_frequency'] = 'Normal'

        return {
            'score': max(0, score),
            'indicators': indicators,
            'flags': flags
        }
