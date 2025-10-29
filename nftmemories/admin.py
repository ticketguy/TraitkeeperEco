from django.contrib import admin
from django.utils.html import format_html
from .models import CollectionEvent, NFTBurn, CollectionRaritySnapshot


@admin.register(CollectionEvent)
class CollectionEventAdmin(admin.ModelAdmin):
    """Admin interface for CollectionEvent - gamified NFT event memories"""
    list_display = [
        'event_type_display',
        'collection_name',
        'nft_mint_short',
        'significance',
        'timestamp',
        'interactions_summary'
    ]
    list_filter = ['significance', 'event__event_type', 'event__marketplace', 'created_at']
    search_fields = [
        'event__event_id',
        'event__nft_mint',
        'event__collection_address'
    ]
    readonly_fields = [
        'event',
        'created_at',
        'event_details_display',
        'interactions_display'
    ]
    ordering = ['-created_at']

    fieldsets = (
        ('Event Reference', {
            'fields': ('event', 'significance')
        }),
        ('User Interactions', {
            'fields': ('user_interactions', 'interactions_display'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )

    def event_type_display(self, obj):
        """Display event type with color coding"""
        colors = {
            'SALE': '#28a745',
            'LIST': '#007bff',
            'DELIST': '#6c757d',
            'BID': '#ffc107',
            'MINT': '#17a2b8',
            'BURN': '#dc3545',
            'TRANSFER': '#6f42c1',
        }
        color = colors.get(obj.event.event_type, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.event.event_type
        )
    event_type_display.short_description = 'Event Type'

    def collection_name(self, obj):
        """Display collection name"""
        return obj.event.collection.name if obj.event.collection else 'Unknown'
    collection_name.short_description = 'Collection'

    def nft_mint_short(self, obj):
        """Display shortened NFT mint address"""
        mint = obj.event.nft_mint
        if mint:
            return f"{mint[:8]}...{mint[-6:]}"
        return '-'
    nft_mint_short.short_description = 'NFT Mint'

    def timestamp(self, obj):
        """Display event timestamp"""
        return obj.event.timestamp
    timestamp.short_description = 'Timestamp'

    def interactions_summary(self, obj):
        """Display summary of user interactions"""
        interactions = obj.user_interactions
        likes = interactions.get('likes', 0)
        comments_count = len(interactions.get('comments', []))
        tributes_count = len(interactions.get('tributes', []))
        reactions = interactions.get('reactions', {})
        total_reactions = sum(reactions.values())

        return format_html(
            '👍 {} | 💬 {} | 🎁 {} | 🔥 {}',
            likes, comments_count, tributes_count, total_reactions
        )
    interactions_summary.short_description = 'Interactions'

    def event_details_display(self, obj):
        """Display full event details"""
        return format_html('<pre>{}</pre>', obj.event)
    event_details_display.short_description = 'Event Details'

    def interactions_display(self, obj):
        """Display formatted user interactions"""
        interactions = obj.user_interactions
        output = []

        output.append(f"<strong>Likes:</strong> {interactions.get('likes', 0)}")

        comments = interactions.get('comments', [])
        if comments:
            output.append(f"<strong>Comments ({len(comments)}):</strong>")
            for comment in comments[:5]:  # Show first 5
                output.append(f"  - {comment.get('user')}: {comment.get('comment')}")
            if len(comments) > 5:
                output.append(f"  ... and {len(comments) - 5} more")

        tributes = interactions.get('tributes', [])
        if tributes:
            output.append(f"<strong>Tributes ({len(tributes)}):</strong>")
            for tribute in tributes[:5]:  # Show first 5
                output.append(f"  - {tribute.get('user')}: {tribute.get('tribute')}")
            if len(tributes) > 5:
                output.append(f"  ... and {len(tributes) - 5} more")

        reactions = interactions.get('reactions', {})
        if any(reactions.values()):
            output.append(f"<strong>Reactions:</strong>")
            output.append(f"  🔥 Fire: {reactions.get('fire', 0)}")
            output.append(f"  💔 Heartbreak: {reactions.get('heartbreak', 0)}")
            output.append(f"  🎉 Party: {reactions.get('party', 0)}")

        return format_html('<pre>{}</pre>', '\n'.join(output))
    interactions_display.short_description = 'Interactions Details'


@admin.register(NFTBurn)
class NFTBurnAdmin(admin.ModelAdmin):
    """Admin interface for NFTBurn - memorial for burned NFTs"""
    list_display = [
        'nft_name',
        'collection_name',
        'mint_short',
        'burner_short',
        'reason_status',
        'burn_timestamp',
        'interactions_summary'
    ]
    list_filter = ['reason_is_approved', 'burn_event__timestamp', 'created_at']
    search_fields = [
        'burn_event__burn_id',
        'burn_event__mint_address',
        'burn_event__burner',
        'name',
        'reason'
    ]
    readonly_fields = [
        'burn_event',
        'created_at',
        'image_preview',
        'rarity_display',
        'interactions_display'
    ]
    ordering = ['-created_at']

    fieldsets = (
        ('Burn Event Reference', {
            'fields': ('burn_event',)
        }),
        ('NFT Details at Time of Burn', {
            'fields': ('name', 'description', 'image_url', 'image_preview', 'number', 'rarity', 'rarity_display')
        }),
        ('Burn Reason', {
            'fields': ('reason', 'reason_is_approved', 'added_by_user'),
            'description': 'User-submitted burn reasons require moderation'
        }),
        ('User Interactions', {
            'fields': ('user_interactions', 'interactions_display'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )

    def nft_name(self, obj):
        """Display NFT name"""
        return obj.name or 'Unnamed NFT'
    nft_name.short_description = 'NFT Name'

    def collection_name(self, obj):
        """Display collection name"""
        return obj.burn_event.collection.name if obj.burn_event.collection else 'Unknown'
    collection_name.short_description = 'Collection'

    def mint_short(self, obj):
        """Display shortened mint address"""
        mint = obj.burn_event.mint_address
        if mint:
            return f"{mint[:8]}...{mint[-6:]}"
        return '-'
    mint_short.short_description = 'Mint Address'

    def burner_short(self, obj):
        """Display shortened burner address"""
        burner = obj.burn_event.burner
        if burner:
            return f"{burner[:8]}...{burner[-6:]}"
        return '-'
    burner_short.short_description = 'Burner'

    def reason_status(self, obj):
        """Display reason approval status"""
        if not obj.reason:
            return format_html('<span style="color: #6c757d;">No reason</span>')
        elif obj.reason_is_approved:
            return format_html('<span style="color: #28a745;">✓ Approved</span>')
        else:
            return format_html('<span style="color: #ffc107;">⏳ Pending</span>')
    reason_status.short_description = 'Reason Status'

    def burn_timestamp(self, obj):
        """Display burn timestamp"""
        return obj.burn_event.timestamp
    burn_timestamp.short_description = 'Burned At'

    def interactions_summary(self, obj):
        """Display summary of user interactions"""
        interactions = obj.user_interactions
        likes = interactions.get('likes', 0)
        comments_count = len(interactions.get('comments', []))
        tributes_count = len(interactions.get('tributes', []))
        reactions = interactions.get('reactions', {})
        total_reactions = sum(reactions.values())

        return format_html(
            '👍 {} | 💬 {} | 🎁 {} | 🔥 {}',
            likes, comments_count, tributes_count, total_reactions
        )
    interactions_summary.short_description = 'Interactions'

    def image_preview(self, obj):
        """Display NFT image preview"""
        if obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 200px;" />',
                obj.image_url
            )
        return 'No image'
    image_preview.short_description = 'Image Preview'

    def rarity_display(self, obj):
        """Display formatted rarity data"""
        if not obj.rarity:
            return 'No rarity data'

        output = []
        for trait_type, trait_data in obj.rarity.items():
            if isinstance(trait_data, dict):
                value = trait_data.get('value', 'Unknown')
                rarity = trait_data.get('rarity', 'N/A')
                output.append(f"{trait_type}: {value} ({rarity}% rarity)")
            else:
                output.append(f"{trait_type}: {trait_data}")

        return format_html('<pre>{}</pre>', '\n'.join(output))
    rarity_display.short_description = 'Rarity Details'

    def interactions_display(self, obj):
        """Display formatted user interactions"""
        interactions = obj.user_interactions
        output = []

        output.append(f"<strong>Likes:</strong> {interactions.get('likes', 0)}")

        comments = interactions.get('comments', [])
        if comments:
            output.append(f"<strong>Comments ({len(comments)}):</strong>")
            for comment in comments[:5]:  # Show first 5
                output.append(f"  - {comment.get('user')}: {comment.get('comment')}")
            if len(comments) > 5:
                output.append(f"  ... and {len(comments) - 5} more")

        tributes = interactions.get('tributes', [])
        if tributes:
            output.append(f"<strong>Tributes ({len(tributes)}):</strong>")
            for tribute in tributes[:5]:  # Show first 5
                output.append(f"  - {tribute.get('user')}: {tribute.get('tribute')}")
            if len(tributes) > 5:
                output.append(f"  ... and {len(tributes) - 5} more")

        reactions = interactions.get('reactions', {})
        if any(reactions.values()):
            output.append(f"<strong>Reactions:</strong>")
            output.append(f"  🔥 Fire: {reactions.get('fire', 0)}")
            output.append(f"  💔 Heartbreak: {reactions.get('heartbreak', 0)}")
            output.append(f"  🎉 Party: {reactions.get('party', 0)}")

        return format_html('<pre>{}</pre>', '\n'.join(output))
    interactions_display.short_description = 'Interactions Details'

    actions = ['approve_reasons', 'reject_reasons']

    def approve_reasons(self, request, queryset):
        """Bulk approve burn reasons"""
        updated = queryset.filter(reason__isnull=False, reason_is_approved=False).update(reason_is_approved=True)
        self.message_user(request, f'Successfully approved {updated} burn reason(s).')
    approve_reasons.short_description = 'Approve selected burn reasons'

    def reject_reasons(self, request, queryset):
        """Bulk reject burn reasons"""
        updated = queryset.filter(reason__isnull=False).update(reason='', reason_is_approved=False, added_by_user=None)
        self.message_user(request, f'Successfully rejected {updated} burn reason(s).')
    reject_reasons.short_description = 'Reject selected burn reasons'


@admin.register(CollectionRaritySnapshot)
class CollectionRaritySnapshotAdmin(admin.ModelAdmin):
    """Admin interface for CollectionRaritySnapshot"""
    list_display = [
        'collection_name',
        'timestamp',
        'total_supply',
        'trait_count',
        'created_at'
    ]
    list_filter = ['timestamp', 'created_at']
    search_fields = ['collection__name', 'collection__address']
    readonly_fields = ['created_at', 'rarity_display']
    ordering = ['-timestamp']

    fieldsets = (
        ('Snapshot Details', {
            'fields': ('collection', 'timestamp', 'total_supply')
        }),
        ('Rarity Distribution', {
            'fields': ('rarity_base', 'rarity_display')
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )

    def collection_name(self, obj):
        """Display collection name"""
        return obj.collection.name
    collection_name.short_description = 'Collection'

    def trait_count(self, obj):
        """Count number of traits tracked"""
        return len(obj.rarity_base.keys())
    trait_count.short_description = 'Traits Tracked'

    def rarity_display(self, obj):
        """Display formatted rarity data"""
        if not obj.rarity_base:
            return 'No rarity data'

        output = []
        for trait_type, values in obj.rarity_base.items():
            output.append(f"<strong>{trait_type}:</strong>")
            if isinstance(values, dict):
                for value, rarity in list(values.items())[:10]:  # Show first 10
                    output.append(f"  - {value}: {rarity}%")
                if len(values) > 10:
                    output.append(f"  ... and {len(values) - 10} more values")
            output.append("")

        return format_html('<pre>{}</pre>', '\n'.join(output))
    rarity_display.short_description = 'Rarity Distribution'
