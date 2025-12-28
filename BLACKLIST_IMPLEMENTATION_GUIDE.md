# 🚫 BLACKLIST SYSTEM - COMPLETE IMPLEMENTATION GUIDE

## ✅ COMPLETED

1. **Axplorer Activated** - Added to INSTALLED_APPS in settings.py
2. **BlacklistedWallet Model** - Created with full admin interface
3. **BlacklistedCollection Model** - Created (admin interface needed)
4. **WalletSuspiciousActivity Model** - Audit trail for suspicious activities

---

## 📋 TODO - REMAINING TASKS

### 1. Add BlacklistedCollection Admin (analytics/admin.py)

Add this at the end of analytics/admin.py (before the last line):

```python
@admin.register(BlacklistedCollection, site=admin_site)
class BlacklistedCollectionAdmin(admin.ModelAdmin):
    """Admin interface for blacklisting entire collections"""
    list_display = (
        'collection_name_link',
        'status_badge',
        'reason',
        'risk_score_display',
        'hide_from_listings',
        'blacklisted_at'
    )
    list_filter = ('status', 'reason', 'hide_from_listings', 'show_warning')
    search_fields = ('collection__name', 'collection__address', 'reviewer_notes')
    readonly_fields = ('first_detected', 'blacklisted_at', 'cleared_at')

    fieldsets = (
        ('Collection', {
            'fields': ('collection', 'status', 'reason')
        }),
        ('Risk Assessment', {
            'fields': ('detection_method', 'risk_score', 'evidence_data')
        }),
        ('Display Options', {
            'fields': ('hide_from_listings', 'show_warning')
        }),
        ('Review', {
            'fields': ('reviewer_notes', 'reviewed_by')
        }),
        ('Timestamps', {
            'fields': ('first_detected', 'blacklisted_at', 'cleared_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['activate_blacklist', 'move_to_monitoring', 'clear_blacklist']

    def collection_name_link(self, obj):
        return admin_link(obj, 'collection')
    collection_name_link.short_description = 'Collection'

    def status_badge(self, obj):
        colors = {'active': 'red', 'monitoring': 'orange', 'cleared': 'green'}
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def risk_score_display(self, obj):
        score = obj.risk_score
        color = 'red' if score >= 75 else 'orange' if score >= 50 else '#ffc107' if score >= 25 else 'green'
        return format_html('<span style="color: {}; font-weight: bold;">{:.1f}/100</span>', color, score)
    risk_score_display.short_description = 'Risk Score'

    @admin.action(description="🔴 Activate blacklist")
    def activate_blacklist(self, request, queryset):
        updated = queryset.update(status='active')
        self.message_user(request, f"{updated} collection(s) blacklisted.")

    @admin.action(description="🟠 Move to monitoring")
    def move_to_monitoring(self, request, queryset):
        updated = queryset.update(status='monitoring')
        self.message_user(request, f"{updated} collection(s) moved to monitoring.")

    @admin.action(description="🟢 Clear blacklist")
    def clear_blacklist(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status='cleared', cleared_at=timezone.now())
        self.message_user(request, f"{updated} collection(s) cleared.")
```

---

### 2. Run Migrations

```bash
python manage.py makemigrations analytics
python manage.py makemigrations axplorer
python manage.py migrate
```

---

### 3. Update Market Aggregation to Exclude Blacklisted (analytics/services/market_aggregation.py)

Add this helper method to MarketAggregationService class:

```python
async def _get_blacklisted_wallets_and_collections(self):
    """Get lists of active blacklisted wallets and collections"""
    from analytics.models import BlacklistedWallet, BlacklistedCollection

    blacklisted_wallets = await sync_to_async(list)(
        BlacklistedWallet.objects.filter(status='active').values_list('wallet_address', flat=True)
    )

    blacklisted_collections = await sync_to_async(list)(
        BlacklistedCollection.objects.filter(status='active').values_list('collection_id', flat=True)
    )

    return set(blacklisted_wallets), set(blacklisted_collections)
```

Update holder calculation (line ~591):

```python
# Get blacklisted wallets
blacklisted_wallets, blacklisted_collections = await self._get_blacklisted_wallets_and_collections()

# Calculate number of unique holders (excluding burnt NFTs AND blacklisted wallets)
number_of_holders = await sync_to_async(
    collection.nfts.filter(is_burned=False)
    .exclude(owner__isnull=True)
    .exclude(owner__in=blacklisted_wallets)  # ← EXCLUDE BLACKLISTED
    .values('owner')
    .distinct()
    .count
)()
```

---

### 4. Create Axplorer Admin (axplorer/admin.py)

Create file `axplorer/admin.py`:

```python
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
```

---

### 5. Create Management Commands

Create `analytics/management/commands/blacklist_wallet.py`:

```python
from django.core.management.base import BaseCommand
from analytics.models import BlacklistedWallet

class Command(BaseCommand):
    help = 'Blacklist a wallet address'

    def add_arguments(self, parser):
        parser.add_argument('wallet_address', type=str)
        parser.add_argument('--reason', type=str, default='manual_review')
        parser.add_argument('--status', type=str, default='monitoring', choices=['active', 'monitoring'])

    def handle(self, *args, **options):
        wallet, created = BlacklistedWallet.objects.get_or_create(
            wallet_address=options['wallet_address'],
            defaults={
                'reason': options['reason'],
                'status': options['status'],
                'detection_method': 'manual',
                'manipulation_score': 0,
                'reviewer_notes': 'Created via management command'
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'Blacklisted {options["wallet_address"]} with status: {options["status"]}'))
        else:
            self.stdout.write(self.style.WARNING(f'Wallet {options["wallet_address"]} already blacklisted'))
```

---

## 🎯 USAGE FROM ADMIN PANEL

### Blacklist a Wallet:
1. Go to Admin → Analytics → Blacklisted Wallets
2. Click "Add Blacklisted Wallet"
3. Enter wallet address & reason
4. Set status: `monitoring` (track) or `active` (exclude)
5. Save

### Blacklist a Collection:
1. Go to Admin → Analytics → Blacklisted Collections
2. Click "Add Blacklisted Collection"
3. Select collection from dropdown
4. Choose reason (scam, rug pull, etc.)
5. Set status: `active` to hide from listings
6. Save

### Review Anomalies (Axplorer):
1. Go to Admin → Axplorer → Anomaly Detection
2. Review detected wash trading / bot activity
3. Click "Create blacklist from anomaly" action
4. Auto-creates wallet/collection blacklists

---

## 🔧 QUICK COMMANDS

```bash
# Run migrations
python manage.py makemigrations
python manage.py migrate

# Blacklist a wallet
python manage.py blacklist_wallet ABC123... --reason bot_listing --status active

# Check blacklisted count
python manage.py shell
>>> from analytics.models import BlacklistedWallet, BlacklistedCollection
>>> BlacklistedWallet.objects.filter(status='active').count()
>>> BlacklistedCollection.objects.filter(status='active').count()
```

---

## ✅ TESTING CHECKLIST

- [ ] Migrations run successfully
- [ ] BlacklistedWallet admin visible & functional
- [ ] BlacklistedCollection admin visible & functional
- [ ] WalletSuspiciousActivity admin works
- [ ] Axplorer AnomalyDetection admin works
- [ ] Blacklist actions work (activate/monitor/clear)
- [ ] Calculations exclude blacklisted wallets
- [ ] Collections hidden when blacklisted
- [ ] Management commands work

---

All systems ready! Just need to:
1. Add BlacklistedCollection admin code above
2. Run migrations
3. Create axplorer/admin.py
4. Test!
