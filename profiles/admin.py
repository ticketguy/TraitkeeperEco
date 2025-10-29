from django.contrib import admin
from django.utils.html import format_html
from .models import Profile, WatchlistItem, AchievementCategory, Achievement, UserAchievement


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
    list_display = ['name', 'key', 'category', 'rarity', 'points', 'is_active', 'is_hidden', 'earned_count']
    list_filter = ['category', 'rarity', 'is_active', 'is_hidden', 'created_at']
    list_editable = ['is_active', 'is_hidden']
    search_fields = ['key', 'name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'icon_preview', 'earned_count']

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
            'description': 'JSON criteria for automatic awarding'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def icon_preview(self, obj):
        """Display icon preview in admin"""
        icon_url = obj.get_icon_url
        if icon_url:
            return format_html('<img src="{}" style="max-width: 64px; max-height: 64px;" />', icon_url)
        return "No icon"
    icon_preview.short_description = "Icon Preview"

    def earned_count(self, obj):
        """Show how many users earned this achievement"""
        return obj.earned_by.count()
    earned_count.short_description = "Times Earned"


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
