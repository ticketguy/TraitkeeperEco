# analytics/models.py

from django.db import models
from django.utils import timezone

# Import core models from the 'nft_data' app to establish relationships.
from nft_data.models import NFTCollection, NFT, TraitType, TraitValue


# ===================================================================
# Collection-Level Analytics
# Models that store insights about an entire collection's performance.
# ===================================================================

class AggregatedCollectionStats(models.Model):
    """
    Stores the final, aggregated, and analyzed metrics for a collection.

    This is the primary data source for displaying a collection's overall health,
    combining intelligently processed data from the indexer into a single,
    up-to-date record. It is the main output of the MetricsCalculationService.
    """
    # Use a OneToOneField to ensure each collection has only one "latest" stats record.
    # For historical data, you could use a separate model or change this to a ForeignKey.
    collection = models.OneToOneField(
        NFTCollection, 
        on_delete=models.CASCADE, 
        related_name='aggregated_stats',
        help_text="The collection these analytics apply to."
    )
    
    # --- Aggregated Base Metrics (Result of intelligent aggregation) ---
    floor_price = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    volume_24h = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    listed_count = models.IntegerField(default=0)
    total_supply = models.IntegerField(default=0)
    number_of_holders = models.IntegerField(default=0)
    
    # --- Calculated Analytics (The output of your service) ---
    vitality_score = models.FloatField(default=0.0, help_text="TraitKeeper's proprietary collection health score.")
    holder_quality_score = models.FloatField(default=0.0)
    sentiment_score = models.FloatField(default=0.0)
    market_influence_score = models.FloatField(default=0.0)
    performance_score = models.FloatField(default=0.0)
    market_cap = models.DecimalField(max_digits=25, decimal_places=9, default=0)
    price_change_24h = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    price_change_7d = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    percent_listed = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    velocity_24h = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    market_efficiency_score = models.FloatField(default=0.0)
    holder_confidence_index = models.FloatField(default=0.0)
    liquidity_health_score = models.FloatField(default=0.0)
    
    # --- Metadata ---
    updated_at = models.DateTimeField(auto_now=True)
    source_attribution = models.JSONField(default=dict, help_text="Details which source was used for each aggregated field.")

    def __str__(self):
        return f"Aggregated Stats for {self.collection.name}"


class CollectionSweepEvent(models.Model):
    """Stores a record of a collection sweep event (a rapid series of buys)."""
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='sweep_events')
    buyer_address = models.CharField(max_length=44, db_index=True, help_text="The primary wallet address leading the sweep.")
    
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration_minutes = models.FloatField()
    num_items = models.IntegerField(help_text="Number of NFTs purchased during the sweep.")
    total_volume = models.FloatField(help_text="Total SOL spent during the sweep.")
    
    significance_score = models.FloatField(default=0.0, help_text="A score (0-100) indicating the market impact of the sweep.")
    nft_mints = models.JSONField(default=list, help_text="A list of mint addresses of the NFTs that were swept.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_time']
        indexes = [models.Index(fields=['collection', '-significance_score'])]

    def __str__(self):
        return f"Sweep of {self.num_items} items from {self.collection.name}"


class HighProfileTransfer(models.Model):
    """Stores a record of a high-value or high-significance NFT transfer or sale."""
    # NOTE: The event is linked via a string to avoid a hard dependency on the indexer app,
    # which is a good practice for decoupling apps.
    event = models.ForeignKey('indexer.NFTEvent', on_delete=models.CASCADE, related_name='high_profile_transfers')
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='high_profile_transfers')
    nft = models.ForeignKey(NFT, on_delete=models.CASCADE, related_name='high_profile_transfers')
    
    high_profile_score = models.FloatField(default=0.0, help_text="A score indicating the significance of this transfer.")
    # Factors contributing to the score
    value_factor = models.FloatField(default=0.0)
    wallet_factor = models.FloatField(default=0.0)
    timing_factor = models.FloatField(default=0.0)
    
    rank = models.IntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-high_profile_score']
        indexes = [models.Index(fields=['collection', '-high_profile_score'])]


# ===================================================================
# Trait-Level Analytics
# Models that score and rank individual traits.
# ===================================================================

class TraitPerformanceScore(models.Model):
    """
    Stores the calculated performance score for a single trait value within a collection.
    
    CRITICAL FIX: This model no longer links to a specific `NFT`. Storing a score
    for every trait on every NFT is extremely inefficient. Instead, this model
    correctly represents the performance of a *trait value* as a whole (e.g., how
    well do "Gold" hats perform in this collection?), which is what the analytics
    service actually calculates.
    """
    trait_type = models.ForeignKey(TraitType, on_delete=models.CASCADE, related_name='performance_scores')
    trait_value = models.ForeignKey(TraitValue, on_delete=models.CASCADE, related_name='performance_scores')
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='trait_performance_scores')
    
    rarity_score = models.FloatField(default=0.0, help_text="The rarity percentage of this trait.")
    avg_sale_price = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    premium_score = models.FloatField(default=0.0, help_text="The calculated price premium this trait commands over the floor.")
    velocity_score = models.FloatField(default=0.0, help_text="A measure of how quickly NFTs with this trait are sold.")
    momentum_score = models.FloatField(default=0.0, help_text="The recent price trend for this trait.")
    performance_score = models.FloatField(default=0.0, db_index=True, help_text="The final combined performance score for this trait.")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-performance_score']
        unique_together = ('collection', 'trait_value') # A trait value can only have one score per collection.
        indexes = [
            models.Index(fields=['collection', '-performance_score']),
            models.Index(fields=['trait_value', '-performance_score']),
        ]

    def __str__(self):
        return f"{self.trait_value.value} ({self.trait_type.name}): {self.performance_score:.2f}"


class TrendingTrait(models.Model):
    """A record of a trait that is currently trending based on recent sales velocity and momentum."""
    trait_value = models.ForeignKey(TraitValue, on_delete=models.CASCADE)
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE)
    trend_score = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-trend_score']


class TopTrait(models.Model):
    """A record of a trait with a high overall performance score, considering rarity, volume, and premium."""
    trait_value = models.ForeignKey(TraitValue, on_delete=models.CASCADE)
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE)
    combined_score = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-combined_score']


# ===================================================================
# Wallet Analytics
# Models that store insights about wallet behavior.
# ===================================================================

class WalletProminence(models.Model):
    """Stores a calculated prominence score for a wallet based on its overall market activity."""
    address = models.CharField(max_length=44, unique=True, db_index=True)
    transaction_count = models.IntegerField(default=0)
    transaction_volume = models.FloatField(default=0.0)
    collections_count = models.IntegerField(default=0)
    prominence_score = models.FloatField(default=0.0, db_index=True, help_text="Score (0-100) indicating wallet's market influence.")
    last_updated = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-prominence_score']
    
class WalletBehaviorProfile(models.Model):
    """
    Advanced wallet behavior classification and analysis.
    Enhances your existing WalletProminence model.
    """
    
    BEHAVIOR_TYPES = [
        ('whale', 'Whale'),
        ('scalper', 'Scalper'),
        ('holder', 'Long-term Holder'),
        ('flipper', 'Quick Flipper'),
        ('collector', 'Collector'),
        ('arbitrageur', 'Arbitrageur'),
        ('market_maker', 'Market Maker'),
        ('institutional', 'Institutional'),
        ('bot', 'Bot/Automated'),
        ('casual', 'Casual Trader'),
    ]
    
    RISK_TOLERANCE = [
        ('very_low', 'Very Low'),
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('very_high', 'Very High'),
    ]
    
    # Core identification
    wallet_address = models.CharField(max_length=44, unique=True, db_index=True)
    behavior_type = models.CharField(max_length=20, choices=BEHAVIOR_TYPES)
    confidence_score = models.FloatField(
        default=0.0,
        help_text="Confidence in behavior classification (0-1)"
    )
    
    # ==================== TRADING BEHAVIOR ====================
    # Trading patterns
    avg_hold_time_hours = models.FloatField(default=0.0)
    trade_frequency_per_day = models.FloatField(default=0.0)
    avg_profit_margin = models.FloatField(default=0.0)
    success_rate = models.FloatField(default=0.0)
    
    # Risk profile
    risk_tolerance = models.CharField(max_length=20, choices=RISK_TOLERANCE, default='medium')
    max_single_purchase = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    diversification_score = models.FloatField(
        default=0.0,
        help_text="How diversified their portfolio is (0-1)"
    )
    
    # ==================== INFLUENCE METRICS ====================
    # Market influence
    influence_score = models.FloatField(
        default=0.0,
        help_text="How much this wallet influences market movements (0-1)"
    )
    trendsetting_ability = models.FloatField(
        default=0.0,
        help_text="How often this wallet's actions predict trends (0-1)"
    )
    
    # Social indicators
    copy_trader_count = models.IntegerField(
        default=0,
        help_text="Estimated number of wallets that copy this wallet's trades"
    )
    network_centrality = models.FloatField(
        default=0.0,
        help_text="Position in the trading network (0-1)"
    )
    
    # ==================== ACTIVITY PATTERNS ====================
    # Time-based patterns
    most_active_hours = models.JSONField(
        default=list,
        help_text="Hours of day when most active (0-23)"
    )
    seasonal_patterns = models.JSONField(
        default=dict,
        help_text="Seasonal trading patterns and preferences"
    )
    
    # Collection preferences
    preferred_collections = models.ManyToManyField(
        NFTCollection,
        related_name='preferred_by_wallets',
        blank=True
    )
    collection_loyalty_score = models.FloatField(
        default=0.0,
        help_text="How loyal to specific collections (0-1)"
    )
    
    # ==================== ADVANCED ANALYTICS ====================
    # Behavioral indicators
    fomo_susceptibility = models.FloatField(
        default=0.0,
        help_text="How susceptible to FOMO buying (0-1)"
    )
    contrarian_indicator = models.FloatField(
        default=0.0,
        help_text="How often they trade against the trend (0-1)"
    )
    
    # Market timing
    market_timing_ability = models.FloatField(
        default=0.0,
        help_text="Ability to time market entries/exits (0-1)"
    )
    
    # ML preparation fields
    behavior_features = models.JSONField(
        default=dict,
        help_text="ML: Feature vector for behavior classification"
    )
    clustering_assignment = models.IntegerField(
        null=True,
        blank=True,
        help_text="ML: Cluster assignment from unsupervised learning"
    )
    
    # Metadata
    first_seen = models.DateTimeField()
    last_activity = models.DateTimeField()
    total_transactions = models.IntegerField(default=0)
    total_volume = models.DecimalField(max_digits=25, decimal_places=9, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['behavior_type', 'influence_score']),
            models.Index(fields=['confidence_score', 'updated_at']),
            models.Index(fields=['risk_tolerance', 'total_volume']),
            models.Index(fields=['clustering_assignment', 'behavior_type']),
        ]
        ordering = ['-influence_score']
    
    def __str__(self):
        return f"{self.wallet_address[:8]} - {self.behavior_type} (confidence: {self.confidence_score:.2f})"


