import asyncio
import logging
from django.core.management.base import BaseCommand
from asgiref.sync import sync_to_async
from admin_panel.models import MarketplaceProviderSetting
from nft_data.models import NFTCollection
from indexer.models import CollectionMarketStats, MarketplaceIdentifier
from core.api_provider.api_providers import APIProviderManager

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Diagnose market stats fetching issues'

    async def diagnose(self):
        """Run comprehensive diagnostics."""

        print("=" * 80)
        print("MARKET STATS DIAGNOSTIC REPORT")
        print("=" * 80)
        print()

        # 1. Check MarketplaceProviderSetting records
        print("1. Checking MarketplaceProviderSetting records in database...")

        @sync_to_async
        def get_marketplace_settings():
            return list(MarketplaceProviderSetting.objects.all().values(
                'name', 'is_active', 'api_key'
            ))

        settings = await get_marketplace_settings()
        if settings:
            for s in settings:
                api_key_preview = s['api_key'][:8] + "..." if s['api_key'] else "None"
                print(f"   - {s['name']}: Active={s['is_active']}, API Key={api_key_preview}")
        else:
            print("   ❌ NO MARKETPLACE PROVIDER SETTINGS FOUND IN DATABASE!")
            print("   → You need to create MarketplaceProviderSetting records")
        print()

        # 2. Check if providers are loaded by APIProviderManager
        print("2. Checking if providers are loaded by APIProviderManager...")
        manager = APIProviderManager()
        providers = await manager.get_rpc_providers()

        magic_eden = providers.get('magic_eden')
        tensor = providers.get('tensor')

        if magic_eden:
            print(f"   ✅ Magic Eden provider loaded: {type(magic_eden).__name__}")
        else:
            print("   ❌ Magic Eden provider NOT LOADED")

        if tensor:
            print(f"   ✅ Tensor provider loaded: {type(tensor).__name__}")
        else:
            print("   ❌ Tensor provider NOT LOADED")
        print()

        # 3. Check listed collections
        print("3. Checking listed collections...")

        @sync_to_async
        def get_collections():
            return list(NFTCollection.objects.filter(is_listed=True).values(
                'name', 'address', 'slug'
            ))

        collections = await get_collections()
        print(f"   Total listed collections: {len(collections)}")

        if collections:
            print("   Collections with Magic Eden slug:")
            for c in collections:
                slug_status = f"✅ {c['slug']}" if c.get('slug') else "❌ NO SLUG"
                print(f"   - {c['name'][:30]}: {slug_status}")
        print()

        # 4. Check existing market stats
        print("4. Checking existing CollectionMarketStats records...")

        @sync_to_async
        def get_stats_count():
            total = CollectionMarketStats.objects.count()
            magic_eden_count = CollectionMarketStats.objects.filter(source='magic_eden').count()
            tensor_count = CollectionMarketStats.objects.filter(source='tensor').count()
            return total, magic_eden_count, tensor_count

        total, me_count, t_count = await get_stats_count()
        print(f"   Total records: {total}")
        print(f"   Magic Eden records: {me_count}")
        print(f"   Tensor records: {t_count}")
        print()

        # 5. Test actual API call for first collection
        if collections and (magic_eden or tensor):
            print("5. Testing actual API call for first collection...")
            test_collection = collections[0]

            @sync_to_async
            def get_test_collection_obj():
                return NFTCollection.objects.get(address=test_collection['address'])

            collection_obj = await get_test_collection_obj()

            # Test Magic Eden
            if magic_eden:
                print(f"   Testing Magic Eden API for {test_collection['name']}...")
                try:
                    marketplace_id = await magic_eden.find_collection_symbol(
                        collection_obj.address,
                        collection_obj.name
                    )
                    print(f"   Magic Eden ID found: {marketplace_id}")

                    if marketplace_id:
                        result = await magic_eden.get_collection_data(
                            marketplace_id,
                            collection_obj.address,
                            collection_obj.priority_tier
                        )
                        if result and result.get('success'):
                            stats = result.get('stats', {})
                            print(f"   ✅ Magic Eden API working! Floor: {stats.get('floor_price')}")
                        else:
                            print(f"   ❌ Magic Eden API failed: {result.get('error')}")
                except Exception as e:
                    print(f"   ❌ Magic Eden test failed: {e}")

            # Test Tensor
            if tensor:
                print(f"   Testing Tensor API for {test_collection['name']}...")
                try:
                    marketplace_id = await tensor.find_collection_symbol(
                        collection_obj.address,
                        collection_obj.name
                    )
                    print(f"   Tensor ID found: {marketplace_id}")

                    if marketplace_id:
                        result = await tensor.get_collection_data(
                            marketplace_id,
                            collection_obj.address,
                            collection_obj.priority_tier
                        )
                        if result and result.get('success'):
                            stats = result.get('stats', {})
                            print(f"   ✅ Tensor API working! Floor: {stats.get('floor_price')}")
                        else:
                            print(f"   ❌ Tensor API failed: {result.get('error')}")
                except Exception as e:
                    print(f"   ❌ Tensor test failed: {e}")

        print()
        print("=" * 80)
        print("DIAGNOSIS COMPLETE")
        print("=" * 80)

    def handle(self, *args, **options):
        asyncio.run(self.diagnose())
