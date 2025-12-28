from django.contrib import admin
from django.utils.html import format_html
from traitkeeper.admin_site import admin_site
from .models import AnomalyDetection

@admin.register(AnomalyDetection, site=admin_site)
class AnomalyDetectionAdmin(admin.ModelAdmin):
    """Admin for viewing detected anomalies (wash trading, bot activity, etc.)"""
    list_display = (
        'anomaly_id_display',
        'anomaly_type_badge',
        'severity_badge',
        'collection_or_wallet',
        'anomaly_score_display',
        'investigation_status',
        'first_detected'
    )
    list_filter = ('anomaly_type', 'severity', 'investigation_status', 'human_validated')
    search_fields = ('anomaly_id', 'wallet_address', 'collection__name', 'pattern_description')
    readonly_fields = ('anomaly_id', 'first_detected', 'last_updated')

    fieldsets = (
        ('Detection', {
            'fields': ('anomaly_id', 'anomaly_type', 'severity', 'detection_algorithm')
        }),
        ('Target', {
            'fields': ('collection', 'wallet_address')
        }),
        ('Analysis', {
            'fields': ('anomaly_score', 'deviation_from_norm', 'pattern_description', 'potential_causes')
        }),
        ('Evidence', {
            'fields': ('detected_value', 'baseline_value', 'contributing_features')
        }),
        ('Related Data', {
            'fields': ('related_transactions', 'related_wallets', 'related_nfts'),
            'classes': ('collapse',)
        }),
        ('Investigation', {
            'fields': ('investigation_status', 'human_validated', 'validation_result')
        }),
        ('Timestamps', {
            'fields': ('analysis_window_start', 'analysis_window_end', 'first_detected', 'last_updated'),
            'classes': ('collapse',)
        }),
    )

    actions = ['mark_investigating', 'mark_resolved', 'create_blacklist_from_anomaly']

    def anomaly_id_display(self, obj):
        return obj.anomaly_id[:16] + "..."
    anomaly_id_display.short_description = 'ID'

    def anomaly_type_badge(self, obj):
        colors = {
            'wash_trading': '#dc3545',
            'bot_activity': '#fd7e14',
            'manipulation_signal': '#dc3545',
            'whale_activity': '#007bff',
        }
        color = colors.get(obj.anomaly_type, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_anomaly_type_display()
        )
    anomaly_type_badge.short_description = 'Type'

    def severity_badge(self, obj):
        colors = {'critical': 'red', 'high': 'orange', 'medium': '#ffc107', 'low': 'green'}
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.severity), obj.get_severity_display().upper()
        )
    severity_badge.short_description = 'Severity'

    def collection_or_wallet(self, obj):
        if obj.collection:
            return f"Collection: {obj.collection.name}"
        elif obj.wallet_address:
            return f"Wallet: {obj.wallet_address[:8]}..."
        return "N/A"
    collection_or_wallet.short_description = 'Target'

    def anomaly_score_display(self, obj):
        score = obj.anomaly_score
        color = 'red' if score >= 0.75 else 'orange' if score >= 0.5 else '#ffc107'
        return format_html('<span style="color: {}; font-weight: bold;">{:.2f}</span>', color, score)
    anomaly_score_display.short_description = 'Score'

    @admin.action(description="🔍 Mark as investigating")
    def mark_investigating(self, request, queryset):
        updated = queryset.update(investigation_status='investigating')
        self.message_user(request, f"{updated} anomaly(ies) marked as investigating.")

    @admin.action(description="✓ Mark as resolved")
    def mark_resolved(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(investigation_status='resolved', resolved_at=timezone.now())
        self.message_user(request, f"{updated} anomaly(ies) resolved.")

    @admin.action(description="🚫 Create blacklist from anomaly")
    def create_blacklist_from_anomaly(self, request, queryset):
        """Create blacklist entries from detected anomalies"""
        from analytics.models import BlacklistedWallet, BlacklistedCollection

        created_wallets = 0
        created_collections = 0

        for anomaly in queryset:
            # Blacklist wallet if wash trading or bot activity
            if anomaly.wallet_address and anomaly.anomaly_type in ['wash_trading', 'bot_activity']:
                _, created = BlacklistedWallet.objects.get_or_create(
                    wallet_address=anomaly.wallet_address,
                    defaults={
                        'reason': 'wash_trading' if anomaly.anomaly_type == 'wash_trading' else 'bot_listing',
                        'status': 'monitoring',
                        'detection_method': 'automatic',
                        'manipulation_score': anomaly.anomaly_score * 100,
                        'suspicious_patterns': anomaly.detected_value,
                        'reviewer_notes': f"Auto-created from Axplorer anomaly: {anomaly.pattern_description}"
                    }
                )
                if created:
                    created_wallets += 1

            # Blacklist collection if collection-wide issue
            if anomaly.collection and anomaly.severity in ['critical', 'high']:
                _, created = BlacklistedCollection.objects.get_or_create(
                    collection=anomaly.collection,
                    defaults={
                        'reason': 'wash_trading_collection',
                        'status': 'monitoring',
                        'detection_method': 'automatic',
                        'risk_score': anomaly.anomaly_score * 100,
                        'evidence_data': anomaly.detected_value,
                        'reviewer_notes': f"Auto-created from Axplorer anomaly: {anomaly.pattern_description}"
                    }
                )
                if created:
                    created_collections += 1

        self.message_user(
            request,
            f"Created {created_wallets} wallet blacklist(s) and {created_collections} collection blacklist(s)."
        )
