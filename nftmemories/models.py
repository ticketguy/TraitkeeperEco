from django.db import models
from django.utils import timezone
from django.conf import settings
from nft_data.models import NFTCollection, NFT
from indexer.models import NFTEvent, BurnEvent  # Import NFTEvent and BurnEvent for foreign key references

def get_default_user_interactions():
    """Return default user interactions dictionary for likes, comments, tributes, and reactions."""
    return {"likes": 0, "comments": [], "tributes": [], "reactions": {"fire": 0, "heartbreak": 0, "party": 0}}

class CollectionEvent(models.Model):
    """Model to store gamification-related data for significant NFT events."""
    SIGNIFICANCE_LEVELS = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('LEGENDARY', 'Legendary'),
    ]
    event = models.ForeignKey(
        NFTEvent,
        on_delete=models.CASCADE,
        related_name='memory_events',
        help_text="Reference to the core NFT event in indexer.models."
    )
    significance = models.CharField(
        max_length=20,
        choices=SIGNIFICANCE_LEVELS,
        default='LOW',
        help_text="Significance level for gamification purposes."
    )
    user_interactions = models.JSONField(
        default=get_default_user_interactions,
        help_text="User engagement with the event (likes, comments, tributes, reactions)."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Collection Event"
        verbose_name_plural = "Collection Events"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event']),
            models.Index(fields=['significance']),
        ]

    def __str__(self):
        return f"{self.event.event_type} Event {self.event.event_id[:8]} - {self.event.collection.name} at {self.event.timestamp}"

    def determine_significance(self):
        """Determine the significance of the event for gamification based on event type and details."""
        details = self.event.details if hasattr(self.event, 'details') else {}
        if self.event.event_type == 'BURN':
            self.significance = 'LEGENDARY'
        elif self.event.event_type == 'SALE':
            price = details.get('price', 0)
            if price > 100:  # Example threshold in SOL
                self.significance = 'HIGH'
            elif price > 10:
                self.significance = 'MEDIUM'
            else:
                self.significance = 'LOW'
        elif self.event.event_type == 'MINT':
            number = details.get('number', None)
            if number == 1:  # First mint
                self.significance = 'HIGH'
            else:
                self.significance = 'MEDIUM'
        else:
            self.significance = 'LOW'

    def save(self, *args, **kwargs):
        """Override save method to determine significance before saving and restrict updates to specific fields."""
        self.determine_significance()
        if self.pk and self._meta.model.objects.filter(pk=self.pk).exists():
            original = self._meta.model.objects.get(pk=self.pk)
            allowed_fields = {'user_interactions', 'significance'}
            for field in self._meta.fields:
                field_name = field.name
                if field_name not in allowed_fields and field_name not in {'created_at'}:
                    setattr(self, field_name, getattr(original, field_name))
        super().save(*args, **kwargs)

class NFTBurn(models.Model):
    """Model to store historical and gamification data for burned NFTs."""
    burn_event = models.ForeignKey(
        BurnEvent,
        on_delete=models.CASCADE,
        related_name='memory_burns',
        help_text="Reference to the core burn event in indexer.models."
    )
    name = models.CharField(max_length=255, blank=True, help_text="NFT name at the time of burning.")
    description = models.TextField(blank=True, help_text="NFT description at the time of burning.")
    image_url = models.URLField(max_length=500, blank=True, help_text="Image URL at the time of burning.")
    number = models.IntegerField(null=True, blank=True, help_text="NFT number (e.g., #123 in the collection).")
    rarity = models.JSONField(default=dict, help_text="Rarity details (e.g., {'trait1': {'value': 'value1', 'rarity': 5.0}}).")
    reason = models.TextField(blank=True, help_text="Reason for the burn, if known or provided by the user.")
    reason_is_approved = models.BooleanField(default=False, help_text="Whether the user-provided reason has been approved by a moderator.")
    added_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who added the reason, if applicable."
    )
    user_interactions = models.JSONField(
        default=get_default_user_interactions,
        help_text="User engagement with the burned NFT (likes, comments, tributes, reactions)."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "NFT Burn"
        verbose_name_plural = "NFT Burns"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['burn_event']),
        ]

    def __str__(self):
        return f"Burn {self.burn_event.burn_id[:8]} - {self.burn_event.mint_address} at {self.burn_event.timestamp}"

    def save(self, *args, **kwargs):
        """Override save method to restrict updates to specific fields after creation."""
        if self.pk and self._meta.model.objects.filter(pk=self.pk).exists():
            original = self._meta.model.objects.get(pk=self.pk)
            allowed_fields = {'user_interactions', 'reason', 'added_by_user', 'reason_is_approved'}
            for field in self._meta.fields:
                field_name = field.name
                if field_name not in allowed_fields and field_name not in {'created_at'}:
                    setattr(self, field_name, getattr(original, field_name))
        super().save(*args, **kwargs)

class CollectionRaritySnapshot(models.Model):
    """Model to store snapshots of a collection's rarity distribution and total supply."""
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='rarity_snapshots')
    timestamp = models.DateTimeField(default=timezone.now)
    total_supply = models.IntegerField()  # Total supply at the time of the snapshot
    rarity_base = models.JSONField(default=dict)  # Rarity distribution (e.g., {"trait_type1": {"value1": 5.0, "value2": 10.0}})
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Collection Rarity Snapshot"
        verbose_name_plural = "Collection Rarity Snapshots"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['collection', 'timestamp']),
        ]

    def __str__(self):
        return f"Rarity Snapshot for {self.collection.name} at {self.timestamp}"

# UserAchievement model removed - now using profiles.UserAchievement
# NFT Memories interactions (likes, comments, tributes) don't award points
# per user request to avoid confusion with airdrop-worthy achievements