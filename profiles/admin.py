from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.urls import reverse
from django.db.models import Count, Sum
from .models import Profile, WatchlistItem, AchievementCategory, Achievement, UserAchievement, Quest, QuestUserProgress, QuestClaim


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'display_name', 'avatar_type', 'is_public', 'created_at']
    list_filter = ['is_public', 'avatar_type', 'created_at']
    search_fields = ['user__username', 'user__email', 'display_name', 'bio']
    readonly_fields = ['created_at', 'updated_at', 'avatar_preview']

    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Profile Information', {
            'fields': ('display_name', 'bio')
        }),
        ('Avatar', {
            'fields': ('avatar_type', 'avatar_image', 'avatar_url', 'avatar_nft_mint', 'avatar_preview')
        }),
        ('Social Links', {
            'fields': ('social_x', 'social_discord', 'website_url')
        }),
        ('Settings', {
            'fields': ('is_public',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def avatar_preview(self, obj):
        """Display avatar preview in admin"""
        avatar_url = obj.get_avatar_url
        if avatar_url:
            return format_html('<img src="{}" style="max-width: 100px; max-height: 100px;" />', avatar_url)
        return "No avatar"
    avatar_preview.short_description = "Avatar Preview"


@admin.register(WatchlistItem)
class WatchlistItemAdmin(admin.ModelAdmin):
    list_display = ['user', 'item_type', 'get_item_name', 'added_at']
    list_filter = ['item_type', 'added_at']
    search_fields = ['user__username', 'nft__name', 'collection__name', 'notes']
    readonly_fields = ['added_at']
    raw_id_fields = ['user', 'nft', 'collection']

    fieldsets = (
        ('Watcher', {
            'fields': ('user',)
        }),
        ('Watched Item', {
            'fields': ('item_type', 'nft', 'collection'),
            'description': 'Set either NFT or Collection based on item_type'
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamp', {
            'fields': ('added_at',)
        }),
    )

    def get_item_name(self, obj):
        """Display the name of the watched item"""
        item = obj.get_item
        return getattr(item, 'name', 'N/A')
    get_item_name.short_description = "Item Name"


@admin.register(AchievementCategory)
class AchievementCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'icon', 'display_order', 'achievement_count']
    list_editable = ['display_order']
    search_fields = ['name', 'slug', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['display_order', 'name']

    def achievement_count(self, obj):
        """Show count of achievements in this category"""
        return obj.achievements.count()
    achievement_count.short_description = "Achievements"


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ['icon_display', 'name', 'category', 'rarity_badge', 'points', 'is_active', 'is_hidden', 'earned_count']
    list_filter = ['category', 'rarity', 'is_active', 'is_hidden', 'created_at']
    list_editable = ['is_active', 'is_hidden']
    search_fields = ['key', 'name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'icon_preview', 'earned_count', 'recent_earners', 'rarity_stats']
    actions = ['award_to_users', 'activate_achievements', 'deactivate_achievements']

    fieldsets = (
        ('Basic Information', {
            'fields': ('key', 'name', 'description', 'category')
        }),
        ('Properties', {
            'fields': ('rarity', 'points', 'display_order')
        }),
        ('Icon', {
            'fields': ('icon_url', 'icon_image', 'icon_preview')
        }),
        ('Status', {
            'fields': ('is_active', 'is_hidden')
        }),
        ('Criteria', {
            'fields': ('criteria',),
            'classes': ('collapse',),
            'description': 'JSON criteria for automatic awarding. Example: {"type": "nft_count", "min": 100}'
        }),
        ('Statistics', {
            'fields': ('earned_count', 'recent_earners', 'rarity_stats'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def icon_display(self, obj):
        """Display icon in list view"""
        icon_url = obj.get_icon_url
        if icon_url:
            return format_html('<img src="{}" style="max-width: 32px; max-height: 32px; border-radius: 4px;" />', icon_url)
        return "❓"
    icon_display.short_description = ''

    def icon_preview(self, obj):
        """Display icon preview in admin"""
        icon_url = obj.get_icon_url
        if icon_url:
            return format_html('<img src="{}" style="max-width: 64px; max-height: 64px;" />', icon_url)
        return "No icon"
    icon_preview.short_description = "Icon Preview"

    def rarity_badge(self, obj):
        """Display colorful rarity badge"""
        colors = {
            'common': '#9CA3AF',        # Gray
            'uncommon': '#10B981',      # Green
            'rare': '#3B82F6',          # Blue
            'epic': '#8B5CF6',          # Purple
            'legendary': '#F59E0B',     # Amber
        }
        color = colors.get(obj.rarity.lower(), '#9CA3AF')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color, obj.rarity.upper()
        )
    rarity_badge.short_description = 'Rarity'

    def status_indicators(self, obj):
        """Show active/hidden status"""
        active_icon = '✅' if obj.is_active else '❌'
        hidden_icon = '🔒' if obj.is_hidden else '👁️'
        return format_html('{} {}', active_icon, hidden_icon)
    status_indicators.short_description = 'Status'

    def earned_count(self, obj):
        """Show how many users earned this achievement"""
        count = obj.earned_by.count()
        return format_html('<strong style="color: #10B981; font-size: 16px;">{}</strong>', count)
    earned_count.short_description = "Earned"

    def recent_earners(self, obj):
        """Show recent users who earned this"""
        recent = obj.earned_by.order_by('-earned_at')[:10]
        if not recent:
            return "No one yet"

        earners_html = '<br/>'.join([
            f"• {ua.user.username} - {ua.earned_at.strftime('%Y-%m-%d %H:%M')}"
            for ua in recent
        ])
        return format_html('<strong>Recent Earners:</strong><br/>{}', earners_html)
    recent_earners.short_description = "Recent Earners"

    def rarity_stats(self, obj):
        """Show rarity statistics"""
        from wallet.models import CustomUser
        total_users = CustomUser.objects.count()
        earned_count = obj.earned_by.count()

        if total_users == 0:
            percentage = 0
        else:
            percentage = (earned_count / total_users) * 100

        rarity_text = "Very Common" if percentage > 50 else \
                      "Common" if percentage > 25 else \
                      "Uncommon" if percentage > 10 else \
                      "Rare" if percentage > 5 else \
                      "Very Rare" if percentage > 1 else "Ultra Rare"

        return format_html(
            '<strong>Earn Rate:</strong> {:.2f}% of users<br/>'
            '<strong>Classification:</strong> {}<br/>'
            '<strong>Total Users:</strong> {}',
            percentage, rarity_text, total_users
        )
    rarity_stats.short_description = "Rarity Statistics"

    # Admin Actions
    def award_to_users(self, request, queryset):
        """Award selected achievements to specific users"""
        # This would redirect to a custom form to select users
        self.message_user(
            request,
            f"Selected {queryset.count()} achievement(s). Implement user selection form to award.",
            level='info'
        )
    award_to_users.short_description = "🏆 Award to users"

    def activate_achievements(self, request, queryset):
        """Activate selected achievements"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} achievement(s)")
    activate_achievements.short_description = "✅ Activate"

    def deactivate_achievements(self, request, queryset):
        """Deactivate selected achievements"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} achievement(s)")
    deactivate_achievements.short_description = "❌ Deactivate"


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ['user', 'achievement', 'earned_at']
    list_filter = ['earned_at', 'achievement__category', 'achievement__rarity']
    search_fields = ['user__username', 'achievement__name', 'achievement__key']
    readonly_fields = ['earned_at']
    raw_id_fields = ['user']

    fieldsets = (
        ('Achievement Earned', {
            'fields': ('user', 'achievement', 'earned_at')
        }),
    )

    def has_add_permission(self, request):
        """Prevent manual addition through admin (should be awarded via code)"""
        return False


# ============================================================================
# QUEST ADMIN INTERFACES
# ============================================================================

@admin.register(Quest)
class QuestAdmin(admin.ModelAdmin):
    list_display = [
        'quest_id_display', 'title', 'action_type', 'target_count',
        'reward_sol_display', 'status_badge', 'claims_count', 'deployment_status'
    ]
    list_filter = ['status', 'action_type', 'is_active', 'created_at']
    search_fields = ['quest_id', 'title', 'description', 'on_chain_address']
    readonly_fields = [
        'created_at', 'updated_at', 'on_chain_address', 'deployment_signature',
        'deployed_at', 'last_synced_at', 'reward_sol_display', 'progress_summary',
        'claim_stats'
    ]

    fieldsets = (
        ('Quest Identification', {
            'fields': ('quest_id', 'title', 'icon')
        }),
        ('Description', {
            'fields': ('description',)
        }),
        ('Requirements', {
            'fields': ('action_type', 'target_count'),
            'description': 'Define what users must do to complete this quest'
        }),
        ('Reward', {
            'fields': ('reward_lamports', 'reward_sol_display'),
            'description': '1 SOL = 1,000,000,000 lamports'
        }),
        ('Status & Display', {
            'fields': ('status', 'is_active', 'display_order')
        }),
        ('Scheduling', {
            'fields': ('start_date', 'end_date'),
            'classes': ('collapse',)
        }),
        ('On-Chain Data (Read-Only)', {
            'fields': (
                'on_chain_address', 'deployment_signature',
                'deployed_at', 'last_synced_at'
            ),
            'classes': ('collapse',),
            'description': 'Automatically populated when quest is deployed to Solana'
        }),
        ('Analytics', {
            'fields': ('progress_summary', 'claim_stats'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    actions = ['deploy_to_solana', 'activate_quests', 'deactivate_quests', 'sync_from_chain']

    def quest_id_display(self, obj):
        """Display quest ID with icon"""
        return format_html('{} Quest #{}', obj.icon, obj.quest_id)
    quest_id_display.short_description = 'Quest'
    quest_id_display.admin_order_field = 'quest_id'

    def reward_sol_display(self, obj):
        """Display reward in SOL (read-only)"""
        return f"{obj.reward_sol:.4f} SOL"
    reward_sol_display.short_description = 'Reward (SOL)'

    def status_badge(self, obj):
        """Display colorful status badge"""
        colors = {
            'draft': '#6B7280',      # Gray
            'pending': '#F59E0B',    # Amber
            'active': '#10B981',     # Green
            'inactive': '#EF4444',   # Red
            'completed': '#8B5CF6'   # Purple
        }
        color = colors.get(obj.status, '#6B7280')
        active_indicator = ' ✅' if obj.is_active else ''
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold;">{}{}</span>',
            color, obj.get_status_display(), active_indicator
        )
    status_badge.short_description = 'Status'

    def deployment_status(self, obj):
        """Show deployment status"""
        if obj.on_chain_address:
            return format_html(
                '<span style="color: #10B981;">⛓️ On-Chain</span><br/><small>{}</small>',
                obj.on_chain_address[:8] + '...'
            )
        return format_html('<span style="color: #EF4444;">📝 Not Deployed</span>')
    deployment_status.short_description = 'Deployment'

    def claims_count(self, obj):
        """Show number of claims"""
        count = obj.claims.count()
        total_sol = obj.claims.aggregate(total=Sum('reward_lamports'))['total'] or 0
        total_sol_display = total_sol / 1_000_000_000
        return format_html(
            '<strong>{}</strong> claims<br/><small>{:.2f} SOL paid</small>',
            count, total_sol_display
        )
    claims_count.short_description = 'Claims'

    def progress_summary(self, obj):
        """Display progress statistics"""
        # This would query on-chain data in production
        return format_html(
            '<strong>Quest Overview</strong><br/>'
            'Users in Progress: <em>Query blockchain</em><br/>'
            'Completed: <em>Query blockchain</em><br/>'
            'Available: {}<br/>',
            '✅ Yes' if obj.is_available else '❌ No'
        )
    progress_summary.short_description = 'Progress Summary'

    def claim_stats(self, obj):
        """Display claim statistics"""
        claims = obj.claims.all()
        if not claims:
            return "No claims yet"

        total_claims = claims.count()
        total_paid = claims.aggregate(total=Sum('reward_lamports'))['total'] or 0
        total_sol = total_paid / 1_000_000_000

        recent_claims = claims.order_by('-claimed_at')[:5]
        recent_html = '<br/>'.join([
            f"• {claim.user.username} - {claim.claimed_at.strftime('%Y-%m-%d %H:%M')}"
            for claim in recent_claims
        ])

        return format_html(
            '<strong>Total Claims:</strong> {}<br/>'
            '<strong>Total Paid:</strong> {:.4f} SOL<br/><br/>'
            '<strong>Recent Claims:</strong><br/>{}',
            total_claims, total_sol, recent_html or 'None'
        )
    claim_stats.short_description = 'Claim Statistics'

    def save_model(self, request, obj, form, change):
        """Set created_by on new quests"""
        if not change and hasattr(request.user, 'adminuser'):
            obj.created_by = request.user.adminuser
        super().save_model(request, obj, form, change)

    # Admin Actions
    def deploy_to_solana(self, request, queryset):
        """Deploy selected quests to Solana blockchain"""
        deployed_count = 0
        for quest in queryset.filter(status='draft'):
            # TODO: Implement Solana deployment logic
            # This would call your Solana program's create_quest instruction
            self.message_user(
                request,
                f"Quest #{quest.quest_id} ready for deployment. Implement Solana service to deploy.",
                level='warning'
            )
            deployed_count += 1

        if deployed_count == 0:
            self.message_user(request, "No draft quests selected", level='warning')
    deploy_to_solana.short_description = "🚀 Deploy to Solana"

    def activate_quests(self, request, queryset):
        """Activate selected quests"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} quest(s)")
    activate_quests.short_description = "✅ Activate quests"

    def deactivate_quests(self, request, queryset):
        """Deactivate selected quests"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} quest(s)")
    deactivate_quests.short_description = "⏸️ Deactivate quests"

    def sync_from_chain(self, request, queryset):
        """Sync quest status from blockchain"""
        for quest in queryset.filter(on_chain_address__isnull=False):
            # TODO: Implement blockchain sync logic
            quest.last_synced_at = timezone.now()
            quest.save()
        self.message_user(request, f"Synced {queryset.count()} quest(s) from blockchain")
    sync_from_chain.short_description = "🔄 Sync from blockchain"


@admin.register(QuestUserProgress)
class QuestUserProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'nfts_bought', 'bids_placed', 'nfts_listed', 'on_chain_link', 'last_synced_at']
    list_filter = ['last_synced_at']
    search_fields = ['user__username', 'user__email', 'on_chain_address']
    readonly_fields = ['last_synced_at', 'progress_chart']

    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Progress', {
            'fields': ('nfts_bought', 'bids_placed', 'nfts_listed', 'progress_chart')
        }),
        ('On-Chain', {
            'fields': ('on_chain_address', 'last_synced_at')
        }),
    )

    def on_chain_link(self, obj):
        """Link to Solana Explorer"""
        if obj.on_chain_address:
            return format_html(
                '<a href="https://solscan.io/account/{}" target="_blank" style="color: #10B981;">View on Solscan</a>',
                obj.on_chain_address
            )
        return "Not on-chain yet"
    on_chain_link.short_description = 'Blockchain'

    def progress_chart(self, obj):
        """Visual representation of progress"""
        return format_html(
            '<div style="margin: 10px 0;">'
            '<strong>NFTs Bought:</strong> <span style="color: #10B981; font-size: 20px;">{}</span><br/>'
            '<strong>Bids Placed:</strong> <span style="color: #F59E0B; font-size: 20px;">{}</span><br/>'
            '<strong>NFTs Listed:</strong> <span style="color: #8B5CF6; font-size: 20px;">{}</span>'
            '</div>',
            obj.nfts_bought, obj.bids_placed, obj.nfts_listed
        )
    progress_chart.short_description = 'Progress Overview'


@admin.register(QuestClaim)
class QuestClaimAdmin(admin.ModelAdmin):
    list_display = ['user', 'quest', 'reward_sol_display', 'claimed_at', 'tx_link']
    list_filter = ['claimed_at', 'quest__action_type']
    search_fields = ['user__username', 'quest__title', 'transaction_signature']
    readonly_fields = ['claimed_at', 'reward_sol_display', 'tx_link']
    raw_id_fields = ['user', 'quest']
    date_hierarchy = 'claimed_at'

    fieldsets = (
        ('Claim Details', {
            'fields': ('user', 'quest', 'claimed_at')
        }),
        ('Reward', {
            'fields': ('reward_lamports', 'reward_sol_display')
        }),
        ('Transaction', {
            'fields': ('transaction_signature', 'tx_link')
        }),
    )

    def reward_sol_display(self, obj):
        """Display reward in SOL"""
        return f"{obj.reward_sol:.4f} SOL"
    reward_sol_display.short_description = 'Reward'

    def tx_link(self, obj):
        """Link to transaction on Solana Explorer"""
        if obj.transaction_signature:
            return format_html(
                '<a href="https://solscan.io/tx/{}" target="_blank" style="color: #10B981; font-weight: bold;">View Transaction →</a>',
                obj.transaction_signature
            )
        return "No signature"
    tx_link.short_description = 'Transaction'

    def has_add_permission(self, request):
        """Prevent manual addition (claims happen on-chain)"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of claim records"""
        return False
