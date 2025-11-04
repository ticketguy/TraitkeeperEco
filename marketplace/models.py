# marketplace/models.py

"""
TraitKeeper Marketplace Models

This module contains all models related to the marketplace functionality,
including auctions, platform fees, and the NFT Vitality system.

The Vitality system is TraitKeeper's proprietary value metric that replaces
floor price as the primary indicator of NFT value.
"""

from django.db import models
from django.utils import timezone

# Import the core catalog models to establish relationships.
from nft_data.models import NFT, NFTCollection

# Import vitality models
from .vitality_models import (
    NFTVitality,
    NFTVitalityHistory,
    CollectionVitality,
    CollectionVitalityHistory,
    VitalityPriceComparison,
    MinimumBidThreshold
)

from datetime import timedelta
from django.db.models import Avg


class AuctionEvent(models.Model):
    """
    Tracks the state and details of a single NFT auction on the platform.

    Each instance represents one auction from its creation to completion or cancellation,
    logging the creator, timing, pricing, and bidding activity.
    """
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    # The transaction signature that created the auction serves as a unique ID.
    auction_id = models.CharField(max_length=88, primary_key=True)
    
    # Direct relationships to the core NFT and Collection models.
    nft = models.ForeignKey(NFT, on_delete=models.CASCADE, related_name='auctions')
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='auctions')
    
    creator = models.CharField(max_length=44, db_index=True, help_text="Wallet address of the auction creator.")
    
    # --- Auction State ---
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(db_index=True, help_text="When the auction is scheduled to end.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    # --- Pricing and Bidding ---
    starting_price = models.DecimalField(max_digits=20, decimal_places=9, help_text="The minimum opening bid in SOL.")
    current_bid = models.DecimalField(max_digits=20, decimal_places=9, null=True, blank=True, help_text="The current highest bid in SOL.")
    current_bidder = models.CharField(max_length=44, null=True, blank=True, db_index=True)
    bid_count = models.IntegerField(default=0)
    
    # --- Final Outcome ---
    final_price = models.DecimalField(max_digits=20, decimal_places=9, null=True, blank=True, help_text="The winning bid amount in SOL.")
    winner = models.CharField(max_length=44, null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-end_time']
        verbose_name = "Auction Event"
        verbose_name_plural = "Auction Events"
        indexes = [
            models.Index(fields=['status', 'end_time']),
            models.Index(fields=['collection', 'status']),
            models.Index(fields=['nft', 'status']),
        ]

    def __str__(self):
        return f"Auction for {self.nft.name} ({self.status})"


class PlatformFee(models.Model):
    """
    An immutable record of a fee collected by the platform from a transaction.
    
    This model is essential for accounting, allowing you to track all revenue
    generated from marketplace activities.
    """
    class EventType(models.TextChoices):
        SALE = 'SALE', 'Direct Sale'
        AUCTION = 'AUCTION', 'Auction Sale'
        # Add other fee-generating events here in the future.

    # The transaction signature provides a unique ID for the fee record.
    tx_signature = models.CharField(max_length=88, primary_key=True)

    # A string-based link to the NFTEvent to avoid hard dependencies between apps.
    event = models.ForeignKey('indexer.NFTEvent', on_delete=models.CASCADE, related_name='platform_fees')
    
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=9, help_text="The fee amount collected in SOL.")
    
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Platform Fee"
        verbose_name_plural = "Platform Fees"
        indexes = [
            models.Index(fields=['event_type', 'timestamp']),
        ]

    def __str__(self):
        return f"Fee of {self.amount} SOL from TX {self.tx_signature[:12]}..."


class PrivateBid(models.Model):
    """
    Represents a private, encrypted bid placed on an NFT.

    In TraitKeeper's privacy-first marketplace, bids are encrypted so only
    the NFT owner can see the bid amount. This prevents front-running and
    maintains negotiation privacy between buyer and seller.

    Bids are escrowed on-chain via smart contract and can be:
    - Accepted by the owner (executes sale)
    - Rejected by the owner (funds returned to bidder)
    - Cancelled by the bidder (funds returned)
    - Expired automatically after expiry time
    """
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        ACCEPTED = 'ACCEPTED', 'Accepted (Sale Executed)'
        REJECTED = 'REJECTED', 'Rejected by Owner'
        CANCELLED = 'CANCELLED', 'Cancelled by Bidder'
        EXPIRED = 'EXPIRED', 'Expired'

    # The transaction signature that created the bid serves as unique ID
    bid_id = models.CharField(max_length=88, primary_key=True)

    # NFT and Collection references
    nft = models.ForeignKey(
        NFT,
        on_delete=models.CASCADE,
        related_name='private_bids',
        help_text="The NFT this bid is for"
    )
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='private_bids',
        help_text="The collection this NFT belongs to"
    )

    amount = models.DecimalField(
        max_digits=20, 
        decimal_places=9, 
        help_text="Bid amount in SOL"
    )

    # Participants
    bidder = models.CharField(
        max_length=44,
        db_index=True,
        help_text="Wallet address of the bidder"
    )
    owner_at_creation = models.CharField(
        max_length=44,
        db_index=True,
        help_text="NFT owner when bid was placed (for tracking ownership changes)"
    )

    # Privacy/Encryption Details
    encrypted_state_account = models.CharField(
        max_length=255,
        help_text="Reference to on-chain encrypted state (Arcium account address)"
    )

    # Bid Lifecycle
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(
        db_index=True,
        help_text="When this bid automatically expires"
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the bid was accepted/rejected/cancelled"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Private Bid"
        verbose_name_plural = "Private Bids"
        indexes = [
            models.Index(fields=['nft', 'status', '-created_at']),
            models.Index(fields=['bidder', 'status']),
            models.Index(fields=['status', 'expires_at']),
            models.Index(fields=['collection', 'status']),
        ]

    def __str__(self):
        return f"Bid on {self.nft.name} by {self.bidder[:8]}... ({self.status})"

    @property
    def is_active(self):
        """Check if bid is still active and not expired."""
        return self.status == self.Status.ACTIVE and timezone.now() < self.expires_at

    @property
    def is_expired(self):
        """Check if bid has passed expiry time."""
        return self.status == self.Status.ACTIVE and timezone.now() >= self.expires_at


class MarketplaceTransaction(models.Model):
    """
    Detailed record of marketplace transactions with analytics data.

    This model extends NFTEvent with marketplace-specific metadata,
    particularly around privacy features and vitality-based pricing.

    Created automatically when:
    - A private bid is accepted
    - A direct "Buy Now" purchase is executed
    - An auction is finalized
    """
    class TransactionType(models.TextChoices):
        BID_ACCEPTED = 'BID_ACCEPTED', 'Private Bid Accepted'
        DIRECT_SALE = 'DIRECT_SALE', 'Direct Buy Now Purchase'
        AUCTION_SALE = 'AUCTION_SALE', 'Auction Sale'
        COUNTER_OFFER_ACCEPTED = 'COUNTER_OFFER_ACCEPTED', 'Counter Offer Accepted'

    # Transaction ID is the on-chain signature
    transaction_id = models.CharField(max_length=88, primary_key=True)

    # Link to the core NFTEvent (for analytics integration)
    nft_event = models.OneToOneField(
        'indexer.NFTEvent',
        on_delete=models.CASCADE,
        related_name='marketplace_transaction',
        help_text="The NFTEvent this transaction is associated with"
    )

    # Transaction Details
    transaction_type = models.CharField(
        max_length=30,
        choices=TransactionType.choices,
        help_text="Type of marketplace transaction"
    )

    # Privacy Features
    was_encrypted = models.BooleanField(
        default=False,
        help_text="Was this transaction encrypted (private bid/auction)?"
    )
    reveal_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the encrypted bid/price was revealed"
    )

    # Vitality Analytics (captured at time of sale)
    nft_vitality_at_sale = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="NFT vitality score when sold"
    )
    suggested_price_at_sale = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        null=True,
        blank=True,
        help_text="Vitality-suggested price at time of sale (SOL)"
    )

    # Price Comparison Metrics
    vs_vitality_suggested = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price vs vitality suggestion multiplier (e.g., 1.25 = 25% above)"
    )
    vs_collection_floor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price vs collection floor multiplier"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Marketplace Transaction"
        verbose_name_plural = "Marketplace Transactions"
        indexes = [
            models.Index(fields=['transaction_type', '-created_at']),
            models.Index(fields=['was_encrypted', '-created_at']),
        ]

    def __str__(self):
        return f"{self.transaction_type} - {self.transaction_id[:12]}..."

    @property
    def sale_price(self):
        """Get sale price from linked NFTEvent."""
        return self.nft_event.amount if self.nft_event else None

    @property
    def buyer(self):
        """Get buyer from linked NFTEvent."""
        return self.nft_event.buyer if self.nft_event else None

    @property
    def seller(self):
        """Get seller from linked NFTEvent."""
        return self.nft_event.seller if self.nft_event else None


# =============================================================================
# Listing and Bidding Models (for Profile Integration)
# =============================================================================

class ListingType(models.TextChoices):
    """Types of NFT listings"""
    DIRECT_SELL = 'DIRECT_SELL', 'Direct Sell'
    SELL_INTENT = 'SELL_INTENT', 'Sell Intent'
    BUY_NOW = 'BUY_NOW', 'Buy Now'


class NFTListing(models.Model):
    """
    Tracks NFTs listed for sale (direct sell, buy now, or sell intent).
    Used for displaying user's active listings on their profile.
    """
    # Transaction signature as unique ID
    listing_id = models.CharField(max_length=88, primary_key=True)

    # NFT and Collection references
    nft = models.ForeignKey(
        NFT,
        on_delete=models.CASCADE,
        related_name='listings',
        help_text="The NFT being listed"
    )
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='listings'
    )

    # Seller information
    seller = models.CharField(
        max_length=44,
        db_index=True,
        help_text="Wallet address of the seller"
    )

    # Listing type
    listing_type = models.CharField(
        max_length=20,
        choices=ListingType.choices,
        default=ListingType.DIRECT_SELL
    )

    # Pricing
    price = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        help_text="Listing price in SOL"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this listing is still active"
    )

    # Timestamps
    listed_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this listing expires"
    )
    sold_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this NFT was sold"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-listed_at']
        verbose_name = "NFT Listing"
        verbose_name_plural = "NFT Listings"
        indexes = [
            models.Index(fields=['seller', 'is_active']),
            models.Index(fields=['nft', 'is_active']),
            models.Index(fields=['collection', 'is_active']),
            models.Index(fields=['listing_type', 'is_active']),
        ]

    def __str__(self):
        return f"{self.get_listing_type_display()} - {self.nft.name} ({self.price} SOL)"


class BidStatus(models.TextChoices):
    """Status of a bid"""
    ACTIVE = 'ACTIVE', 'Active'
    ACCEPTED = 'ACCEPTED', 'Accepted'
    REJECTED = 'REJECTED', 'Rejected'
    EXPIRED = 'EXPIRED', 'Expired'
    CANCELLED = 'CANCELLED', 'Cancelled'
    OUTBID = 'OUTBID', 'Outbid'


class Bid(models.Model):
    """
    Tracks bids placed on NFTs (both auction bids and private offers).
    Used for displaying user's bids and bids received on their profile.
    """
    # Transaction signature as unique ID
    bid_id = models.CharField(max_length=88, primary_key=True)

    # NFT and Collection references
    nft = models.ForeignKey(
        NFT,
        on_delete=models.CASCADE,
        related_name='bids',
        help_text="The NFT this bid is for"
    )
    collection = models.ForeignKey(
        NFTCollection,
        on_delete=models.CASCADE,
        related_name='bids'
    )

    # Bidder information
    bidder = models.CharField(
        max_length=44,
        db_index=True,
        help_text="Wallet address of the bidder"
    )

    # Related auction (if it's an auction bid)
    auction = models.ForeignKey(
        'AuctionEvent',
        on_delete=models.CASCADE,
        related_name='bids',
        null=True,
        blank=True,
        help_text="Related auction if this is an auction bid"
    )

    # Bid details
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=9,
        help_text="Bid amount in SOL"
    )
    status = models.CharField(
        max_length=20,
        choices=BidStatus.choices,
        default=BidStatus.ACTIVE,
        db_index=True
    )

    # Timestamps
    placed_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this bid expires"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-placed_at']
        verbose_name = "Bid"
        verbose_name_plural = "Bids"
        indexes = [
            models.Index(fields=['bidder', 'status']),
            models.Index(fields=['nft', 'status']),
            models.Index(fields=['auction', 'status']),
            models.Index(fields=['status', '-placed_at']),
        ]

    def __str__(self):
        bid_type = "Auction" if self.auction else "Private"
        return f"{bid_type} Bid: {self.amount} SOL on {self.nft.name}"

    @property
    def is_auction_bid(self):
        """Check if this is an auction bid"""
        return self.auction is not None

    @property
    def is_offer(self):
        """Check if this is a private offer (not auction)"""
        return self.auction is None


class TransactionMonitoring(models.Model):
    """
    Track Solana transaction lifecycle for health monitoring.

    This model monitors all marketplace transactions from submission to finalization,
    enabling real-time alerts on stuck transactions and performance metrics.
    """

    class TransactionStatus(models.TextChoices):
        SUBMITTED = 'SUBMITTED', 'Submitted to RPC'
        PENDING = 'PENDING', 'Pending confirmation'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        FINALIZED = 'FINALIZED', 'Finalized'
        FAILED = 'FAILED', 'Failed'
        TIMEOUT = 'TIMEOUT', 'Confirmation timeout'

    class ActionType(models.TextChoices):
        PLACE_BID = 'place_bid', 'Place Bid'
        ACCEPT_BID = 'accept_bid', 'Accept Bid'
        REJECT_BID = 'reject_bid', 'Reject Bid'
        CANCEL_BID = 'cancel_bid', 'Cancel Bid'
        CREATE_AUCTION = 'create_auction', 'Create Auction'
        PLACE_AUCTION_BID = 'place_auction_bid', 'Place Auction Bid'
        CANCEL_AUCTION = 'cancel_auction', 'Cancel Auction'
        FINALIZE_AUCTION = 'finalize_auction', 'Finalize Auction'
        SET_SELL_INTENT = 'set_sell_intent', 'Set Sell Intent'
        REMOVE_SELL_INTENT = 'remove_sell_intent', 'Remove Sell Intent'
        COUNTER_OFFER = 'counter_offer', 'Counter Offer'

    # Transaction identification
    transaction_signature = models.CharField(
        max_length=88,
        unique=True,
        db_index=True,
        help_text="Solana transaction signature"
    )
    action_type = models.CharField(
        max_length=50,
        choices=ActionType.choices,
        db_index=True,
        help_text="Type of marketplace action"
    )

    # Timing
    submitted_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When transaction was submitted to RPC"
    )
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When transaction was confirmed on-chain"
    )
    finalized_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When transaction reached finality"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.SUBMITTED,
        db_index=True
    )

    # Performance metrics
    confirmation_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Time to confirm in milliseconds"
    )
    finalization_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Time to finalize in milliseconds"
    )

    # Infrastructure
    rpc_provider = models.CharField(
        max_length=50,
        blank=True,
        help_text="RPC provider used (helius, quicknode, etc.)"
    )

    # Context
    nft_mint = models.CharField(
        max_length=44,
        blank=True,
        db_index=True,
        help_text="NFT involved in transaction"
    )
    user_wallet = models.CharField(
        max_length=44,
        blank=True,
        db_index=True,
        help_text="User wallet that initiated transaction"
    )

    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text="Error message if transaction failed"
    )
    retry_count = models.IntegerField(
        default=0,
        help_text="Number of confirmation retry attempts"
    )

    # Additional metadata
    metadata = models.JSONField(
        default=dict,
        help_text="Additional transaction context"
    )

    class Meta:
        verbose_name = "Transaction Monitoring"
        verbose_name_plural = "Transaction Monitoring"
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['status', '-submitted_at']),
            models.Index(fields=['action_type', '-submitted_at']),
            models.Index(fields=['rpc_provider', '-submitted_at']),
            models.Index(fields=['nft_mint', '-submitted_at']),
            models.Index(fields=['user_wallet', '-submitted_at']),
        ]

    def __str__(self):
        return f"{self.get_action_type_display()}: {self.transaction_signature[:12]}... ({self.get_status_display()})"

    @classmethod
    def create_from_transaction(
        cls,
        signature: str,
        action_type: str,
        nft_mint: str = '',
        user_wallet: str = '',
        rpc_provider: str = '',
        **kwargs
    ):
        """
        Create transaction monitoring record.

        Args:
            signature: Solana transaction signature
            action_type: Type of marketplace action
            nft_mint: NFT mint address
            user_wallet: User wallet address
            rpc_provider: RPC provider name
            **kwargs: Additional metadata

        Returns:
            TransactionMonitoring instance
        """
        return cls.objects.create(
            transaction_signature=signature,
            action_type=action_type,
            nft_mint=nft_mint,
            user_wallet=user_wallet,
            rpc_provider=rpc_provider,
            metadata=kwargs
        )

    def mark_confirmed(self):
        """Mark transaction as confirmed and calculate confirmation time"""
        now = timezone.now()
        self.confirmed_at = now
        self.status = self.TransactionStatus.CONFIRMED
        self.confirmation_time_ms = int((now - self.submitted_at).total_seconds() * 1000)
        self.save(update_fields=['confirmed_at', 'status', 'confirmation_time_ms'])

    def mark_finalized(self):
        """Mark transaction as finalized and calculate finalization time"""
        now = timezone.now()
        self.finalized_at = now
        self.status = self.TransactionStatus.FINALIZED
        self.finalization_time_ms = int((now - self.submitted_at).total_seconds() * 1000)
        self.save(update_fields=['finalized_at', 'status', 'finalization_time_ms'])

    def mark_failed(self, error: str):
        """Mark transaction as failed with error message"""
        self.status = self.TransactionStatus.FAILED
        self.error_message = error
        self.save(update_fields=['status', 'error_message'])

    def mark_timeout(self):
        """Mark transaction as timed out"""
        self.status = self.TransactionStatus.TIMEOUT
        self.error_message = f"Transaction confirmation timeout after {self.retry_count} attempts"
        self.save(update_fields=['status', 'error_message'])

    def increment_retry(self):
        """Increment retry counter"""
        self.retry_count += 1
        self.save(update_fields=['retry_count'])

    @classmethod
    def get_stuck_transactions(cls, minutes: int = 5):
        """
        Get transactions stuck in PENDING/SUBMITTED for > N minutes.

        Args:
            minutes: Number of minutes to consider a transaction stuck

        Returns:
            QuerySet of stuck transactions
        """
        cutoff = timezone.now() - timedelta(minutes=minutes)
        return cls.objects.filter(
            status__in=[cls.TransactionStatus.PENDING, cls.TransactionStatus.SUBMITTED],
            submitted_at__lt=cutoff
        )

    @classmethod
    def get_failure_rate_24h(cls) -> float:
        """
        Calculate failure rate in last 24 hours.

        Returns:
            Failure rate as percentage (0-100)
        """
        cutoff = timezone.now() - timedelta(hours=24)
        total = cls.objects.filter(submitted_at__gte=cutoff).count()
        if total == 0:
            return 0.0
        failed = cls.objects.filter(
            submitted_at__gte=cutoff,
            status__in=[cls.TransactionStatus.FAILED, cls.TransactionStatus.TIMEOUT]
        ).count()
        return (failed / total) * 100

    @classmethod
    def get_avg_confirmation_time(cls, hours: int = 1) -> float:
        """
        Get average confirmation time in last N hours.

        Args:
            hours: Number of hours to analyze

        Returns:
            Average confirmation time in milliseconds
        """
        cutoff = timezone.now() - timedelta(hours=hours)
        avg_time = cls.objects.filter(
            status=cls.TransactionStatus.CONFIRMED,
            confirmed_at__gte=cutoff,
            confirmation_time_ms__isnull=False
        ).aggregate(avg=Avg('confirmation_time_ms'))['avg']

        return avg_time or 0.0

    @classmethod
    def get_rpc_performance(cls, hours: int = 24):
        """
        Get RPC provider performance statistics.

        Args:
            hours: Number of hours to analyze

        Returns:
            Dict of RPC providers with their performance metrics
        """
        from django.db.models import Count, Avg

        cutoff = timezone.now() - timedelta(hours=hours)

        stats = cls.objects.filter(
            submitted_at__gte=cutoff
        ).values('rpc_provider').annotate(
            total_transactions=Count('id'),
            avg_confirmation_time=Avg('confirmation_time_ms'),
            failed_count=Count('id', filter=models.Q(
                status__in=[cls.TransactionStatus.FAILED, cls.TransactionStatus.TIMEOUT]
            ))
        )

        return {
            stat['rpc_provider']: {
                'total_transactions': stat['total_transactions'],
                'avg_confirmation_time_ms': stat['avg_confirmation_time'] or 0,
                'failed_count': stat['failed_count'],
                'failure_rate': (stat['failed_count'] / stat['total_transactions'] * 100)
                    if stat['total_transactions'] > 0 else 0
            }
            for stat in stats
        }