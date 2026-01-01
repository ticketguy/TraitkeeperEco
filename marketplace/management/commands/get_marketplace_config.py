# marketplace/management/commands/get_marketplace_config.py

import asyncio
import logging
from django.core.management.base import BaseCommand
from marketplace.solana_client import MarketplaceSolanaClient

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fetches the marketplace configuration from the blockchain'

    async def fetch_config(self):
        """Fetch marketplace config from blockchain."""
        logger.info("=" * 80)
        logger.info("🔍 FETCHING MARKETPLACE CONFIG FROM BLOCKCHAIN")
        logger.info("=" * 80)

        try:
            client = MarketplaceSolanaClient()
            state = await client.get_state()

            # Get config PDA
            config_pda = state["config_pda"]
            program = state["program"]

            logger.info(f"📍 Config PDA: {config_pda}")

            # Fetch config account
            config_account = await program.account["config"].fetch(config_pda)

            logger.info("\n✅ MARKETPLACE CONFIGURATION:")
            logger.info(f"  Platform Fee (BPS): {config_account.platform_fee_bps} ({config_account.platform_fee_bps / 100}%)")
            logger.info(f"  Max Royalty Subsidy (BPS): {config_account.max_royalty_subsidy_bps} ({config_account.max_royalty_subsidy_bps / 100}%)")
            logger.info(f"  Min Vitality for Rebate: {config_account.min_vitality_for_rebate}")
            logger.info(f"  Rebate Counter Min: {config_account.rebate_counter_min}")
            logger.info(f"  Auction Loser Rebate (Lamports): {config_account.auction_loser_rebate_lamports}")
            logger.info(f"  Rejection Counter Min: {config_account.rejection_counter_min}")
            logger.info(f"  Rejection Rebate (Lamports): {config_account.rejection_rebate_lamports}")
            logger.info(f"\n💰 Fee Wallet: {config_account.fee_wallet}")
            logger.info(f"🎯 Quest Wallet: {config_account.quest_wallet}")
            logger.info(f"🏦 Vault Wallet: {config_account.vault_wallet}")
            logger.info(f"📦 Quest Program: {config_account.quest_program}")

            return config_account

        except Exception as e:
            logger.error(f"❌ Failed to fetch marketplace config: {e}", exc_info=True)
            return None

    def handle(self, *args, **options):
        """Synchronous entry point for the management command."""
        try:
            asyncio.run(self.fetch_config())
        except KeyboardInterrupt:
            self.stdout.write("Command stopped manually.")
