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
    BlacklistedWallet,
    BlacklistedCollection,
    WalletSuspiciousActivity,
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


# ===================================================================
# Wallet Blacklist Admin Views
# ===================================================================

@admin.register(BlacklistedWallet, site=admin_site)
class BlacklistedWalletAdmin(admin.ModelAdmin):
    """
    Admin interface for managing blacklisted wallets.
    Allows manual blacklisting and review of automatically detected bot wallets.
    """
    list_display = (
        'wallet_address_display',
        'status_badge',
        'reason',
        'manipulation_score_display',
        'detection_method',
        'suspicious_tx_ratio',
        'blacklisted_at'
    )
    list_filter = ('status', 'reason', 'detection_method', 'blacklisted_at')
    search_fields = ('wallet_address', 'reviewer_notes')
    readonly_fields = (
        'first_detected',
        'last_activity_detected',
        'blacklisted_at',
        'cleared_at',
        'total_transactions_analyzed',
        'suspicious_transaction_count'
    )
    filter_horizontal = ('affected_collections',)

    fieldsets = (
        ('Wallet Information', {
            'fields': ('wallet_address', 'status', 'reason')
        }),
        ('Detection Details', {
            'fields': ('detection_method', 'manipulation_score', 'suspicious_patterns')
        }),
        ('Activity Summary', {
            'fields': (
                'total_transactions_analyzed',
                'suspicious_transaction_count',
                'affected_collections'
            )
        }),
        ('Review', {
            'fields': ('reviewer_notes', 'reviewed_by', 'auto_clear_after_days')
        }),
        ('Timestamps', {
            'fields': ('first_detected', 'last_activity_detected', 'blacklisted_at', 'cleared_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['activate_blacklist', 'move_to_monitoring', 'clear_blacklist']

    def wallet_address_display(self, obj):
        """Display shortened wallet address with copy icon"""
        short_addr = f"{obj.wallet_address[:6]}...{obj.wallet_address[-4:]}"
        return format_html(
            '<span title="{}">{}</span>',
            obj.wallet_address,
            short_addr
        )
    wallet_address_display.short_description = 'Wallet'

    def status_badge(self, obj):
        """Color-coded status badge"""
        colors = {
            'active': 'red',
            'monitoring': 'orange',
            'cleared': 'green'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def manipulation_score_display(self, obj):
        """Color-coded manipulation score"""
        score = obj.manipulation_score
        if score >= 75:
            color = 'red'
        elif score >= 50:
            color = 'orange'
        elif score >= 25:
            color = '#ffc107'  # Yellow
        else:
            color = 'green'

        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}/100</span>',
            color,
            score
        )
    manipulation_score_display.short_description = 'Manipulation Score'

    def suspicious_tx_ratio(self, obj):
        """Display percentage of suspicious transactions"""
        if obj.total_transactions_analyzed == 0:
            return "N/A"
        ratio = (obj.suspicious_transaction_count / obj.total_transactions_analyzed) * 100
        return f"{ratio:.1f}%"
    suspicious_tx_ratio.short_description = 'Suspicious TX %'

    # Admin actions
    @admin.action(description="🔴 Activate blacklist (exclude from calculations)")
    def activate_blacklist(self, request, queryset):
        updated = queryset.update(status='active')
        self.message_user(request, f"{updated} wallet(s) moved to ACTIVE blacklist status.")

    @admin.action(description="🟠 Move to monitoring (track but don't exclude)")
    def move_to_monitoring(self, request, queryset):
        updated = queryset.update(status='monitoring')
        self.message_user(request, f"{updated} wallet(s) moved to MONITORING status.")

    @admin.action(description="🟢 Clear blacklist (remove restrictions)")
    def clear_blacklist(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status='cleared', cleared_at=timezone.now())
        self.message_user(request, f"{updated} wallet(s) CLEARED from blacklist.")


@admin.register(WalletSuspiciousActivity, site=admin_site)
class WalletSuspiciousActivityAdmin(admin.ModelAdmin):
    """
    Admin interface for reviewing individual suspicious wallet activities.
    Used to build evidence for blacklisting decisions.
    """
    list_display = (
        'wallet_address_display',
        'activity_type_badge',
        'collection_link',
        'severity_display',
        'confidence_display',
        'reviewed_status',
        'detected_at'
    )
    list_filter = (
        'activity_type',
        'reviewed',
        'false_positive',
        'collection',
        'detected_at'
    )
    search_fields = ('wallet_address', 'pattern_description')
    readonly_fields = ('detected_at',)

    fieldsets = (
        ('Activity Details', {
            'fields': ('wallet_address', 'blacklisted_wallet', 'activity_type', 'collection')
        }),
        ('Detection Metrics', {
            'fields': ('severity_score', 'confidence_score', 'pattern_description')
        }),
        ('Evidence', {
            'fields': ('transaction_signatures', 'evidence_data', 'time_window_start', 'time_window_end')
        }),
        ('Review Status', {
            'fields': ('reviewed', 'false_positive')
        }),
        ('Metadata', {
            'fields': ('detected_at',),
            'classes': ('collapse',)
        }),
    )

    actions = ['mark_as_reviewed', 'mark_as_false_positive', 'create_blacklist_entry']

    def wallet_address_display(self, obj):
        """Display shortened wallet address"""
        short_addr = f"{obj.wallet_address[:6]}...{obj.wallet_address[-4:]}"
        if obj.blacklisted_wallet:
            return format_html(
                '<span title="{}" style="color: red; font-weight: bold;">{} ⚠️</span>',
                obj.wallet_address,
                short_addr
            )
        return format_html('<span title="{}">{}</span>', obj.wallet_address, short_addr)
    wallet_address_display.short_description = 'Wallet'

    def activity_type_badge(self, obj):
        """Color-coded activity type"""
        return format_html(
            '<span style="background-color: #dc3545; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
            obj.get_activity_type_display()
        )
    activity_type_badge.short_description = 'Activity'

    def collection_link(self, obj):
        return admin_link(obj, 'collection')
    collection_link.short_description = 'Collection'

    def severity_display(self, obj):
        """Color-coded severity score"""
        score = obj.severity_score
        if score >= 75:
            color = 'red'
        elif score >= 50:
            color = 'orange'
        else:
            color = '#ffc107'
        return format_html('<span style="color: {}; font-weight: bold;">{:.1f}</span>', color, score)
    severity_display.short_description = 'Severity'

    def confidence_display(self, obj):
        """Display confidence as percentage"""
        return f"{obj.confidence_score * 100:.0f}%"
    confidence_display.short_description = 'Confidence'

    def reviewed_status(self, obj):
        """Display review status with icon"""
        if obj.false_positive:
            return format_html('<span style="color: green;">✓ False Positive</span>')
        elif obj.reviewed:
            return format_html('<span style="color: blue;">✓ Reviewed</span>')
        else:
            return format_html('<span style="color: red;">⏳ Pending Review</span>')
    reviewed_status.short_description = 'Review Status'

    # Admin actions
    @admin.action(description="✓ Mark as reviewed")
    def mark_as_reviewed(self, request, queryset):
        updated = queryset.update(reviewed=True)
        self.message_user(request, f"{updated} activity(ies) marked as reviewed.")

    @admin.action(description="✗ Mark as false positive")
    def mark_as_false_positive(self, request, queryset):
        updated = queryset.update(reviewed=True, false_positive=True)
        self.message_user(request, f"{updated} activity(ies) marked as false positive.")

    @admin.action(description="🚫 Create blacklist entry from selected")
    def create_blacklist_entry(self, request, queryset):
        """Create blacklist entries for wallets with suspicious activities"""
        from django.utils import timezone

        created_count = 0
        for activity in queryset:
            # Only process if not already reviewed as false positive
            if not activity.false_positive:
                blacklist, created = BlacklistedWallet.objects.get_or_create(
                    wallet_address=activity.wallet_address,
                    defaults={
                        'reason': 'bot_listing' if 'listing' in activity.activity_type else 'wash_trading',
                        'status': 'monitoring',  # Start with monitoring
                        'detection_method': 'automatic',
                        'manipulation_score': activity.severity_score,
                        'total_transactions_analyzed': 1,
                        'suspicious_transaction_count': 1,
                        'suspicious_patterns': activity.evidence_data,
                        'reviewer_notes': f"Auto-created from suspicious activity: {activity.pattern_description}"
                    }
                )

                if created:
                    created_count += 1
                    # Link the activity to the blacklist entry
                    activity.blacklisted_wallet = blacklist
                    activity.save()
                    # Add affected collection
                    blacklist.affected_collections.add(activity.collection)

        self.message_user(request, f"{created_count} new blacklist entry(ies) created (status: monitoring).")