"""
Bid Validation Service

This service validates bids against NFT vitality scores and collection-specific
minimum bid thresholds.

User Requirements:
- Bids cannot be too far below vitality score
- Minimum threshold range: -15% to -30% below vitality
- Collection-level and NFT-level minimum bids supported
- Helpful error messages for invalid bids
"""

from decimal import Decimal
from typing import Tuple, Optional
from django.db import models
from asgiref.sync import sync_to_async
import logging

from nft_data.models import NFT, NFTCollection
from .vitality_models import NFTVitality, MinimumBidThreshold

logger = logging.getLogger(__name__)


class BidValidationService:
    """
    Service for validating bids against vitality scores and minimum thresholds.

    Validation Rules:
    1. Check NFT-level minimum threshold (if exists)
    2. Check collection-level minimum threshold (if exists)
    3. Check global minimum threshold (if exists)
    4. Vitality-based thresholds: -15% to -30% below vitality score
    5. Absolute SOL minimums (if configured)
    """

    # Default thresholds if no configured thresholds exist
    DEFAULT_VITALITY_THRESHOLD = Decimal('-20.00')  # -20% below vitality
    DEFAULT_ABSOLUTE_MINIMUM_SOL = Decimal('0.01')  # 0.01 SOL minimum

    async def validate_bid(
        self,
        nft: NFT,
        bid_amount: Decimal
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a bid against NFT vitality and minimum thresholds.

        Args:
            nft: The NFT being bid on
            bid_amount: The bid amount in SOL

        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if bid is valid, False otherwise
            - error_message: None if valid, detailed error message if invalid

        Examples:
            >>> service = BidValidationService()
            >>> is_valid, error = await service.validate_bid(nft, Decimal('5.0'))
            >>> if not is_valid:
            ...     print(error)
        """
        # Step 1: Basic validation
        if bid_amount <= 0:
            return False, "Bid amount must be greater than 0 SOL"

        # Step 2: Check absolute minimum
        if bid_amount < self.DEFAULT_ABSOLUTE_MINIMUM_SOL:
            return False, f"Bid must be at least {self.DEFAULT_ABSOLUTE_MINIMUM_SOL} SOL"

        # Step 3: Get NFT vitality
        try:
            vitality = await sync_to_async(
                NFTVitality.objects.select_related('nft').get,
                thread_sensitive=False # <--- ADD THIS LINE
            )(nft=nft)
        except NFTVitality.DoesNotExist:
            logger.warning(f"No vitality score found for NFT {nft.mint_address}")
            return False, "NFT vitality score not available. Cannot validate bid."

        # Step 4: Check if vitality has sufficient data
        if not vitality.has_sufficient_data:
            return False, "NFT vitality score is not yet calculated. Try again later."

        # Step 5: Get applicable threshold (NFT-level > Collection-level > Global)
        threshold = await self._get_applicable_threshold(nft)

        # Step 6: Validate based on threshold type
        if threshold:
            is_valid, error = await self._validate_against_threshold(
                bid_amount=bid_amount,
                vitality=vitality,
                threshold=threshold
            )
            if not is_valid:
                return False, error
        else:
            # No configured threshold, use default vitality-based validation
            is_valid, error = await self._validate_against_default(
                bid_amount=bid_amount,
                vitality=vitality
            )
            if not is_valid:
                return False, error

        # All validations passed
        logger.info(
            f"Bid validated: NFT={nft.mint_address}, "
            f"Bid={bid_amount} SOL, Vitality={vitality.vitality_score}"
        )
        return True, None

    async def _get_applicable_threshold(
        self,
        nft: NFT
    ) -> Optional[MinimumBidThreshold]:
        """
        Get the most specific applicable threshold.

        Priority:
        1. NFT-level threshold (most specific)
        2. Collection-level threshold
        3. Global threshold (least specific)

        Args:
            nft: The NFT being bid on

        Returns:
            Most specific applicable MinimumBidThreshold, or None
        """
        # Get the collection_id safely *before* entering sync_to_async
        collection_id = nft.collection_id
        nft_pk = nft.pk # Get primary key

        # --- NFT-level Threshold ---
        # Pass nft_pk directly
        nft_threshold = await sync_to_async(
            MinimumBidThreshold.objects.filter(nft_id=nft_pk, is_active=True).first,
            thread_sensitive=False
        )()
        if nft_threshold: # Check if found before proceeding
            return nft_threshold # Return early if NFT-specific threshold exists

        # --- Collection-level Threshold ---
        # Pass collection_id directly
        collection_threshold = await sync_to_async(
            MinimumBidThreshold.objects.filter(collection_id=collection_id, nft__isnull=True, is_active=True).first,
            thread_sensitive=False
        )()
        if collection_threshold: # Check if found
             return collection_threshold # Return early

        # --- Global Threshold ---
        global_threshold = await sync_to_async(
            MinimumBidThreshold.objects.filter(collection__isnull=True, nft__isnull=True, is_active=True).first,
            thread_sensitive=False
        )()

        # Return global_threshold which might be None if none are found
        return global_threshold

    async def _validate_against_threshold(
        self,
        bid_amount: Decimal,
        vitality: NFTVitality,
        threshold: MinimumBidThreshold
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate bid against a specific threshold configuration.

        Args:
            bid_amount: Bid amount in SOL
            vitality: NFT vitality object
            threshold: Applicable threshold configuration

        Returns:
            Tuple of (is_valid, error_message)
        """
        if threshold.threshold_type == 'VITALITY_BASED':
            return await self._validate_vitality_based(bid_amount, vitality, threshold)
        elif threshold.threshold_type == 'ABSOLUTE':
            return await self._validate_absolute_sol(bid_amount, threshold)
        elif threshold.threshold_type == 'BOTH':
            # For 'BOTH', calculate both minimums and enforce the stricter (higher) one
            vitality_min, _ = await self._calculate_vitality_minimum(vitality, threshold)
            absolute_min = threshold.absolute_minimum_sol
            
            # Use the higher of the two minimums
            effective_minimum = max(vitality_min, absolute_min)

            if bid_amount < effective_minimum:
                return False, f"Bid too low. The minimum bid for this item is {effective_minimum} SOL."
            
            return True, None
        else:
            logger.error(f"Unknown threshold type: {threshold.threshold_type}")
            return True, None  # Default to allowing if unknown type

    async def _calculate_vitality_minimum(
        self,
        vitality: NFTVitality,
        threshold: MinimumBidThreshold
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculate the minimum bid based on vitality threshold.
        
        Helper method to avoid code duplication when checking vitality-based minimums.

        Args:
            vitality: NFT vitality object
            threshold: Threshold configuration

        Returns:
            Tuple of (minimum_bid, suggested_price)
        """
        suggested_price = vitality.suggested_price or await self._estimate_price_from_vitality(vitality)
        threshold_percentage = threshold.vitality_percentage_threshold / Decimal('100')
        minimum_bid = suggested_price * (Decimal('1') + threshold_percentage)
        return minimum_bid, suggested_price

    async def _validate_vitality_based(
        self,
        bid_amount: Decimal,
        vitality: NFTVitality,
        threshold: MinimumBidThreshold
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate bid against vitality-based threshold.

        Threshold is a percentage (e.g., -20.00 means -20% below vitality).
        Valid range: -15% to -30%

        Args:
            bid_amount: Bid amount in SOL
            vitality: NFT vitality object
            threshold: Threshold configuration

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Use helper method to calculate minimum bid and suggested price
        minimum_bid, suggested_price = await self._calculate_vitality_minimum(vitality, threshold)

        if bid_amount < minimum_bid:
            percentage_below = ((bid_amount - suggested_price) / suggested_price) * Decimal('100')
            return False, (
                f"Bid too low. Your bid of {bid_amount} SOL is {abs(percentage_below):.1f}% "
                f"below the vitality-based price of {suggested_price} SOL. "
                f"Minimum allowed is {minimum_bid} SOL "
                f"({abs(threshold.vitality_percentage_threshold)}% below vitality price)."
            )

        return True, None

    async def _validate_absolute_sol(
        self,
        bid_amount: Decimal,
        threshold: MinimumBidThreshold
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate bid against absolute SOL minimum.

        Args:
            bid_amount: Bid amount in SOL
            threshold: Threshold configuration

        Returns:
            Tuple of (is_valid, error_message)
        """
        minimum = threshold.absolute_minimum_sol

        if bid_amount < minimum:
            return False, (
                f"Bid too low. Minimum bid for this NFT is {minimum} SOL. "
                f"Your bid: {bid_amount} SOL."
            )

        return True, None

    async def _validate_against_default(
        self,
        bid_amount: Decimal,
        vitality: NFTVitality
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate against default threshold when no configured threshold exists.

        Default: -20% below vitality-based price

        Args:
            bid_amount: Bid amount in SOL
            vitality: NFT vitality object

        Returns:
            Tuple of (is_valid, error_message)
        """
        suggested_price = vitality.suggested_price or await self._estimate_price_from_vitality(vitality)

        # Apply default threshold (-20%)
        threshold_multiplier = Decimal('1') + (self.DEFAULT_VITALITY_THRESHOLD / Decimal('100'))
        minimum_bid = suggested_price * threshold_multiplier

        if bid_amount < minimum_bid:
            percentage_below = ((bid_amount - suggested_price) / suggested_price) * Decimal('100')
            return False, (
                f"Bid too low. Your bid of {bid_amount} SOL is {abs(percentage_below):.1f}% "
                f"below the vitality-based price of {suggested_price} SOL. "
                f"Minimum allowed is {minimum_bid} SOL (20% below vitality price)."
            )

        return True, None

    async def _estimate_price_from_vitality(self, vitality: NFTVitality) -> Decimal:
        """
        Estimate price from vitality score when suggested_price is not available.

        TODO: Replace with proper price suggestion algorithm.
        This is a simple implementation using collection floor as baseline.

        Args:
            vitality: NFT vitality object

        Returns:
            Estimated price in SOL
        """
        collection = vitality.nft.collection
        floor_price = collection.floor_price or Decimal('1.0')

        # Simple multiplier based on vitality score (0-100)
        # Score 50 = 1x floor, Score 100 = 2x floor, Score 0 = 0.5x floor
        vitality_multiplier = Decimal('0.5') + (vitality.vitality_score / Decimal('100'))

        estimated_price = floor_price * vitality_multiplier

        logger.info(
            f"Estimated price for {vitality.nft.mint_address}: "
            f"{estimated_price} SOL (Floor: {floor_price}, Vitality: {vitality.vitality_score})"
        )

        return estimated_price

    async def get_minimum_bid_info(self, nft: NFT) -> dict:
        """
        Get information about minimum bid requirements for an NFT.

        Useful for displaying to users before they place a bid.

        Args:
            nft: The NFT to get minimum bid info for

        Returns:
            Dictionary with minimum bid information:
            {
                'has_vitality': bool,
                'vitality_score': Decimal or None,
                'suggested_price': Decimal or None,
                'minimum_bid': Decimal or None,
                'threshold_type': str or None,
                'threshold_percentage': Decimal or None,
                'error': str or None
            }
        """
        try:
            vitality = await sync_to_async(
                NFTVitality.objects.select_related('nft').get,
                thread_sensitive=False 
            )(nft=nft)
        except NFTVitality.DoesNotExist:
            return {
                'has_vitality': False,
                'vitality_score': None,
                'suggested_price': None,
                'minimum_bid': self.DEFAULT_ABSOLUTE_MINIMUM_SOL,
                'threshold_type': None,
                'threshold_percentage': None,
                'error': 'Vitality score not available'
            }

        if not vitality.has_sufficient_data:
            return {
                'has_vitality': True,
                'vitality_score': vitality.vitality_score,
                'suggested_price': None,
                'minimum_bid': self.DEFAULT_ABSOLUTE_MINIMUM_SOL,
                'threshold_type': None,
                'threshold_percentage': None,
                'error': 'Insufficient data for vitality calculation'
            }

        # Get suggested price
        suggested_price = vitality.suggested_price or await self._estimate_price_from_vitality(vitality)

        # Get applicable threshold
        threshold = await self._get_applicable_threshold(nft)

        if threshold:
            if threshold.threshold_type == 'VITALITY_BASED':
                minimum_bid, suggested_price = await self._calculate_vitality_minimum(vitality, threshold)
                threshold_type = 'Vitality-based'
                threshold_percentage = threshold.vitality_percentage_threshold
            elif threshold.threshold_type == 'ABSOLUTE':
                minimum_bid = threshold.absolute_minimum_sol
                threshold_type = 'Absolute SOL'
                threshold_percentage = None
            else:  # BOTH
                vitality_min, suggested_price = await self._calculate_vitality_minimum(vitality, threshold)
                absolute_min = threshold.absolute_minimum_sol
                minimum_bid = max(vitality_min, absolute_min)
                threshold_type = 'Hybrid (Vitality & Absolute)'
                threshold_percentage = None  # Not applicable for hybrid
        else:
            # Use default
            threshold_multiplier = Decimal('1') + (self.DEFAULT_VITALITY_THRESHOLD / Decimal('100'))
            minimum_bid = suggested_price * threshold_multiplier
            threshold_type = 'Default vitality-based'
            threshold_percentage = self.DEFAULT_VITALITY_THRESHOLD

        return {
            'has_vitality': True,
            'vitality_score': vitality.vitality_score,
            'suggested_price': suggested_price,
            'minimum_bid': minimum_bid,
            'threshold_type': threshold_type,
            'threshold_percentage': threshold_percentage,
            'error': None
        }