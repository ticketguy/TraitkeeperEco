# marketplace/vitality_models.py

"""
NFT Vitality System - TraitKeeper's Proprietary Value Metric

This module contains models for calculating and storing NFT Vitality scores,
which serve as the primary value indicator in TraitKeeper's marketplace.

Vitality is a multi-component score (0-100) that represents an NFT's true value
based on trait performance, rarity, collection health, market momentum, holder quality,
and historical stability. Unlike floor price (which is collection-level), Vitality
provides individual NFT-level valuation.

Component Weights (User-Specified):
- Market Momentum: 25%
- Trait Performance: 20%
- Collection Health: 15%
- Collection Utility: 10%
- Rarity Score: 10%
- Holder Quality: 10%
- Sentiment Score: 5% (TODO: Not yet implemented, returns neutral)
- Market Influence: 5%

Total: 100%
"""

from django.db import models
from django.utils import timezone
from decimal import Decimal

from django.db.models import Avg
from nft_data.models import NFT, NFTCollection


class NFTVitality(models.Model):
    """
    Stores the current vitality score for an individual NFT.

    This is the main model for NFT-level vitality. Each NFT has exactly one
    current vitality record that gets updated periodically based on the
    collection's priority tier (VIP = every 15 min, ACTIVE = hourly, etc.).

    Vitality is PUBLIC - anyone can see the score and its component breakdown.
    This transparency helps buyers and sellers make informed decisions.
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

    # === Component Scores (0-1 range, weighted in calculation) ===

    # Market Momentum (25% weight)
    # Recent price velocity and interest trends for this specific NFT
    # Calculated using 60-day lookback period
    market_momentum = models.FloatField(
        default=0.5,
        help_text="Price/interest momentum over 60 days (0-1)"
    )

    # Trait Performance (20% weight)
    # How well NFTs with similar traits are performing in the market
    trait_performance = models.FloatField(
        default=0.5,
        help_text="Avg performance of this NFT's traits (0-1)"
    )

    # Collection Health (15% weight)
    # Overall health of the parent collection
    collection_health = models.FloatField(
        default=0.5,
        help_text="Parent collection's market health (0-1)"
    )

    # Collection Utility (10% weight)
    # Utility value the collection provides (staking, governance, access, etc.)
    collection_utility = models.FloatField(
        default=0.5,
        help_text="Collection's utility/use-case value (0-1)"
    )

    # Rarity Score (10% weight)
    # Statistical rarity of trait combinations
    rarity_score = models.FloatField(
        default=0.5,
        help_text="Trait combination rarity (0-1)"
    )

    # Holder Quality (10% weight)
    # Quality/influence of the current holder's wallet
    holder_quality = models.FloatField(
        default=0.5,
        help_text="Current holder's wallet quality (0-1)"
    )

    # Sentiment Score (5% weight)
    # TODO: Implement sentiment analysis from social media/community
    # Future: Twitter mentions, Discord activity, user reviews
    # For now, defaults to 0.5 (neutral)
    sentiment_score = models.FloatField(
        default=0.5,
        help_text="Community sentiment (0-1) - TODO: Not yet implemented"
    )

    # Market Influence (5% weight)
    # How influential this NFT/collection is in the broader market
    market_influence = models.FloatField(
        default=0.5,
        help_text="Market influence score (0-1)"
    )

    # === Suggested Price ===
    # TODO: Implement price suggestion algorithm
    # This will convert vitality score to a suggested SOL price
    # For now, set to None until algorithm is finalized
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

    Stores snapshots of vitality calculations over time, allowing us to:
    - Track how an NFT's value changes
    - Analyze vitality trends
    - Provide historical charts to users
    - Validate vitality accuracy (compare to actual sale prices)

    This is PUBLIC data - transparency builds trust in the vitality system.
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
    market_momentum = models.FloatField()
    trait_performance = models.FloatField()
    collection_health = models.FloatField()
    collection_utility = models.FloatField()
    rarity_score = models.FloatField()
    holder_quality = models.FloatField()
    sentiment_score = models.FloatField()
    market_influence = models.FloatField()

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

    While NFTs within a collection have different individual vitality scores,
    the collection as a whole also has a vitality score representing its
    overall market health and value proposition.

    This is used in the NFT vitality calculation (collection_health component)
    and also displayed on collection pages.
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

    # === Collection-Level Components ===
    # These are aggregated from all NFTs in the collection

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

    sentiment_score = models.FloatField(
        default=0.5,
        help_text="Collection sentiment (0-1) - TODO: Not yet implemented"
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
        """Total number of NFTs in the collection."""
        # Count via the NFT model's FK to NFTCollection (assumes the FK field is named 'collection')
        return NFT.objects.filter(collection=self.collection).count()

    @property
    def nfts_with_data(self):
        """Number of NFTs in the collection that have a vitality score."""
        return NFT.objects.filter(collection=self.collection, vitality__isnull=False).count()

    @property
    def avg_nft_vitality(self):
        """The average vitality score of all NFTs within this collection."""
        aggregation = NFT.objects.filter(collection=self.collection).aggregate(avg_score=Avg('vitality__vitality_score'))
        return round(aggregation['avg_score'], 2) if aggregation['avg_score'] else 0.0

    @property
    def trait_performance(self):
        """Placeholder for trait performance logic."""
        # This requires complex logic. For now, a placeholder will fix the error.
        # You would calculate this based on trait sales, rarity, etc.
        return "N/A" 
        return "N/A" 

    @property
    def holder_quality(self):
        """Placeholder for holder quality logic."""
        # This requires complex logic. For now, a placeholder will fix the error.
        # You would analyze the wallets holding NFTs from this collection.
        return "N/A"

    @property
    def suggested_floor_price(self):
        """Placeholder for a calculated suggested floor price."""
        # Your VitalityCalculationService would likely determine this.
        # For now, this placeholder will fix the admin error.
        return "N/A"
## Missing Fields for His


class CollectionVitalityHistory(models.Model):
    """
    Time-series history of collection vitality scores.

    Allows tracking of collection-level vitality trends over time.
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

    # Component breakdown
    market_momentum = models.FloatField()
    avg_trait_performance = models.FloatField()
    collection_health = models.FloatField()
    collection_utility = models.FloatField()
    avg_rarity_score = models.FloatField()
    holder_quality_avg = models.FloatField()
    sentiment_score = models.FloatField()
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

    This model helps us:
    1. Validate vitality accuracy
    2. Improve the vitality algorithm over time
    3. Show users how accurate vitality predictions are

    Created automatically when an NFT is sold (from any marketplace).
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

    As specified by user:
    - Option 1: Set minimum price for certain collections
    - Option 2: Bids cannot be too far below vitality (lowest -15% to -30%)

    This model allows flexibility:
    - Collection-level minimums (e.g., "No bids below 0.5 SOL for this collection")
    - NFT-level minimums (e.g., owner sets "no bids below 1.0 SOL")
    - Vitality-based minimums (e.g., "no bids below -20% of vitality score")
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
