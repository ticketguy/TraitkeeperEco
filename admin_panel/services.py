# admin_panel/services.py
import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, F
from asgiref.sync import sync_to_async

# Import the central, site-wide cache manager
from core.cache_manager import cache_manager, CacheType

# Import the models needed for analytics
from nft_data.models import NFTCollection, NFT
from indexer.models import NFTEvent
from wallet.models import CustomUser, WalletProfile
from .models import AdminUser, AdminLoginAttempt

logger = logging.getLogger(__name__)

class AdminAnalyticsService:
    """
    A dedicated service for handling complex data aggregation and calculations
    for the admin panel dashboard, with integrated caching.
    """

    async def get_user_stats(self) -> dict:
        """
        Calculates and caches primary user statistics.
        """
        # Define a key for this specific piece of data, using a prefix from settings.
        cache_key = cache_manager._get_key_with_prefix(CacheType.GLOBAL, "admin_user_stats")
        
        # Check the central cache first.
        stats = await cache_manager.get(cache_key)
        if stats:
            logger.debug("Cache hit for user stats.")
            return stats

        logger.info("Cache miss for user stats, calculating from database...")

        # Exclude admin users from counts
        from admin_panel.models import AdminUser
        admin_user_ids = await sync_to_async(list)(AdminUser.objects.values_list('id', flat=True))

        # If not cached, run the database queries.
        # sync_to_async is used because Django ORM calls are synchronous.
        total_users = await sync_to_async(CustomUser.objects.exclude(id__in=admin_user_ids).count)()
        active_users = await sync_to_async(
            CustomUser.objects.exclude(id__in=admin_user_ids).filter(last_login__gte=timezone.now() - timedelta(days=30)).count
        )()
        new_users_query = CustomUser.objects.exclude(id__in=admin_user_ids).filter(date_joined__gte=timezone.now() - timedelta(days=7))
        new_user_count = await sync_to_async(new_users_query.count)()
        retained_users = await sync_to_async(
            new_users_query.filter(last_login__gt=F('date_joined')).count
        )()

        stats = {
            'total_users': total_users,
            'active_users': active_users,
            'wallet_connections': await sync_to_async(WalletProfile.objects.count)(),
            'admin_users': await sync_to_async(AdminUser.objects.count)(),
            'retention_rate': (retained_users / new_user_count * 100) if new_user_count > 0 else 0
        }

        # Store the result in the cache for next time using a standard TTL for global data.
        ttl = cache_manager.get_ttl(CacheType.GLOBAL)
        await cache_manager.set(cache_key, stats, ttl=ttl)
        
        return stats

    async def get_nft_stats(self) -> dict:
        """Calculates and caches primary NFT statistics."""
        cache_key = cache_manager._get_key_with_prefix(CacheType.GLOBAL, "admin_nft_stats")
        stats = await cache_manager.get(cache_key)
        if stats:
            return stats

        logger.info("Cache miss for NFT stats, calculating from database...")
        stats = {
            'collections': await sync_to_async(NFTCollection.objects.count)(),
            'nfts': await sync_to_async(NFT.objects.count)(),
            'transactions': await sync_to_async(NFTEvent.objects.filter(event_type='SALE').count)(),
        }
        
        ttl = cache_manager.get_ttl(CacheType.STATS, priority_tier='ACTIVE') # Stats can be cached for a medium duration
        await cache_manager.set(cache_key, stats, ttl=ttl)
        return stats

    async def get_weekly_activity_data(self, model, date_field) -> dict:
        """
        A generic helper to get the count of new records per day for the last 7 days.
        """
        cache_key = cache_manager._get_key_with_prefix(CacheType.GLOBAL, f"weekly_activity:{model.__name__}")
        chart_data = await cache_manager.get(cache_key)
        if chart_data:
            return chart_data
        
        logger.info(f"Cache miss for weekly {model.__name__} activity, calculating...")
        
        end_date = timezone.now()
        start_date = end_date - timedelta(days=6)
        
        # Generate date labels for the last 7 days.
        date_labels = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
        daily_counts = {label: 0 for label in date_labels}

        # Query the database for records in the date range.
        queryset = model.objects.filter(**{f'{date_field}__range': (start_date, end_date)})
        
        # This is a bit complex, but it groups records by day and counts them.
        daily_results = await sync_to_async(list)(
            queryset.extra(select={'day': "DATE(timestamp)"})
                    .values('day')
                    .annotate(count=Count('pk'))
                    .order_by('day')
        )

        for result in daily_results:
            day_str = result['day'].strftime('%Y-%m-%d')
            if day_str in daily_counts:
                daily_counts[day_str] = result['count']

        chart_data = {
            'labels': list(daily_counts.keys()),
            'data': list(daily_counts.values()),
        }
        
        ttl = cache_manager.get_ttl(CacheType.METRICS)
        await cache_manager.set(cache_key, chart_data, ttl=ttl)
        
        return chart_data