# marketplace/admin.py

import csv
from django.contrib import admin
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html

# Import models from the marketplace app.
from .models import AuctionEvent, PlatformFee, NFTListing, Bid
from .vitality_models import (
    NFTVitality,
    NFTVitalityHistory,
    CollectionVitality,
    CollectionVitalityHistory,
    VitalityPriceComparison,
    MinimumBidThreshold
)

# Your custom admin site.
from traitkeeper.admin_site import admin_site

# --- Helper function for creating clickable admin links ---
def admin_link(obj, field_name, display_name=None):
    """
    Creates a clickable link to a related model in the Django admin.

    Args:
        obj: The model instance.
        field_name (str): The name of the foreign key field on the instance.
        display_name (str, optional): The text to display for the link.

    Returns:
        str: An HTML safe string for the admin link.
    """
    related_obj = getattr(obj, field_name, None)
    if related_obj is None:
        return "N/A"
    
    app_label = related_obj._meta.app_label
    model_name = related_obj._meta.model_name
    link = reverse(f'admin:{app_label}_{model_name}_change', args=[related_obj.pk])
    return format_html('<a href="{}">{}</a>', link, display_name or str(related_obj))


@admin.register(AuctionEvent, site=admin_site)
class AuctionEventAdmin(admin.ModelAdmin):
    """
    Admin interface for monitoring and managing NFT auctions.
    
    This view is primarily read-only to ensure data integrity, but provides
    emergency actions for administrators to cancel or finalize auctions if needed.
    """
    list_display = (
        'nft_link',
        'collection_link',
        'status',
        'current_bid',
        'creator',
        'end_time'
    )
    list_filter = ('status', 'collection')
    search_fields = ('nft__mint_address', 'creator', 'winner')
    
    # Most fields are read-only as they are controlled by the marketplace service.
    readonly_fields = (
        'auction_id', 'nft', 'collection', 'creator', 'start_time', 'end_time',
        'starting_price', 'current_bid', 'current_bidder', 'final_price',
        'winner', 'created_at', 'updated_at'
    )
    
    fieldsets = (
        ("Overview", {'fields': ('auction_id', 'nft', 'collection', 'status')}),
        ("Auction Details", {'fields': ('creator', 'start_time', 'end_time', 'starting_price')}),
        ("Bidding Activity", {'fields': ('current_bid', 'current_bidder')}),
        ("Outcome", {'fields': ('final_price', 'winner')}),
    )

    actions = ['cancel_selected_auctions']

    def nft_link(self, obj):
        """Provides a clickable link to the NFT being auctioned."""
        return admin_link(obj, 'nft')
    nft_link.short_description = "NFT"

    def collection_link(self, obj):
        """Provides a clickable link to the collection."""
        return admin_link(obj, 'collection')
    collection_link.short_description = "Collection"

    def cancel_selected_auctions(self, request, queryset):
        """Admin action to forcibly cancel active auctions."""
        # Note: In a real app, this should call a method in MarketplaceService
        # to handle bid refunds and smart contract interactions.
        active_auctions = queryset.filter(status='ACTIVE')
        count = active_auctions.update(status='CANCELLED')
        self.message_user(request, f"Successfully cancelled {count} active auction(s).", level='success')
    cancel_selected_auctions.short_description = "Cancel selected ACTIVE auctions"


@admin.register(PlatformFee, site=admin_site)
class PlatformFeeAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing platform fees collected from marketplace activities.
    
    This is a strictly read-only interface for accounting and review purposes.
    """
    list_display = ('tx_signature_short', 'event_type', 'amount', 'timestamp', 'event_link')
    list_filter = ('event_type', 'timestamp')
    search_fields = ('tx_signature', 'event__nft_mint')
    
    # All fields are read-only as this is an immutable financial record.
    readonly_fields = [f.name for f in PlatformFee._meta.fields]
    
    actions = ['export_fees_to_csv']

    def tx_signature_short(self, obj):
        """Shortens the transaction signature for display."""
        return f"{obj.tx_signature[:10]}..."
    tx_signature_short.short_description = "TX Signature"

    def event_link(self, obj):
        """Provides a clickable link to the underlying NFTEvent."""
        return admin_link(obj, 'event')
    event_link.short_description = "Source Event"
    
    def export_fees_to_csv(self, request, queryset):
        """Admin action to export selected fee records to a CSV file."""
        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename={meta.verbose_name_plural}.csv'
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])

        return response
    export_fees_to_csv.short_description = "Export selected fees to CSV"


# ============================================================================
# VITALITY SYSTEM ADMIN INTERFACES
# ============================================================================

@admin.register(NFTVitality, site=admin_site)
class NFTVitalityAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing and managing individual NFT vitality scores.

    Displays the current vitality score for each NFT along with component breakdowns.
    """
    list_display = (
        'nft_link',
        'vitality_score_display',
        'market_momentum',
        'trait_performance',
        'has_sufficient_data',
        'updated_at'
    )
    list_filter = ('has_sufficient_data', 'nft__collection')
    search_fields = ('nft__mint_address', 'nft__name', 'nft__collection__name')
    readonly_fields = (
        'nft', 'vitality_score', 'market_momentum', 'trait_performance',
        'collection_health', 'collection_utility', 'rarity_score',
        'holder_quality', 'perception_index', 'market_influence',
        'suggested_price', 'has_sufficient_data', 'updated_at'
    )

    fieldsets = (
        ("NFT Information", {
            'fields': ('nft', 'vitality_score', 'suggested_price', 'has_sufficient_data')
        }),
        ("Component Scores (0-1 range)", {
            'fields': (
                'market_momentum',
                'trait_performance',
                'collection_health',
                'collection_utility',
                'rarity_score',
                'holder_quality',
                'perception_index',
                'market_influence'
            ),
            'description': 'Individual component scores that contribute to the overall vitality score.'
        }),
        ("Metadata", {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        })
    )

    def nft_link(self, obj):
        """Provides a clickable link to the NFT."""
        return admin_link(obj, 'nft', display_name=f"{obj.nft.name or obj.nft.mint_address[:10]}...")
    nft_link.short_description = "NFT"

    def vitality_score_display(self, obj):
        """Display vitality score with color coding."""
        score = float(obj.vitality_score)
        if score >= 70:
            color = 'green'
        elif score >= 40:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.2f}</span>',
            color,
            score
        )
    vitality_score_display.short_description = "Vitality Score"


@admin.register(NFTVitalityHistory, site=admin_site)
class NFTVitalityHistoryAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing historical vitality score changes for NFTs.

    Useful for tracking how an NFT's vitality has changed over time.
    """
    list_display = (
        'nft_link',
        'vitality_score',
        'recorded_at_date'
    )
    list_filter = ('nft__collection', 'recorded_at')
    search_fields = ('nft__mint_address', 'nft__name')
    readonly_fields = [f.name for f in NFTVitalityHistory._meta.fields]
    date_hierarchy = 'recorded_at'

    def nft_link(self, obj):
        """Provides a clickable link to the NFT."""
        return admin_link(obj, 'nft', display_name=f"{obj.nft.name or obj.nft.mint_address[:10]}...")
    nft_link.short_description = "NFT"

    def recorded_at_date(self, obj):
        """Format the recorded_at timestamp."""
        return obj.recorded_at.strftime('%Y-%m-%d %H:%M:%S')
    recorded_at_date.short_description = "Recorded At"


@admin.register(CollectionVitality, site=admin_site)
class CollectionVitalityAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing collection-level vitality scores.

    Shows the overall vitality of an entire collection.
    """
    list_display = (
        'collection_link',
        'vitality_score_display',
        'avg_nft_vitality',
        'nfts_with_data_percent',
        'updated_at'
    )
    list_filter = ('collection__is_featured',)
    search_fields = ('collection__name', 'collection__address')
    readonly_fields = (
        'collection', 'vitality_score', 'avg_nft_vitality',
        'total_nfts', 'nfts_with_data', 'market_momentum',
        'avg_trait_performance',
        'collection_health', 'collection_utility',
        'holder_quality_avg',
        'perception_index', 'market_influence',
        'suggested_floor_price', 'updated_at'
    )

    fieldsets = (
        ("Collection Information", {
            'fields': ('collection', 'vitality_score', 'suggested_floor_price')
        }),
        ("NFT Coverage", {
            'fields': ('total_nfts', 'nfts_with_data', 'avg_nft_vitality')
        }),
        ("Component Scores (0-1 range)", {
            # Corrected field names
            'fields': (
                'market_momentum',
                'avg_trait_performance',
                'collection_health',
                'collection_utility',
                'holder_quality_avg',
                'perception_index',
                'market_influence'
            )
        }),
        ("Metadata", {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        })
    )

    def collection_link(self, obj):
        """Provides a clickable link to the collection."""
        return admin_link(obj, 'collection')
    collection_link.short_description = "Collection"

    def vitality_score_display(self, obj):
        """Display vitality score with color coding."""
        score = float(obj.vitality_score)
        if score >= 70:
            color = 'green'
        elif score >= 40:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.2f}</span>',
            color,
            score
        )
    vitality_score_display.short_description = "Vitality Score"

    def nfts_with_data_percent(self, obj):
        """Calculate percentage of NFTs with sufficient data."""
        if obj.total_nfts == 0:
            return "0%"
        percentage = (obj.nfts_with_data / obj.total_nfts) * 100
        return f"{percentage:.1f}%"
    nfts_with_data_percent.short_description = "Data Coverage"


@admin.register(CollectionVitalityHistory, site=admin_site)
class CollectionVitalityHistoryAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing historical collection vitality changes.

    Tracks how a collection's vitality has evolved over time.
    """
    list_display = (
        'collection_link',
        'vitality_score',
        'recorded_at_date'
    )
    list_filter = ('collection', 'recorded_at')
    search_fields = ('collection__name', 'collection__address')
    readonly_fields = [f.name for f in CollectionVitalityHistory._meta.fields]
    date_hierarchy = 'recorded_at'

    def collection_link(self, obj):
        """Provides a clickable link to the collection."""
        return admin_link(obj, 'collection')
    collection_link.short_description = "Collection"

    def recorded_at_date(self, obj):
        """Format the recorded_at timestamp."""
        return obj.recorded_at.strftime('%Y-%m-%d %H:%M:%S')
    recorded_at_date.short_description = "Recorded At"


@admin.register(VitalityPriceComparison, site=admin_site)
class VitalityPriceComparisonAdmin(admin.ModelAdmin):
    """
    Admin interface for comparing actual sale prices vs vitality-predicted prices.

    Helps evaluate the accuracy of the vitality prediction system.
    """
    list_display = (
        'sale_event_link',
        'actual_sale_price',
        'suggested_price_at_sale',
        'deviation_percent_display',  # Corrected method name
        'accuracy_rating',
        'sale_timestamp'
    )
    list_filter = ('nft__collection',)
    # Corrected search field for the event signature
    search_fields = ('nft__mint_address', 'nft__name', 'sale_event__event_id')
    readonly_fields = [f.name for f in VitalityPriceComparison._meta.fields]
    date_hierarchy = 'sale_timestamp'

    fieldsets = (
        ("Sale Information", {
            # Corrected field names
            'fields': ('sale_event', 'nft', 'sale_timestamp')
        }),
        ("Price Comparison", {
            # Corrected field names
            'fields': (
                'actual_sale_price',
                'suggested_price_at_sale',
                'price_difference_sol',
                'price_difference_percent',
                'accuracy_rating'
            )
        }),
        ("Vitality at Sale Time", {
            'fields': ('vitality_at_sale',),
            'classes': ('collapse',)
        })
    )

    def sale_event_link(self, obj):
        """Provides a clickable link to the sale event."""
        # Corrected to use event_id from the related NFTEvent model
        return admin_link(obj, 'sale_event', display_name=f"Sale {obj.sale_event.event_id[:10]}...")
    sale_event_link.short_description = "Sale Event"

    def deviation_percent_display(self, obj):
        """Display deviation percentage with color coding."""
        # Correctly reference 'price_difference_percent' from the model
        deviation = float(obj.price_difference_percent)
        if abs(deviation) <= 10:
            color = 'green'
        elif abs(deviation) <= 25:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {};">{:+.2f}%</span>',
            color,
            deviation
        )
    deviation_percent_display.short_description = "Deviation %"


@admin.register(MinimumBidThreshold, site=admin_site)
class MinimumBidThresholdAdmin(admin.ModelAdmin):
    """
    Admin interface for configuring minimum bid thresholds.

    Allows admins to set collection-level, NFT-level, or global minimum bid rules.
    """
    list_display = (
        'threshold_scope',
        'threshold_type',
        'threshold_value_display',
        'set_by',
        'is_active',
        'created_at'
    )
    list_filter = ('threshold_type', 'set_by', 'is_active')
    search_fields = ('collection__name', 'nft__mint_address', 'notes')

    fieldsets = (
        ("Scope", {
            'fields': ('collection', 'nft'),
            'description': 'Leave both empty for a global threshold.'
        }),
        ("Threshold Configuration", {
            'fields': (
                'threshold_type',
                'vitality_percentage_threshold',
                'absolute_minimum_sol',
                'floor_percentage_threshold'
            ),
            'description': 'Only fill in the field corresponding to the threshold type.'
        }),
        ("Metadata", {
            'fields': ('set_by', 'is_active', 'notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    readonly_fields = ('created_at', 'updated_at')

    def threshold_scope(self, obj):
        """Display the scope of the threshold."""
        if obj.nft:
            return f"NFT: {obj.nft.name or obj.nft.mint_address[:10]}..."
        elif obj.collection:
            return f"Collection: {obj.collection.name}"
        else:
            return "Global"
    threshold_scope.short_description = "Scope"

    def threshold_value_display(self, obj):
        """Display the threshold value based on type."""
        if obj.threshold_type == 'VITALITY_BASED':
            return f"{obj.vitality_percentage_threshold}% below vitality"
        elif obj.threshold_type == 'ABSOLUTE_SOL':
            return f"{obj.absolute_minimum_sol} SOL"
        elif obj.threshold_type == 'FLOOR_PERCENTAGE':
            return f"{obj.floor_percentage_threshold}% of floor"
        return "N/A"
    threshold_value_display.short_description = "Threshold Value"

    def save_model(self, request, obj, form, change):
        """Automatically set the set_by field to the current admin user."""
        if not change:  # Only on creation
            obj.set_by = 'ADMIN'
        super().save_model(request, obj, form, change)


# ============================================================================
# MARKETPLACE LISTING & BIDDING ADMIN INTERFACES
# ============================================================================

@admin.register(NFTListing, site=admin_site)
class NFTListingAdmin(admin.ModelAdmin):
    """
    Admin interface for monitoring NFT listings on the marketplace.
    """
    list_display = (
        'nft_link',
        'listing_type',
        'price',
        'seller_short',
        'is_active',
        'listed_at'
    )
    list_filter = ('listing_type', 'is_active', 'listed_at')
    search_fields = ('nft__name', 'nft__mint_address', 'seller', 'listing_id')
    readonly_fields = (
        'listing_id', 'nft', 'seller', 'listing_type', 'price',
        'listed_at', 'expires_at', 'sold_at'
    )
    date_hierarchy = 'listed_at'

    fieldsets = (
        ("Listing Information", {
            'fields': ('listing_id', 'nft', 'listing_type', 'is_active')
        }),
        ("Seller Details", {
            'fields': ('seller', 'price')
        }),
        ("Timestamps", {
            'fields': ('listed_at', 'expires_at', 'sold_at'),
            'classes': ('collapse',)
        })
    )

    actions = ['mark_as_inactive']

    def nft_link(self, obj):
        """Provides a clickable link to the NFT."""
        return admin_link(obj, 'nft', display_name=f"{obj.nft.name or obj.nft.mint_address[:10]}...")
    nft_link.short_description = "NFT"

    def seller_short(self, obj):
        """Display shortened seller wallet address."""
        return f"{obj.seller[:8]}...{obj.seller[-6:]}"
    seller_short.short_description = "Seller"

    def mark_as_inactive(self, request, queryset):
        """Admin action to mark listings as inactive."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"Successfully marked {count} listing(s) as inactive.", level='success')
    mark_as_inactive.short_description = "Mark selected listings as inactive"


@admin.register(Bid, site=admin_site)
class BidAdmin(admin.ModelAdmin):
    """
    Admin interface for monitoring bids on NFTs.
    """
    list_display = (
        'nft_link',
        'amount',
        'bidder_short',
        'status',
        'is_auction_bid',
        'placed_at'
    )
    list_filter = ('status', 'placed_at', 'auction')
    search_fields = ('nft__name', 'nft__mint_address', 'bidder', 'bid_id')
    readonly_fields = (
        'bid_id', 'nft', 'bidder', 'auction', 'amount', 'status',
        'placed_at', 'updated_at'
    )
    date_hierarchy = 'placed_at'

    fieldsets = (
        ("Bid Information", {
            'fields': ('bid_id', 'nft', 'amount', 'status')
        }),
        ("Bidder Details", {
            'fields': ('bidder', 'auction')
        }),
        ("Timestamps", {
            'fields': ('placed_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def nft_link(self, obj):
        """Provides a clickable link to the NFT."""
        return admin_link(obj, 'nft', display_name=f"{obj.nft.name or obj.nft.mint_address[:10]}...")
    nft_link.short_description = "NFT"

    def bidder_short(self, obj):
        """Display shortened bidder wallet address."""
        return f"{obj.bidder[:8]}...{obj.bidder[-6:]}"
    bidder_short.short_description = "Bidder"

    def is_auction_bid(self, obj):
        """Indicate if this is an auction bid."""
        return obj.is_auction_bid
    is_auction_bid.boolean = True
    is_auction_bid.short_description = "Auction Bid"