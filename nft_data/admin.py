from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from admin_panel.models import AdminLogEntry
from asgiref.sync import async_to_sync
from typing import Any
from django.contrib.contenttypes.models import ContentType
from .models import NFTCollection, NFT, TraitType, TraitValue, PendingCollection
# CORRECTED: Import services to delegate actions to the right apps.
from analytics.services.main import MetricsCalculationService
from .services import NFTDataService
from traitkeeper.admin_site import admin_site # custom admin site

# Import for backfill actions
from indexer.services.main import IndexerService
from indexer.models import NFTEvent
import asyncio

@admin.register(NFTCollection, site=admin_site)
class NFTCollectionAdmin(admin.ModelAdmin): # Keep inheriting from admin.ModelAdmin
    list_display = ('display_name', 'address_short', 'is_featured', 'is_listed', 'priority_tier', 'view_analytics_link')
    list_filter = ('is_featured', 'is_listed', 'priority_tier')
    search_fields = ('name', 'display_name', 'address', 'slug')
    list_editable = ('is_featured', 'is_listed') # Keep this if you want direct editing in the list view

    readonly_fields = ('address', 'name', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('display_name', 'slug', 'description', 'is_featured', 'is_listed', 'priority_tier')}),
        ('Core Data', {'fields': ('name', 'address', 'image_url', 'creator_address', 'social_media_links'), 'classes': ('collapse',)}), # Added creator_address
    )

    actions = ['trigger_analytics_update', 'list_collections', 'delist_collections', 'mark_featured',
        'unmark_featured', 'backfill_selected_collections', 'backfill_all_listed_collections']

    @admin.display(description="Address")
    def address_short(self, obj):
        return f"{obj.address[:6]}...{obj.address[-4:]}"

    @admin.display(description="Analytics")
    def view_analytics_link(self, obj):
        try:
            # Assuming you have a related name 'aggregated_stats'
            stats_id = obj.aggregated_stats.id
            url = reverse('admin:analytics_aggregatedcollectionstats_change', args=[stats_id])
            return format_html('<a href="{}">View Analytics</a>', url)
        except Exception:
            return "No analytics yet"

    # --- Admin Actions ---
    @admin.action(description="Trigger analytics update for selected")
    def trigger_analytics_update(self, request, queryset):
        analytics_service = MetricsCalculationService()
        count = 0
        for collection in queryset:
            try:
                # Assuming this function exists and works
                async_to_sync(analytics_service.update_collection_metrics)(collection)
                count += 1
            except Exception as e:
                 self.message_user(request, f"Error updating analytics for {collection}: {e}", level='error')
        if count > 0:
            self.message_user(request, f"Analytics update triggered for {count} collection(s).", level='success')

    @admin.action(description="Mark selected as LISTED")
    def list_collections(self, request, queryset):
        updated_count = queryset.update(is_listed=True)
        # Log the action using custom log
        for obj in queryset:
             self.log_change(request, obj, f"Marked as LISTED via admin action.")
        self.message_user(request, f"Marked {updated_count} collection(s) as LISTED.", level='success')

    @admin.action(description="Mark selected as DELISTED")
    def delist_collections(self, request, queryset):
        updated_count = queryset.update(is_listed=False)
        # Log the action using custom log
        for obj in queryset:
             self.log_change(request, obj, f"Marked as DELISTED via admin action.")
        self.message_user(request, f"Marked {updated_count} collection(s) as DELISTED.", level='success')

    @admin.action(description="Mark selected as FEATURED")
    def mark_featured(self, request, queryset):
        updated_count = queryset.update(is_featured=True)
        # Log the action using custom log
        for obj in queryset:
             self.log_change(request, obj, f"Marked as FEATURED via admin action.")
        self.message_user(request, f"Marked {updated_count} collection(s) as FEATURED.", level='success')

    @admin.action(description="UNMARK selected as featured")
    def unmark_featured(self, request, queryset):
        updated_count = queryset.update(is_featured=False)
        # Log the action using custom log
        for obj in queryset:
             self.log_change(request, obj, f"UNMARKED as featured via admin action.")
        self.message_user(request, f"Unmarked {updated_count} collection(s) as featured.", level='success')

    @admin.action(description="🔄 Backfill selected collections (historical data)")
    def backfill_selected_collections(self, request, queryset):
        """
        Backfill historical transaction data for selected collections.
        This will:
        1. Fix any misclassified BID events to SALE
        2. Process historical blockchain transactions
        3. Fetch current market stats
        """
        async def run_backfill():
            indexer = IndexerService()
            total = queryset.count()
            success_count = 0
            error_count = 0

            # Step 1: Fix existing BID → SALE for Magic Eden
            self.message_user(request, "Step 1/3: Fixing misclassified events...", level='info')
            try:
                updated = NFTEvent.objects.filter(
                    event_type='BID',
                    marketplace='magic_eden_v2'
                ).update(event_type='SALE')
                if updated > 0:
                    self.message_user(request, f"✅ Fixed {updated} misclassified BID→SALE events", level='success')
            except Exception as e:
                self.message_user(request, f"⚠️ Error fixing events: {e}", level='warning')

            # Step 2: Process each selected collection
            self.message_user(request, f"Step 2/3: Processing {total} collection(s)...", level='info')

            for i, collection in enumerate(queryset, 1):
                try:
                    self.message_user(
                        request,
                        f"[{i}/{total}] Processing {collection.name}...",
                        level='info'
                    )

                    # Process historical transactions
                    await indexer.process_onchain_events(collection.address)

                    # Fetch market stats
                    await indexer.fetch_and_store_all_market_stats(collection)

                    # Calculate blockchain volume
                    await indexer.calculate_and_store_blockchain_volume(collection)

                    success_count += 1
                    self.log_change(request, collection, f"Historical backfill completed via admin action.")

                except Exception as e:
                    error_count += 1
                    self.message_user(
                        request,
                        f"❌ Error processing {collection.name}: {str(e)}",
                        level='error'
                    )
                    continue

            # Step 3: Summary
            self.message_user(
                request,
                f"Step 3/3: Backfill complete! Success: {success_count}, Errors: {error_count}",
                level='success' if error_count == 0 else 'warning'
            )

            # Show event summary
            try:
                from django.db.models import Count
                events = NFTEvent.objects.values('event_type').annotate(count=Count('event_id'))
                summary = ", ".join([f"{e['event_type']}: {e['count']}" for e in events])
                self.message_user(request, f"📊 Event Summary: {summary}", level='info')
            except Exception:
                pass

        # Run async backfill
        try:
            async_to_sync(run_backfill)()
        except Exception as e:
            self.message_user(request, f"❌ Backfill failed: {str(e)}", level='error')

    @admin.action(description="🔄 Backfill ALL listed collections (comprehensive)")
    def backfill_all_listed_collections(self, request, queryset):
        """
        Backfill ALL listed collections regardless of selection.
        Use this for comprehensive database rebuild.

        WARNING: This processes ALL is_listed=True collections and may take a long time.
        """
        async def run_full_backfill():
            indexer = IndexerService()

            # Get ALL listed collections (not just selected)
            all_collections = NFTCollection.objects.filter(is_listed=True)
            total = all_collections.count()
            success_count = 0
            error_count = 0

            self.message_user(
                request,
                f"⚠️ Starting FULL backfill for {total} listed collections...",
                level='warning'
            )

            # Step 1: Fix existing BID → SALE
            self.message_user(request, "Step 1/3: Fixing misclassified events...", level='info')
            try:
                updated = NFTEvent.objects.filter(
                    event_type='BID',
                    marketplace='magic_eden_v2'
                ).update(event_type='SALE')
                if updated > 0:
                    self.message_user(request, f"✅ Fixed {updated} misclassified BID→SALE events", level='success')
            except Exception as e:
                self.message_user(request, f"⚠️ Error fixing events: {e}", level='warning')

            # Step 2: Process ALL collections
            self.message_user(request, f"Step 2/3: Processing {total} collections...", level='info')

            for i, collection in enumerate(all_collections, 1):
                try:
                    self.message_user(
                        request,
                        f"[{i}/{total}] Processing {collection.name}...",
                        level='info'
                    )

                    # Process historical transactions
                    await indexer.process_onchain_events(collection.address)

                    # Fetch market stats
                    await indexer.fetch_and_store_all_market_stats(collection)

                    # Calculate blockchain volume
                    await indexer.calculate_and_store_blockchain_volume(collection)

                    success_count += 1

                    # Small delay to avoid rate limits
                    if i < total:
                        await asyncio.sleep(2)

                except Exception as e:
                    error_count += 1
                    self.message_user(
                        request,
                        f"❌ Error processing {collection.name}: {str(e)}",
                        level='error'
                    )
                    continue

            # Step 3: Summary
            self.message_user(
                request,
                f"Step 3/3: FULL backfill complete! Success: {success_count}, Errors: {error_count}",
                level='success' if error_count == 0 else 'warning'
            )

            # Show comprehensive event summary
            try:
                from django.db.models import Count
                events = NFTEvent.objects.values('event_type').annotate(count=Count('event_id'))
                summary = "\n".join([f"  • {e['event_type']}: {e['count']}" for e in events])
                self.message_user(request, f"📊 Complete Event Summary:\n{summary}", level='info')
            except Exception:
                pass

        # Run async backfill
        try:
            async_to_sync(run_full_backfill)()
        except Exception as e:
            self.message_user(request, f"❌ Full backfill failed: {str(e)}", level='error')

    # <<<--- ADD THESE METHODS FOR CUSTOM LOGGING --- >>>

    def log_change(self, request, object, message):
        """Logs changes made to an NFTCollection using the custom AdminLogEntry."""
        AdminLogEntry.objects.log_action(
            user_id=request.user.id, # request.user is AdminUser here
            content_type_id=ContentType.objects.get_for_model(object).pk,
            object_id=object.pk, # Use .pk for primary key
            object_repr=str(object),
            action_flag=2, # 2 = Change
            change_message=str(message),
        )

    def log_addition(self, request, object, message):
        """Logs additions of NFTCollection using the custom AdminLogEntry."""
        AdminLogEntry.objects.log_action(
            user_id=request.user.id,
            content_type_id=ContentType.objects.get_for_model(object).pk,
            object_id=object.pk,
            object_repr=str(object),
            action_flag=1, # 1 = Addition
            change_message=str(message),
        )

    def log_deletion(self, request, object, object_repr):
        """Logs deletions of NFTCollection using the custom AdminLogEntry."""
        AdminLogEntry.objects.log_action(
            user_id=request.user.id,
            content_type_id=ContentType.objects.get_for_model(object).pk,
            object_id=object.pk,
            object_repr=object_repr,
            action_flag=3, # 3 = Deletion
        )
    # <<<--- END OF CUSTOM LOGGING METHODS --- >>>


@admin.register(NFT, site=admin_site)
class NFTAdmin(admin.ModelAdmin):
    """Admin interface for individual NFTs."""
    list_display = ('name', 'mint_address', 'collection', 'owner', 'is_listed', 'listing_price')
    list_filter = ('collection', 'is_listed', 'is_burned')
    search_fields = ('name', 'mint_address', 'owner')
    readonly_fields = ('mint_address', 'collection', 'name', 'image_url', 'traits', 'trait_values', 'created_at', 'updated_at')
    
    fieldsets = (
        (None, {'fields': ('name', 'mint_address', 'collection', 'owner')}),
        ('Market State (Cached)', {'fields': ('is_listed', 'listing_price')}),
        ('Metadata', {'fields': ('image_url', 'traits', 'trait_values', 'is_burned'), 'classes': ('collapse',)}),
    )


@admin.register(PendingCollection, site=admin_site)
class PendingCollectionAdmin(admin.ModelAdmin):
    """Admin interface for the collection submission and approval workflow."""
    list_display = ('name', 'mint_address', 'status', 'submitted_by', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'mint_address', 'submitted_by')
    readonly_fields = ('name', 'mint_address', 'submitted_by', 'social_media_links', 'created_at', 'updated_at', 'validation_error')
    actions = ['approve_collections', 'reject_collections']

    @admin.action(description="Approve selected pending collections")
    def approve_collections(self, request, queryset):
        """Approves pending collections using the dedicated service."""
        service = NFTDataService()
        for pending in queryset.filter(status='pending'):
            # The service handles the complex logic and notifications
            async_to_sync(service.approve_pending_collection)(pending.id, request.user)
        self.message_user(request, f"Approval process initiated for {queryset.count()} collection(s).", level='success')

    @admin.action(description="Reject selected pending collections")
    def reject_collections(self, request, queryset):
        """Rejects pending collections using the dedicated service."""
        service = NFTDataService()
        for pending in queryset.filter(status='pending'):
            async_to_sync(service.reject_pending_collection)(pending.id, request.user.username)
        self.message_user(request, f"Rejected {queryset.count()} collection(s).", level='success')
admin_site.register(TraitType)
admin_site.register(TraitValue)