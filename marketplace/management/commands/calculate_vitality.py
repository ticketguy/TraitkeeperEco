# marketplace/management/commands/calculate_vitality.py

import asyncio
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from asgiref.sync import sync_to_async

from nft_data.models import NFT, NFTCollection
from marketplace.vitality_service import VitalityCalculationService


class Command(BaseCommand):
    help = 'Calculate NFT vitality scores for collections or individual NFTs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--collection',
            type=str,
            help='Collection address to calculate vitality for'
        )
        parser.add_argument(
            '--nft',
            type=str,
            help='NFT mint address to calculate vitality for'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of NFTs to process (for bulk operations)'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Calculate vitality for all listed collections'
        )

    # The synchronous entry point that runs our async logic
    def handle(self, *args, **options):
        asyncio.run(self.a_handle(*args, **options))

    async def a_handle(self, *args, **options):
        """The main asynchronous logic for the command."""
        service = VitalityCalculationService()

        # Single NFT calculation
        if options['nft']:
            await self.calculate_single_nft(service, options['nft'])

        # Single collection calculation
        elif options['collection']:
            await self.calculate_collection(service, options['collection'], options.get('limit'))

        # All collections calculation
        elif options['all']:
            await self.calculate_all_collections(service, options.get('limit'))

        # Default: Show help
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Please specify --nft, --collection, or --all\n\n'
                    'Examples:\n'
                    '  python manage.py calculate_vitality --nft <mint_address>\n'
                    '  python manage.py calculate_vitality --collection <address>\n'
                    '  python manage.py calculate_vitality --all\n'
                )
            )

    async def calculate_single_nft(self, service, mint_address):
        """Asynchronously calculate vitality for a single NFT."""
        self.stdout.write(f'\nCalculating vitality for NFT: {mint_address}')

        try:
            # Use sync_to_async for the database query
            nft = await sync_to_async(NFT.objects.select_related('collection').get)(mint_address=mint_address)
            self.stdout.write(f'  NFT: {nft.name or "Unnamed"}')
            self.stdout.write(f'  Collection: {nft.collection.name}')

            # Use await for the async service call
            vitality = await service.calculate_nft_vitality(nft, store_history=True)

            if vitality:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✓ Vitality calculated: {vitality.vitality_score}/100\n'
                    )
                )
                self.display_component_breakdown(vitality)
            else:
                self.stdout.write(
                    self.style.WARNING(
                        '✗ Vitality calculation failed (insufficient data)\n'
                    )
                )

        except NFT.DoesNotExist:
            raise CommandError(f'NFT not found: {mint_address}')

    async def calculate_collection(self, service, collection_address, limit=None):
        """Asynchronously calculate vitality for all NFTs in a collection."""
        self.stdout.write(f'\nCalculating vitality for collection: {collection_address}')

        try:
            collection = await sync_to_async(NFTCollection.objects.get)(address=collection_address)
            self.stdout.write(f'  Collection: {collection.name}')

            # Calculate collection vitality
            self.stdout.write('\n  Calculating collection-level vitality...')
            collection_vitality = await service.calculate_collection_vitality(
                collection,
                store_history=True
            )

            if collection_vitality:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Collection Vitality: {collection_vitality.vitality_score}/100'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        '  ✗ Collection vitality calculation failed'
                    )
                )

            # Bulk calculate NFT vitality
            nft_count = await sync_to_async(NFT.objects.filter(collection=collection).count)()
            self.stdout.write(f'\n  Calculating NFT vitality ({nft_count} NFTs)...')

            if limit:
                self.stdout.write(f'  Limit: {limit} NFTs')

            successful, failed = await service.bulk_calculate_collection_nfts(
                collection,
                limit=limit
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ Bulk calculation complete:'
                )
            )
            self.stdout.write(f'  Successful: {successful}')
            self.stdout.write(f'  Failed: {failed}\n')

        except NFTCollection.DoesNotExist:
            raise CommandError(f'Collection not found: {collection_address}')

    async def calculate_all_collections(self, service, limit=None):
        """Asynchronously calculate vitality for all listed collections."""
        collections = await sync_to_async(list)(NFTCollection.objects.filter(is_listed=True))
        total_collections = len(collections)

        self.stdout.write(
            f'\nCalculating vitality for all listed collections ({total_collections} total)\n'
        )

        for idx, collection in enumerate(collections, 1):
            self.stdout.write(
                self.style.WARNING(
                    f'\n[{idx}/{total_collections}] {collection.name}'
                )
            )

            try:
                # Calculate collection vitality
                collection_vitality = await service.calculate_collection_vitality(
                    collection,
                    store_history=True
                )

                if collection_vitality:
                    self.stdout.write(
                        f'  Collection Vitality: {collection_vitality.vitality_score}/100'
                    )

                # Bulk calculate NFTs
                nft_count = await sync_to_async(NFT.objects.filter(collection=collection).count)()
                self.stdout.write(f'  Calculating {nft_count} NFTs...')

                successful, failed = await service.bulk_calculate_collection_nfts(
                    collection,
                    limit=limit
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ NFTs: {successful} successful, {failed} failed'
                    )
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'  ✗ Error: {str(e)}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ All collections processed!\n'
            )
        )

    # This method doesn't do any I/O, so it can remain synchronous
    def display_component_breakdown(self, vitality):
        """Display component breakdown for a vitality score."""
        self.stdout.write('\n  Component Breakdown:')
        self.stdout.write(f'    Market Momentum:     {vitality.market_momentum:.3f} (25%)')
        self.stdout.write(f'    Trait Performance:   {vitality.trait_performance:.3f} (20%)')
        self.stdout.write(f'    Collection Health:   {vitality.collection_health:.3f} (15%)')
        self.stdout.write(f'    Collection Utility:  {vitality.collection_utility:.3f} (10%)')
        self.stdout.write(f'    Rarity Score:        {vitality.rarity_score:.3f} (10%)')
        self.stdout.write(f'    Holder Quality:      {vitality.holder_quality:.3f} (10%)')
        self.stdout.write(f'    Sentiment Score:     {vitality.sentiment_score:.3f} (5%)')
        self.stdout.write(f'    Market Influence:    {vitality.market_influence:.3f} (5%)')