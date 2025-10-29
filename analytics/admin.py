# analytics/admin.py

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

# Import all models from the analytics app.
from .models import (
    AggregatedCollectionStats,
    TraitPerformanceScore,
    WalletProminence,
    WalletBehaviorProfile,
    CollectionSweepEvent,
    HighProfileTransfer,
    TrendingTrait,
    TopTrait,
)

# Your custom admin site (this is correct)
from traitkeeper.admin_site import admin_site

# --- Helper function for creating clickable admin links ---
def admin_link(obj, field_name, display_name=None):
    """
    Creates a clickable link to a related model in the Django admin.

    Args:
        obj: The model instance.
        field_name (str): The name of the foreign key field on the instance.
        display_name (str, optional): The text to display for the link. 
                                      Defaults to the string representation of the related object.

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


# ===================================================================
# Main Analytics Admin Views
# ===================================================================

@admin.register(AggregatedCollectionStats, site=admin_site)
class AggregatedCollectionStatsAdmin(admin.ModelAdmin):
    """
    Admin view for the final, calculated analytics results for a collection.
    
    This interface is read-only, as all data is populated by the
    MetricsCalculationService.
    """
    list_display = (
        'collection_link', 
        'health_indicator', 
        'floor_price', 
        'volume_24h', 
        'market_cap', 
        'price_change_24h', 
        'updated_at'
    )
    search_fields = ('collection__name', 'collection__address')
    # Make all fields read-only to prevent manual edits of calculated data.
    readonly_fields = [f.name for f in AggregatedCollectionStats._meta.fields]

    def collection_link(self, obj):
        """Provides a clickable link to the core NFTCollection object."""
        return admin_link(obj, 'collection')
    collection_link.short_description = "Collection"
    
    def health_indicator(self, obj):
        """Displays a color-coded health score for easy visual assessment."""
        score = obj.performance_score or 0
        if score >= 75: color, status = 'green', 'Excellent'
        elif score >= 50: color, status = '#007bff', 'Good' # Blue
        elif score >= 25: color, status = 'orange', 'Fair'
        else: color, status = 'red', 'Poor'
        return format_html('<span style="color: {}; font-weight: bold;">{} ({:.1f})</span>', color, status, score)
    health_indicator.short_description = 'Health'


@admin.register(TraitPerformanceScore, site=admin_site)
class TraitPerformanceScoreAdmin(admin.ModelAdmin):
    """Admin view for the calculated performance scores of individual traits."""
    list_display = ('trait_value_link', 'collection_link', 'performance_score', 'premium_score', 'rarity_score', 'updated_at')
    list_filter = ('collection',)
    search_fields = ('trait_value__value', 'trait_type__name', 'collection__name')
    readonly_fields = [f.name for f in TraitPerformanceScore._meta.fields]

    def collection_link(self, obj):
        return admin_link(obj, 'collection')
    collection_link.short_description = "Collection"

    def trait_value_link(self, obj):
        return admin_link(obj, 'trait_value')
    trait_value_link.short_description = "Trait Value"


# ===================================================================
# Wallet Analytics Admin Views
# ===================================================================

@admin.register(WalletProminence, site=admin_site)
class WalletProminenceAdmin(admin.ModelAdmin):
    """Admin view for basic wallet prominence scores."""
    list_display = ('address', 'prominence_score', 'transaction_volume', 'transaction_count', 'last_updated')
    search_fields = ('address',)
    readonly_fields = [f.name for f in WalletProminence._meta.fields]


@admin.register(WalletBehaviorProfile, site=admin_site)
class WalletBehaviorProfileAdmin(admin.ModelAdmin):
    """Admin view for advanced wallet behavior classifications."""
    list_display = ('wallet_address_short', 'behavior_type', 'confidence_score', 'influence_score', 'risk_tolerance', 'last_activity')
    list_filter = ('behavior_type', 'risk_tolerance')
    search_fields = ('wallet_address',)
    readonly_fields = [f.name for f in WalletBehaviorProfile._meta.fields]
    
    def wallet_address_short(self, obj):
        """Shortens the wallet address for cleaner display."""
        return f"{obj.wallet_address[:6]}...{obj.wallet_address[-4:]}"
    wallet_address_short.short_description = 'Wallet'


# ===================================================================
# Event-Based Analytics Admin Views
# ===================================================================

@admin.register(CollectionSweepEvent, site=admin_site)
class CollectionSweepEventAdmin(admin.ModelAdmin):
    """Admin view for detected collection sweep events."""
    list_display = ('collection_link', 'buyer_address_short', 'significance_score', 'num_items', 'total_volume', 'start_time')
    list_filter = ('collection',)
    search_fields = ('buyer_address', 'collection__name')
    readonly_fields = [f.name for f in CollectionSweepEvent._meta.fields]

    def collection_link(self, obj):
        return admin_link(obj, 'collection')
    collection_link.short_description = "Collection"

    def buyer_address_short(self, obj):
        return f"{obj.buyer_address[:6]}...{obj.buyer_address[-4:]}"
    buyer_address_short.short_description = 'Buyer'


@admin.register(HighProfileTransfer, site=admin_site)
class HighProfileTransferAdmin(admin.ModelAdmin):
    """Admin view for significant, high-profile NFT sales."""
    list_display = ('nft_link', 'collection_link', 'high_profile_score', 'rank', 'updated_at')
    list_filter = ('collection',)
    search_fields = ('nft__mint_address', 'collection__name')
    readonly_fields = [f.name for f in HighProfileTransfer._meta.fields]

    def collection_link(self, obj):
        return admin_link(obj, 'collection')
    collection_link.short_description = "Collection"
    
    def nft_link(self, obj):
        return admin_link(obj, 'nft')
    nft_link.short_description = "NFT"

# ===================================================================
# Simple Read-Only Views for Trait Analytics
# ===================================================================

@admin.register(TrendingTrait, site=admin_site)
class TrendingTraitAdmin(admin.ModelAdmin):
    """Admin view for traits with high recent trading activity."""
    list_display = ('trait_value', 'collection', 'trend_score', 'updated_at')
    readonly_fields = [f.name for f in TrendingTrait._meta.fields]
    search_fields = ('trait_value__value', 'collection__name')

@admin.register(TopTrait, site=admin_site)
class TopTraitAdmin(admin.ModelAdmin):
    """Admin view for traits with the highest overall performance scores."""
    list_display = ('trait_value', 'collection', 'combined_score', 'updated_at')
    readonly_fields = [f.name for f in TopTrait._meta.fields]
    search_fields = ('trait_value__value', 'collection__name')