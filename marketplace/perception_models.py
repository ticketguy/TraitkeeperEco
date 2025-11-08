# marketplace/perception_models.py

"""
Parallel Lines Integration - Perception Data Models

This module defines the data models for storing perception data from the
Parallel Lines world perception engine (LLM-based sentiment analysis system).

Parallel Lines Architecture:
- Submind Layer: Silent observer - raw subconscious perception signals
- IntuOne Layer: Expressive interpreter - structured sentiment and Perception Graph
- Output: Perception Index (0-1) that feeds into TraitKeeper's 20% Vitality component

Granularity Support:
- Collection-level perception (e.g., "DeGods community sentiment")
- NFT-level perception (e.g., "DeGods #4321 holder sentiment")
- Trait-level perception (e.g., "Blue Background trait demand signals")
"""

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

from nft_data.models import NFT, NFTCollection, TraitValue


class PerceptionSnapshot(models.Model):
    """
    Stores timestamped perception data from Parallel Lines.

    This is the primary model for storing perception index scores
    at various granularities (collection, NFT, or trait level).

    Data Source: Parallel Lines webhook or API polling
    Update Frequency: Real-time via webhook or periodic polling
    """

    # === Entity Tracking (Polymorphic - Exactly ONE of these will be set) ===
    # This implements a polymorphic pattern where a PerceptionSnapshot can belong to
    # EITHER a collection, OR an NFT, OR a trait value - but NEVER more than one.
    # This is enforced by a CHECK constraint at the database level.

    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='perception_snapshots',
        help_text="Collection this perception data applies to (e.g., 'DeGods sentiment')"
    )

    nft = models.ForeignKey(
        NFT,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='perception_snapshots',
        help_text="Specific NFT this perception data applies to (e.g., 'DeGods #4321 holder perception')"
    )

    trait_value = models.ForeignKey(
        TraitValue,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='perception_snapshots',
        help_text="Specific trait this perception data applies to (e.g., 'Blue Background trait demand')"
    )

    # === Core Perception Metrics ===

    perception_index = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Final Perception Index score (0-1) from IntuOne layer"
    )

    # === Submind Layer Outputs (Raw Subconscious Signals) ===
    # The Submind layer is the "silent observer" that captures perception signals
    # below the surface of conscious awareness - hidden patterns, unseen dynamics,
    # and raw behavioral data that humans might miss.

    submind_raw_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Raw behavioral score from Submind layer (0-1) - unfiltered subconscious perception"
    )

    submind_hidden_sentiment = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Hidden sentiment classification detected by Submind (positive, negative, neutral, mixed)"
    )

    manipulation_probability = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Anti-gaming metric: Probability of manipulation detected (0-1, higher = more suspicious). "
                  "Used to dampen perception scores when gaming is suspected."
    )

    behavioral_pattern_flags = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detected behavioral patterns from Submind analysis. "
                  "Examples: {'bot_activity': true, 'wash_trading_influence': 0.08, 'coordinated_shilling': false}"
    )

    # === IntuOne Layer Outputs (Structured Interpretation) ===
    # The IntuOne layer is the "expressive interpreter" that translates the raw
    # emotional resonance and language tone captured by Submind into structured,
    # actionable perception data - creating the Perception Graph.

    emotional_resonance = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Emotional resonance score from IntuOne layer (0-1) - how strongly the community feels"
    )

    language_tone = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Analyzed language tone from IntuOne (enthusiastic, cautious, fearful, euphoric, skeptical, etc.)"
    )

    community_awareness_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Community awareness/engagement score from IntuOne (0-1) - how aware/engaged the community is"
    )

    # === Perception Graph Reference ===
    # The full graph structure is stored in PerceptionGraphNode/Edge models
    # This is just a reference ID for linking
    perception_graph_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="ID of the perception graph topology this snapshot belongs to"
    )

    # === Data Quality & Metadata ===

    confidence_score = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Confidence in this perception measurement (0-1)"
    )

    data_sources = models.JSONField(
        default=list,
        blank=True,
        help_text="List of data sources used (twitter, discord, reddit, on-chain, etc.)"
    )

    sample_size = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of data points analyzed for this snapshot"
    )

    # === Timestamps ===

    timestamp = models.DateTimeField(
        db_index=True,
        help_text="When this perception measurement was taken by Parallel Lines"
    )

    received_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When TraitKeeper received this data"
    )

    # === Source Tracking ===

    class DataSource(models.TextChoices):
        WEBHOOK = 'WEBHOOK', 'Webhook (Real-time)'
        API_POLL = 'API_POLL', 'API Polling'
        MANUAL = 'MANUAL', 'Manual Entry'
        BACKFILL = 'BACKFILL', 'Historical Backfill'

    source_type = models.CharField(
        max_length=20,
        choices=DataSource.choices,
        default=DataSource.WEBHOOK,
        help_text="How this data was received"
    )

    raw_payload = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw JSON payload from Parallel Lines (for debugging/audit)"
    )

    class Meta:
        verbose_name = "Perception Snapshot"
        verbose_name_plural = "Perception Snapshots"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['collection', '-timestamp']),
            models.Index(fields=['nft', '-timestamp']),
            models.Index(fields=['trait_value', '-timestamp']),
            models.Index(fields=['perception_graph_id', '-timestamp']),
            models.Index(fields=['-timestamp', 'perception_index']),
        ]
        constraints = [
            # Ensure exactly one entity is set (collection XOR nft XOR trait_value)
            models.CheckConstraint(
                check=(
                    models.Q(collection__isnull=False, nft__isnull=True, trait_value__isnull=True) |
                    models.Q(collection__isnull=True, nft__isnull=False, trait_value__isnull=True) |
                    models.Q(collection__isnull=True, nft__isnull=True, trait_value__isnull=False)
                ),
                name='perception_snapshot_exactly_one_entity'
            )
        ]

    def __str__(self):
        entity = self.collection or self.nft or self.trait_value
        return f"Perception: {entity} - {self.perception_index:.3f} @ {self.timestamp}"

    @property
    def entity_type(self):
        """Returns the type of entity this snapshot is for."""
        if self.collection:
            return 'collection'
        elif self.nft:
            return 'nft'
        elif self.trait_value:
            return 'trait'
        return 'unknown'

    @property
    def entity(self):
        """Returns the actual entity object."""
        return self.collection or self.nft or self.trait_value

    @property
    def is_recent(self):
        """Check if this snapshot is recent (within last 24 hours)."""
        return self.timestamp >= timezone.now() - timezone.timedelta(hours=24)

    @property
    def anti_gaming_flags(self):
        """
        Extract anti-gaming related flags from behavioral patterns.

        This property analyzes the Submind layer's behavioral pattern detection
        and returns human-readable flags for suspicious activity.

        Anti-Gaming Detection Logic:
        1. High manipulation_probability (> 0.5) triggers WARNING flag
        2. Bot activity detection from behavioral patterns
        3. Wash trading influence signals
        4. Coordinated shilling campaigns

        Returns:
            list: List of string flags indicating detected gaming attempts
                  e.g., ['HIGH_MANIPULATION_RISK', 'BOT_ACTIVITY_DETECTED']
        """
        flags = []

        # Check manipulation probability threshold
        # Values > 0.5 indicate likely gaming attempts
        if self.manipulation_probability and self.manipulation_probability > 0.5:
            flags.append('HIGH_MANIPULATION_RISK')

        # Parse behavioral pattern flags from Submind layer
        if self.behavioral_pattern_flags:
            # Bot activity detection (boolean flag)
            if self.behavioral_pattern_flags.get('bot_activity'):
                flags.append('BOT_ACTIVITY_DETECTED')

            # Wash trading influence (any non-zero value is suspicious)
            if self.behavioral_pattern_flags.get('wash_trading_influence'):
                flags.append('WASH_TRADING_SIGNALS')

            # Coordinated shilling campaigns (boolean flag)
            if self.behavioral_pattern_flags.get('coordinated_shilling'):
                flags.append('COORDINATED_SHILLING')

        return flags


class PerceptionGraphNode(models.Model):
    """
    Stores nodes in the Perception Graph topology.

    The Perception Graph is a dynamic topology of community awareness
    generated by the IntuOne layer. Nodes represent entities (users,
    topics, communities) and edges represent perception relationships.
    """

    graph_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="ID of the perception graph this node belongs to"
    )

    node_id = models.CharField(
        max_length=100,
        help_text="Unique identifier for this node within the graph"
    )

    node_type = models.CharField(
        max_length=50,
        help_text="Type of node (user, topic, community, hashtag, influencer, etc.)"
    )

    label = models.CharField(
        max_length=255,
        help_text="Human-readable label for this node"
    )

    # Node metrics
    influence_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Influence score of this node in the graph (0-1)"
    )

    sentiment = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Sentiment associated with this node"
    )

    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional node attributes from Parallel Lines"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Perception Graph Node"
        verbose_name_plural = "Perception Graph Nodes"
        unique_together = [['graph_id', 'node_id']]
        indexes = [
            models.Index(fields=['graph_id', 'node_type']),
            models.Index(fields=['node_type', '-influence_score']),
        ]

    def __str__(self):
        return f"{self.node_type}: {self.label} (Graph: {self.graph_id})"


class PerceptionGraphEdge(models.Model):
    """
    Stores edges (relationships) in the Perception Graph.

    Edges represent perception relationships between nodes,
    such as "user mentions topic" or "influencer endorses project".
    """

    graph_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="ID of the perception graph this edge belongs to"
    )

    source_node = models.ForeignKey(
        PerceptionGraphNode,
        on_delete=models.CASCADE,
        related_name='outgoing_edges',
        help_text="Source node of this relationship"
    )

    target_node = models.ForeignKey(
        PerceptionGraphNode,
        on_delete=models.CASCADE,
        related_name='incoming_edges',
        help_text="Target node of this relationship"
    )

    edge_type = models.CharField(
        max_length=50,
        help_text="Type of relationship (mentions, endorses, criticizes, discusses, etc.)"
    )

    weight = models.FloatField(
        default=1.0,
        help_text="Strength/weight of this relationship"
    )

    sentiment = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Sentiment of this relationship"
    )

    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional edge attributes"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perception Graph Edge"
        verbose_name_plural = "Perception Graph Edges"
        indexes = [
            models.Index(fields=['graph_id', 'edge_type']),
            models.Index(fields=['source_node', 'target_node']),
        ]

    def __str__(self):
        return f"{self.source_node.label} --[{self.edge_type}]--> {self.target_node.label}"


class PerceptionAggregation(models.Model):
    """
    Pre-computed aggregated perception metrics for performance.

    This model stores rolled-up perception data (hourly, daily, weekly)
    to speed up historical queries and trend analysis.
    """

    # Entity (same polymorphic pattern as PerceptionSnapshot)
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='perception_aggregations'
    )

    nft = models.ForeignKey(
        NFT,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='perception_aggregations'
    )

    trait_value = models.ForeignKey(
        TraitValue,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='perception_aggregations'
    )

    # Aggregation period
    class AggregationPeriod(models.TextChoices):
        HOURLY = 'HOURLY', 'Hourly'
        DAILY = 'DAILY', 'Daily'
        WEEKLY = 'WEEKLY', 'Weekly'
        MONTHLY = 'MONTHLY', 'Monthly'

    period = models.CharField(
        max_length=20,
        choices=AggregationPeriod.choices,
        help_text="Aggregation time period"
    )

    period_start = models.DateTimeField(
        db_index=True,
        help_text="Start of aggregation period"
    )

    period_end = models.DateTimeField(
        help_text="End of aggregation period"
    )

    # Aggregated metrics
    avg_perception_index = models.FloatField(
        help_text="Average perception index over period"
    )

    min_perception_index = models.FloatField(
        help_text="Minimum perception index in period"
    )

    max_perception_index = models.FloatField(
        help_text="Maximum perception index in period"
    )

    perception_volatility = models.FloatField(
        null=True,
        blank=True,
        help_text="Standard deviation of perception (volatility measure)"
    )

    avg_manipulation_probability = models.FloatField(
        null=True,
        blank=True,
        help_text="Average manipulation probability over period"
    )

    sample_count = models.IntegerField(
        help_text="Number of snapshots aggregated"
    )

    # Metadata
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Perception Aggregation"
        verbose_name_plural = "Perception Aggregations"
        ordering = ['-period_start']
        indexes = [
            models.Index(fields=['collection', 'period', '-period_start']),
            models.Index(fields=['nft', 'period', '-period_start']),
            models.Index(fields=['trait_value', 'period', '-period_start']),
        ]
        unique_together = [
            ['collection', 'period', 'period_start'],
            ['nft', 'period', 'period_start'],
            ['trait_value', 'period', 'period_start'],
        ]

    def __str__(self):
        entity = self.collection or self.nft or self.trait_value
        return f"{entity} - {self.period} avg: {self.avg_perception_index:.3f}"


class ParallelLinesWebhookLog(models.Model):
    """
    Audit log of all webhook calls from Parallel Lines.

    Useful for debugging, monitoring uptime, and detecting issues
    with the Parallel Lines integration.
    """

    # Request details
    received_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When webhook was received"
    )

    endpoint = models.CharField(
        max_length=255,
        help_text="Webhook endpoint that received the call"
    )

    method = models.CharField(
        max_length=10,
        default='POST',
        help_text="HTTP method (usually POST)"
    )

    headers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Request headers"
    )

    payload = models.JSONField(
        help_text="Full webhook payload"
    )

    # Processing results
    class Status(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Successfully Processed'
        FAILED = 'FAILED', 'Processing Failed'
        VALIDATION_ERROR = 'VALIDATION_ERROR', 'Validation Error'
        AUTH_ERROR = 'AUTH_ERROR', 'Authentication Error'
        DUPLICATE = 'DUPLICATE', 'Duplicate Data'

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        help_text="Processing status"
    )

    error_message = models.TextField(
        null=True,
        blank=True,
        help_text="Error message if processing failed"
    )

    snapshots_created = models.IntegerField(
        default=0,
        help_text="Number of PerceptionSnapshot records created"
    )

    processing_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Processing time in milliseconds"
    )

    # Linking
    perception_snapshot = models.ForeignKey(
        PerceptionSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_logs',
        help_text="Created PerceptionSnapshot (if applicable)"
    )

    class Meta:
        verbose_name = "Parallel Lines Webhook Log"
        verbose_name_plural = "Parallel Lines Webhook Logs"
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['-received_at', 'status']),
            models.Index(fields=['status', '-received_at']),
        ]

    def __str__(self):
        return f"{self.status} - {self.endpoint} @ {self.received_at}"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_latest_perception_index(entity, entity_type='collection'):
    """
    Helper function to get the most recent perception index for an entity.

    Args:
        entity: NFTCollection, NFT, or TraitValue instance
        entity_type: 'collection', 'nft', or 'trait'

    Returns:
        float: Perception index (0-1), or None if no data available
    """
    filter_kwargs = {entity_type: entity}

    snapshot = PerceptionSnapshot.objects.filter(
        **filter_kwargs
    ).order_by('-timestamp').first()

    return snapshot.perception_index if snapshot else None


def get_perception_trend(entity, entity_type='collection', days=7):
    """
    Get perception trend over the last N days.

    Args:
        entity: NFTCollection, NFT, or TraitValue instance
        entity_type: 'collection', 'nft', or 'trait'
        days: Number of days to look back

    Returns:
        dict: {'current': float, 'average': float, 'change': float, 'trend': str}
    """
    from django.db.models import Avg
    from datetime import timedelta

    filter_kwargs = {entity_type: entity}
    since = timezone.now() - timedelta(days=days)

    snapshots = PerceptionSnapshot.objects.filter(
        **filter_kwargs,
        timestamp__gte=since
    ).order_by('-timestamp')

    if not snapshots.exists():
        return None

    current = snapshots.first().perception_index
    average = snapshots.aggregate(Avg('perception_index'))['perception_index__avg']
    change = current - average

    if change > 0.05:
        trend = 'improving'
    elif change < -0.05:
        trend = 'declining'
    else:
        trend = 'stable'

    return {
        'current': current,
        'average': average,
        'change': change,
        'trend': trend
    }
