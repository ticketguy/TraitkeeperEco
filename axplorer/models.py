from django.db import models
from nft_data.models import NFTCollection, TraitType, TraitValue
from analytics.models import AggregatedCollectionStats

# Create your models here.

class CrossMarketplaceComparison(models.Model):
    """Compare performance across different marketplaces."""
    
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='marketplace_comparisons'
    )
    
    # Price comparison
    tensor_floor = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    magic_eden_floor = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    price_differential = models.DecimalField(
        max_digits=10, decimal_places=4, default=0,
        help_text="Percentage difference between marketplace floors"
    )
    
    # Volume comparison
    tensor_volume_24h = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    magic_eden_volume_24h = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    volume_distribution = models.FloatField(
        default=0.0,
        help_text="Volume distribution ratio (0 = all ME, 1 = all Tensor)"
    )
    
    # Liquidity comparison
    tensor_listings = models.IntegerField(default=0)
    magic_eden_listings = models.IntegerField(default=0)
    liquidity_preference = models.FloatField(
        default=0.0,
        help_text="Where liquidity is concentrated (0 = ME, 1 = Tensor)"
    )
    
    # Arbitrage opportunities
    arbitrage_opportunity = models.DecimalField(
        max_digits=10, decimal_places=4, default=0,
        help_text="Potential arbitrage profit percentage"
    )
    arbitrage_direction = models.CharField(
        max_length=20,
        choices=[
            ('tensor_to_me', 'Buy Tensor, Sell Magic Eden'),
            ('me_to_tensor', 'Buy Magic Eden, Sell Tensor'),
            ('none', 'No Arbitrage'),
        ],
        default='none'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    activity_distribution_tensor = models.FloatField(default=0.0)
    activity_distribution_magic_eden = models.FloatField(default=0.0)
    momentum_differential = models.FloatField(default=0.0)
    leading_platform = models.CharField(
        max_length=20,
        choices=[  # Change this from whatever it currently is
            ('tensor', 'Tensor'),
            ('magic_eden', 'Magic Eden'),
            ('balanced', 'Balanced'),
        ],
        default='balanced'
    )
    liquidity_preference_score = models.FloatField(default=0.0)
    
    class Meta:
        indexes = [
            models.Index(fields=['collection', 'created_at']),
            models.Index(fields=['arbitrage_opportunity', 'created_at']),
        ]
        ordering = ['-created_at']


# ==================== ANALYTICS ALERT MODELS ====================

class MarketAlert(models.Model):
    """Model for tracking and sending market-based alerts."""
    
    ALERT_TYPES = [
        ('price_spike', 'Price Spike'),
        ('price_drop', 'Price Drop'),
        ('volume_surge', 'Volume Surge'),
        ('supply_pressure', 'Supply Pressure'),
        ('bid_activity', 'High Bid Activity'),
        ('arbitrage', 'Arbitrage Opportunity'),
        ('trend_reversal', 'Trend Reversal'),
    ]
    
    SEVERITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='market_alerts'
    )
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default='medium')
    
    # Alert details
    title = models.CharField(max_length=200)
    message = models.TextField()
    trigger_value = models.DecimalField(
        max_digits=20, decimal_places=9, null=True, blank=True,
        help_text="The value that triggered this alert (price, percentage, etc.)"
    )
    threshold_value = models.DecimalField(
        max_digits=20, decimal_places=9, null=True, blank=True,
        help_text="The threshold that was crossed"
    )
    
    # Associated data
    associated_stats = models.ForeignKey(
        AggregatedCollectionStats,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The stats record that triggered this alert"
    )
    
    # Alert metadata
    is_active = models.BooleanField(default=True)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # User interaction
    views_count = models.IntegerField(default=0)
    dismissed_by = models.JSONField(
        default=list,
        help_text="List of user IDs who dismissed this alert"
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['collection', 'alert_type', 'created_at']),
            models.Index(fields=['severity', 'is_active', 'created_at']),
            models.Index(fields=['is_active', 'is_resolved']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.alert_type} alert for {self.collection.name} - {self.severity}"

class AnalyticsSnapshot(models.Model):
    """Periodic snapshots of key analytics for historical analysis."""
    
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='analytics_snapshots'
    )
    
    # Snapshot metadata
    snapshot_type = models.CharField(
        max_length=20,
        choices=[
            ('hourly', 'Hourly'),
            ('daily', 'Daily'), 
            ('weekly', 'Weekly'),
            ('event_driven', 'Event Driven'),
        ],
        default='daily'
    )
    
    # Core metrics at time of snapshot
    floor_price = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    volume_24h = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    listed_count = models.IntegerField(default=0)
    bid_count = models.IntegerField(default=0)
    
    # Analytics scores at time of snapshot
    market_efficiency_score = models.FloatField(default=0.0)
    holder_confidence_index = models.FloatField(default=0.0)
    liquidity_health_score = models.FloatField(default=0.0)
    
    # Market condition indicators
    market_condition = models.CharField(
        max_length=20,
        choices=[
            ('bull', 'Bull Market'),
            ('bear', 'Bear Market'),
            ('sideways', 'Sideways'),
            ('volatile', 'Volatile'),
        ],
        default='sideways'
    )
    
    # Event triggers (if event-driven snapshot)
    trigger_events = models.JSONField(
        default=list,
        help_text="Events that triggered this snapshot (for event_driven type)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['collection', 'snapshot_type', 'created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['market_condition', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.snapshot_type} snapshot for {self.collection.name} - {self.created_at}"

# ==================== USAGE TRACKING ====================

class AnalyticsUsage(models.Model):
    """Track which analytics features are being used most."""
    
    feature_name = models.CharField(max_length=100)
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='analytics_usage',
        null=True,
        blank=True
    )
    
    # Usage metadata
    user_id = models.CharField(max_length=100, null=True, blank=True)  # Can be anonymous
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Query details
    query_parameters = models.JSONField(
        default=dict,
        help_text="Parameters used in the analytics query"
    )
    response_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Response time in milliseconds"
    )
    
    # Timestamps
    accessed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['feature_name', 'accessed_at']),
            models.Index(fields=['collection', 'feature_name']),
            models.Index(fields=['accessed_at']),
        ]
        ordering = ['-accessed_at']
    
    def __str__(self):
        collection_name = self.collection.name if self.collection else "All Collections"
        return f"{self.feature_name} - {collection_name}"


# ==================== ADVANCED ANALYTICS MODELS ====================

class MarketRegime(models.Model):
    """
    Track market regime changes for adaptive analytics.
    Critical for implementing regime-aware scoring and trend analysis.
    """
    
    REGIME_TYPES = [
        ('bull_run', 'Bull Run'),
        ('bear_market', 'Bear Market'),
        ('consolidation', 'Consolidation'),
        ('high_volatility', 'High Volatility'),
        ('low_liquidity', 'Low Liquidity'),
        ('recovery', 'Recovery'),
        ('distribution', 'Distribution'),
    ]
    
    # Regime identification
    regime_type = models.CharField(max_length=30, choices=REGIME_TYPES)
    confidence_score = models.FloatField(
        default=0.0,
        help_text="Confidence in regime classification (0.0-1.0)"
    )
    
    # Market indicators that define this regime
    avg_volume_change = models.FloatField(default=0.0)
    avg_price_volatility = models.FloatField(default=0.0)
    avg_listing_pressure = models.FloatField(default=0.0)
    avg_bid_activity = models.FloatField(default=0.0)
    
    # Regime timing
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration_hours = models.IntegerField(null=True, blank=True)
    
    # Collections affected (if regime is collection-specific)
    collections_affected = models.ManyToManyField(
        NFTCollection,
        related_name='market_regimes',
        blank=True,
        help_text="Collections affected by this regime (empty = market-wide)"
    )
    
    # Regime characteristics
    typical_price_range = models.JSONField(
        default=dict,
        help_text="Typical price ranges observed in this regime"
    )
    volume_characteristics = models.JSONField(
        default=dict,
        help_text="Volume patterns characteristic of this regime"
    )
    
    # Triggers and indicators
    regime_triggers = models.JSONField(
        default=list,
        help_text="Events or indicators that triggered this regime identification"
    )
    
    # ML preparation fields
    feature_vector = models.JSONField(
        default=dict,
        help_text="ML: Feature vector used for regime classification"
    )
    model_version = models.CharField(
        max_length=20,
        default='v1.0',
        help_text="ML: Version of classification model used"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['regime_type', 'start_time']),
            models.Index(fields=['confidence_score', 'start_time']),
            models.Index(fields=['start_time', 'end_time']),
            models.Index(fields=['model_version', 'created_at']),
        ]
        ordering = ['-start_time']
    
    def __str__(self):
        duration = f" ({self.duration_hours}h)" if self.duration_hours else ""
        return f"{self.regime_type} regime{duration} - {self.confidence_score:.2f} confidence"

class AdvancedCrossMarketplaceAnalysis(models.Model):
    """
    Enhanced cross-marketplace analysis with advanced metrics.
    Replaces/enhances your existing CrossMarketplaceComparison model.
    """
    
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='advanced_marketplace_analysis'
    )
    
    # ==================== PRICE ANALYSIS ====================
    # Multi-marketplace floor prices
    tensor_floor = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    magic_eden_floor = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    opensea_floor = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    
    # Price efficiency metrics
    price_convergence_score = models.FloatField(
        default=0.0,
        help_text="How closely prices align across marketplaces (0-1)"
    )
    arbitrage_opportunity_score = models.FloatField(
        default=0.0,
        help_text="Strength of arbitrage opportunities (0-1)"
    )
    optimal_marketplace = models.CharField(
        max_length=20,
        choices=[
            ('tensor', 'Tensor'),
            ('magic_eden', 'Magic Eden'),
            ('opensea', 'OpenSea'),
            ('balanced', 'Balanced'),
        ],
        default='balanced'
    )
    
    # ==================== ACTIVITY DISTRIBUTION ====================
    # Volume distribution across marketplaces
    tensor_volume_share = models.FloatField(default=0.0)
    magic_eden_volume_share = models.FloatField(default=0.0)
    opensea_volume_share = models.FloatField(default=0.0)
    
    # Activity distribution across marketplaces
    tensor_activity_share = models.FloatField(default=0.0)
    magic_eden_activity_share = models.FloatField(default=0.0)
    opensea_activity_share = models.FloatField(default=0.0)
    
    # ==================== MOMENTUM ANALYSIS ====================
    # Momentum differences between platforms
    tensor_momentum = models.FloatField(default=0.0)
    magic_eden_momentum = models.FloatField(default=0.0)
    opensea_momentum = models.FloatField(default=0.0)
    
    momentum_leader = models.CharField(
        max_length=20,
        choices=[
            ('tensor', 'Tensor'),
            ('magic_eden', 'Magic Eden'),
            ('opensea', 'OpenSea'),
            ('synchronized', 'Synchronized'),
        ],
        default='synchronized'
    )
    
    # ==================== LIQUIDITY ANALYSIS ====================
    # Liquidity preference indicators
    liquidity_concentration = models.FloatField(
        default=0.0,
        help_text="How concentrated liquidity is (0=distributed, 1=concentrated)"
    )
    
    primary_liquidity_venue = models.CharField(
        max_length=20,
        choices=[
            ('tensor', 'Tensor'),
            ('magic_eden', 'Magic Eden'),
            ('opensea', 'OpenSea'),
            ('distributed', 'Distributed'),
        ],
        default='distributed'
    )
    
    # Bid/ask spread comparison
    tensor_spread = models.FloatField(default=0.0)
    magic_eden_spread = models.FloatField(default=0.0)
    opensea_spread = models.FloatField(default=0.0)
    
    # ==================== ADVANCED METRICS ====================
    # Cross-platform correlation
    price_correlation = models.FloatField(
        default=0.0,
        help_text="Price correlation across platforms (-1 to 1)"
    )
    volume_correlation = models.FloatField(
        default=0.0,
        help_text="Volume correlation across platforms (-1 to 1)"
    )
    
    # Market efficiency indicators
    information_efficiency = models.FloatField(
        default=0.0,
        help_text="How quickly information propagates across platforms (0-1)"
    )
    
    # ML preparation fields
    cross_platform_features = models.JSONField(
        default=dict,
        help_text="ML: Cross-platform feature vector for analysis"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['collection', 'created_at']),
            models.Index(fields=['arbitrage_opportunity_score', 'created_at']),
            models.Index(fields=['optimal_marketplace', 'created_at']),
            models.Index(fields=['momentum_leader', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Advanced marketplace analysis for {self.collection.name} - {self.created_at}"


class AdvancedTraitAnalytics(models.Model):
    """
    Advanced trait performance analytics with cross-platform analysis.
    Enhances your existing TraitPerformanceScore model.
    """
    
    trait_type = models.ForeignKey(TraitType, on_delete=models.CASCADE, related_name='advanced_analytics')
    trait_value = models.ForeignKey(TraitValue, on_delete=models.CASCADE, related_name='advanced_analytics')
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='advanced_trait_analytics')
    
    # ==================== CROSS-PLATFORM PERFORMANCE ====================
    # Performance on different marketplaces
    tensor_performance_score = models.FloatField(default=0.0)
    magic_eden_performance_score = models.FloatField(default=0.0)
    opensea_performance_score = models.FloatField(default=0.0)
    
    # Platform preference indicator
    optimal_marketplace = models.CharField(
        max_length=20,
        choices=[
            ('tensor', 'Tensor'),
            ('magic_eden', 'Magic Eden'),
            ('opensea', 'OpenSea'),
            ('no_preference', 'No Preference'),
        ],
        default='no_preference'
    )
    
    # ==================== ADVANCED RARITY ANALYSIS ====================
    # Enhanced rarity metrics
    mathematical_rarity = models.FloatField(
        default=0.0,
        help_text="Mathematical rarity score (product of trait rarities)"
    )
    statistical_rarity = models.FloatField(
        default=0.0,
        help_text="Statistical rarity based on distribution analysis"
    )
    perceived_rarity = models.FloatField(
        default=0.0,
        help_text="Market-perceived rarity based on trading behavior"
    )
    
    # Rarity trend
    rarity_trend = models.CharField(
        max_length=20,
        choices=[
            ('increasing', 'Increasing'),
            ('decreasing', 'Decreasing'),
            ('stable', 'Stable'),
            ('volatile', 'Volatile'),
        ],
        default='stable'
    )
    
    # ==================== TRAIT RELATIONSHIP ANALYSIS ====================
    # Trait combination analysis
    synergy_traits = models.JSONField(
        default=list,
        help_text="Traits that perform better when combined with this trait"
    )
    conflict_traits = models.JSONField(
        default=list,
        help_text="Traits that perform worse when combined with this trait"
    )
    combination_premium = models.FloatField(
        default=0.0,
        help_text="Price premium when combined with synergy traits"
    )
    
    # ==================== MARKET DYNAMICS ====================
    # Supply and demand indicators
    supply_shock_risk = models.FloatField(
        default=0.0,
        help_text="Risk of sudden supply increase affecting price (0-1)"
    )
    demand_elasticity = models.FloatField(
        default=0.0,
        help_text="How responsive demand is to price changes"
    )
    
    # Whale involvement
    whale_concentration = models.FloatField(
        default=0.0,
        help_text="Percentage of trait holders that are whales"
    )
    institutional_interest = models.FloatField(
        default=0.0,
        help_text="Level of institutional interest in this trait (0-1)"
    )
    
    # ==================== PREDICTIVE INDICATORS ====================
    # Trend prediction
    trend_prediction_score = models.FloatField(
        default=0.0,
        help_text="Predicted trend direction strength (-1 to 1)"
    )
    momentum_sustainability = models.FloatField(
        default=0.0,
        help_text="How sustainable current momentum is (0-1)"
    )
    
    # Future performance indicators
    growth_potential = models.FloatField(
        default=0.0,
        help_text="Estimated growth potential (0-1)"
    )
    risk_score = models.FloatField(
        default=0.0,
        help_text="Risk score for this trait investment (0-1)"
    )
    
    # ==================== BEHAVIORAL ANALYTICS ====================
    # Holder behavior
    avg_holder_behavior = models.CharField(
        max_length=20,
        choices=[
            ('hodler', 'Long-term Holder'),
            ('flipper', 'Quick Flipper'),
            ('trader', 'Active Trader'),
            ('collector', 'Collector'),
            ('mixed', 'Mixed Behavior'),
        ],
        default='mixed'
    )
    
    holder_conviction = models.FloatField(
        default=0.0,
        help_text="How strongly holders believe in this trait (0-1)"
    )
    
    # ==================== ML PREPARATION ====================
    # Feature vectors for ML models
    price_prediction_features = models.JSONField(
        default=dict,
        help_text="ML: Features for price prediction models"
    )
    trend_prediction_features = models.JSONField(
        default=dict,
        help_text="ML: Features for trend prediction models"
    )
    classification_features = models.JSONField(
        default=dict,
        help_text="ML: Features for trait classification models"
    )
    
    # Model outputs
    ml_predicted_price_change = models.FloatField(
        null=True,
        blank=True,
        help_text="ML: Predicted price change percentage"
    )
    ml_confidence_score = models.FloatField(
        null=True,
        blank=True,
        help_text="ML: Model confidence in predictions (0-1)"
    )
    
    # Metadata
    analysis_period_start = models.DateTimeField()
    analysis_period_end = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['collection', 'trait_type', 'created_at']),
            models.Index(fields=['optimal_marketplace', 'growth_potential']),
            models.Index(fields=['trend_prediction_score', 'created_at']),
            models.Index(fields=['risk_score', 'growth_potential']),
        ]
        ordering = ['-created_at']
        unique_together = ('trait_type', 'trait_value', 'collection')
    
    def __str__(self):
        return f"Advanced analytics: {self.trait_type.name}={self.trait_value.value} ({self.collection.name})"

class PredictionRecord(models.Model):
    """
    Track predictions made by analytics algorithms and their accuracy.
    Essential for ML model validation and improvement.
    """
    
    PREDICTION_TYPES = [
        ('price_direction', 'Price Direction'),
        ('price_target', 'Price Target'),
        ('volume_forecast', 'Volume Forecast'),
        ('trend_reversal', 'Trend Reversal'),
        ('breakout', 'Breakout'),
        ('support_resistance', 'Support/Resistance'),
        ('trait_performance', 'Trait Performance'),
        ('collection_ranking', 'Collection Ranking'),
    ]
    
    PREDICTION_STATUS = [
        ('pending', 'Pending'),
        ('correct', 'Correct'),
        ('incorrect', 'Incorrect'),
        ('partially_correct', 'Partially Correct'),
        ('expired', 'Expired'),
    ]
    
    # Core prediction data
    prediction_id = models.CharField(max_length=100, unique=True, db_index=True)
    prediction_type = models.CharField(max_length=30, choices=PREDICTION_TYPES)
    
    # Target of prediction
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='predictions',
        null=True,
        blank=True
    )
    trait_type = models.ForeignKey(
        TraitType,
        on_delete=models.CASCADE,
        related_name='predictions',
        null=True,
        blank=True
    )
    trait_value = models.ForeignKey(
        TraitValue,
        on_delete=models.CASCADE,
        related_name='predictions',
        null=True,
        blank=True
    )
    
    # ==================== PREDICTION DETAILS ====================
    # Prediction values
    predicted_value = models.JSONField(
        default=dict,
        help_text="The predicted value(s) - structure depends on prediction type"
    )
    confidence_score = models.FloatField(
        default=0.0,
        help_text="Model confidence in this prediction (0-1)"
    )
    
    # Timing
    prediction_horizon_hours = models.IntegerField(
        help_text="How far into the future this prediction extends"
    )
    target_date = models.DateTimeField(
        help_text="When this prediction should be evaluated"
    )
    
    # Context at time of prediction
    market_context = models.JSONField(
        default=dict,
        help_text="Market conditions when prediction was made"
    )
    
    # ==================== MODEL INFORMATION ====================
    # Model metadata
    model_name = models.CharField(max_length=100)
    model_version = models.CharField(max_length=20)
    algorithm_type = models.CharField(
        max_length=30,
        choices=[
            ('linear_regression', 'Linear Regression'),
            ('random_forest', 'Random Forest'),
            ('neural_network', 'Neural Network'),
            ('ensemble', 'Ensemble'),
            ('rule_based', 'Rule-based'),
            ('statistical', 'Statistical'),
        ]
    )
    
    # Input features used
    input_features = models.JSONField(
        default=dict,
        help_text="Features/inputs used to make this prediction"
    )
    feature_importance = models.JSONField(
        default=dict,
        help_text="Importance scores for each feature used"
    )
    
    # ==================== VALIDATION ====================
    # Actual outcome
    actual_value = models.JSONField(
        null=True,
        blank=True,
        help_text="The actual outcome when evaluated"
    )
    accuracy_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Accuracy of this prediction (0-1)"
    )
    error_magnitude = models.FloatField(
        null=True,
        blank=True,
        help_text="Magnitude of prediction error"
    )
    
    # Status tracking
    status = models.CharField(max_length=20, choices=PREDICTION_STATUS, default='pending')
    evaluated_at = models.DateTimeField(null=True, blank=True)
    
    # Performance metrics
    sharpe_ratio = models.FloatField(
        null=True,
        blank=True,
        help_text="Risk-adjusted return if prediction was traded"
    )
    maximum_drawdown = models.FloatField(
        null=True,
        blank=True,
        help_text="Maximum loss if prediction was traded"
    )
    
    # ==================== METADATA ====================
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(
        max_length=100,
        default='system',
        help_text="System or user that created this prediction"
    )
    
    # External validation
    human_validation = models.CharField(
        max_length=20,
        choices=[
            ('agree', 'Human Agrees'),
            ('disagree', 'Human Disagrees'),
            ('uncertain', 'Human Uncertain'),
            ('not_validated', 'Not Validated'),
        ],
        default='not_validated'
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['prediction_type', 'status', 'target_date']),
            models.Index(fields=['collection', 'prediction_type', 'created_at']),
            models.Index(fields=['model_name', 'model_version', 'accuracy_score']),
            models.Index(fields=['confidence_score', 'accuracy_score']),
            models.Index(fields=['target_date', 'status']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        target = self.collection.name if self.collection else "Market"
        return f"{self.prediction_type} prediction for {target} - {self.confidence_score:.2f} confidence"

class AnomalyDetection(models.Model):
    """
    Track market anomalies and unusual patterns for advanced market intelligence.
    """
    
    ANOMALY_TYPES = [
        ('price_anomaly', 'Price Anomaly'),
        ('volume_anomaly', 'Volume Anomaly'),
        ('activity_anomaly', 'Activity Anomaly'),
        ('liquidity_anomaly', 'Liquidity Anomaly'),
        ('behavioral_anomaly', 'Behavioral Anomaly'),
        ('cross_platform_anomaly', 'Cross-Platform Anomaly'),
        ('manipulation_signal', 'Manipulation Signal'),
        ('whale_activity', 'Whale Activity'),
        ('bot_activity', 'Bot Activity'),
        ('wash_trading', 'Wash Trading'),
    ]
    
    SEVERITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    # Core anomaly identification
    anomaly_id = models.CharField(max_length=100, unique=True, db_index=True)
    anomaly_type = models.CharField(max_length=30, choices=ANOMALY_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS)
    
    # Target of anomaly
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='anomalies',
        null=True,
        blank=True
    )
    wallet_address = models.CharField(
        max_length=44,
        null=True,
        blank=True,
        db_index=True
    )
    
    # ==================== ANOMALY DETAILS ====================
    # Statistical measures
    anomaly_score = models.FloatField(
        default=0.0,
        help_text="How anomalous this event is (0-1, higher = more unusual)"
    )
    deviation_from_norm = models.FloatField(
        default=0.0,
        help_text="Number of standard deviations from normal"
    )
    
    # Detection details
    detected_value = models.JSONField(
        default=dict,
        help_text="The values that triggered the anomaly detection"
    )
    baseline_value = models.JSONField(
        default=dict,
        help_text="Normal/baseline values for comparison"
    )
    
    # Context and patterns
    pattern_description = models.TextField(
        help_text="Description of the anomalous pattern detected"
    )
    potential_causes = models.JSONField(
        default=list,
        help_text="Potential explanations for this anomaly"
    )
    
    # ==================== DETECTION METHODOLOGY ====================
    # Detection algorithm used
    detection_algorithm = models.CharField(
        max_length=50,
        choices=[
            ('statistical_outlier', 'Statistical Outlier Detection'),
            ('isolation_forest', 'Isolation Forest'),
            ('local_outlier_factor', 'Local Outlier Factor'),
            ('one_class_svm', 'One-Class SVM'),
            ('autoencoder', 'Autoencoder'),
            ('rule_based', 'Rule-based'),
            ('threshold_based', 'Threshold-based'),
        ]
    )
    
    # Features that contributed to detection
    contributing_features = models.JSONField(
        default=dict,
        help_text="Features and their contributions to anomaly detection"
    )
    
    # Time window analyzed
    analysis_window_start = models.DateTimeField()
    analysis_window_end = models.DateTimeField()
    
    # ==================== IMPACT ASSESSMENT ====================
    # Market impact
    market_impact_score = models.FloatField(
        default=0.0,
        help_text="How much this anomaly impacted the market (0-1)"
    )
    price_impact = models.FloatField(
        default=0.0,
        help_text="Price impact in percentage points"
    )
    volume_impact = models.FloatField(
        default=0.0,
        help_text="Volume impact in percentage points"
    )
    
    # Follow-up effects
    triggered_other_anomalies = models.BooleanField(
        default=False,
        help_text="Whether this anomaly triggered others"
    )
    contagion_score = models.FloatField(
        default=0.0,
        help_text="How much this anomaly spread to other collections (0-1)"
    )
    
    # ==================== VALIDATION ====================
    # Human validation
    human_validated = models.BooleanField(default=False)
    validation_result = models.CharField(
        max_length=20,
        choices=[
            ('true_positive', 'True Positive'),
            ('false_positive', 'False Positive'),
            ('uncertain', 'Uncertain'),
            ('not_validated', 'Not Validated'),
        ],
        default='not_validated'
    )
    
    # Investigation status
    investigation_status = models.CharField(
        max_length=20,
        choices=[
            ('new', 'New'),
            ('investigating', 'Under Investigation'),
            ('resolved', 'Resolved'),
            ('dismissed', 'Dismissed'),
            ('escalated', 'Escalated'),
        ],
        default='new'
    )
    
    # ==================== RELATED DATA ====================
    # Related transactions
    related_transactions = models.JSONField(
        default=list,
        help_text="Transaction signatures related to this anomaly"
    )
    
    # Related wallet addresses
    related_wallets = models.JSONField(
        default=list,
        help_text="Wallet addresses involved in this anomaly"
    )
    
    # Related NFT mint addresses
    related_nfts = models.JSONField(
        default=list,
        help_text="NFT mint addresses involved in this anomaly"
    )
    
    # ==================== ALERTING ====================
    # Alert settings
    alert_generated = models.BooleanField(default=False)
    alert_recipients = models.JSONField(
        default=list,
        help_text="Users/systems that were alerted about this anomaly"
    )
    alert_acknowledged = models.BooleanField(default=False)
    
    # ==================== ML FEEDBACK ====================
    # ML model feedback
    model_feedback = models.JSONField(
        default=dict,
        help_text="Feedback for improving anomaly detection models"
    )
    false_positive_reasons = models.JSONField(
        default=list,
        help_text="Reasons why this was a false positive (if applicable)"
    )
    
    # ==================== METADATA ====================
    first_detected = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Detection system metadata
    detection_system_version = models.CharField(
        max_length=20,
        default='v1.0',
        help_text="Version of detection system that found this anomaly"
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['anomaly_type', 'severity', 'first_detected']),
            models.Index(fields=['collection', 'anomaly_type', 'first_detected']),
            models.Index(fields=['wallet_address', 'anomaly_type']),
            models.Index(fields=['anomaly_score', 'severity']),
            models.Index(fields=['investigation_status', 'first_detected']),
            models.Index(fields=['human_validated', 'validation_result']),
        ]
        ordering = ['-first_detected']
    
    def __str__(self):
        target = self.collection.name if self.collection else self.wallet_address or "Market"
        return f"{self.anomaly_type} anomaly ({self.severity}) - {target}"


# ==================== ADDITIONAL HELPER MODELS ====================

class MarketRegimeTransition(models.Model):
    """
    Track transitions between market regimes for better regime prediction.
    """
    
    from_regime = models.ForeignKey(
        MarketRegime,
        on_delete=models.CASCADE,
        related_name='transitions_from'
    )
    to_regime = models.ForeignKey(
        MarketRegime,
        on_delete=models.CASCADE,
        related_name='transitions_to'
    )
    
    # Transition characteristics
    transition_duration_hours = models.FloatField(
        help_text="How long the transition took"
    )
    transition_smoothness = models.FloatField(
        default=0.0,
        help_text="How smooth the transition was (0=abrupt, 1=gradual)"
    )
    
    # Trigger events
    trigger_events = models.JSONField(
        default=list,
        help_text="Events that triggered this regime transition"
    )
    
    # Market impact during transition
    volatility_during_transition = models.FloatField(default=0.0)
    volume_spike = models.FloatField(default=0.0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['from_regime', 'to_regime', 'created_at']),
            models.Index(fields=['transition_duration_hours']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Transition: {self.from_regime.regime_type} → {self.to_regime.regime_type}"

class PredictionAccuracyTracker(models.Model):
    """
    Aggregate prediction accuracy metrics for different models and prediction types.
    """
    
    model_name = models.CharField(max_length=100)
    model_version = models.CharField(max_length=20)
    prediction_type = models.CharField(max_length=30)
    
    # Accuracy metrics
    total_predictions = models.IntegerField(default=0)
    correct_predictions = models.IntegerField(default=0)
    accuracy_percentage = models.FloatField(default=0.0)
    
    # Performance metrics
    avg_confidence_score = models.FloatField(default=0.0)
    avg_error_magnitude = models.FloatField(default=0.0)
    precision = models.FloatField(default=0.0)
    recall = models.FloatField(default=0.0)
    f1_score = models.FloatField(default=0.0)
    
    # Time-based performance
    performance_trend = models.CharField(
        max_length=20,
        choices=[
            ('improving', 'Improving'),
            ('declining', 'Declining'),
            ('stable', 'Stable'),
            ('volatile', 'Volatile'),
        ],
        default='stable'
    )
    
    # Calculation period
    calculation_period_start = models.DateTimeField()
    calculation_period_end = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['model_name', 'prediction_type', 'updated_at']),
            models.Index(fields=['accuracy_percentage', 'updated_at']),
        ]
        ordering = ['-accuracy_percentage']
        unique_together = ('model_name', 'model_version', 'prediction_type', 'calculation_period_start')
    
    def __str__(self):
        return f"{self.model_name} v{self.model_version} - {self.prediction_type}: {self.accuracy_percentage:.1f}%"

# ==================== ML PREPARATION MODELS ====================

class MLModelMetadata(models.Model):
    """
    Track ML model versions, features, and performance for the future ML implementation.
    """
    
    MODEL_TYPES = [
        ('price_prediction', 'Price Prediction'),
        ('trend_prediction', 'Trend Prediction'),
        ('anomaly_detection', 'Anomaly Detection'),
        ('behavior_classification', 'Behavior Classification'),
        ('regime_detection', 'Regime Detection'),
        ('trait_performance', 'Trait Performance'),
        ('recommendation', 'Recommendation Engine'),
    ]
    
    # Model identification
    model_name = models.CharField(max_length=100, unique=True)
    model_type = models.CharField(max_length=30, choices=MODEL_TYPES)
    version = models.CharField(max_length=20)
    
    # Model architecture
    algorithm = models.CharField(max_length=50)
    framework = models.CharField(max_length=30, default='scikit-learn')
    hyperparameters = models.JSONField(default=dict)
    
    # Training data
    training_data_features = models.JSONField(default=list)
    training_data_size = models.IntegerField(default=0)
    training_period_start = models.DateTimeField(null=True, blank=True)
    training_period_end = models.DateTimeField(null=True, blank=True)
    
    # Model performance
    validation_accuracy = models.FloatField(default=0.0)
    test_accuracy = models.FloatField(default=0.0)
    cross_validation_score = models.FloatField(default=0.0)
    
    # Feature importance
    feature_importance = models.JSONField(
        default=dict,
        help_text="Importance scores for each feature"
    )
    
    # Model status
    is_active = models.BooleanField(default=False)
    is_production_ready = models.BooleanField(default=False)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    trained_at = models.DateTimeField(null=True, blank=True)
    deployed_at = models.DateTimeField(null=True, blank=True)
    
    # Model file storage (for future use)
    model_file_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Path to saved model file"
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['model_type', 'is_active']),
            models.Index(fields=['validation_accuracy', 'is_production_ready']),
        ]
        ordering = ['-validation_accuracy']
        unique_together = ('model_name', 'version')
    
    def __str__(self):
        return f"{self.model_name} v{self.version} ({self.model_type})"

class FeatureEngineering(models.Model):
    """
    Track feature engineering experiments for ML model development.
    """
    
    experiment_name = models.CharField(max_length=100)
    feature_set_name = models.CharField(max_length=100)
    
    # Feature details
    base_features = models.JSONField(default=list)
    engineered_features = models.JSONField(default=list)
    feature_transformations = models.JSONField(default=dict)
    
    # Performance impact
    baseline_performance = models.FloatField(default=0.0)
    improved_performance = models.FloatField(default=0.0)
    performance_lift = models.FloatField(default=0.0)
    
    # Feature statistics
    feature_correlations = models.JSONField(default=dict)
    feature_distributions = models.JSONField(default=dict)
    missing_value_handling = models.JSONField(default=dict)
    
    # Experiment metadata
    target_model_type = models.CharField(max_length=30)
    experiment_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['target_model_type', 'performance_lift']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-performance_lift']
    
    def __str__(self):
        return f"{self.experiment_name} - {self.feature_set_name} (+{self.performance_lift:.2f}%)"