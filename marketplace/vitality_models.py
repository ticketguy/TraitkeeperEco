# marketplace/vitality_models.py

"""
NFT Vitality System - TraitKeeper's Proprietary Value Metric

This module contains models for calculating and storing NFT Vitality scores.
Component fields are changed from DecimalField to FloatField for consistency
with the calculation service, while the final vitality_score remains a precise Decimal.
"""

from django.db import models
from django.utils import timezone
from decimal import Decimal

from django.db.models import Avg, Q
from nft_data.models import NFT, NFTCollection


class NFTVitality(models.Model):
    """
    Stores the current vitality score for an individual NFT.
    """

    # One-to-one relationship ensures each NFT has exactly one current vitality score
    nft = models.OneToOneField(
        NFT,
        on_delete=models.CASCADE,
        related_name='vitality',
        help_text="The NFT this vitality score belongs to"
    )

    # === Overall Vitality Score (0-100) ===
    vitality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('50.00'),
        help_text="Final weighted vitality score (0-100)"
    )

    # === Component Scores (0-1 range, now FloatField for calculation service consistency) ===

    # Market Momentum (25% weight)
    market_momentum = models.FloatField( # FIXED: Changed to FloatField
        default=0.5,
        help_text="Price/interest momentum over 60 days (0-1)"
    )

    # Trait Performance (20% weight)
    trait_performance = models.FloatField( # FIXED: Changed to FloatField
        default=0.5,
        help_text="Avg performance of this NFT's traits (0-1)"
    )

    # Collection Health (15% weight)
    collection_health = models.FloatField( # FIXED: Changed to FloatField
        default=0.5,
        help_text="Parent collection's market health (0-1)"
    )

    # Collection Utility (10% weight)
    collection_utility = models.FloatField( # FIXED: Changed to FloatField
        default=0.5,
        help_text="Collection's utility/use-case value (0-1)"
    )

    # Rarity Score (10% weight)
    rarity_score = models.FloatField( # FIXED: Changed to FloatField
        default=0.5,
        help_text="Trait combination rarity (0-1)"
    )

    # Holder Quality (10% weight)
    holder_quality = models.FloatField( # FIXED: Changed to FloatField
        default=0.5,
        help_text="Current holder's wallet quality (0-1)"
    )

    # Perception Index (20% weight) - Anti-gaming metric
    perception_index = models.FloatField( # FIXED: Changed to FloatField
        default=0.5,
        help_text="Community perception (0-1) - TODO: Not yet implemented"
    )

    # Market Influence (5% weight)
    market_influence = models.FloatField( # FIXED: Changed to FloatField
        default=0.5,
        help_text="Market influence score (0-1)"
    )

    # === Suggested Price ===
    suggested_price = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="Suggested SOL price based on vitality - NOT YET IMPLEMENTED"
    )

    # === Metadata ===
    last_calculated = models.DateTimeField(
        auto_now=True,
        help_text="When this vitality score was last updated"
    )

    calculation_source = models.CharField(
        max_length=50,
        default='system',
        help_text="What triggered this calculation (system, manual, event)"
    )

    # Track if we have sufficient data for accurate calculation
    has_sufficient_data = models.BooleanField(
        default=False,
        help_text="True if collection has at least 1 transaction for calculation"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "NFT Vitality"
        verbose_name_plural = "NFT Vitalities"
        indexes = [
            models.Index(fields=['vitality_score', '-last_calculated']),
            models.Index(fields=['has_sufficient_data', 'vitality_score']),
        ]

    def __str__(self):
        return f"{self.nft.name}: {self.vitality_score}/100"


class NFTVitalityHistory(models.Model):
    """
    Time-series history of NFT vitality scores.
    """

    nft = models.ForeignKey(
        NFT,
        on_delete=models.CASCADE,
        related_name='vitality_history',
        help_text="The NFT this historical record belongs to"
    )

    # === Snapshot of Vitality at This Point in Time ===
    vitality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Vitality score at this timestamp"
    )

    # Component breakdown (stored for transparency)
    market_momentum = models.FloatField() # FIXED: Changed to FloatField
    trait_performance = models.FloatField() # FIXED: Changed to FloatField
    collection_health = models.FloatField() # FIXED: Changed to FloatField
    collection_utility = models.FloatField() # FIXED: Changed to FloatField
    rarity_score = models.FloatField() # FIXED: Changed to FloatField
    holder_quality = models.FloatField() # FIXED: Changed to FloatField
    perception_index = models.FloatField() # FIXED: Changed to FloatField
    market_influence = models.FloatField() # FIXED: Changed to FloatField

    suggested_price = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        null=True,
        blank=True
    )

    # Timestamp
    calculated_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this snapshot was created"
    )
    recorded_at = models.DateTimeField(auto_now_add=True) 
    class Meta:
        verbose_name = "NFT Vitality History"
        verbose_name_plural = "NFT Vitality Histories"
        ordering = ['-calculated_at']
        indexes = [
            models.Index(fields=['nft', '-calculated_at']),
            models.Index(fields=['calculated_at', 'vitality_score']),
        ]

    def __str__(self):
        return f"{self.nft.name} - {self.vitality_score} at {self.calculated_at}"


class CollectionVitality(models.Model):
    """
    Collection-level vitality score.
    """

    # One-to-one: each collection has one current vitality score
    collection = models.OneToOneField(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='vitality',
        help_text="The collection this vitality score belongs to"
    )

    # === Overall Collection Vitality (0-100) ===
    vitality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('50.00'),
        help_text="Collection-level vitality score (0-100)"
    )

    # === Collection-Level Components (FIXED: Changed to FloatField) ===

    market_momentum = models.FloatField(
        default=0.5,
        help_text="Collection's price/volume momentum over 60 days (0-1)"
    )

    avg_trait_performance = models.FloatField(
        default=0.5,
        help_text="Average trait performance across collection (0-1)"
    )

    collection_health = models.FloatField(
        default=0.5,
        help_text="Overall market health (0-1)"
    )

    collection_utility = models.FloatField(
        default=0.5,
        help_text="Collection's utility/use-case value (0-1)"
    )

    avg_rarity_score = models.FloatField(
        default=0.5,
        help_text="Average rarity across collection (0-1)"
    )

    holder_quality_avg = models.FloatField(
        default=0.5,
        help_text="Average holder quality (0-1)"
    )

    perception_index = models.FloatField(
        default=0.5,
        help_text="Collection perception (0-1) - TODO: Not yet implemented"
    )

    market_influence = models.FloatField(
        default=0.5,
        help_text="Collection's market influence (0-1)"
    )

    # === Metadata ===
    last_calculated = models.DateTimeField(auto_now=True)

    has_sufficient_data = models.BooleanField(
        default=False,
        help_text="True if collection has at least 1 transaction"
    )

    updated_at = models.DateTimeField(auto_now=True) 
    class Meta:
        verbose_name = "Collection Vitality"
        verbose_name_plural = "Collection Vitalities"
        indexes = [
            models.Index(fields=['vitality_score', '-last_calculated']),
        ]
    def __str__(self):
        return f"{self.collection.display_name}: {self.vitality_score}/100"
    

    @property
    def total_nfts(self):
        """
        FIXED: Removed synchronous DB query. Access this via an async service or pre-annotation.
        """
        raise NotImplementedError("Access this via an async service or pre-annotation.")

    @property
    def nfts_with_data(self):
        """
        FIXED: Removed synchronous DB query. Access this via an async service or pre-annotation.
        """
        raise NotImplementedError("Access this via an async service or pre-annotation.")

    @property
    def avg_nft_vitality(self):
        """
        FIXED: Removed synchronous DB query. Access this via an async service or pre-annotation.
        """
        raise NotImplementedError("Access this via an async service or pre-annotation.")

    @property
    def trait_performance(self):
        """Placeholder for trait performance logic."""
        return "N/A" 

    @property
    def holder_quality(self):
        """Placeholder for holder quality logic."""
        return "N/A"

    @property
    def suggested_floor_price(self):
        """Placeholder for a calculated suggested floor price."""
        return "N/A"
## Missing Fields for His


class CollectionVitalityHistory(models.Model):
    """
    Time-series history of collection vitality scores.
    """

    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='vitality_history',
        help_text="The collection this historical record belongs to"
    )

    vitality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Collection vitality at this timestamp"
    )

    # Component breakdown (FIXED: Changed to FloatField)
    market_momentum = models.FloatField()
    avg_trait_performance = models.FloatField()
    collection_health = models.FloatField()
    collection_utility = models.FloatField()
    avg_rarity_score = models.FloatField()
    holder_quality_avg = models.FloatField()
    perception_index = models.FloatField()
    market_influence = models.FloatField()

    calculated_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    recorded_at = models.DateTimeField(auto_now_add=True) 
    class Meta:
        verbose_name = "Collection Vitality History"
        verbose_name_plural = "Collection Vitality Histories"
        ordering = ['-calculated_at']
        indexes = [
            models.Index(fields=['collection', '-calculated_at']),
        ]

    def __str__(self):
        return f"{self.collection.display_name} - {self.vitality_score} at {self.calculated_at}"


class VitalityPriceComparison(models.Model):
    """
    Tracks actual sale prices vs vitality-suggested prices.
    """

    # Link to the sale event
    sale_event = models.OneToOneField(
        'indexer.NFTEvent',
        on_delete=models.CASCADE,
        related_name='vitality_comparison',
        help_text="The sale event being analyzed"
    )

    nft = models.ForeignKey(
        NFT,
        on_delete=models.CASCADE,
        related_name='vitality_comparisons'
    )

    # === Sale Details ===
    actual_sale_price = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        help_text="Actual SOL price the NFT sold for"
    )

    marketplace = models.CharField(
        max_length=50,
        help_text="Where the sale occurred (magic_eden, tensor, traitkeeper, etc.)"
    )

    # === Vitality at Time of Sale ===
    vitality_at_sale = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Vitality score when the NFT was sold"
    )

    suggested_price_at_sale = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="What vitality suggested the price should be"
    )

    # === Comparison Metrics ===
    price_difference_sol = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        help_text="Actual - Suggested (positive = sold above vitality)"
    )

    price_difference_percent = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="(Actual - Suggested) / Suggested * 100"
    )

    # === Collection Context ===
    collection_floor_at_sale = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        help_text="Collection floor price at time of sale"
    )

    vs_floor_percent = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="How the actual price compared to floor"
    )

    # Metadata
    sale_timestamp = models.DateTimeField(help_text="When the sale occurred")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vitality Price Comparison"
        verbose_name_plural = "Vitality Price Comparisons"
        ordering = ['-sale_timestamp']
        indexes = [
            models.Index(fields=['nft', '-sale_timestamp']),
            models.Index(fields=['marketplace', '-sale_timestamp']),
            models.Index(fields=['-price_difference_percent']),
        ]

    def __str__(self):
        return f"{self.nft.name} - Actual: {self.actual_sale_price} vs Suggested: {self.suggested_price_at_sale}"

    @property
    def accuracy_rating(self):
        """
        Calculates a simple 'Excellent', 'Good', 'Fair', or 'Poor'
        rating based on the price deviation percentage.
        """
        deviation = abs(self.price_difference_percent)
        if deviation <= 10:
            return "Excellent"
        elif deviation <= 25:
            return "Good"
        elif deviation <= 50:
            return "Fair"
        else:
            return "Poor"

class MinimumBidThreshold(models.Model):
    """
    Stores minimum bid thresholds for collections or individual NFTs.
    """

    # Either collection-level OR NFT-level (one must be null)
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='bid_thresholds',
        help_text="If set, this threshold applies to the entire collection"
    )

    nft = models.ForeignKey(
        NFT,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='bid_threshold',
        help_text="If set, this threshold applies to this specific NFT"
    )

    # === Threshold Types ===

    # Type 1: Absolute minimum price (in SOL)
    absolute_minimum_sol = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="Hard minimum price in SOL (e.g., 0.5 SOL)"
    )

    # Type 2: Percentage below vitality
    vitality_percentage_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Max % below vitality allowed (e.g., -15.00 means -15%)"
    )

    # Which threshold to use
    class ThresholdType(models.TextChoices):
        ABSOLUTE = 'ABSOLUTE', 'Absolute SOL Minimum'
        VITALITY_BASED = 'VITALITY_BASED', 'Vitality Percentage-Based'
        BOTH = 'BOTH', 'Use Whichever is Higher'

    threshold_type = models.CharField(
        max_length=20,
        choices=ThresholdType.choices,
        default=ThresholdType.VITALITY_BASED,
        help_text="Which threshold rule to enforce"
    )

    # === Who Set This Threshold ===
    class SetBy(models.TextChoices):
        SYSTEM = 'SYSTEM', 'System Default'
        OWNER = 'OWNER', 'NFT Owner'
        ADMIN = 'ADMIN', 'Platform Admin'

    set_by = models.CharField(
        max_length=20,
        choices=SetBy.choices,
        default=SetBy.SYSTEM
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_active = models.BooleanField(
        default=True,
        help_text="Can be disabled without deleting"
    )

    class Meta:
        verbose_name = "Minimum Bid Threshold"
        verbose_name_plural = "Minimum Bid Thresholds"
        # Ensure only one threshold per collection/NFT
        constraints = [
            models.CheckConstraint(
                check=models.Q(collection__isnull=False) | models.Q(nft__isnull=False),
                name='threshold_must_have_collection_or_nft'
            ),
            models.CheckConstraint(
                check=~(models.Q(collection__isnull=False) & models.Q(nft__isnull=False)),
                name='threshold_cannot_have_both_collection_and_nft'
            ),
        ]

    def __str__(self):
        target = self.collection.display_name if self.collection else self.nft.name
        return f"Bid Threshold for {target}: {self.threshold_type}"