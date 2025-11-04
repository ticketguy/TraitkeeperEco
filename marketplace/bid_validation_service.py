# marketplace/bid_validation_service.py
"""
Bid Validation Service

This service validates bids against NFT vitality scores and collection-specific
minimum bid thresholds.
"""

from decimal import Decimal
from typing import Tuple, Optional
from django.db import models
from asgiref.sync import sync_to_async
import logging

# Ensure these models exist in your project structure
from nft_data.models import NFT, NFTCollection
from .vitality_models import NFTVitality, MinimumBidThreshold

logger = logging.getLogger(__name__)


class BidValidationService:
    """
    Service for validating bids against vitality scores and minimum thresholds.
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
        """
        # Step 1: Basic validation
        if bid_amount <= 0:
            return False, "Bid amount must be greater than 0 SOL"

        # Step 2: Check absolute minimum (Global floor)
        if bid_amount < self.DEFAULT_ABSOLUTE_MINIMUM_SOL:
            return False, f"Bid must be at least {self.DEFAULT_ABSOLUTE_MINIMUM_SOL} SOL"

        # Step 3: Get NFT vitality (EAGER LOAD NFT and Collection for efficiency)
        try:
            vitality = await sync_to_async(
                # FIX: Added 'nft__collection' to ensure floor price access is efficient
                NFTVitality.objects.select_related('nft__collection').get,
                thread_sensitive=False
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

        Priority: NFT-level > Collection-level > Global
        """
        collection_id = nft.collection_id
        nft_pk = nft.pk

        # --- NFT-level Threshold ---
        # Pass nft_pk directly
        nft_threshold = await sync_to_async(
            MinimumBidThreshold.objects.filter(nft_id=nft_pk, is_active=True).first,
            thread_sensitive=False
        )()
        if nft_threshold:
            return nft_threshold

        # --- Collection-level Threshold ---
        # Pass collection_id directly
        collection_threshold = await sync_to_async(
            MinimumBidThreshold.objects.filter(collection_id=collection_id, nft__isnull=True, is_active=True).first,
            thread_sensitive=False
        )()
        if collection_threshold:
             return collection_threshold

        # --- Global Threshold ---
        global_threshold = await sync_to_async(
            MinimumBidThreshold.objects.filter(collection__isnull=True, nft__isnull=True, is_active=True).first,
            thread_sensitive=False
        )()

        return global_threshold

    async def _validate_against_threshold(
        self,
        bid_amount: Decimal,
        vitality: NFTVitality,
        threshold: MinimumBidThreshold
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate bid against a specific threshold configuration.
        """
        if threshold.threshold_type == 'VITALITY_BASED':
            return await self._validate_vitality_based(bid_amount, vitality, threshold)
        
        elif threshold.threshold_type == 'ABSOLUTE':
            return await self._validate_absolute_sol(bid_amount, threshold)
        
        elif threshold.threshold_type == 'BOTH':
            # For 'BOTH', enforce the stricter (higher) minimum
            vitality_min, _ = await self._calculate_vitality_minimum(vitality, threshold)
            absolute_min = threshold.absolute_minimum_sol
            
            effective_minimum = max(vitality_min, absolute_min)

            if bid_amount < effective_minimum:
                return False, f"Bid too low. The minimum bid for this item is {effective_minimum} SOL."
            
            return True, None
            
        else:
            logger.error(f"Unknown threshold type: {threshold.threshold_type}")
            return True, None

    async def _calculate_vitality_minimum(
        self,
        vitality: NFTVitality,
        threshold: MinimumBidThreshold
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculate the minimum bid based on vitality threshold.
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
        Validate bid against vitality-based threshold (e.g., no more than 20% below suggested price).
        """
        minimum_bid, suggested_price = await self._calculate_vitality_minimum(vitality, threshold)

        if bid_amount < minimum_bid:
            # Calculation to show the user how far off they are
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
        Default: -20% below vitality-based price.
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
        Uses collection floor as baseline.
        """
        # Accessing vitality.nft.collection is efficient because of select_related in validate_bid
        collection = vitality.nft.collection 
        
        # NOTE: Assumes NFTCollection has a 'floor_price' field (not shown, using placeholder logic)
        floor_price = getattr(collection, 'floor_price', Decimal('1.0')) or Decimal('1.0')

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
        Get information about minimum bid requirements for an NFT (for UI display).
        """
        try:
            # FIX: Added nft__collection to select_related for efficiency
            vitality = await sync_to_async(
                NFTVitality.objects.select_related('nft__collection').get,
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

        suggested_price = vitality.suggested_price or await self._estimate_price_from_vitality(vitality)
        threshold = await self._get_applicable_threshold(nft)

        # Logic to determine the final minimum bid based on threshold priority
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
                threshold_percentage = None
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