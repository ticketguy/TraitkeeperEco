# indexer/management/commands/review_discriminators.py

from django.core.management.base import BaseCommand
from indexer.models import UnknownDiscriminator

class Command(BaseCommand):
    help = 'Review auto-discovered discriminators'

    def handle(self, *args, **options):
        pending = UnknownDiscriminator.objects.filter(is_approved=False).order_by('-occurrence_count')
        
        self.stdout.write(f"\n📋 Found {pending.count()} unknown discriminators:\n")
        
        for unknown in pending[:20]:  # Show top 20
            self.stdout.write(f"\n{'='*80}")
            self.stdout.write(f"Program: {unknown.program_id}")
            self.stdout.write(f"Discriminator: {unknown.discriminator}")
            self.stdout.write(f"Inferred: {unknown.inferred_marketplace} -> {unknown.inferred_action}")
            self.stdout.write(f"Occurrences: {unknown.occurrence_count}")
            self.stdout.write(f"Has NFT transfer: {unknown.has_nft_transfer}")
            self.stdout.write(f"Has payment: {unknown.has_native_transfer}")
            self.stdout.write(f"Log patterns: {', '.join(unknown.log_patterns)}")
            self.stdout.write(f"Should ignore: {unknown.should_ignore}")
            self.stdout.write(f"Sample sigs: {unknown.sample_signatures[:2]}")