from django.core.management.base import BaseCommand
from indexer.models import UnknownDiscriminator

class Command(BaseCommand):
    help = 'Export discovered discriminators to Python dict format'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-occurrences',
            type=int,
            default=10,
            help='Minimum occurrences to export (default: 10)'
        )

    def handle(self, *args, **options):
        min_count = options['min_occurrences']
        
        discovered = UnknownDiscriminator.objects.filter(
            occurrence_count__gte=min_count
        ).order_by('-occurrence_count')
        
        self.stdout.write("\n# Auto-discovered discriminators - add these to nft_constants.py:\n")
        
        by_program = {}
        for d in discovered:
            marketplace = d.inferred_marketplace or 'unknown'
            if marketplace not in by_program:
                by_program[marketplace] = []
            by_program[marketplace].append(d)
        
        for marketplace, items in by_program.items():
            self.stdout.write(f"\n'{marketplace}': {{")
            for item in items:
                action = item.inferred_action
                disc = item.discriminator
                count = item.occurrence_count
                ignore = " # ADMIN - ignore" if item.should_ignore else ""
                self.stdout.write(f"    '{action}': bytes.fromhex('{disc}'),  # {count} occurrences{ignore}")
            self.stdout.write("},")