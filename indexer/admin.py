# indexer/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    NFTEvent, NFTListing, CollectionMarketStats, TraitEvent, 
    FailedTransaction, BurnEvent, MarketplaceIdentifier
)
from traitkeeper.admin_site import admin_site # custom admin site

# --- Helper function to create admin links ---
def admin_link(obj, field_name, display_name=None):
    """Creates a clickable link to a related admin object."""
    if not obj or not hasattr(obj, field_name):
        return "N/A"
    
    related_obj = getattr(obj, field_name)
    if related_obj is None:
        return "N/A"
        
    app_label = related_obj._meta.app_label
    model_name = related_obj._meta.model_name
    link = reverse(f'admin:{app_label}_{model_name}_change', args=[related_obj.pk])
    return format_html('<a href="{}">{}</a>', link, display_name or str(related_obj))


@admin.register(NFTEvent, site=admin_site)
class NFTEventAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'event_type', 'nft_link', 'collection_link', 'amount', 'buyer', 'seller', 'timestamp')
    list_filter = ('event_type', 'timestamp', 'marketplace')
    search_fields = ('event_id', 'nft_mint', 'collection_address', 'buyer', 'seller')
    readonly_fields = ('event_id', 'event_type', 'nft_mint', 'collection_address', 'amount', 'buyer', 'seller', 'timestamp', 'marketplace', 'details', 'created_at', 'source_listing')

    def collection_link(self, obj):
        url = reverse('admin:nft_data_nftcollection_change', args=[obj.collection_address])
        return format_html('<a href="{}">{}...</a>', url, obj.collection_address[:12])
    collection_link.short_description = "Collection"

    def nft_link(self, obj):
        url = reverse('admin:nft_data_nft_change', args=[obj.nft_mint])
        return format_html('<a href="{}">{}...</a>', url, obj.nft_mint[:12])
    nft_link.short_description = "NFT Mint"


@admin.register(NFTListing, site=admin_site)
class NFTListingAdmin(admin.ModelAdmin):
    list_display = ('listing_id', 'nft_link', 'collection_link', 'price', 'marketplace', 'status', 'seller_address', 'listed_at')
    list_filter = ('marketplace', 'status', 'listed_at')
    search_fields = ('listing_id', 'nft_mint', 'collection_address', 'seller_address')
    readonly_fields = ('listing_id', 'nft_mint', 'collection_address', 'marketplace', 'price', 'seller_address', 'listed_at', 'expires_at', 'raw_data', 'last_updated')

    def collection_link(self, obj):
        url = reverse('admin:nft_data_nftcollection_change', args=[obj.collection_address])
        return format_html('<a href="{}">{}...</a>', url, obj.collection_address[:12])
    collection_link.short_description = "Collection"

    def nft_link(self, obj):
        url = reverse('admin:nft_data_nft_change', args=[obj.nft_mint])
        return format_html('<a href="{}">{}...</a>', url, obj.nft_mint[:12])
    nft_link.short_description = "NFT Mint"


@admin.register(CollectionMarketStats, site=admin_site)
class CollectionMarketStatsAdmin(admin.ModelAdmin):
    """
    Admin view for the RAW, unprocessed market stats from each source.
    """
    list_display = ('collection_link', 'source', 'timestamp', 'floor_price', 'volume_24h', 'listed_count')
    list_filter = ('source', 'timestamp')
    search_fields = ('collection__name', 'collection__address')
    readonly_fields = [f.name for f in CollectionMarketStats._meta.fields] # Make all fields read-only

    def collection_link(self, obj):
        return admin_link(obj, 'collection')
    collection_link.short_description = "Collection"


@admin.register(FailedTransaction, site=admin_site)
class FailedTransactionAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'error_message', 'retry_count', 'last_retry', 'created_at')
    list_filter = ('retry_count', 'last_retry')
    search_fields = ('event_id', 'error_message')
    readonly_fields = ('event_id', 'event_data', 'error_message', 'retry_count', 'last_retry')
    # Your actions like 'retry_transactions' would remain here.

# Register other simple, read-only indexer models
admin_site.register(TraitEvent)
admin_site.register(BurnEvent)
admin_site.register(MarketplaceIdentifier)