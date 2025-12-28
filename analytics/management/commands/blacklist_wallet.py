from django.core.management.base import BaseCommand
from analytics.models import BlacklistedWallet

class Command(BaseCommand):
    help = 'Blacklist a wallet address'

    def add_arguments(self, parser):
        parser.add_argument('wallet_address', type=str, help='The wallet address to blacklist')
        parser.add_argument('--reason', type=str, default='manual_review',
                            choices=[
                                'bot_listing', 'wash_trading', 'price_manipulation',
                                'spam_transactions', 'sybil_attack', 'coordinated_pumping',
                                'fake_volume', 'manual_review', 'other'
                            ],
                            help='Reason for blacklisting')
        parser.add_argument('--status', type=str, default='monitoring',
                            choices=['active', 'monitoring'],
                            help='Blacklist status (active=exclude from calculations, monitoring=track only)')
        parser.add_argument('--score', type=float, default=0.0,
                            help='Manipulation score (0-100)')
        parser.add_argument('--notes', type=str, default='',
                            help='Additional notes about this wallet')

    def handle(self, *args, **options):
        wallet_address = options['wallet_address']

        wallet, created = BlacklistedWallet.objects.get_or_create(
            wallet_address=wallet_address,
            defaults={
                'reason': options['reason'],
                'status': options['status'],
                'detection_method': 'manual',
                'manipulation_score': options['score'],
                'reviewer_notes': options['notes'] or 'Created via management command'
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Blacklisted wallet {wallet_address} with status: {options["status"]}'
                )
            )
            self.stdout.write(f'  Reason: {options["reason"]}')
            if options['score'] > 0:
                self.stdout.write(f'  Manipulation score: {options["score"]}/100')
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'⚠ Wallet {wallet_address} is already blacklisted'
                )
            )
            self.stdout.write(f'  Current status: {wallet.status}')
            self.stdout.write(f'  Current reason: {wallet.reason}')

            # Ask if they want to update
            self.stdout.write(
                self.style.NOTICE(
                    '\nTo update, use: python manage.py shell'
                )
            )
