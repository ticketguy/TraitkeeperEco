from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Avg
from django.urls import reverse
from django.utils.safestring import mark_safe
from traitkeeper.admin_site import admin_site
from .models import (
    AnomalyDetection,
    MarketAlert,
    AnalyticsSnapshot,
    AnalyticsUsage,
    MarketRegime,
    AdvancedCrossMarketplaceAnalysis,
    PredictionRecord,
)


# ==================== ANOMALY DETECTION ADMIN ====================

@admin.register(AnomalyDetection, site=admin_site)
class AnomalyDetectionAdmin(admin.ModelAdmin):
    """
    Admin interface for anomaly detection with color-coded badges and bulk actions.
    Integrates with the blacklist system for wallet/collection management.
    """

    list_display = (
        'anomaly_id_display',
        'anomaly_type_badge',
        'severity_badge',
        'collection_or_wallet',
        'anomaly_score_display',
        'investigation_status_badge',
        'first_detected',
        'detection_algorithm',
    )

    list_filter = (
        'anomaly_type',
        'severity',
        'investigation_status',
        'detection_algorithm',
        'human_validated',
        'validation_result',
        'first_detected',
    )

    search_fields = (
        'anomaly_id',
        'wallet_address',
        'collection__name',
        'collection__collection_id',
        'pattern_description',
    )

    readonly_fields = (
        'anomaly_id',
        'first_detected',
        'last_updated',
        'detection_details_display',
        'impact_metrics_display',
        'related_data_display',
    )

    fieldsets = (
        ('Anomaly Identification', {
            'fields': (
                'anomaly_id',
                'anomaly_type',
                'severity',
                'collection',
                'wallet_address',
            )
        }),
        ('Detection Details', {
            'fields': (
                'anomaly_score',
                'deviation_from_norm',
                'detection_algorithm',
                'pattern_description',
                'potential_causes',
                'contributing_features',
                'detection_details_display',
            )
        }),
        ('Analysis Window', {
            'fields': (
                'analysis_window_start',
                'analysis_window_end',
                'detected_value',
                'baseline_value',
            )
        }),
        ('Impact Assessment', {
            'fields': (
                'market_impact_score',
                'price_impact',
                'volume_impact',
                'triggered_other_anomalies',
                'contagion_score',
                'impact_metrics_display',
            )
        }),
        ('Investigation & Validation', {
            'fields': (
                'investigation_status',
                'human_validated',
                'validation_result',
                'alert_generated',
                'alert_acknowledged',
            )
        }),
        ('Related Data', {
            'fields': (
                'related_transactions',
                'related_wallets',
                'related_nfts',
                'related_data_display',
            ),
            'classes': ('collapse',)
        }),
        ('ML Feedback', {
            'fields': (
                'model_feedback',
                'false_positive_reasons',
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': (
                'first_detected',
                'last_updated',
                'resolved_at',
                'detection_system_version',
            )
        }),
    )

    actions = [
        'mark_investigating',
        'mark_resolved',
        'mark_dismissed',
        'create_blacklist_from_anomaly',
        'generate_alert',
        'mark_false_positive',
    ]

    date_hierarchy = 'first_detected'

    def anomaly_id_display(self, obj):
        """Display anomaly ID with icon."""
        return format_html(
            '<span style="font-family: monospace; font-size: 0.9em;">🔍 {}</span>',
            obj.anomaly_id
        )
    anomaly_id_display.short_description = 'Anomaly ID'
    anomaly_id_display.admin_order_field = 'anomaly_id'

    def anomaly_type_badge(self, obj):
        """Display anomaly type with color-coded badge."""
        type_colors = {
            'price_anomaly': '#FF6B6B',
            'volume_anomaly': '#4ECDC4',
            'wash_trading': '#FF3838',
            'bot_activity': '#FFA726',
            'manipulation_signal': '#D32F2F',
            'whale_activity': '#1976D2',
            'activity_anomaly': '#66BB6A',
            'liquidity_anomaly': '#AB47BC',
            'behavioral_anomaly': '#FDD835',
            'cross_platform_anomaly': '#8D6E63',
        }
        color = type_colors.get(obj.anomaly_type, '#757575')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 0.85em; font-weight: 500;">{}</span>',
            color,
            obj.get_anomaly_type_display()
        )
    anomaly_type_badge.short_description = 'Type'
    anomaly_type_badge.admin_order_field = 'anomaly_type'

    def severity_badge(self, obj):
        """Display severity with color-coded badge."""
        severity_colors = {
            'low': '#4CAF50',
            'medium': '#FF9800',
            'high': '#FF5722',
            'critical': '#D32F2F',
        }
        color = severity_colors.get(obj.severity, '#757575')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 0.85em; font-weight: 600; text-transform: uppercase;">{}</span>',
            color,
            obj.severity
        )
    severity_badge.short_description = 'Severity'
    severity_badge.admin_order_field = 'severity'

    def collection_or_wallet(self, obj):
        """Display collection or wallet address."""
        if obj.collection:
            collection_url = reverse('admin:nft_data_nftcollection_change', args=[obj.collection.pk])
            return format_html(
                '<a href="{}" style="color: #1976D2; text-decoration: none;">📦 {}</a>',
                collection_url,
                obj.collection.name
            )
        elif obj.wallet_address:
            return format_html(
                '<span style="font-family: monospace; font-size: 0.85em;">💼 {}...{}</span>',
                obj.wallet_address[:6],
                obj.wallet_address[-4:]
            )
        return format_html('<span style="color: #999;">N/A</span>')
    collection_or_wallet.short_description = 'Target'

    def anomaly_score_display(self, obj):
        """Display anomaly score with visual indicator."""
        score_pct = int(obj.anomaly_score * 100)
        if score_pct >= 80:
            color = '#D32F2F'
        elif score_pct >= 60:
            color = '#FF5722'
        elif score_pct >= 40:
            color = '#FF9800'
        else:
            color = '#4CAF50'

        return format_html(
            '<div style="display: flex; align-items: center; gap: 8px;">'
            '<div style="width: 60px; height: 8px; background: #e0e0e0; border-radius: 4px; overflow: hidden;">'
            '<div style="width: {}%; height: 100%; background: {};"></div>'
            '</div>'
            '<span style="font-weight: 600; color: {};">{:.1f}%</span>'
            '</div>',
            score_pct, color, color, score_pct
        )
    anomaly_score_display.short_description = 'Score'
    anomaly_score_display.admin_order_field = 'anomaly_score'

    def investigation_status_badge(self, obj):
        """Display investigation status with color-coded badge."""
        status_config = {
            'new': ('#2196F3', '🆕'),
            'investigating': ('#FF9800', '🔬'),
            'resolved': ('#4CAF50', '✅'),
            'dismissed': ('#9E9E9E', '❌'),
            'escalated': ('#D32F2F', '⚠️'),
        }
        color, icon = status_config.get(obj.investigation_status, ('#757575', ''))
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 0.85em;">{} {}</span>',
            color,
            icon,
            obj.get_investigation_status_display()
        )
    investigation_status_badge.short_description = 'Status'
    investigation_status_badge.admin_order_field = 'investigation_status'

    def detection_details_display(self, obj):
        """Display detailed detection information."""
        html = '<div style="font-family: monospace; font-size: 0.9em;">'
        html += f'<strong>Deviation:</strong> {obj.deviation_from_norm:.2f}σ<br>'
        html += f'<strong>Algorithm:</strong> {obj.get_detection_algorithm_display()}<br>'
        if obj.contributing_features:
            html += '<strong>Top Contributing Features:</strong><ul style="margin: 5px 0; padding-left: 20px;">'
            for feature, value in list(obj.contributing_features.items())[:5]:
                html += f'<li>{feature}: {value}</li>'
            html += '</ul>'
        html += '</div>'
        return mark_safe(html)
    detection_details_display.short_description = 'Detection Details'

    def impact_metrics_display(self, obj):
        """Display impact metrics."""
        html = '<div style="font-family: monospace; font-size: 0.9em;">'
        html += f'<strong>Market Impact:</strong> {obj.market_impact_score * 100:.1f}%<br>'
        html += f'<strong>Price Impact:</strong> {obj.price_impact:+.2f}%<br>'
        html += f'<strong>Volume Impact:</strong> {obj.volume_impact:+.2f}%<br>'
        html += f'<strong>Contagion:</strong> {obj.contagion_score * 100:.1f}%<br>'
        if obj.triggered_other_anomalies:
            html += '<strong style="color: #D32F2F;">⚠️ Triggered other anomalies</strong>'
        html += '</div>'
        return mark_safe(html)
    impact_metrics_display.short_description = 'Impact Metrics'

    def related_data_display(self, obj):
        """Display related data in a formatted way."""
        html = '<div style="font-family: monospace; font-size: 0.85em;">'

        if obj.related_wallets:
            html += f'<strong>Related Wallets:</strong> {len(obj.related_wallets)}<br>'

        if obj.related_transactions:
            html += f'<strong>Related Transactions:</strong> {len(obj.related_transactions)}<br>'

        if obj.related_nfts:
            html += f'<strong>Related NFTs:</strong> {len(obj.related_nfts)}<br>'

        if obj.alert_recipients:
            html += f'<strong>Alert Recipients:</strong> {len(obj.alert_recipients)}<br>'

        html += '</div>'
        return mark_safe(html)
    related_data_display.short_description = 'Related Data Summary'

    # Bulk Actions

    @admin.action(description='Mark as investigating')
    def mark_investigating(self, request, queryset):
        """Mark selected anomalies as under investigation."""
        updated = queryset.update(investigation_status='investigating')
        self.message_user(request, f'✓ Marked {updated} anomalies as investigating')

    @admin.action(description='Mark as resolved')
    def mark_resolved(self, request, queryset):
        """Mark selected anomalies as resolved."""
        from django.utils import timezone
        updated = queryset.update(
            investigation_status='resolved',
            resolved_at=timezone.now()
        )
        self.message_user(request, f'✓ Resolved {updated} anomalies')

    @admin.action(description='Mark as dismissed')
    def mark_dismissed(self, request, queryset):
        """Mark selected anomalies as dismissed."""
        updated = queryset.update(investigation_status='dismissed')
        self.message_user(request, f'✓ Dismissed {updated} anomalies')

    @admin.action(description='Create blacklist from anomaly')
    def create_blacklist_from_anomaly(self, request, queryset):
        """Create blacklist entries from anomalies."""
        from analytics.models import BlacklistedWallet, BlacklistedCollection

        wallets_created = 0
        collections_created = 0

        for anomaly in queryset:
            # Map anomaly type to blacklist reason
            reason_map = {
                'wash_trading': 'wash_trading',
                'bot_activity': 'bot_listing',
                'manipulation_signal': 'price_manipulation',
                'whale_activity': 'coordinated_pumping',
            }
            reason = reason_map.get(anomaly.anomaly_type, 'manual_review')

            # Create wallet blacklist if wallet is involved
            if anomaly.wallet_address and anomaly.anomaly_type in reason_map:
                wallet, created = BlacklistedWallet.objects.get_or_create(
                    wallet_address=anomaly.wallet_address,
                    defaults={
                        'reason': reason,
                        'status': 'monitoring',
                        'detection_method': 'automated',
                        'manipulation_score': anomaly.anomaly_score * 100,
                        'reviewer_notes': f'Auto-created from anomaly: {anomaly.anomaly_id}\n{anomaly.pattern_description}'
                    }
                )
                if created:
                    wallets_created += 1

            # Create collection blacklist for severe collection-level anomalies
            if anomaly.collection and anomaly.severity in ['high', 'critical']:
                collection, created = BlacklistedCollection.objects.get_or_create(
                    collection_id=anomaly.collection.collection_id,
                    defaults={
                        'reason': 'suspicious_activity',
                        'status': 'monitoring',
                        'detection_method': 'automated',
                        'severity_score': anomaly.anomaly_score * 100,
                        'notes': f'Auto-created from anomaly: {anomaly.anomaly_id}\n{anomaly.pattern_description}'
                    }
                )
                if created:
                    collections_created += 1

        msg = f'✓ Created {wallets_created} wallet blacklist entries and {collections_created} collection blacklist entries'
        self.message_user(request, msg)

    @admin.action(description='Generate alerts for anomalies')
    def generate_alert(self, request, queryset):
        """Generate alerts for selected anomalies."""
        updated = queryset.filter(alert_generated=False).update(alert_generated=True)
        self.message_user(request, f'✓ Generated alerts for {updated} anomalies')

    @admin.action(description='Mark as false positive')
    def mark_false_positive(self, request, queryset):
        """Mark selected anomalies as false positives."""
        updated = queryset.update(
            validation_result='false_positive',
            human_validated=True,
            investigation_status='dismissed'
        )
        self.message_user(request, f'✓ Marked {updated} anomalies as false positives')


# ==================== MARKET ALERT ADMIN ====================

@admin.register(MarketAlert, site=admin_site)
class MarketAlertAdmin(admin.ModelAdmin):
    """Admin interface for market alerts."""

    list_display = (
        'collection',
        'alert_type_badge',
        'severity_badge',
        'title',
        'is_active',
        'is_resolved',
        'views_count',
        'created_at',
    )

    list_filter = (
        'alert_type',
        'severity',
        'is_active',
        'is_resolved',
        'created_at',
    )

    search_fields = (
        'collection__name',
        'title',
        'message',
    )

    readonly_fields = ('created_at', 'resolved_at')

    def alert_type_badge(self, obj):
        """Display alert type with badge."""
        type_colors = {
            'price_spike': '#4CAF50',
            'price_drop': '#F44336',
            'volume_surge': '#2196F3',
            'supply_pressure': '#FF9800',
            'bid_activity': '#9C27B0',
            'arbitrage': '#00BCD4',
            'trend_reversal': '#FF5722',
        }
        color = type_colors.get(obj.alert_type, '#757575')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 0.85em;">{}</span>',
            color,
            obj.get_alert_type_display()
        )
    alert_type_badge.short_description = 'Type'

    def severity_badge(self, obj):
        """Display severity with badge."""
        colors = {'low': '#4CAF50', 'medium': '#FF9800', 'high': '#FF5722', 'critical': '#D32F2F'}
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 0.85em; text-transform: uppercase;">{}</span>',
            colors.get(obj.severity, '#757575'),
            obj.severity
        )
    severity_badge.short_description = 'Severity'


# ==================== ANALYTICS SNAPSHOT ADMIN ====================

@admin.register(AnalyticsSnapshot, site=admin_site)
class AnalyticsSnapshotAdmin(admin.ModelAdmin):
    """Admin interface for analytics snapshots."""

    list_display = (
        'collection',
        'snapshot_type',
        'floor_price',
        'volume_24h',
        'market_condition',
        'created_at',
    )

    list_filter = (
        'snapshot_type',
        'market_condition',
        'created_at',
    )

    search_fields = ('collection__name',)
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


# ==================== PREDICTION RECORD ADMIN ====================

@admin.register(PredictionRecord, site=admin_site)
class PredictionRecordAdmin(admin.ModelAdmin):
    """Admin interface for prediction tracking."""

    list_display = (
        'prediction_id',
        'prediction_type',
        'collection',
        'confidence_score_display',
        'status_badge',
        'accuracy_score_display',
        'created_at',
        'target_date',
    )

    list_filter = (
        'prediction_type',
        'status',
        'algorithm_type',
        'human_validation',
        'created_at',
    )

    search_fields = (
        'prediction_id',
        'collection__name',
        'model_name',
    )

    readonly_fields = (
        'prediction_id',
        'created_at',
        'evaluated_at',
    )

    def confidence_score_display(self, obj):
        """Display confidence with visual bar."""
        pct = int(obj.confidence_score * 100)
        color = '#4CAF50' if pct >= 70 else '#FF9800' if pct >= 50 else '#F44336'
        return format_html(
            '<span style="color: {}; font-weight: 600;">{:.0f}%</span>',
            color, pct
        )
    confidence_score_display.short_description = 'Confidence'

    def status_badge(self, obj):
        """Display status with badge."""
        colors = {
            'pending': '#2196F3',
            'correct': '#4CAF50',
            'incorrect': '#F44336',
            'partially_correct': '#FF9800',
            'expired': '#9E9E9E',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 0.85em;">{}</span>',
            colors.get(obj.status, '#757575'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def accuracy_score_display(self, obj):
        """Display accuracy if evaluated."""
        if obj.accuracy_score is not None:
            pct = int(obj.accuracy_score * 100)
            color = '#4CAF50' if pct >= 70 else '#FF9800' if pct >= 50 else '#F44336'
            return format_html(
                '<span style="color: {}; font-weight: 600;">{:.0f}%</span>',
                color, pct
            )
        return format_html('<span style="color: #999;">N/A</span>')
    accuracy_score_display.short_description = 'Accuracy'
