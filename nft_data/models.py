# nft_data/models.py

from django.db import models
from django.utils import timezone
from model_utils.models import TimeStampedModel
import re
import logging

logger = logging.getLogger(__name__)

# ===================================================================
# Core Catalog Models
# These models define the fundamental structure of NFTs and Collections.
# ===================================================================

class Creator(models.Model):
    """Stores information about a single NFT creator wallet."""
    address = models.CharField(max_length=44, unique=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name or 'Unknown Creator'} ({self.address[:8]})"


class NFTCollection(models.Model):
    """
    Stores the core, descriptive metadata for an NFT collection.
    
    This model only stores the intrinsic properties of the collection.
    """
    address = models.CharField(max_length=255, primary_key=True)
    name = models.CharField(max_length=255, help_text="Raw collection name from the blockchain.")
    display_name = models.CharField(max_length=255, blank=True, help_text="Clean, user-friendly collection name.")
    slug = models.SlugField(max_length=255, unique=True, blank=True, help_text="A clean, URL-friendly slug.")
    symbol = models.CharField(max_length=20, blank=True, null=True)
    
    image_url = models.URLField(max_length=1000, blank=True)
    description = models.TextField(blank=True)
    creator_address = models.CharField(max_length=255, blank=True)
    social_media_links = models.JSONField(null=True, blank=True)

    # --- Operational & Status Fields ---
    is_featured = models.BooleanField(default=False, help_text="Manually marked by an admin as featured.")
    is_listed = models.BooleanField(default=True, help_text="Controls public visibility of the collection.")
    source = models.CharField(max_length=50, default='webhook', help_text="How the collection was added (e.g., 'submission', 'webhook').")
    
    # NOTE: API Quota and update scheduling fields are operational and remain here.
    priority_tier = models.CharField(max_length=10, choices=[('VIP', 'VIP'), ('ACTIVE', 'Active'), ('INACTIVE', 'Inactive')], default='ACTIVE')
    update_frequency_minutes = models.IntegerField(default=120)
    next_update_due = models.DateTimeField(null=True, blank=True)
    last_fetched = models.DateTimeField(null=True, blank=True, help_text="Timestamp of the last successful data fetch.")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'NFT Collection'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        """Overrides save to auto-generate a clean display_name and slug."""
        if not self.display_name and self.name:
            self.display_name = self._clean_raw_name(self.name)
        if self.display_name and not self.slug:
            self.slug = self.display_name.lower().replace(' ', '_')
        super().save(*args, **kwargs)

    def _clean_raw_name(self, raw_name: str) -> str:
        """Helper to generate a clean name from the raw blockchain name."""
        if not raw_name: return ""
        cleaned = re.sub(r'\s*#\d+\s*.*$', '', raw_name, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\(Official\)\s*.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*Collection\s*.*$', '', cleaned, flags=re.IGNORECASE)
        return ' '.join(cleaned.split()).strip()

    def __str__(self):
        display = self.display_name or self.name
        return f"{display} ({self.address[:6]}...)"


class NFT(models.Model):
    """Stores the core, descriptive metadata for a single NFT."""
    mint_address = models.CharField(max_length=44, primary_key=True)
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='nfts')
    
    name = models.CharField(max_length=255)
    image_url = models.URLField(max_length=500, blank=True)
    owner = models.CharField(max_length=44, null=True, blank=True)
    
    traits = models.JSONField(default=dict, blank=True)
    trait_values = models.ManyToManyField('TraitValue', related_name='nfts')
    
    # NOTE: These are denormalized fields acting as a cache of the current market state.
    listing_price = models.DecimalField(max_digits=20, decimal_places=9, null=True, blank=True)
    asking_price = models.DecimalField(
    max_digits=20,
    decimal_places=9,
    null=True,
    blank=True,
    help_text="Owner's asking price in SOL"
)

    has_sell_intent = models.BooleanField(
        default=False,
        help_text="Whether owner has expressed intent to sell"
    )

    is_open_to_offers = models.BooleanField(
        default=False,
        help_text="Whether NFT is open to receiving private offers"
    )

    has_buy_price = models.BooleanField(
        default=False,
        help_text="Whether NFT has a set buy-now price"
    )

    active_auction = models.ForeignKey(
        'marketplace.AuctionEvent',  # Adjust app name if needed
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='nft_in_auction',
        help_text="Reference to active auction if any"
    )

    vitality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="NFT vitality score for pricing suggestions"
    )

    is_listed = models.BooleanField(
        default=False,
        help_text="Whether NFT is listed for sale"
    )
    buy_price = models.DecimalField(
        max_digits=20, decimal_places=9, null=True, blank=True,
        help_text="The public, fixed price in SOL for an instant buy."
    )    
    is_burned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.mint_address[:6]}...)"

class TraitType(models.Model):
    """A category of trait for a collection, e.g., 'Hat', 'Background'."""
    name = models.CharField(max_length=255)
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='trait_types')

    class Meta:
        unique_together = ('name', 'collection')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.collection.name})"


class TraitValue(models.Model):
    """A specific value for a TraitType, e.g., 'Crown', 'Blue'."""
    trait_type = models.ForeignKey(TraitType, on_delete=models.CASCADE, related_name='trait_values')
    value = models.CharField(max_length=255)
    count = models.IntegerField(default=0, help_text="The number of NFTs in the collection with this trait.")
    rarity = models.FloatField(default=0.0, help_text="The percentage of NFTs in the collection with this trait.")

    class Meta:
        unique_together = ('trait_type', 'value')
        ordering = ['value']

    def __str__(self):
        return f"{self.trait_type.name}: {self.value}"



class PendingCollection(TimeStampedModel):
    """A staging area for user-submitted collections awaiting admin approval."""
    mint_address = models.CharField(max_length=44, unique=True)
    name = models.CharField(max_length=255)
    creator = models.CharField(max_length=255, blank=True)  # Add this
    description = models.TextField(blank=True)  # Add this
    image_url = models.URLField(max_length=1000, blank=True)  # Add this
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending')
    
    submitted_by = models.CharField(max_length=255)
    social_media_links = models.JSONField(null=True, blank=True)
    validation_error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"Pending: {self.name} ({self.mint_address[:6]}...)"