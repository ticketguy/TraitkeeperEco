# indexer/models.py

from django.db import models
from nft_data.models import NFTCollection

# ===================================================================
# Core Indexer Models
# These models store the primary raw data fetched from the blockchain
# and external marketplace APIs.
# ===================================================================

class NFTListing(models.Model):
    """
    Represents a single, raw NFT listing from a marketplace.

    This model tracks the state of an individual NFT for sale, including its
    price, seller, and current status (e.g., Active, Sold).
    """
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        SOLD = 'SOLD', 'Sold'
        CANCELLED = 'CANCELLED', 'Cancelled'
        EXPIRED = 'EXPIRED', 'Expired'

    listing_id = models.CharField(max_length=88, primary_key=True, help_text="Marketplace-specific ID for the listing.")
    
    # Using CharFields for resilience. This decouples the indexer from the main
    # app, preventing failures if an NFT record doesn't exist yet.
    nft_mint = models.CharField(max_length=44, db_index=True, help_text="The mint address of the NFT being listed.")
    collection_address = models.CharField(max_length=44, db_index=True, help_text="The collection this NFT belongs to.")
    
    marketplace = models.CharField(max_length=50, help_text="e.g., 'magic_eden', 'tensor'")
    price = models.DecimalField(max_digits=20, decimal_places=9, help_text="Listing price in SOL.")
    seller_address = models.CharField(max_length=44, db_index=True, help_text="The wallet address of the seller.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    
    # Timestamps for tracking the listing's lifecycle.
    listed_at = models.DateTimeField(help_text="When the listing was created on the marketplace.")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="When the listing is set to expire.")
    
    # Metadata for debugging and future analysis.
    raw_data = models.JSONField(default=dict, help_text="The complete raw data payload from the source API.")
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-listed_at', 'price']
        indexes = [
            models.Index(fields=['collection_address', 'status', 'price']),
            models.Index(fields=['nft_mint', 'status']),
            models.Index(fields=['marketplace', 'status', 'listed_at']),
        ]

    def __str__(self):
        return f"Listing for {self.nft_mint[:8]} at {self.price} SOL on {self.marketplace}"


class NFTEvent(models.Model):
    """
    Stores an immutable record of an on-chain event related to an NFT.

    This model acts as a historical log for all significant actions, such as
    sales, transfers, mints, and bids.
    """
    class EventType(models.TextChoices):
        SALE = 'SALE', 'Sale'
        LISTING = 'LISTING', 'Listing'
        CANCEL_LISTING = 'CANCEL_LISTING', 'Cancel Listing'
        BID = 'BID', 'Bid'
        CANCEL_BID = 'CANCEL_BID', 'Cancel Bid'
        TRANSFER = 'TRANSFER', 'Transfer'
        MINT = 'MINT', 'Mint'
        BURN = 'BURN', 'Burn'

    event_id = models.CharField(max_length=88, primary_key=True, help_text="The transaction signature of the event.")
    
    # Addresses are stored as CharFields for indexer speed and resilience.
    collection_address = models.CharField(max_length=44, db_index=True, )
    nft_mint = models.CharField(max_length=44, db_index=True, null=True)
    
    event_type = models.CharField(max_length=20, choices=EventType.choices, db_index=True)
    marketplace = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    
    amount = models.DecimalField(max_digits=20, decimal_places=9, null=True, blank=True, help_text="Price for a sale/listing, or the bid amount.")
    buyer = models.CharField(max_length=44, null=True, blank=True, db_index=True, help_text="The buyer or bidder.")
    seller = models.CharField(max_length=44, null=True, blank=True, db_index=True, help_text="The seller or lister.")
    
    source_listing = models.ForeignKey(
        NFTListing,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resulting_events',
        help_text="Links a sale or cancellation event back to its original listing."
    )
    
    timestamp = models.DateTimeField(db_index=True, help_text="The on-chain timestamp of the event.")
    details = models.JSONField(default=dict, help_text="Additional raw details from the transaction source.")
    created_at = models.DateTimeField(auto_now_add=True)


    def get_collection(self):
        """Helper method to get the collection object when needed."""
        from nft_data.models import NFTCollection
        return NFTCollection.objects.filter(address=self.collection_address).first()
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['collection_address', 'event_type', 'timestamp']),
            models.Index(fields=['nft_mint', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} for {self.nft_mint[:8]}"


# ===================================================================
# Helper & Utility Models
# These models support the indexing process by storing metadata,
# tracking failures, and mapping identifiers.
# ===================================================================

class CollectionMarketStats(models.Model):
    """
    Stores raw, timestamped market statistics from a single external source (e.g., Magic Eden's API).
    
    This model is a simple log of what a marketplace API reported at a specific time.
    It contains NO calculated or aggregated data.
    """
    class DataSource(models.TextChoices):
        MAGIC_EDEN = 'magic_eden', 'Magic Eden'
        TENSOR = 'tensor', 'Tensor'
        BLOCKCHAIN = 'blockchain', 'Blockchain'
        TRAITKEEPER = 'traitkeeper', 'TraitKeeper'

    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='raw_market_stats')
    source = models.CharField(max_length=20, choices=DataSource.choices)
    
    # All fields are nullable, as API responses can vary.
    floor_price = models.DecimalField(max_digits=20, decimal_places=9, null=True, blank=True)
    volume_24h = models.DecimalField(max_digits=20, decimal_places=9, null=True, blank=True)
    sales_count_24h = models.IntegerField(null=True, blank=True)
    owners_count = models.IntegerField(null=True, blank=True)
    listed_count = models.IntegerField(null=True, blank=True)
    total_supply = models.IntegerField(null=True, blank=True)
    # ... other raw metric fields ...
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    raw_data = models.JSONField(default=dict, help_text="Complete raw API response from the source.")

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['collection', 'source', 'timestamp'])]

class MarketplaceIdentifier(models.Model):
    """Maps an NFTCollection to its various identifiers across different marketplaces (e.g., slug, UUID)."""
    class Marketplace(models.TextChoices):
        MAGIC_EDEN = 'magic_eden', 'Magic Eden'
        TENSOR = 'tensor', 'Tensor'
        OPENSEA = 'opensea', 'OpenSea'

    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='marketplace_ids')
    marketplace = models.CharField(max_length=50, choices=Marketplace.choices)
    identifier_value = models.CharField(max_length=100, help_text="The slug, symbol, or UUID used by the marketplace.")
    
    class Meta:
        unique_together = ('collection', 'marketplace')
        indexes = [models.Index(fields=['marketplace', 'identifier_value'])]

class BurnEvent(models.Model):
    """A specific record for when an NFT is burned, an irreversible event."""
    burn_id = models.CharField(max_length=88, primary_key=True, help_text="Transaction signature of the burn.")
    nft_mint = models.CharField(max_length=44, db_index=True,null=True )
    collection_address = models.CharField(max_length=44, db_index=True)
    burner = models.CharField(max_length=44, blank=True, help_text="Wallet that initiated the burn.")
    timestamp = models.DateTimeField(db_index=True)

class TraitEvent(models.Model):
    """Tracks a metadata update where a trait is added, updated, or removed from an NFT."""
    class Action(models.TextChoices):
        ADDED = 'ADDED', 'Added'
        UPDATED = 'UPDATED', 'Updated'
        REMOVED = 'REMOVED', 'Removed'

    event_id = models.CharField(max_length=88, primary_key=True, help_text="Transaction signature of the metadata update.")
    nft_mint = models.CharField(max_length=44, db_index=True)
    collection_address = models.CharField(max_length=44, db_index=True)
    details = models.JSONField(default=dict, help_text="Details of the change, e.g., {'trait_type': 'Hat', 'new_value': 'Crown'}")
    action = models.CharField(max_length=20, choices=Action.choices)
    timestamp = models.DateTimeField(db_index=True)

class FailedTransaction(models.Model):
    """Logs transactions that failed during processing for investigation or retry."""
    event_id = models.CharField(max_length=88, primary_key=True, help_text="Transaction signature that failed.")
    event_data = models.JSONField(help_text="The full event data that could not be processed.")
    error_message = models.TextField()
    retry_count = models.IntegerField(default=0)
    last_retry = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)



class UnknownDiscriminator(models.Model):
    """Tracks unknown instruction discriminators for auto-learning."""
    
    program_id = models.CharField(max_length=44, db_index=True)
    discriminator = models.CharField(max_length=16, db_index=True)  # hex string
    
    # What we inferred about it
    inferred_marketplace = models.CharField(max_length=50, blank=True)
    inferred_action = models.CharField(max_length=50, blank=True)
    
    # How we figured it out
    has_nft_transfer = models.BooleanField(default=False)
    has_native_transfer = models.BooleanField(default=False)
    log_patterns = models.JSONField(default=list)  # matched log patterns
    
    # Examples
    sample_signatures = models.JSONField(default=list)  # up to 5 examples
    occurrence_count = models.IntegerField(default=1)
    
    # Status
    is_approved = models.BooleanField(default=False)  # manual review flag
    should_ignore = models.BooleanField(default=False)  # if it's admin ops
    
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('program_id', 'discriminator')
        indexes = [
            models.Index(fields=['program_id', 'is_approved']),
            models.Index(fields=['inferred_marketplace', 'inferred_action']),
        ]
    
    def __str__(self):
        return f"{self.program_id[:8]}.../{self.discriminator} -> {self.inferred_action}"