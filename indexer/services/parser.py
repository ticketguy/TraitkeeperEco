# indexer/services/parser.py
import asyncio
import logging
import re
import json
from typing import Optional, List, Dict, Any
from django.utils import timezone
from datetime import timezone as dt_timezone, datetime
from decimal import Decimal
from asgiref.sync import sync_to_async
import base58

from core.api_provider.api_providers import APIProviderManager
from ..models import NFTEvent, FailedTransaction
from nft_data.models import NFT, NFTCollection

# --- POWERFUL IMPORTS FROM YOUR CONSTANTS FILE ---
from ..nft_constants import (
    # Discriminators
    MARKETPLACE_DISCRIMINATORS,
    
    # Magic Eden V2 Layouts
    ME_V2_EXECUTE_SALE_LAYOUT, ME_V2_BUY_LAYOUT, ME_V2_CANCEL_SELL_LAYOUT,
    ME_V2_DEPOSIT_LAYOUT, ME_V2_WITHDRAW_LAYOUT, ME_V2_MIP1_SELL_LAYOUT,
    ME_V2_CORE_SELL_LAYOUT, ME_V2_MIP1_CANCEL_SELL_LAYOUT,
    ME_V2_MIP1_EXECUTE_SALE_V2_LAYOUT, ME_V2_CORE_CANCEL_SELL_LAYOUT,
    ME_V2_CORE_EXECUTE_SALE_V2_LAYOUT, ME_V2_UPDATE_AUCTION_HOUSE_LAYOUT,
    
    # Magic Eden MMM Layouts
    ME_MMM_SOL_FULFILL_SELL_LAYOUT, ME_MMM_SOL_MIP1_FULFILL_SELL_LAYOUT,
    ME_MMM_SOL_EXT_FULFILL_SELL_LAYOUT, ME_MMM_MIP1_WITHDRAW_SELL_LAYOUT,
    ME_MMM_MPL_CORE_WITHDRAW_SELL_LAYOUT, ME_MMM_OCP_WITHDRAW_SELL_LAYOUT,
    ME_MMM_SOL_OCP_FULFILL_SELL_LAYOUT, ME_MMM_DEPOSIT_SELL_LAYOUT,
    ME_MMM_EXT_DEPOSIT_SELL_LAYOUT, ME_MMM_MPL_CORE_DEPOSIT_SELL_LAYOUT,
    ME_MMM_SOL_WITHDRAW_BUY_LAYOUT, ME_MMM_SOL_DEPOSIT_BUY_LAYOUT,
    ME_MMM_CNFT_FULFILL_BUY_LAYOUT, ME_MMM_SOL_EXT_FULFILL_BUY_LAYOUT,
    ME_MMM_SOL_MPL_CORE_FULFILL_SELL_LAYOUT, ME_MMM_SOL_OCP_FULFILL_BUY_LAYOUT,
    ME_MMM_UPDATE_POOL_LAYOUT, ME_MMM_CREATE_POOL_LAYOUT,
    ME_MMM_SET_SHARED_ESCROW_LAYOUT, ME_MMM_UPDATE_ALLOWLISTS_LAYOUT,
    ME_MMM_SOL_FULFILL_SELL_LAYOUT_V2,
    
    # Tensor cNFT Layouts
    TENSOR_CNFT_BID_LAYOUT, TENSOR_CNFT_LIST_LAYOUT, TCOMP_BUY_LAYOUT,
    TENSOR_CNFT_EDIT_LAYOUT, TENSOR_CNFT_CANCEL_BID_LAYOUT,
    TENSOR_CNFT_TAKE_BID_LEGACY_LAYOUT, TENSOR_CNFT_DELIST_LAYOUT,
    TENSOR_CNFT_LIST_CORE_LAYOUT, TENSOR_CNFT_BUY_CORE_LAYOUT,
    TENSOR_CNFT_TAKE_BID_T22_LAYOUT, TENSOR_CNFT_TAKE_BID_WNS_LAYOUT,
    TENSOR_CNFT_TAKE_BID_FULL_META_LAYOUT, TENSOR_CNFT_TAKE_BID_META_HASH_LAYOUT,
    TENSOR_CNFT_DELIST_CORE_LAYOUT, TENSOR_CNFT_CLOSE_EXPIRED_LISTING_LAYOUT,
    TENSOR_CNFT_CLOSE_EXPIRED_BID_LAYOUT, TENSOR_CNFT_BUY_SPL_LAYOUT,
    
    # Tensor AMM Layouts
    TENSOR_AMM_BUY_NFT_LAYOUT, TENSOR_AMM_BUY_NFT_CORE_LAYOUT,
    TENSOR_AMM_BUY_NFT_T22_LAYOUT,
    
    # Utility functions
    identify_instruction_enhanced, get_marketplace_from_program_id,
    normalize_marketplace_name, get_event_type, get_tensor_program_type
)

from solders.pubkey import Pubkey

logger = logging.getLogger(__name__)


class TransactionParserService:
    """
    An advanced, multi-tiered parser that uses instruction analysis first,
    then falls back to simpler methods. This is the "Detective" that understands
    the raw data from any provider.
    
    Architecture:
    - Tier 1: Instruction Discriminator Parsing (Most Accurate)
    - Tier 2: Log Message Analysis (Heuristic)
    - Tier 3: Transfer Correlation (Fallback)
    """
    
    def __init__(self, provider_manager: APIProviderManager):
        self.provider_manager = provider_manager
        logger.info("TransactionParserService initialized with tiered parsing system")

    # ===================================================================
    # PUBLIC ENTRY POINT
    # ===================================================================
    async def parse_and_store_event(self, event_data: dict) -> Optional[NFTEvent]:
        """
        Main entry point for parsing any transaction into an NFT event.
        
        Args:
            event_data: Raw or enriched transaction data from any provider
            
        Returns:
            NFTEvent object if successfully parsed and stored, None otherwise
        """
        try:
            if not event_data:
                logger.warning("[PARSER] Received None or empty data.")
                return None

            # Normalize the transaction data format FIRST to get signature
            normalized_tx = self.normalize_transaction_data(event_data)
            signature = normalized_tx.get('signature')
            
            if not signature:
                logger.warning("[PARSER] Normalized data is missing a signature. Aborting.")
                return None

            logger.info(f"--- [PARSER] STARTING PARSE FOR SIGNATURE: {signature} ---")

            # --- OPTIMIZATION: Pre-filter by collection before expensive parsing ---
            has_tracked_collection = await self._has_tracked_collection(normalized_tx)
            if not has_tracked_collection:
                logger.info(f"⏭️  [{signature[:16]}...] SKIPPED - No tracked collections involved in transaction")
                return None  # Skip silently - not a parsing error, just not relevant

            # --- Call the tiered parser ---
            parsed_event = await self._parse_transaction_with_tiers(normalized_tx)

            # Check if transaction was intentionally skipped
            if isinstance(parsed_event, dict) and parsed_event.get('_skipped'):
                logger.info(f"[{signature}] Transaction intentionally skipped (admin/system operation)")
                return None

            if not parsed_event:
                logger.warning(f"[{signature}] All parsing tiers failed. No actionable event found.")
                # Don't save as failed - we only track failures for collections we care about
                # If parsing failed, we can't determine the collection anyway
                return None
            
            # --- Collection Resolution ---
            collection_address = parsed_event.get('collection_address')
            if not collection_address and parsed_event.get('mint_address'):
                logger.info(f"[{signature}] Event is missing collection. Resolving from mint...")
                collection_address = await self._get_collection_for_mint(parsed_event['mint_address'])
            
            if not collection_address:
                logger.info(f"⏭️  [{signature[:16]}...] SKIPPED - Could not resolve collection address for NFT mint")
                return None  # Not a parsing failure, just can't determine collection

            # --- Validate Collection Exists in Database ---
            collection = await sync_to_async(NFTCollection.objects.filter(address=collection_address).first)()
            if not collection:
                logger.info(
                    f"⏭️  [{signature[:16]}...] SKIPPED - Collection {collection_address[:8]}... not tracked in database"
                )
                return None  # Don't save as failed, just skip silently

            # --- Validate Parsed Event ---
            if not self._validate_parsed_event(parsed_event, signature):
                logger.error(f"[{signature}] Event validation failed for tracked collection {collection.name}")
                # Save as failed since this is for a collection we're tracking
                await self._save_to_failed_transactions(
                    signature,
                    event_data,
                    f"Event validation failed for collection {collection.address}"
                )
                return None

            # --- Save to Database ---
            defaults = self._prepare_event_defaults(parsed_event, collection, normalized_tx)
            nft_event, created = await sync_to_async(NFTEvent.objects.update_or_create)(
                event_id=signature,
                defaults=defaults
            )
            
            # --- Update NFT Owner for Sales/Transfers ---
            if nft_event.event_type in ['SALE', 'TRANSFER']:
                await self._update_nft_owner(nft_event)

            # --- Mark NFT as Burned for BURN events ---
            if nft_event.event_type == 'BURN':
                await self._mark_nft_as_burned(nft_event)

            status = "CREATED" if created else "UPDATED"
            logger.info(f"--- [PARSER] SUCCESS ({status}) for signature {signature} as {nft_event.event_type} ---")
            return nft_event

        except Exception as e:
            # Use signature from normalized_tx if available, otherwise from event_data
            sig = normalized_tx.get('signature') if 'normalized_tx' in locals() else event_data.get('signature', 'UNKNOWN')
            logger.error(f"--- [PARSER] FAILED for signature {sig}: {e} ---", exc_info=True)
            if sig != 'UNKNOWN':
                await self._save_to_failed_transactions(sig, event_data, str(e))
            return None
        
    # ===================================================================
    # HIERARCHICAL PARSING LOGIC ("The Professional Chef")
    # ===================================================================

    async def _parse_transaction_with_tiers(self, enriched_tx: dict) -> Optional[dict]:
        """Three-tiered parsing with smart filtering."""
        signature = enriched_tx.get('signature', 'unknown')
        final_event = None
        
        # Initialize filter and learner
        from .transaction_filter import TransactionFilter
        from .discriminator_learner import DiscriminatorLearner
        tx_filter = TransactionFilter()
        learner = DiscriminatorLearner()

        # --- TIER 1: Discriminator Parsing ---
        try:
            logger.info(f"[{signature}] Starting Tier 1: Discriminator Parsing")
            for instruction in enriched_tx.get('instructions', []):
                program_id = instruction.get('programId')
                data = instruction.get('data', '')
                
                # Skip system programs immediately
                if tx_filter.should_skip_by_program(program_id):
                    continue
                
                if not program_id or not data:
                    continue

                try:
                    decoded_data = base58.b58decode(data)
                except Exception:
                    continue

                if len(decoded_data) < 8:
                    continue
                
                discriminator = decoded_data[:8]
                marketplace, action = identify_instruction_enhanced(program_id, discriminator)

                if action != 'unknown':
                    # Check if we should skip this action
                    if tx_filter.should_skip_by_action(marketplace, action):
                        logger.info(f"[{signature}] Tier 1: Skipping admin action: {marketplace}/{action}")
                        return {'_skipped': True, 'reason': f'Admin action: {marketplace}/{action}'}
                    
                    # Known and valuable - parse it
                    logger.info(f"[{signature}] Tier 1 SUCCESS: Matched {marketplace} -> {action}")
                    event = await self._route_to_sub_parser(
                        marketplace, action, discriminator, enriched_tx, instruction, decoded_data
                    )
                    if event:
                        event['parsing_tier'] = 'tier_1_discriminator'
                        event['parsing_confidence'] = 0.95
                        final_event = event
                        break
                else:
                    # Unknown - learn it
                    logger.warning(f"[{signature}] Unknown discriminator: {discriminator.hex()}")
                    await learner.handle_unknown_discriminator(
                        program_id, discriminator, enriched_tx, signature
                    )
        
        except Exception as e:
            logger.warning(f"[{signature}] Tier 1 failed: {e}", exc_info=True)

        if final_event:
            return final_event

        # --- TIER 2: Log Message Analysis ---
        logger.info(f"[{signature}] Tier 1 failed. Trying Tier 2: Log Analysis")
        try:
            detected_type = self._detect_event_type_from_logs(enriched_tx.get('logMessages', []))
            
            if detected_type == 'SKIP':
                logger.info(f"[{signature}] Tier 2: Detected skip pattern in logs")
                return {'_skipped': True, 'reason': 'Skip pattern detected in logs'}

            if detected_type != 'UNKNOWN':
                # Check if we should skip this event type
                if tx_filter.should_skip_by_event_type(detected_type):
                    logger.info(f"[{signature}] Tier 2: Skipping event type: {detected_type}")
                    return {'_skipped': True, 'reason': f'Ignorable event type: {detected_type}'}
                
                logger.info(f"[{signature}] Tier 2: Detected '{detected_type}' from logs")
                enriched_tx['detected_event_type'] = detected_type
        except Exception as e:
            logger.warning(f"[{signature}] Tier 2 failed: {e}")

        # --- TIER 3: Transfer Correlation ---
        logger.info(f"[{signature}] Proceeding to Tier 3: Transfer Analysis")
        try:
            event_from_transfers = self._analyze_unknown_transaction(enriched_tx)
            
            if event_from_transfers and event_from_transfers.get('confidence', 0) > 0.5:
                logger.info(f"[{signature}] Tier 3 SUCCESS: Parsed via transfer analysis")
                event_from_transfers['parsing_tier'] = 'tier_3_transfers'
                event_from_transfers['parsing_confidence'] = event_from_transfers.get('confidence', 0.7)
                final_event = event_from_transfers
            else:
                if event_from_transfers is None:
                    logger.info(f"[{signature}] Tier 3: Transaction skipped (not valuable)")
                else:
                    logger.warning(f"[{signature}] Tier 3: Low confidence ({event_from_transfers.get('confidence', 0)})")
        except Exception as e:
            logger.warning(f"[{signature}] Tier 3 failed: {e}", exc_info=True)

        return final_event

    async def _route_to_sub_parser(self, marketplace: str, action: str, discriminator: bytes, 
                                   tx: dict, ix: dict, decoded_data: bytes) -> Optional[dict]:
        """
        Routes to the correct, highly-specific parser based on marketplace and action.
        
        Args:
            marketplace: Normalized marketplace name (e.g., 'magic_eden_v2')
            action: Instruction action (e.g., 'execute_sale')
            discriminator: 8-byte instruction discriminator
            tx: Full transaction details
            ix: Current instruction being parsed
            decoded_data: Base58-decoded instruction data
            
        Returns:
            Parsed event dict or None
        """
        timestamp = tx.get('timestamp')
        collection_address = tx.get('collection_address', '')
        
        # --- THIS IS THE KEY FIX ---
        # The 'marketplace' variable can be the generic alias 'tensor'.
        # We need the SPECIFIC program ID from the instruction to choose the right parser.
        program_id = ix.get('programId')
        specific_marketplace = get_marketplace_from_program_id(program_id)
        # --- END FIX ---

        try:
            if specific_marketplace == 'magic_eden_v2':
                return await self._parse_me_v2_instruction(tx, ix, decoded_data, collection_address, timestamp)
            elif specific_marketplace == 'magic_eden_mmm':
                return await self._parse_me_mmm_instruction(tx, ix, decoded_data, collection_address, timestamp)
            elif specific_marketplace == 'tensor_cnft_marketplace':
                return await self._parse_tensor_cnft_instruction(tx, ix, decoded_data, collection_address, timestamp)
            elif specific_marketplace == 'tensor_amm':
                return await self._parse_tensor_amm_instruction(tx, ix, decoded_data, collection_address, timestamp)
            elif specific_marketplace == 'tensor_escrow':
                return await self._parse_tensor_escrow_instruction(tx, ix, decoded_data, collection_address, timestamp)
            elif specific_marketplace == 'mpl_core':
                return await self._parse_mpl_core_instruction(tx, ix, decoded_data, collection_address, timestamp)
            elif specific_marketplace == 'token_metadata':
                return await self._parse_token_metadata_instruction(tx, ix, decoded_data, collection_address, timestamp)

            logger.warning(f"No sub-parser implemented for marketplace: {specific_marketplace} (alias: {marketplace})")
            return None
            
        except Exception as e:
            logger.error(f"Error routing to sub-parser for {specific_marketplace}/{action}: {e}", exc_info=True)
            return None

    # ===================================================================
    # MAGIC EDEN V2 PARSERS
    # ===================================================================

    async def _parse_me_v2_instruction(self, tx_details: Dict, ix: Dict, decoded_data: bytes,
                                      collection_address: str, timestamp: Any) -> Optional[Dict]:
        """
        Parse Magic Eden V2 instruction using discriminator matching.
        
        Handles all ME V2 instruction types including MIP1 and Core variants.
        """
        if len(decoded_data) < 8:
            logger.warning("ME V2 instruction data too short")
            return None
            
        discriminator = decoded_data[:8]
        accounts = ix.get('accounts', [])
        
        # Discriminator → (parser_function, layout) mapping
        me_v2_parsers = {
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['execute_sale']:
                (self._parse_me_v2_execute_sale, ME_V2_EXECUTE_SALE_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['buy']:
                (self._parse_me_v2_bid, ME_V2_BUY_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['sell']:
                (self._parse_me_v2_listing, ME_V2_MIP1_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['cancel_sell']:
                (self._parse_me_v2_cancel_sell, ME_V2_CANCEL_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['cancel_sell_v2']:
                (self._parse_me_v2_cancel_sell, ME_V2_CANCEL_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['deposit']:
                (self._parse_me_v2_deposit, ME_V2_DEPOSIT_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['withdraw']:
                (self._parse_me_v2_withdraw, ME_V2_WITHDRAW_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['mip1_sell']:
                (self._parse_me_v2_listing, ME_V2_MIP1_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['mip1_sell_v2']:
                (self._parse_me_v2_listing, ME_V2_MIP1_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['mip1_sell_v3']:
                (self._parse_me_v2_listing, ME_V2_MIP1_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['core_sell']:
                (self._parse_me_v2_listing, ME_V2_CORE_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['mip1_cancel_sell']:
                (self._parse_me_v2_mip1_cancel_sell, ME_V2_MIP1_CANCEL_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['mip1_execute_sale_v2']:
                (self._parse_me_v2_mip1_execute_sale, ME_V2_MIP1_EXECUTE_SALE_V2_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['core_cancel_sell']:
                (self._parse_me_v2_core_cancel_sell, ME_V2_CORE_CANCEL_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['core_execute_sale_v2']:
                (self._parse_me_v2_core_execute_sale, ME_V2_CORE_EXECUTE_SALE_V2_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_v2']['update_auction_house']:
                (self._parse_me_v2_update_auction_house, ME_V2_UPDATE_AUCTION_HOUSE_LAYOUT),
        }
        
        parser_tuple = me_v2_parsers.get(discriminator)
        if not parser_tuple:
            logger.warning(f"Unknown ME V2 discriminator: {discriminator.hex()}")
            return None
            
        parser_func, layout = parser_tuple
        try:
            parsed_data = layout.parse(decoded_data)
            return await parser_func(tx_details, accounts, parsed_data, collection_address, timestamp)
        except Exception as e:
            logger.error(f"Error parsing ME V2 instruction {discriminator.hex()}: {e}", exc_info=True)
            return None

    async def _parse_me_v2_execute_sale(self, tx_details: dict, accounts: list, 
                                       parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse ME V2 executeSaleV2 instruction."""
        nft_transfer = next(
            (t for t in tx_details.get('tokenTransfers', []) 
             if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']), 
            None
        )
        if not nft_transfer:
            logger.warning("No NFT transfer found in executeSaleV2")
            return None
            
        return {
            'event_type': 'SALE',
            'mint_address': nft_transfer.get('mint'),
            'amount': parsed_data.buyer_price / 1e9,
            'buyer': nft_transfer.get('toUserAccount'),
            'seller': nft_transfer.get('fromUserAccount'),
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_v2',
            'traits': {}
        }

    async def _parse_me_v2_bid(self, tx_details: dict, accounts: list,
                               parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse ME V2 buyV2 instruction (buyer purchases NFT = SALE)."""
        # Find the NFT transfer to get accurate buyer/seller/mint info
        nft_transfer = next(
            (t for t in tx_details.get('tokenTransfers', [])
             if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']),
            None
        )

        if not nft_transfer:
            logger.warning("No NFT transfer found in buyV2")
            return None

        return {
            'event_type': 'SALE',
            'mint_address': nft_transfer.get('mint'),
            'amount': parsed_data.buyer_price / 1e9,
            'buyer': nft_transfer.get('toUserAccount'),
            'seller': nft_transfer.get('fromUserAccount'),
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_v2',
            'traits': {}
        }

    async def _parse_me_v2_listing(self, tx_details: Dict, accounts: list, 
                                parsed_data: Any, collection: str, ts: Any) -> Optional[Dict]:
        """
        Parse Magic Eden V2 MIP1 Sell (listing) instruction.
        Handles both mip1_sell and core_sell variants.
        """
        final_collection_address = collection
        nft_mint = ''
        
        try:
            # Extract NFT mint from accounts
            if len(accounts) < 5:
                logger.error("[_parse_me_v2_listing] Not enough accounts")
                return None
            
            seller = accounts[0]  # Wallet (signer)
            nft_mint = accounts[4]  # Token Mint
            
            logger.info(f"[_parse_me_v2_listing] NFT mint: {nft_mint}, Seller: {seller}")
            
            # Extract price from parsed data
            price = 0
            if hasattr(parsed_data, 'args') and hasattr(parsed_data.args, 'price'):
                price = parsed_data.args.price / 1e9
            elif hasattr(parsed_data, 'price'):
                price = parsed_data.price / 1e9
            
            logger.info(f"[_parse_me_v2_listing] Price: {price} SOL")
            
            # Resolve collection from NFT mint
            final_collection_address = await self._lookup_collection_in_db(nft_mint)
            
            if not final_collection_address:
                final_collection_address = await self._extract_collection_from_transaction(tx_details, nft_mint)
            
            if not final_collection_address:
                final_collection_address = await self._fetch_collection_from_metadata(nft_mint)
            
            if final_collection_address:
                logger.info(f"[_parse_me_v2_listing] ✅ Resolved collection: {final_collection_address}")
            else:
                logger.warning(f"[_parse_me_v2_listing] Could not resolve collection")
                final_collection_address = collection  # Fallback
            
        except Exception as e:
            logger.error(f"[_parse_me_v2_listing] Error: {e}", exc_info=True)
            final_collection_address = collection
        
        return {
            'event_type': 'LISTING',
            'mint_address': nft_mint,
            'amount': price,
            'buyer': '',
            'seller': seller,
            'timestamp': ts,
            'collection_address': final_collection_address,
            'marketplace': 'magic_eden_v2',
            'traits': {}
        }

    async def _parse_magic_eden_mip1_sell(self, tx_details: dict, accounts: list, 
                                        parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """
        Parse Magic Eden V2 MIP1 Sell (listing) instruction.
        
        Account structure:
        accounts[0] = Seller/Wallet
        accounts[1] = Notary
        accounts[2] = Program as Signer
        accounts[3] = Token Account (where NFT is stored)
        accounts[4] = Token Mint (NFT mint address)
        accounts[5] = Metadata
        accounts[6] = Auction House
        accounts[7] = Seller Trade State
        ...
        """
        final_collection_address = collection
        nft_mint = ''
        
        try:
            # 1. Extract NFT mint from accounts[4]
            if len(accounts) < 5:
                logger.error("[_parse_magic_eden_mip1_sell] Not enough accounts")
                return None
            
            seller = accounts[0]
            nft_mint = accounts[4]
            token_account = accounts[3]
            
            logger.info(f"[_parse_magic_eden_mip1_sell] NFT mint: {nft_mint}")
            logger.info(f"[_parse_magic_eden_mip1_sell] Seller: {seller}")
            logger.info(f"[_parse_magic_eden_mip1_sell] Token account: {token_account}")
            
            # 2. Extract price from parsed data or logs
            price = 0
            if hasattr(parsed_data, 'args') and hasattr(parsed_data.args, 'price'):
                price = parsed_data.args.price / 1e9
                logger.info(f"[_parse_magic_eden_mip1_sell] Price from args: {price} SOL")
            else:
                # Try extracting from logs
                logs = tx_details.get('meta', {}).get('logMessages', [])
                for log in logs:
                    if '"price":' in log:
                        import json
                        import re
                        # Extract JSON from log
                        match = re.search(r'\{.*"price":\s*(\d+).*\}', log)
                        if match:
                            price = int(match.group(1)) / 1e9
                            logger.info(f"[_parse_magic_eden_mip1_sell] Price from logs: {price} SOL")
                            break
            
            # 3. Resolve collection from NFT mint
            final_collection_address = await self._lookup_collection_in_db(nft_mint)
            
            if not final_collection_address:
                final_collection_address = await self._extract_collection_from_transaction(tx_details, nft_mint)
            
            if not final_collection_address:
                final_collection_address = await self._fetch_collection_from_metadata(nft_mint)
            
            if final_collection_address:
                logger.info(f"[_parse_magic_eden_mip1_sell] ✅ Resolved collection: {final_collection_address}")
            else:
                logger.warning(f"[_parse_magic_eden_mip1_sell] Could not resolve collection")
                final_collection_address = collection
            
        except Exception as e:
            logger.error(f"[_parse_magic_eden_mip1_sell] Error: {e}", exc_info=True)
            final_collection_address = collection
        
        # 4. Build event
        return {
            'event_type': 'LISTING',
            'mint_address': nft_mint,
            'amount': price,
            'buyer': '',
            'seller': seller,
            'timestamp': ts,
            'collection_address': final_collection_address,
            'marketplace': 'magic_eden_v2',
            'traits': {}
        }

    async def _parse_me_v2_cancel_sell(self, tx_details: dict, accounts: list, 
                                       parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse ME V2 cancelSell instruction."""
        nft_transfer = next(
            (t for t in tx_details.get('tokenTransfers', []) 
             if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']), 
            None
        )
        
        mint_address = nft_transfer.get('mint') if nft_transfer else (accounts[4] if len(accounts) > 4 else '')
        
        return {
            'event_type': 'CANCEL_LISTING',
            'mint_address': mint_address,
            'amount': 0,
            'buyer': '',
            'seller': accounts[0] if accounts else '',
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_v2',
            'traits': {}
        }

    async def _parse_me_v2_deposit(self, tx_details: dict, accounts: list, 
                                   parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse ME V2 deposit instruction (deposit SOL to escrow for bidding)."""
        return {
            'event_type': 'POOL_DEPOSIT',
            'mint_address': '',
            'amount': parsed_data.amount / 1e9,
            'buyer': accounts[0] if accounts else '',
            'seller': '',
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_v2',
            'traits': {}
        }

    async def _parse_me_v2_withdraw(self, tx_details: dict, accounts: list, 
                                    parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse ME V2 withdraw instruction (withdraw SOL from escrow)."""
        return {
            'event_type': 'POOL_WITHDRAW',
            'mint_address': '',
            'amount': parsed_data.amount / 1e9,
            'buyer': accounts[0] if accounts else '',
            'seller': '',
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_v2',
            'traits': {}
        }

    async def _parse_me_v2_mip1_cancel_sell(self, tx_details: dict, accounts: list, 
                                            parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse ME V2 mip1CancelSell instruction."""
        nft_transfer = next(
            (t for t in tx_details.get('tokenTransfers', []) 
             if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']), 
            None
        )
        
        mint_address = nft_transfer.get('mint') if nft_transfer else ''
        seller = nft_transfer.get('toUserAccount') if nft_transfer else (accounts[0] if accounts else '')
        
        return {
            'event_type': 'CANCEL_LISTING',
            'mint_address': mint_address,
            'amount': 0,
            'buyer': '',
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_v2',
            'traits': {}
        }

    async def _parse_me_v2_mip1_execute_sale(self, tx_details: dict, accounts: list, 
                                             parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse ME V2 mip1ExecuteSaleV2 instruction."""
        nft_transfer = next(
            (t for t in tx_details.get('tokenTransfers', []) 
             if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']), 
            None
        )
        
        if not nft_transfer:
            logger.warning("No NFT transfer found in mip1ExecuteSaleV2")
            return None
        
        return {
            'event_type': 'SALE',
            'mint_address': nft_transfer.get('mint'),
            'amount': parsed_data.args.price / 1e9,
            'buyer': nft_transfer.get('toUserAccount'),
            'seller': nft_transfer.get('fromUserAccount'),
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_v2',
            'traits': {}
        }

    async def _parse_me_v2_core_cancel_sell(self, tx_details: dict, accounts: list, 
                                            parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse ME V2 coreCancelSell instruction."""
        mint_address = accounts[4] if len(accounts) > 4 else ''
        seller = accounts[1] if len(accounts) > 1 else ''
        
        return {
            'event_type': 'CANCEL_LISTING',
            'mint_address': mint_address,
            'amount': 0,
            'buyer': '',
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_v2',
            'traits': {}
        }

    async def _parse_me_v2_core_execute_sale(self, tx_details: dict, accounts: list, 
                                             parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse ME V2 coreExecuteSaleV2 instruction."""
        # Extract price from native transfers
        price_lamports = max(
            (t.get('amount', 0) for t in tx_details.get('nativeTransfers', [])),
            default=0
        )
        
        mint_address = accounts[5] if len(accounts) > 5 else ''
        buyer = accounts[1] if len(accounts) > 1 else ''
        seller = accounts[2] if len(accounts) > 2 else ''
        
        return {
            'event_type': 'SALE',
            'mint_address': mint_address,
            'amount': price_lamports / 1e9,
            'buyer': buyer,
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_v2',
            'traits': {}
        }

    async def _parse_me_v2_update_auction_house(self, tx_details: dict, accounts: list, 
                                                parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse ME V2 updateAuctionHouse instruction (admin operation, not tracked)."""
        logger.debug("Ignoring ME V2 UpdateAuctionHouse admin instruction")
        return None

    # ===================================================================
    # MAGIC EDEN MMM PARSERS
    # ===================================================================

    async def _parse_me_mmm_instruction(self, tx_details: Dict, ix: Dict, decoded_data: bytes,
                                       collection_address: str, timestamp: Any) -> Optional[Dict]:
        """
        Parse Magic Eden MMM (M3) instruction using discriminator matching.
        
        Handles pool operations (buy/sell) and liquidity management.
        """
        if len(decoded_data) < 8:
            logger.warning("MMM instruction data too short")
            return None
            
        discriminator = decoded_data[:8]
        accounts = ix.get('accounts', [])
        
        # Discriminator → (parser_function, layout) mapping
        mmm_parsers = {
            # Sale/Buy fulfillment variants
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['sol_fulfill_sell']: 
                (self._parse_mmm_sale, ME_MMM_SOL_FULFILL_SELL_LAYOUT_V2),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['sol_mip1_fulfill_sell']: 
                (self._parse_mmm_sale, ME_MMM_SOL_MIP1_FULFILL_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['sol_ocp_fulfill_sell']: 
                (self._parse_mmm_sale, ME_MMM_SOL_OCP_FULFILL_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['sol_ext_fulfill_sell']: 
                (self._parse_mmm_sale, ME_MMM_SOL_EXT_FULFILL_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['sol_mpl_core_fulfill_sell']: 
                (self._parse_mmm_sale, ME_MMM_SOL_MPL_CORE_FULFILL_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['sol_ext_fulfill_buy']: 
                (self._parse_mmm_sale, ME_MMM_SOL_EXT_FULFILL_BUY_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['sol_ocp_fulfill_buy']: 
                (self._parse_mmm_sale, ME_MMM_SOL_OCP_FULFILL_BUY_LAYOUT),
            
            # cNFT operations
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['cnft_fulfill_buy']: 
                (self._parse_mmm_cnft_buy, ME_MMM_CNFT_FULFILL_BUY_LAYOUT),
            
            # Deposit/Withdraw NFT operations
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['deposit_sell']: 
                (self._parse_mmm_deposit_sell, ME_MMM_DEPOSIT_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['ext_deposit_sell']: 
                (self._parse_mmm_deposit_sell, ME_MMM_EXT_DEPOSIT_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['mpl_core_deposit_sell']: 
                (self._parse_mmm_deposit_sell, ME_MMM_MPL_CORE_DEPOSIT_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['mip1_withdraw_sell']: 
                (self._parse_mmm_withdraw_sell, ME_MMM_MIP1_WITHDRAW_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['mpl_core_withdraw_sell']: 
                (self._parse_mmm_withdraw_sell, ME_MMM_MPL_CORE_WITHDRAW_SELL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['ocp_withdraw_sell']: 
                (self._parse_mmm_withdraw_sell, ME_MMM_OCP_WITHDRAW_SELL_LAYOUT),
                # V2 versions (same handler)
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['update_pool_v2']: 
                (self._parse_mmm_pool_change, ME_MMM_UPDATE_POOL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['set_shared_escrow_v2']: 
                (self._parse_mmm_pool_change, ME_MMM_SET_SHARED_ESCROW_LAYOUT),
            
            # SOL deposit/withdraw operations
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['sol_deposit_buy']: 
                (self._parse_mmm_sol_deposit_buy, ME_MMM_SOL_DEPOSIT_BUY_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['sol_withdraw_buy']: 
                (self._parse_mmm_sol_withdraw_buy, ME_MMM_SOL_WITHDRAW_BUY_LAYOUT),
            
            # Pool management (admin operations)
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['create_pool']: 
                (self._parse_mmm_pool_change, ME_MMM_CREATE_POOL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['update_pool']: 
                (self._parse_mmm_pool_change, ME_MMM_UPDATE_POOL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['set_shared_escrow']: 
                (self._parse_mmm_pool_change, ME_MMM_SET_SHARED_ESCROW_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['magic_eden_mmm']['update_allowlists']: 
                (self._parse_mmm_pool_change, ME_MMM_UPDATE_ALLOWLISTS_LAYOUT),
        }
        
        parser_tuple = mmm_parsers.get(discriminator)
        if not parser_tuple:
            logger.warning(f"Unknown MMM discriminator: {discriminator.hex()}")
            return None
            
        parser_func, layout = parser_tuple
        try:
            parsed_data = layout.parse(decoded_data)
            return await parser_func(tx_details, accounts, parsed_data, collection_address, timestamp)
        except Exception as e:
            logger.error(f"Error parsing MMM instruction {discriminator.hex()}: {e}", exc_info=True)
            return None

    async def _parse_mmm_sale(self, tx_details: dict, accounts: list, 
                              parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """
        Parse MMM sale instruction (handles all fulfill_buy/fulfill_sell variants).
        
        Works for: solFulfillSell, solMip1FulfillSell, solOcpFulfillSell, 
                   solExtFulfillSell, solMplCoreFulfillSell, solExtFulfillBuy, solOcpFulfillBuy
        """
        # Find the NFT transfer
        nft_transfer = next(
            (t for t in tx_details.get('tokenTransfers', []) 
             if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']), 
            None
        )
        
        if not nft_transfer:
            logger.warning("No NFT transfer found in MMM sale")
            return None
        
        # Extract price from native transfers (most reliable for MMM)
        price_lamports = max(
            (t.get('amount', 0) for t in tx_details.get('nativeTransfers', []) 
             if t.get('type') == 'credit'),
            default=0
        )
        
        return {
            'event_type': 'SALE',
            'mint_address': nft_transfer.get('mint'),
            'amount': price_lamports / 1e9,
            'buyer': nft_transfer.get('toUserAccount'),
            'seller': nft_transfer.get('fromUserAccount'),
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_mmm',
            'traits': {}
        }

    async def _parse_mmm_cnft_buy(self, tx_details: dict, accounts: list, 
                                  parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse MMM cNFT fulfill buy instruction."""
        # Extract price from native transfers
        price_lamports = max(
            (t.get('amount', 0) for t in tx_details.get('nativeTransfers', [])),
            default=0
        )
        
        # For cNFTs, the asset_id is in the parsed args
        asset_id = str(Pubkey(parsed_data.args.asset_id)) if hasattr(parsed_data, 'args') else ''
        
        buyer = accounts[2] if len(accounts) > 2 else ''
        seller = accounts[1] if len(accounts) > 1 else ''
        
        return {
            'event_type': 'SALE',
            'mint_address': asset_id,
            'amount': price_lamports / 1e9,
            'buyer': buyer,
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_mmm',
            'traits': {}
        }

    async def _parse_mmm_deposit_sell(self, tx_details: dict, accounts: list, 
                                      parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """
        Parse MMM deposit sell instruction (deposit NFT into pool).
        
        Works for: depositSell, extDepositSell, mplCoreDepositSell
        """
        # Find the NFT being deposited
        nft_transfer = next(
            (t for t in tx_details.get('tokenTransfers', []) 
             if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']), 
            None
        )
        
        if not nft_transfer:
            logger.warning("No NFT transfer found in MMM deposit sell")
            return None
        
        # Extract asset amount if available
        asset_amount = 1  # Default for NFTs
        if hasattr(parsed_data, 'args') and hasattr(parsed_data.args, 'asset_amount'):
            asset_amount = parsed_data.args.asset_amount
        
        return {
            'event_type': 'POOL_DEPOSIT',
            'mint_address': nft_transfer.get('mint'),
            'amount': asset_amount,
            'buyer': '',
            'seller': accounts[0] if accounts else '',
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_mmm',
            'traits': {}
        }

    async def _parse_mmm_withdraw_sell(self, tx_details: dict, accounts: list, 
                                       parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """
        Parse MMM withdraw sell instruction (withdraw NFT from pool).
        
        Works for: mip1WithdrawSell, mplCoreWithdrawSell, ocpWithdrawSell
        """
        # Find the NFT being withdrawn
        nft_transfer = next(
            (t for t in tx_details.get('tokenTransfers', []) 
             if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']), 
            None
        )
        
        if not nft_transfer:
            logger.warning("No NFT transfer found in MMM withdraw sell")
            return None
        
        # Extract asset amount if available
        asset_amount = 1  # Default for NFTs
        if hasattr(parsed_data, 'args') and hasattr(parsed_data.args, 'asset_amount'):
            asset_amount = parsed_data.args.asset_amount
        
        return {
            'event_type': 'POOL_WITHDRAW',
            'mint_address': nft_transfer.get('mint'),
            'amount': asset_amount,
            'buyer': '',
            'seller': accounts[0] if accounts else '',
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_mmm',
            'traits': {}
        }

    async def _parse_mmm_sol_deposit_buy(self, tx_details: dict, accounts: list, 
                                         parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse MMM SOL deposit buy instruction (deposit SOL into buy pool)."""
        payment_amount = parsed_data.args.payment_amount / 1e9 if hasattr(parsed_data, 'args') else 0
        
        return {
            'event_type': 'POOL_DEPOSIT',
            'mint_address': '',
            'amount': payment_amount,
            'buyer': accounts[0] if accounts else '',
            'seller': '',
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_mmm',
            'traits': {}
        }

    async def _parse_mmm_sol_withdraw_buy(self, tx_details: dict, accounts: list, 
                                          parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse MMM SOL withdraw buy instruction (withdraw SOL from buy pool)."""
        payment_amount = parsed_data.args.payment_amount / 1e9 if hasattr(parsed_data, 'args') else 0
        
        return {
            'event_type': 'POOL_WITHDRAW',
            'mint_address': '',
            'amount': payment_amount,
            'buyer': accounts[0] if accounts else '',
            'seller': '',
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'magic_eden_mmm',
            'traits': {}
        }

    async def _parse_mmm_pool_change(self, tx_details: dict, accounts: list, 
                                     parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """
        Parse MMM pool management instructions (admin operations, not tracked).
        
        Works for: createPool, updatePool, setSharedEscrow, updateAllowlists
        """
        logger.debug("Ignoring MMM pool management admin instruction")
        return None

    # ===================================================================
    # TENSOR cNFT MARKETPLACE PARSERS
    # ===================================================================

    async def _parse_tensor_cnft_instruction(self, tx_details: Dict, ix: Dict, decoded_data: bytes,
                                            collection_address: str, timestamp: Any) -> Optional[Dict]:
        """
        Parse Tensor cNFT Marketplace (TComp) instruction using discriminator matching.
        
        Handles listing, buying, bidding operations for compressed NFTs and Core assets.
        """
        if len(decoded_data) < 8:
            logger.warning("Tensor cNFT instruction data too short")
            return None
            
        discriminator = decoded_data[:8]
        accounts = ix.get('accounts', [])
        
        # Discriminator → (parser_function, layout) mapping
        tensor_cnft_parsers = {
            # Buy operations
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['buy']: 
                (self._parse_tensor_cnft_buy, TCOMP_BUY_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['buy_spl']: 
                (self._parse_tensor_cnft_buy, TENSOR_CNFT_BUY_SPL_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['buy_core']: 
                (self._parse_tensor_cnft_buy_core, TENSOR_CNFT_BUY_CORE_LAYOUT),
            
            # List operations
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['list']: 
                (self._parse_tensor_cnft_list, TENSOR_CNFT_LIST_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['list_core']: 
                (self._parse_tensor_cnft_list_core, TENSOR_CNFT_LIST_CORE_LAYOUT),
            
            # Delist operations
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['delist']: 
                (self._parse_tensor_cnft_delist, TENSOR_CNFT_DELIST_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['delist_core']: 
                (self._parse_tensor_cnft_delist_core, TENSOR_CNFT_DELIST_CORE_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['close_expired_listing']: 
                (self._parse_tensor_cnft_delist, TENSOR_CNFT_CLOSE_EXPIRED_LISTING_LAYOUT),
            
            # Bid operations
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['bid']: 
                (self._parse_tensor_cnft_bid, TENSOR_CNFT_BID_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['cancel_bid']: 
                (self._parse_tensor_cnft_cancel_bid, TENSOR_CNFT_CANCEL_BID_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['cancel_bid_v2']: \
                (self._parse_tensor_cnft_cancel_bid, TENSOR_CNFT_CANCEL_BID_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['close_expired_bid']: 
                (self._parse_tensor_cnft_cancel_bid, TENSOR_CNFT_CLOSE_EXPIRED_BID_LAYOUT),
            
            # Take bid operations (multiple variants)
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['take_bid_legacy']: 
                (self._parse_tensor_take_bid, TENSOR_CNFT_TAKE_BID_LEGACY_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['take_bid_t22']: 
                (self._parse_tensor_take_bid, TENSOR_CNFT_TAKE_BID_T22_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['take_bid_wns']: 
                (self._parse_tensor_take_bid, TENSOR_CNFT_TAKE_BID_WNS_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['take_bid_meta_hash']: 
                (self._parse_tensor_cnft_take_bid_meta_hash, TENSOR_CNFT_TAKE_BID_META_HASH_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['take_bid_full_meta']: 
                (self._parse_tensor_take_bid, TENSOR_CNFT_TAKE_BID_FULL_META_LAYOUT),
            
            # Edit operations
            MARKETPLACE_DISCRIMINATORS['tensor_cnft_marketplace']['edit']: 
                (self._parse_tensor_cnft_edit, TENSOR_CNFT_EDIT_LAYOUT),
        }
        
        parser_tuple = tensor_cnft_parsers.get(discriminator)
        if not parser_tuple:
            logger.warning(f"Unknown Tensor cNFT discriminator: {discriminator.hex()}")
            return None
            
        parser_func, layout = parser_tuple
        try:
            parsed_data = layout.parse(decoded_data)
            return await parser_func(tx_details, accounts, parsed_data, collection_address, timestamp)
        except Exception as e:
            logger.error(f"Error parsing Tensor cNFT instruction {discriminator.hex()}: {e}", exc_info=True)
            return None

    async def _parse_tensor_cnft_buy(self, tx_details: dict, accounts: list, 
                                     parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse Tensor cNFT buy instruction."""
        # Extract price from native transfers, filtering for the seller's receipt
        seller_account = accounts[11] if len(accounts) > 11 else ''
        price_lamports = max(
            (t.get('amount', 0) for t in tx_details.get('nativeTransfers', []) 
             if t.get('userAccount') == seller_account and t.get('type') == 'credit'),
            default=0
        )
        
        buyer = accounts[9] if len(accounts) > 9 else ''
        seller = accounts[11] if len(accounts) > 11 else ''
        
        return {
            'event_type': 'SALE',
            'mint_address': '',  # cNFT doesn't have traditional mint
            'amount': price_lamports / 1e9,
            'buyer': buyer,
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'tensor',
            'traits': {}
        }

    async def _parse_tensor_cnft_buy_core(self, tx_details: dict, accounts: list, 
                                          parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse Tensor Core asset buy instruction."""
        # Extract price from native transfers to seller
        seller_account = accounts[6] if len(accounts) > 6 else ''
        price_lamports = max(
            (t.get('amount', 0) for t in tx_details.get('nativeTransfers', []) 
             if t.get('userAccount') == seller_account and t.get('type') == 'credit'),
            default=0
        )
        
        mint_address = accounts[2] if len(accounts) > 2 else ''
        buyer = accounts[4] if len(accounts) > 4 else ''
        seller = accounts[6] if len(accounts) > 6 else ''
        
        return {
            'event_type': 'SALE',
            'mint_address': mint_address,
            'amount': price_lamports / 1e9,
            'buyer': buyer,
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'tensor',
            'traits': {}
        }

    async def _parse_tensor_cnft_list(self, tx_details: dict, accounts: list, 
                                      parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse Tensor cNFT list instruction."""
        amount = parsed_data.amount / 1e9 if hasattr(parsed_data, 'amount') else 0
        seller = accounts[1] if len(accounts) > 1 else ''
        
        return {
            'event_type': 'LISTING',
            'mint_address': '',  # cNFT doesn't have traditional mint
            'amount': amount,
            'buyer': '',
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'tensor',
            'traits': {}
        }

    async def _parse_tensor_cnft_list_core(self, tx_details: dict, accounts: list, 
                                           parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse Tensor Core asset list instruction."""
        amount = parsed_data.amount / 1e9 if hasattr(parsed_data, 'amount') else 0
        mint_address = accounts[0] if accounts else ''
        seller = accounts[3] if len(accounts) > 3 else ''
        
        return {
            'event_type': 'LISTING',
            'mint_address': mint_address,
            'amount': amount,
            'buyer': '',
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'tensor',
            'traits': {}
        }

    async def _parse_tensor_cnft_delist(self, tx_details: dict, accounts: list, 
                                        parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse Tensor cNFT delist instruction."""
        seller = accounts[1] if len(accounts) > 1 else ''
        
        return {
            'event_type': 'CANCEL_LISTING',
            'mint_address': '',
            'amount': 0,
            'buyer': '',
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'tensor',
            'traits': {}
        }

    async def _parse_tensor_cnft_delist_core(self, tx_details: dict, accounts: list, 
                                             parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse Tensor Core asset delist instruction."""
        mint_address = accounts[0] if accounts else ''
        seller = accounts[2] if len(accounts) > 2 else ''
        
        return {
            'event_type': 'CANCEL_LISTING',
            'mint_address': mint_address,
            'amount': 0,
            'buyer': '',
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'tensor',
            'traits': {}
        }


    async def _parse_tensor_cnft_bid(self, tx_details: dict, accounts: list, 
                                    parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """
        Parse Tensor cNFT bid instruction.
        Handles BOTH collection-wide bids (whitelist) and direct NFT bids (token account).
        """
        final_collection_address = collection  # Default fallback
        target_address = ''
        nft_mint = ''  # For direct NFT bids
        
        try:
            # 1. Extract the target_id (could be whitelist OR token account)
            if hasattr(parsed_data, 'target_id'):
                target_id_pubkey = Pubkey(parsed_data.target_id)
                target_address = str(target_id_pubkey)
                logger.info(f"[_parse_tensor_cnft_bid] Extracted target address (target_id): {target_address}")
            else:
                logger.error("[_parse_tensor_cnft_bid] Could not find 'target_id' in parsed instruction data.")
                return None

            if not target_address:
                return None

            # 2. Fetch the on-chain account to determine its type
            provider = await self.provider_manager.get_rpc_provider(target_address)
            if not provider:
                logger.error(f"[_parse_tensor_cnft_bid] Could not get provider")
                raise Exception("Provider not available")

            logger.debug(f"[_parse_tensor_cnft_bid] Fetching account info for {target_address}...")
            account_info = await provider.get_account_info(target_address)
            
            if not account_info or not account_info.get('value'):
                logger.error(f"[_parse_tensor_cnft_bid] Could not fetch account info for {target_address}")
                raise Exception("Account info not available")

            account_value = account_info['value']
            owner = account_value.get('owner')
            logger.info(f"[_parse_tensor_cnft_bid] Target account {target_address} is owned by: {owner}")

            # 3. Decode the account data
            import base64
            import struct
            
            raw_data = base64.b64decode(account_value['data'][0])
            logger.debug(f"[_parse_tensor_cnft_bid] Raw account data length: {len(raw_data)} bytes")

            # 4. Determine if this is a COLLECTION BID or DIRECT NFT BID
            if owner == 'TL1ST2iRBzuGTqLn1KXnGdSnEow62BzPnGiqyRXhWtW':
                # ✅ COLLECTION BID - Parse whitelist to get collection address
                logger.info(f"[_parse_tensor_cnft_bid] 🎯 COLLECTION BID detected (whitelist)")
                final_collection_address = await self._parse_whitelist_for_collection(raw_data, target_address)
                
            elif owner == 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA':
                # ✅ DIRECT NFT BID - Parse token account to get NFT mint
                logger.info(f"[_parse_tensor_cnft_bid] 🎯 DIRECT NFT BID detected (token account)")
                nft_mint, final_collection_address = await self._parse_token_account_for_nft(raw_data, target_address, tx_details)
                
            else:
                logger.error(f"[_parse_tensor_cnft_bid] Unknown target owner: {owner}")
                raise Exception(f"Unsupported owner program: {owner}")

            if not final_collection_address:
                logger.error(f"[_parse_tensor_cnft_bid] Could not resolve collection address")
                raise Exception("Collection resolution failed")

            logger.info(f"[_parse_tensor_cnft_bid] ✅ SUCCESS: Collection={final_collection_address}, NFT={nft_mint or 'collection-wide'}")

        except Exception as e:
            logger.error(f"[_parse_tensor_cnft_bid] CRITICAL FAILURE: {e}", exc_info=True)
            final_collection_address = collection  # Fallback

        # 5. Build the event
        amount = parsed_data.amount / 1e9 if hasattr(parsed_data, 'amount') else 0
        buyer = accounts[3] if len(accounts) > 3 else ''
        
        return {
            'event_type': 'BID',
            'mint_address': nft_mint,  # Empty for collection bids, filled for direct NFT bids
            'amount': amount,
            'buyer': buyer,
            'seller': '',
            'timestamp': ts,
            'collection_address': final_collection_address,
            'marketplace': 'tensor',
            'traits': {}
        }



    async def _parse_tensor_cnft_cancel_bid(self, tx_details: dict, accounts: list, 
                                    parsed_data: Any, collection: str, ts: Any) -> Optional[Dict]:
        """
        Parse Tensor cNFT cancel bid instruction.
        
        Account structure:
        accounts[0] = Bid State (PDA containing bid info)
        accounts[1] = Owner/Bidder (who placed the bid)
        accounts[2] = System Program
        accounts[3] = Tcomp Program
        accounts[4] = Rent Dest
        """
        final_collection_address = collection
        bidder = ''
        
        try:
            if len(accounts) < 2:
                logger.error("[_parse_tensor_cancel_bid] Not enough accounts")
                return None
            
            bid_state_account = accounts[0]
            bidder = accounts[1]
            
            logger.info(f"[_parse_tensor_cancel_bid] Bid State: {bid_state_account}, Bidder: {bidder}")
            
            # Try to fetch the Bid State account to get collection info
            provider = await self.provider_manager.get_rpc_provider()
            if provider:
                try:
                    bid_state_info = await provider.get_account_info(bid_state_account)
                    if bid_state_info and bid_state_info.get('value'):
                        import base64
                        raw_data = base64.b64decode(bid_state_info['value']['data'][0])
                        logger.debug(f"[_parse_tensor_cancel_bid] Bid State data: {len(raw_data)} bytes")
                        
                        # Bid State structure (similar to List State):
                        # - discriminator (8 bytes)
                        # - version (1 byte)
                        # - bump (Vec<u8>)
                        # - owner (32 bytes)
                        # - target (1 byte enum)
                        # - target_id (32 bytes) - This could be collection or whitelist
                        
                        # Try to extract target_id (collection/whitelist address)
                        # This is a simplified approach - full parsing would need proper struct
                        if len(raw_data) >= 74:  # discriminator + version + minimal data
                            # Target_id is typically around byte 42-74 (varies with bump length)
                            # For now, we'll skip detailed parsing since we don't know exact structure
                            logger.debug("[_parse_tensor_cancel_bid] Bid State account found but parsing not implemented")
                except Exception as e:
                    logger.debug(f"[_parse_tensor_cancel_bid] Could not fetch/parse Bid State: {e}")
            
            # If collection not resolved, use fallback
            if not final_collection_address or final_collection_address == 'unknown':
                logger.warning("[_parse_tensor_cancel_bid] Could not resolve collection from Bid State")
                final_collection_address = collection
            
        except Exception as e:
            logger.error(f"[_parse_tensor_cancel_bid] Error: {e}", exc_info=True)
            final_collection_address = collection
        
        # Build event
        return {
            'event_type': 'BID_CANCELLED',
            'mint_address': '',  # Cancel bid doesn't have specific NFT mint
            'amount': 0,  # No price info in cancel
            'buyer': bidder,
            'seller': '',
            'timestamp': ts,
            'collection_address': final_collection_address,
            'marketplace': 'tensor',
            'traits': {}
        }

    async def _parse_tensor_take_bid(self, tx_details: dict, accounts: list, 
                                     parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """
        Parse Tensor take bid instruction (generic handler for legacy, T22, WNS, full_meta variants).
        """
        # Find NFT transfer
        nft_transfer = next(
            (t for t in tx_details.get('tokenTransfers', []) 
             if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']), 
            None
        )
        
        if not nft_transfer:
            logger.warning("No NFT transfer found in Tensor take bid")
            return None
        
        # Extract minimum amount from parsed data
        min_amount = 0
        if hasattr(parsed_data, 'min_amount'):
            min_amount = parsed_data.min_amount / 1e9
        elif hasattr(parsed_data, 'args') and hasattr(parsed_data.args, 'min_amount'):
            min_amount = parsed_data.args.min_amount / 1e9
        
        buyer = accounts[3] if len(accounts) > 3 else ''
        seller = accounts[1] if len(accounts) > 1 else ''
        
        return {
            'event_type': 'SALE',
            'mint_address': nft_transfer.get('mint'),
            'amount': min_amount,
            'buyer': buyer,
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'tensor',
            'traits': {}
        }

    async def _parse_tensor_cnft_take_bid_meta_hash(self, tx_details: dict, accounts: list, 
                                                     parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """Parse Tensor cNFT take bid with meta hash variant."""
        # Extract price (use both parsed min_amount and native transfers)
        price_from_parsed = parsed_data.min_amount / 1e9 if hasattr(parsed_data, 'min_amount') else 0
        price_from_transfers = max(
            (t.get('amount', 0) for t in tx_details.get('nativeTransfers', []) 
             if t.get('type') == 'credit'),
            default=0
        ) / 1e9
        
        # Use the minimum of the two (min_amount is the floor)
        final_price = min(price_from_parsed, price_from_transfers) if price_from_parsed > 0 else price_from_transfers
        
        buyer = accounts[12] if len(accounts) > 12 else ''
        seller = accounts[2] if len(accounts) > 2 else ''
        
        return {
            'event_type': 'SALE',
            'mint_address': '',  # cNFT
            'amount': final_price,
            'buyer': buyer,
            'seller': seller,
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'tensor',
            'traits': {}
        }

    async def _parse_tensor_cnft_edit(self, tx_details: dict, accounts: list, 
                                    parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """
        Parse Tensor cNFT edit (listing price change/update).
        """
        final_collection_address = collection
        nft_mint = ''
        
        try:
            if len(accounts) < 1:
                logger.error("[_parse_tensor_cnft_edit] No accounts found")
                return None
            
            list_state_account = accounts[0]
            seller = accounts[1] if len(accounts) > 1 else ''
            
            logger.info(f"[_parse_tensor_cnft_edit] List State: {list_state_account}, Seller: {seller}")
            
            # Fetch the List State account data
            provider = await self.provider_manager.get_rpc_provider()
            if not provider:
                raise Exception("Provider not available")
            
            list_state_info = await provider.get_account_info(list_state_account)
            if not list_state_info or not list_state_info.get('value'):
                raise Exception("List State not found")
            
            import base64
            import struct
            
            raw_data = base64.b64decode(list_state_info['value']['data'][0])
            logger.debug(f"[_parse_tensor_cnft_edit] List State data: {len(raw_data)} bytes")
            
            # ✅ FIX: More robust parsing with better error handling
            if len(raw_data) < 50:  # Minimum size check
                raise Exception(f"List State data too short: {len(raw_data)} bytes")
            
            offset = 8  # Skip discriminator
            
            # Read version
            if offset >= len(raw_data):
                raise Exception("Cannot read version")
            version = raw_data[offset]
            offset += 1
            logger.debug(f"[_parse_tensor_cnft_edit] Version: {version}")
            
            # Read bump Vec<u8>
            if offset + 4 > len(raw_data):
                raise Exception("Cannot read bump length")
            bump_len = struct.unpack('<I', raw_data[offset:offset+4])[0]
            offset += 4
            
            # ✅ FIX: Validate bump_len is reasonable
            if bump_len > 100:  # Bump should never be this large
                logger.error(f"[_parse_tensor_cnft_edit] Invalid bump_len: {bump_len}")
                raise Exception(f"Invalid bump length: {bump_len}")
            
            offset += bump_len
            logger.debug(f"[_parse_tensor_cnft_edit] Bump length: {bump_len}, offset after bump: {offset}")
            
            # ✅ FIX: Check if we have enough data left
            if offset + 32 > len(raw_data):
                logger.error(f"[_parse_tensor_cnft_edit] Not enough data for owner. Offset: {offset}, Data length: {len(raw_data)}")
                raise Exception(f"Data too short to read owner at offset {offset}")
            
            # Read owner (32 bytes)
            owner_bytes = raw_data[offset:offset+32]
            owner = str(Pubkey(owner_bytes))
            offset += 32
            logger.debug(f"[_parse_tensor_cnft_edit] Owner: {owner}")
            
            # Read assetId (32 bytes) - THIS IS THE NFT MINT!
            if offset + 32 > len(raw_data):
                raise Exception(f"Data too short to read assetId at offset {offset}")
            
            asset_bytes = raw_data[offset:offset+32]
            nft_mint = str(Pubkey(asset_bytes))
            logger.info(f"[_parse_tensor_cnft_edit] 🎨 Extracted NFT mint (assetId): {nft_mint}")
            
            # Resolve collection from NFT mint
            final_collection_address = await self._lookup_collection_in_db(nft_mint)
            
            if not final_collection_address:
                final_collection_address = await self._extract_collection_from_transaction(tx_details, nft_mint)
            
            if not final_collection_address:
                final_collection_address = await self._fetch_collection_from_metadata(nft_mint)
            
            if final_collection_address:
                logger.info(f"[_parse_tensor_cnft_edit] ✅ Resolved collection: {final_collection_address}")
            else:
                logger.warning(f"[_parse_tensor_cnft_edit] Could not resolve collection, using fallback")
                final_collection_address = collection
            
        except Exception as e:
            logger.error(f"[_parse_tensor_cnft_edit] Error: {e}", exc_info=True)
            final_collection_address = collection
        
        # Extract new price from instruction data
        amount = parsed_data.amount / 1e9 if hasattr(parsed_data, 'amount') else 0
        
        return {
            'event_type': 'LISTING_EDIT',
            'mint_address': nft_mint,
            'amount': amount,
            'buyer': '',
            'seller': seller,
            'timestamp': ts,
            'collection_address': final_collection_address,
            'marketplace': 'tensor',
            'traits': {}
        }

    # ===================================================================
    # TENSOR AMM PARSERS
    # ===================================================================

    async def _parse_tensor_amm_instruction(self, tx_details: Dict, ix: Dict, decoded_data: bytes,
                                           collection_address: str, timestamp: Any) -> Optional[Dict]:
        """
        Parse Tensor AMM instruction using discriminator matching.
        
        Handles buying NFTs from AMM pools.
        """
        if len(decoded_data) < 8:
            logger.warning("Tensor AMM instruction data too short")
            return None
            
        discriminator = decoded_data[:8]
        accounts = ix.get('accounts', [])
        
        # Discriminator → (parser_function, layout) mapping
        tensor_amm_parsers = {
            MARKETPLACE_DISCRIMINATORS['tensor_amm']['buy_nft']: 
                (self._parse_tensor_amm_sale, TENSOR_AMM_BUY_NFT_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_amm']['buy_nft_core']: 
                (self._parse_tensor_amm_sale, TENSOR_AMM_BUY_NFT_CORE_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['tensor_amm']['buy_nft_t22']: 
                (self._parse_tensor_amm_sale, TENSOR_AMM_BUY_NFT_T22_LAYOUT),
        }
        
        parser_tuple = tensor_amm_parsers.get(discriminator)
        if not parser_tuple:
            logger.warning(f"Unknown Tensor AMM discriminator: {discriminator.hex()}")
            return None
            
        parser_func, layout = parser_tuple
        try:
            parsed_data = layout.parse(decoded_data)
            return await parser_func(tx_details, accounts, parsed_data, collection_address, timestamp)
        except Exception as e:
            logger.error(f"Error parsing Tensor AMM instruction {discriminator.hex()}: {e}", exc_info=True)
            return None

    async def _parse_tensor_amm_sale(self, tx_details: dict, accounts: list, 
                                     parsed_data: Any, collection: str, ts: Any) -> Optional[dict]:
        """
        Parse Tensor AMM buy NFT instruction (all variants).
        
        Works for: buyNft, buyNftCore, buyNftT22
        """
        # Find NFT transfer
        nft_transfer = next(
            (t for t in tx_details.get('tokenTransfers', []) 
             if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']), 
            None
        )
        
        if not nft_transfer:
            logger.warning("No NFT transfer found in Tensor AMM sale")
            return None
        
        # Extract max_amount from parsed data (this is the price cap)
        max_amount = parsed_data.max_amount / 1e9 if hasattr(parsed_data, 'max_amount') else 0
        
        return {
            'event_type': 'SALE',
            'mint_address': nft_transfer.get('mint'),
            'amount': max_amount,
            'buyer': nft_transfer.get('toUserAccount'),
            'seller': nft_transfer.get('fromUserAccount'),
            'timestamp': ts,
            'collection_address': collection,
            'marketplace': 'tensor_amm',
            'traits': {}
        }

    # ===================================================================
    # TENSOR ESCROW PARSERS (Stub for now)
    # ===================================================================

    async def _parse_tensor_escrow_instruction(self, tx_details: Dict, ix: Dict, decoded_data: bytes,
                                               collection_address: str, timestamp: Any) -> Optional[Dict]:
        """
        Parse Tensor Escrow (TensorSwap) instruction.
        
        TODO: Implement when Tensor Escrow layouts are needed.
        Currently returns None as these are less common.
        """
        logger.debug("Tensor Escrow parsing not yet implemented")
        return None

    # ===================================================================
    # IMPROVED FALLBACK PARSER (TIER 3)
    # ===================================================================

    def _analyze_unknown_transaction(self, tx_data: dict) -> Optional[dict]:
        """
        Enhanced Tier 3: Smart transfer analysis with skip logic.
        
        Returns parsed event dict or None if should skip.
        """
        logger.info("🔍 Tier 3: Analyzing transaction via transfers and logs")
        
        # STEP 1: Use filter to check if valuable
        from .transaction_filter import TransactionFilter
        tx_filter = TransactionFilter()
        
        value_analysis = tx_filter.analyze_transaction_value(tx_data)

        if not value_analysis['is_valuable']:
            logger.info(f"Tier 3: Skipping - {value_analysis['reason']}")
            return {'_skipped': True, 'reason': value_analysis['reason']}
        
        logger.info(f"Tier 3: Transaction appears valuable - {value_analysis['reason']} (confidence: {value_analysis['confidence']})")
        
        # STEP 2: Extract transfer data
        token_transfers = tx_data.get("tokenTransfers", [])
        native_transfers = tx_data.get("nativeTransfers", [])
        log_messages = tx_data.get("logMessages", [])
        detected_event_type = tx_data.get("detected_event_type", "UNKNOWN")
        
        # STEP 3: Find NFT transfer
        nft_transfer = next(
            (t for t in token_transfers 
            if t.get("tokenStandard") in ["NonFungible", "NonFungibleEdition"] or t.get("tokenAmount") == 1),
            None
        )
        
        if not nft_transfer:
            logger.warning("Tier 3: No NFT transfer found despite valuable transaction")
            return None

        # STEP 4: Extract basic info
        nft_mint = nft_transfer.get("mint", "")
        buyer = nft_transfer.get("toUserAccount", "")
        seller = nft_transfer.get("fromUserAccount", "")
        
        logger.info(f"Tier 3: NFT Transfer - Mint: {nft_mint[:8]}..., {seller[:8]}... → {buyer[:8]}...")
        
        # STEP 5: Extract payment
        price_info = self._extract_price_from_native_transfers(native_transfers, buyer, seller)
        price_lamports = price_info['amount']
        confidence = price_info['confidence']
        
        logger.info(f"Tier 3: Price: {price_lamports / 1e9} SOL (confidence: {confidence})")
        
        # STEP 6: Determine event type intelligently
        event_type = self._determine_event_type_from_context(
            detected_event_type=detected_event_type,
            has_nft_transfer=True,
            price_lamports=price_lamports,
            log_messages=log_messages,
            buyer=buyer,
            seller=seller
        )
        
        # STEP 7: Check if we should skip this event type
        if tx_filter.should_skip_by_event_type(event_type):
            logger.info(f"Tier 3: Skipping event type: {event_type}")
            return None
        
        # STEP 8: Detect marketplace
        marketplace = 'unknown'
        program_ids = [ix.get('programId') for ix in tx_data.get('instructions', [])]
        for prog_id in program_ids:
            detected_marketplace = get_marketplace_from_program_id(prog_id)
            if detected_marketplace != 'unknown':
                marketplace = detected_marketplace
                break
        
        logger.info(f"Tier 3: Marketplace: {marketplace}")
        
        # STEP 9: Build result
        result = {
            'event_type': event_type,
            'mint_address': nft_mint,
            'amount': price_lamports / 1e9,
            'buyer': buyer,
            'seller': seller,
            'timestamp': tx_data.get('timestamp'),
            'collection_address': tx_data.get('collection_address', ''),
            'marketplace': marketplace,
            'traits': {},
            'confidence': min(confidence, value_analysis['confidence'])  # Use lowest confidence
        }
        
        logger.info(f"Tier 3: Result - {event_type}, {result['amount']} SOL, confidence: {result['confidence']}")
        return result

    def _determine_event_type_from_context(
        self,
        detected_event_type: str,
        has_nft_transfer: bool,
        price_lamports: int,
        log_messages: List[str],
        buyer: str,
        seller: str
    ) -> str:
        """
        Smart event type determination using multiple signals.
        
        Priority:
        1. Log-detected type (if not UNKNOWN)
        2. Price + transfer combination
        3. Log pattern analysis
        4. Default: TRANSFER
        """
        
        # Priority 1: Use log-detected type if available
        if detected_event_type != 'UNKNOWN':
            logger.debug(f"Using log-detected event type: {detected_event_type}")
            return detected_event_type
        
        # Priority 2: Analyze price + transfer
        if has_nft_transfer and price_lamports > 10_000_000:  # > 0.01 SOL
            logger.debug("Inferred SALE from NFT transfer + payment")
            return 'SALE'
        
        # Priority 3: Check logs for specific patterns
        log_text = ' '.join(log_messages).lower() if log_messages else ''
        
        # Check for withdraw patterns
        if 'withdraw' in log_text and has_nft_transfer:
            logger.debug("Detected POOL_WITHDRAW from logs")
            return 'POOL_WITHDRAW'
        
        # Check for deposit patterns  
        if 'deposit' in log_text and has_nft_transfer:
            logger.debug("Detected POOL_DEPOSIT from logs")
            return 'POOL_DEPOSIT'
        
        # Check for listing patterns
        if any(p in log_text for p in ['list', 'sell']) and not price_lamports:
            logger.debug("Detected LISTING from logs")
            return 'LISTING'
        
        # Check for delist patterns
        if any(p in log_text for p in ['delist', 'cancel']) and not price_lamports:
            logger.debug("Detected CANCEL_LISTING from logs")
            return 'CANCEL_LISTING'
        
        # Priority 4: Default to TRANSFER
        logger.debug("Defaulting to TRANSFER")
        return 'TRANSFER'

    def _extract_price_from_native_transfers(self, native_transfers: List[Dict], 
                                            buyer: str, seller: str) -> Dict:
        """
        Extract the most likely payment amount from native SOL transfers.
        
        Returns dict with 'amount' (lamports) and 'confidence' (0.0-1.0).
        """
        if not native_transfers:
            return {'amount': 0, 'confidence': 0.5}
        
        # Strategy 1: Find the largest credit to the seller
        seller_credits = [
            t.get('amount', 0) for t in native_transfers
            if t.get('userAccount') == seller and t.get('type') == 'credit'
        ]
        
        if seller_credits:
            max_credit = max(seller_credits)
            if max_credit > 5_000_000:  # More than 0.005 SOL
                return {'amount': max_credit, 'confidence': 0.9}
        
        # Strategy 2: Find the largest debit from the buyer
        buyer_debits = [
            abs(t.get('amount', 0)) for t in native_transfers
            if t.get('userAccount') == buyer and t.get('type') == 'debit'
        ]
        
        if buyer_debits:
            max_debit = max(buyer_debits)
            if max_debit > 5_000_000:
                return {'amount': max_debit, 'confidence': 0.85}
        
        # Strategy 3: Find any large credit (likely payment to seller)
        all_credits = [
            t.get('amount', 0) for t in native_transfers
            if t.get('type') == 'credit' and t.get('amount', 0) > 5_000_000
        ]
        
        if all_credits:
            return {'amount': max(all_credits), 'confidence': 0.7}
        
        # Strategy 4: Use the largest absolute transfer
        all_amounts = [abs(t.get('amount', 0)) for t in native_transfers]
        if all_amounts:
            max_amount = max(all_amounts)
            if max_amount > 5_000_000:
                return {'amount': max_amount, 'confidence': 0.6}
        
        # No significant payment found
        return {'amount': 0, 'confidence': 0.5}

    def _detect_event_type_from_logs(self, log_messages: List[str]) -> str:
        """
        Enhanced log analysis with early skip detection.
        
        Returns event type or 'SKIP' if should be ignored.
        """
        if not log_messages:
            return 'UNKNOWN'
        
        log_text = ' '.join(log_messages).lower()
        
        # CRITICAL: Check for admin/skip patterns FIRST
        skip_patterns = {
            'SKIP': [
                'instruction: updatepool',
                'instruction: createpool', 
                'instruction: setsharedescrow',
                'instruction: updateallowlists',
                'instruction: updateauctionhouse',
                'program log: post_update_pool',
                'program log: post_set_shared_escrow',
                'program log: post_create_pool',
            ]
        }
        
        for event_type, pattern_list in skip_patterns.items():
            for pattern in pattern_list:
                if pattern in log_text:
                    logger.debug(f"Log analysis detected skip pattern: '{pattern}'")
                    return event_type
        
        # Then check for valuable patterns (order by specificity)
        valuable_patterns = {
            'SALE': [
                'instruction: executesale',
                'instruction: fulfillsell',
                'instruction: fulfillbuy',
                'instruction: buynft',
                'instruction: takebid',
                'program log: sell_nft',
                'program log: buy_nft',
            ],
            'LISTING': [
                'instruction: list',
                'instruction: sell',
                'instruction: mip1sell',
                'instruction: coresell',
                'program log: list_nft',
            ],
            'CANCEL_LISTING': [
                'instruction: delist',
                'instruction: cancelsell',
                'instruction: cancellist',
                'program log: cancel_listing',
                'program log: delist_nft',
            ],
            'BID': [
                'instruction: bid',
                'instruction: makeoffer',
                'program log: place_bid',
            ],
            'BID_CANCELLED': [
                'instruction: cancelbid',
                'instruction: canceloffer',
                'program log: cancel_bid',
            ],
            'POOL_WITHDRAW': [
                'instruction: withdrawsell',
                'instruction: withdraw',
                'program log: withdraw_sell',
            ],
            'POOL_DEPOSIT': [
                'instruction: depositsell',
                'instruction: deposit',
                'program log: deposit_sell',
            ]
        }
        
        for event_type, pattern_list in valuable_patterns.items():
            for pattern in pattern_list:
                if pattern in log_text:
                    logger.debug(f"Log analysis detected {event_type} from pattern: '{pattern}'")
                    return event_type
        
        return 'UNKNOWN'

    # ===================================================================
    # HELPER & VALIDATION METHODS
    # ===================================================================

    def _validate_parsed_event(self, parsed_event: dict, signature: str) -> bool:
        """
        Validate parsed event data before saving to database.
        
        Returns True if event passes all validation checks, False otherwise.
        """
        try:
            # Check required fields
            if not parsed_event.get('event_type'):
                logger.error(f"[{signature}] Validation failed: Missing event_type")
                return False
            
            # Validate event type is in allowed list
            valid_event_types = ['SALE', 'LISTING', 'CANCEL_LISTING', 'BID', 'BID_CANCELLED', 
                                'TRANSFER', 'POOL_DEPOSIT', 'POOL_WITHDRAW', 'LISTING_UPDATE']
            if parsed_event['event_type'] not in valid_event_types:
                logger.error(f"[{signature}] Validation failed: Invalid event_type: {parsed_event['event_type']}")
                return False
            
            # Validate mint address for relevant event types
            relevant_events = ['SALE', 'LISTING', 'CANCEL_LISTING', 'BID', 'TRANSFER']
            if parsed_event['event_type'] in relevant_events:
                mint_address = parsed_event.get('mint_address', '')
                # Allow empty for cNFTs, but if present must be valid
                if mint_address and len(mint_address) < 32:
                    logger.warning(f"[{signature}] Validation warning: Suspicious mint_address length: {len(mint_address)}")
            
            # Validate amount is non-negative
            amount = parsed_event.get('amount', 0)
            if amount < 0:
                logger.error(f"[{signature}] Validation failed: Negative amount: {amount}")
                return False
            
            # Validate amount is reasonable (less than 1 million SOL)
            if amount > 1_000_000:
                logger.error(f"[{signature}] Validation failed: Unreasonably large amount: {amount}")
                return False
            
            # Validate buyer/seller for sale events
            if parsed_event['event_type'] == 'SALE':
                buyer = parsed_event.get('buyer', '')
                seller = parsed_event.get('seller', '')
                
                if not buyer or not seller:
                    logger.warning(f"[{signature}] Validation warning: SALE event missing buyer or seller")
                
                if buyer == seller and buyer:
                    logger.error(f"[{signature}] Validation failed: Buyer and seller are the same: {buyer}")
                    return False
            
            # Validate timestamp
            timestamp = parsed_event.get('timestamp')
            if timestamp:
                if isinstance(timestamp, (int, float)):
                    # Check it's not in the future or too far in the past
                    current_time = timezone.now().timestamp()
                    if timestamp > current_time + 3600:  # 1 hour future tolerance
                        logger.error(f"[{signature}] Validation failed: Timestamp in future")
                        return False
                    if timestamp < 1577836800:  # Before 2020
                        logger.error(f"[{signature}] Validation failed: Timestamp too old")
                        return False
            
            # Validate marketplace
            marketplace = parsed_event.get('marketplace', '')
            if not marketplace or marketplace == 'unknown':
                logger.warning(f"[{signature}] Validation warning: Unknown marketplace")
            
            logger.debug(f"[{signature}] Validation passed")
            return True
            
        except Exception as e:
            logger.error(f"[{signature}] Validation error: {e}", exc_info=True)
            return False

    def _prepare_event_defaults(self, parsed_event: dict, collection: NFTCollection, 
                                original_tx: dict) -> dict:
        """
        Prepare the defaults dict for NFTEvent.objects.update_or_create().
        
        Converts parsed event data into the format required by the Django model.
        """
        # Handle timestamp conversion
        timestamp = parsed_event.get('timestamp')
        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp, tz=dt_timezone.utc)
        elif isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                timestamp = timezone.now()
        elif not timestamp:
            timestamp = timezone.now()

        # Map parsed event_type to database EVENT_TYPE choices
        event_type_mapping = {
            'SALE': 'SALE',
            'LISTING': 'LISTING',
            'CANCEL_LISTING': 'DELISTING',
            'BID': 'BID',
            'BID_CANCELLED': 'BID_CANCEL',
            'TRANSFER': 'TRANSFER',
            'POOL_DEPOSIT': 'DEPOSIT',
            'POOL_WITHDRAW': 'WITHDRAW',
            'LISTING_UPDATE': 'LISTING'
        }
        
        db_event_type = event_type_mapping.get(parsed_event.get('event_type', 'UNKNOWN'), 'SALE')

        return {
            'collection_address': collection.address,
            'event_type': db_event_type,
            'marketplace': parsed_event.get('marketplace', 'unknown'),
            'amount': Decimal(str(parsed_event.get('amount', '0'))),
            'buyer': parsed_event.get('buyer', ''),
            'seller': parsed_event.get('seller', ''),
            'nft_mint': parsed_event.get('mint_address', ''),
            'timestamp': timestamp,
            'details': original_tx,
        }

    async def _update_nft_owner(self, nft_event: NFTEvent) -> None:
        """
        Update the owner field of the NFT after a sale or transfer.

        Args:
            nft_event: The NFTEvent that was just created/updated
        """
        mint = nft_event.nft_mint
        buyer = nft_event.buyer

        if not mint or not buyer:
            return

        try:
            nft = await sync_to_async(NFT.objects.filter(mint_address=mint).first)()
            if nft and nft.owner != buyer:
                old_owner = nft.owner
                nft.owner = buyer
                await sync_to_async(nft.save)(update_fields=['owner'])
                logger.info(f"Updated NFT {mint[:8]}... owner: {old_owner[:8]}... → {buyer[:8]}...")
        except Exception as e:
            logger.error(f"Failed to update NFT owner for {mint}: {e}")

    async def _mark_nft_as_burned(self, nft_event: NFTEvent) -> None:
        """
        Mark the NFT as burned when a BURN event is detected.
        This updates the supply and holder calculations automatically.

        Args:
            nft_event: The BURN NFTEvent that was just created/updated
        """
        mint = nft_event.nft_mint

        if not mint:
            logger.warning("BURN event missing mint address, cannot mark NFT as burned")
            return

        try:
            nft = await sync_to_async(NFT.objects.filter(mint_address=mint).first)()
            if nft:
                if not nft.is_burned:
                    nft.is_burned = True
                    nft.owner = None  # Clear owner since NFT is burned
                    await sync_to_async(nft.save)(update_fields=['is_burned', 'owner', 'updated_at'])
                    logger.info(f"🔥 Marked NFT {mint[:8]}... as BURNED - will be excluded from supply/holders")
                else:
                    logger.debug(f"NFT {mint[:8]}... already marked as burned")
            else:
                logger.warning(f"NFT {mint} not found in database, cannot mark as burned")
        except Exception as e:
            logger.error(f"Failed to mark NFT {mint} as burned: {e}")

    async def _has_tracked_collection(self, normalized_tx: dict) -> bool:
        """
        PERFORMANCE OPTIMIZATION: Quick check if transaction involves any tracked collections.

        This runs BEFORE expensive parsing to avoid wasting CPU on irrelevant transactions.
        Extracts all potential NFT mint addresses and collection addresses from the raw
        transaction data and checks if any match collections in our database.

        ONLY does database lookups - NO API calls.

        Args:
            normalized_tx: Normalized transaction data

        Returns:
            True if transaction might involve a tracked collection, False otherwise
        """
        try:
            potential_addresses = set()

            # 1. Extract all account keys (includes all participants)
            account_keys = normalized_tx.get('account_keys', [])
            if account_keys:
                potential_addresses.update(account_keys)

            # 2. Extract mint addresses from token balance changes
            meta = normalized_tx.get('meta', {})
            for balance_list in ['preTokenBalances', 'postTokenBalances']:
                balances = meta.get(balance_list, [])
                for balance in balances:
                    mint = balance.get('mint')
                    if mint:
                        potential_addresses.add(mint)

            if not potential_addresses:
                # No addresses found - allow parsing as fail-safe
                return True

            # 3. Quick DB check: Do any addresses match our tracked collections?
            has_collection_match = await sync_to_async(
                NFTCollection.objects.filter(address__in=potential_addresses).exists
            )()

            if has_collection_match:
                return True

            # 4. Check if any mint addresses belong to NFTs in our tracked collections
            # This catches transactions where the collection address isn't directly in the tx
            has_nft_match = await sync_to_async(
                NFT.objects.filter(
                    mint_address__in=potential_addresses,
                    collection__isnull=False
                ).exists
            )()

            return has_nft_match

        except Exception as e:
            logger.warning(f"Error in collection pre-filter check: {e}")
            # On error, return True to allow parsing (fail-safe)
            return True

    async def _get_collection_for_mint(self, mint_address: str) -> Optional[str]:
        """
        Find the collection address for a given mint.

        OPTIMIZED STRATEGY (User requirement: Only track NFTs we've already retrieved):
        1. Redis cache (fastest - 90%+ hit rate after warmup)
        2. Database lookup (PRIMARY METHOD - for tracked NFTs)
        3. If NOT in DB → Skip entirely (not a tracked NFT)

        We do NOT make external API calls during transaction parsing.
        NFTs are retrieved separately when collections are added/updated.
        This ensures we only process transactions for NFTs we actually care about.

        Args:
            mint_address: The NFT mint address

        Returns:
            Collection address if NFT is tracked, None otherwise
        """
        if not mint_address:
            return None

        # OPTIMIZATION 1: Check Redis cache first (Solution 2)
        from django.core.cache import cache
        cache_key = f"collection:mint:{mint_address}"

        try:
            cached_collection = await sync_to_async(cache.get)(cache_key)
            if cached_collection:
                if cached_collection == "NOT_FOUND":
                    # Previously failed to resolve - don't retry for 1 hour
                    logger.debug(f"[CACHE HIT] Mint {mint_address[:8]}... previously failed to resolve")
                    return None
                logger.debug(f"[CACHE HIT] Collection {cached_collection[:8]}... for mint {mint_address[:8]}...")
                return cached_collection
        except Exception as e:
            logger.debug(f"Cache read error for mint {mint_address}: {e}")

        # OPTIMIZATION 2: Check database first (for known NFTs)
        try:
            nft = await sync_to_async(
                NFT.objects.select_related('collection').filter(mint_address=mint_address).first
            )()
            if nft and nft.collection:
                collection_address = nft.collection.address
                # Cache the database hit
                try:
                    await sync_to_async(cache.set)(cache_key, collection_address, timeout=86400)  # 24h
                except Exception:
                    pass
                logger.debug(f"[DB HIT] Collection {collection_address[:8]}... for mint {mint_address[:8]}...")
                return collection_address
        except Exception as e:
            logger.error(f"Database error while getting collection for mint {mint_address}: {e}")

        # OPTIMIZATION 3: Unknown NFT - Resolve via Helius API
        # CRITICAL: This handles NEW NFTs minted in tracked collections
        # Without this, we'd miss new mints in Rogues, Player 1, Bulma NFT!
        logger.info(f"[UNKNOWN NFT] Resolving collection via Helius for mint {mint_address[:8]}...")

        try:
            # Get Helius provider specifically (not QuickNode)
            helius = await self.provider_manager.get_provider_by_name('helius')
            if helius and hasattr(helius, 'get_collection_for_mint'):
                # Use provider's method with built-in rate limiting
                collection_address = await helius.get_collection_for_mint(mint_address)
                if collection_address:
                    logger.info(f"✅ Resolved via Helius: {collection_address[:8]}... for mint {mint_address[:8]}...")

                    # Check if this collection is one we're tracking
                    is_tracked = await sync_to_async(
                        NFTCollection.objects.filter(address=collection_address, is_listed=True).exists
                    )()

                    if is_tracked:
                        # This is a NEW NFT in a tracked collection!
                        # Cache it so we don't need to call API again
                        try:
                            await sync_to_async(cache.set)(cache_key, collection_address, timeout=86400)  # 24h
                        except Exception:
                            pass
                        logger.info(f"🆕 NEW NFT in tracked collection {collection_address[:8]}...")
                        return collection_address
                    else:
                        # Resolved successfully but not a tracked collection - cache as NOT_FOUND
                        try:
                            await sync_to_async(cache.set)(cache_key, "NOT_FOUND", timeout=86400)  # 24h
                        except Exception:
                            pass
                        logger.debug(f"[UNTRACKED] Collection {collection_address[:8]}... not in tracked list")
                        return None
        except Exception as e:
            logger.debug(f"Helius API failed for mint {mint_address}: {e}")

        # If Helius fails, cache as NOT_FOUND with shorter TTL (might be temporary failure)
        try:
            await sync_to_async(cache.set)(cache_key, "NOT_FOUND", timeout=3600)  # 1h (shorter for failures)
        except Exception:
            pass

        logger.warning(f"Could not resolve collection for mint {mint_address[:8]}...")
        return None

    async def _save_to_failed_transactions(self, signature: str, event_data: dict, error_message: str) -> None:
        """
        Save a failed transaction to the database for later analysis.

        Args:
            signature: Transaction signature
            event_data: The raw transaction data
            error_message: Description of why parsing failed
        """
        try:
            # Use update_or_create to handle duplicates gracefully
            failed_tx, created = await sync_to_async(FailedTransaction.objects.update_or_create)(
                event_id=signature,
                defaults={
                    'event_data': event_data,
                    'error_message': error_message,
                }
            )
            action = "Saved" if created else "Updated"
            logger.info(f"{action} failed transaction {signature} to database")
        except Exception as e:
            logger.error(f"Failed to save failed transaction {signature}: {e}")

    def normalize_transaction_data(self, tx_data: dict) -> dict:
        """
        Normalize transaction data from different providers into a consistent format.
        
        Ensures all transactions have:
        - tokenTransfers: List of token transfers
        - nativeTransfers: List of SOL transfers
        - instructions: List of instructions
        - signature: Transaction signature
        - timestamp: Block timestamp
        
        Args:
            tx_data: Raw transaction data from any provider
            
        Returns:
            Normalized transaction dict
        """
        if not tx_data:
            return {}
        
        # If already normalized (has tokenTransfers), return as-is
        if 'tokenTransfers' in tx_data:
            return tx_data
        
        # Extract signature
        signature = tx_data.get('signature', '')
        if not signature:
            signatures = tx_data.get('transaction', {}).get('signatures', [])
            signature = signatures[0] if signatures else ''
        
        # Extract timestamp
        timestamp = tx_data.get('blockTime') or tx_data.get('timestamp')
        
        # Get meta and transaction structure
        meta = tx_data.get('meta', {})
        transaction = tx_data.get('transaction', {})
        message = transaction.get('message', {})
        
        # Build account keys array
        account_keys = []
        raw_keys = message.get('accountKeys', [])
        for key in raw_keys:
            if isinstance(key, str):
                account_keys.append(key)
            elif isinstance(key, dict):
                account_keys.append(key.get('pubkey', ''))
            else:
                account_keys.append(str(key))
        
        # Extract instructions
        instructions = message.get('instructions', [])
        
        # Normalize instructions format
        normalized_instructions = []
        for ix in instructions:
            normalized_ix = {
                'programId': ix.get('programId', ''),
                'accounts': ix.get('accounts', []),
                'data': ix.get('data', ''),
            }
            if 'parsed' in ix:
                normalized_ix['parsed'] = ix['parsed']
            normalized_instructions.append(normalized_ix)
        
        # Build normalized structure
        normalized = {
            'signature': signature,
            'timestamp': timestamp,
            'slot': tx_data.get('slot'),
            'err': meta.get('err'),
            'fee': meta.get('fee', 0),
            'logMessages': meta.get('logMessages', []),
            'instructions': normalized_instructions,
            'innerInstructions': meta.get('innerInstructions', []),
            'accountKeys': account_keys,
            'preBalances': meta.get('preBalances', []),
            'postBalances': meta.get('postBalances', []),
            'preTokenBalances': meta.get('preTokenBalances', []),
            'postTokenBalances': meta.get('postTokenBalances', []),
        }
        
        # Parse token transfers from balance changes
        normalized['tokenTransfers'] = self._parse_token_transfers_from_balances(
            meta.get('preTokenBalances', []),
            meta.get('postTokenBalances', [])
        )
        
        # Parse native transfers from balance changes
        normalized['nativeTransfers'] = self._parse_native_transfers_from_balances(
            meta.get('preBalances', []),
            meta.get('postBalances', []),
            account_keys,
            meta.get('fee', 0)
        )
        
        return normalized

    def _parse_token_transfers_from_balances(self, pre_balances: List[Dict], 
                                            post_balances: List[Dict]) -> List[Dict]:
        """
        Parse token transfers by comparing pre and post token balances.
        
        Args:
            pre_balances: Token balances before transaction
            post_balances: Token balances after transaction
            
        Returns:
            List of token transfer dicts
        """
        transfers = []
        
        if not pre_balances or not post_balances:
            return transfers
        
        # Build lookup dictionaries
        pre_lookup = {
            (b.get('mint'), b.get('owner')): b.get('uiTokenAmount', {})
            for b in pre_balances
        }
        
        post_lookup = {
            (b.get('mint'), b.get('owner')): b.get('uiTokenAmount', {})
            for b in post_balances
        }
        
        # Track changes per mint
        mint_changes = {}
        all_keys = set(pre_lookup.keys()) | set(post_lookup.keys())
        
        for mint, owner in all_keys:
            pre_amount = float(pre_lookup.get((mint, owner), {}).get('uiAmountString', '0'))
            post_amount = float(post_lookup.get((mint, owner), {}).get('uiAmountString', '0'))
            change = post_amount - pre_amount
            
            if change == 0:
                continue
            
            if mint not in mint_changes:
                mint_changes[mint] = {}
            
            if change > 0:
                mint_changes[mint]['to'] = owner
                mint_changes[mint]['amount'] = change
            else:
                mint_changes[mint]['from'] = owner
        
        # Build transfer objects
        for mint, change_data in mint_changes.items():
            if 'from' in change_data and 'to' in change_data:
                # Get decimals
                decimals = 0
                for b in post_balances:
                    if b.get('mint') == mint:
                        decimals = b.get('uiTokenAmount', {}).get('decimals', 0)
                        break
                
                # Determine token standard
                token_standard = 'NonFungible' if decimals == 0 and change_data.get('amount') == 1 else 'Fungible'
                
                transfers.append({
                    'mint': mint,
                    'fromUserAccount': change_data['from'],
                    'toUserAccount': change_data['to'],
                    'tokenAmount': change_data.get('amount', 0),
                    'tokenStandard': token_standard,
                    'decimals': decimals
                })
        
        return transfers

    def _parse_native_transfers_from_balances(self, pre_balances: List[int], 
                                             post_balances: List[int],
                                             account_keys: List[str], 
                                             fee: int) -> List[Dict]:
        """
        Parse native SOL transfers by comparing pre and post balances.
        
        Args:
            pre_balances: SOL balances before transaction (in lamports)
            post_balances: SOL balances after transaction (in lamports)
            account_keys: List of account addresses
            fee: Transaction fee in lamports
            
        Returns:
            List of native transfer dicts
        """
        transfers = []
        
        if len(pre_balances) != len(post_balances) or len(pre_balances) != len(account_keys):
            logger.warning("Balance arrays length mismatch in normalize_transaction_data")
            return transfers
        
        for i, (pre_bal, post_bal) in enumerate(zip(pre_balances, post_balances)):
            change = post_bal - pre_bal
            
            # Account for fee (first account is fee payer)
            if i == 0 and change != 0:
                change += fee
            
            if change != 0:
                transfers.append({
                    'userAccount': account_keys[i],
                    'amount': abs(change),
                    'type': 'credit' if change > 0 else 'debit',
                    'balanceChange': change
                })
        
        return transfers
            
    async def _resolve_collection_from_whitelist(self, whitelist_address: str, whitelist_data: dict) -> Optional[str]:
        """
        Resolves collection address from a TensorList whitelist account.
        Used for collection-wide bids.
        """
        try:
            account_data_b64 = whitelist_data.get('data', [None])[0]
            if not account_data_b64:
                logger.error(f"[_resolve_collection_from_whitelist] No data in whitelist {whitelist_address}")
                return None
            
            account_data_bytes = base64.b64decode(account_data_b64)
            
            # Find conditions vector at offset 139
            if len(account_data_bytes) < 139 + 4:
                logger.error(f"[_resolve_collection_from_whitelist] Account data too short")
                return None
            
            # Read the 4-byte length of the conditions vector
            conditions_length_bytes = account_data_bytes[139:143]
            conditions_length = struct.unpack('<I', conditions_length_bytes)[0]
            logger.info(f"[_resolve_collection_from_whitelist] Found conditions vector at offset 139")
            
            if conditions_length == 0:
                logger.error(f"[_resolve_collection_from_whitelist] Conditions vector is empty")
                return None
            
            # Each condition is 33 bytes (1 byte type + 32 bytes pubkey)
            conditions_start = 143
            first_condition_type = account_data_bytes[conditions_start]
            
            if first_condition_type != 0:
                logger.warning(f"[_resolve_collection_from_whitelist] First condition type is {first_condition_type}, expected 0")
            
            # Extract the 32-byte collection pubkey
            collection_pubkey_bytes = account_data_bytes[conditions_start + 1 : conditions_start + 33]
            collection_address = base58.b58encode(collection_pubkey_bytes).decode('utf-8')
            
            logger.info(f"[_resolve_collection_from_whitelist] SUCCESS: Resolved collection {collection_address}")
            return collection_address
            
        except Exception as e:
            logger.error(f"[_resolve_collection_from_whitelist] CRITICAL FAILURE: {e}", exc_info=True)
            return None

    async def _resolve_collection_from_token_account(self, token_account: str, token_data: dict, transaction: dict) -> Optional[str]:
        """
        Resolves collection address from a token account (for direct NFT bids).
        
        Strategy:
        1. Parse token account to get NFT mint address
        2. Look up mint in our database to find collection
        3. If not in DB, fetch NFT metadata on-chain
        """
        try:
            # Parse token account data to extract mint address
            account_data_b64 = token_data.get('data', [None])[0]
            if not account_data_b64:
                logger.error(f"[_resolve_collection_from_token_account] No data in token account")
                return None
            
            account_data_bytes = base64.b64decode(account_data_b64)
            
            # Token account structure: mint is at bytes 0-32
            if len(account_data_bytes) < 32:
                logger.error(f"[_resolve_collection_from_token_account] Token account data too short")
                return None
            
            mint_pubkey_bytes = account_data_bytes[0:32]
            nft_mint = base58.b58encode(mint_pubkey_bytes).decode('utf-8')
            logger.info(f"[_resolve_collection_from_token_account] Extracted NFT mint: {nft_mint}")
            
            # Strategy 1: Check our database first (fastest)
            collection_address = await self._lookup_nft_collection_in_db(nft_mint)
            if collection_address:
                logger.info(f"[_resolve_collection_from_token_account] ✅ Found in DB: {collection_address}")
                return collection_address
            
            # Strategy 2: Fetch metadata on-chain (slower but comprehensive)
            logger.info(f"[_resolve_collection_from_token_account] Not in DB, fetching metadata on-chain...")
            collection_address = await self._fetch_nft_collection_from_metadata(nft_mint)
            if collection_address:
                logger.info(f"[_resolve_collection_from_token_account] ✅ Found via metadata: {collection_address}")
                return collection_address
            
            logger.error(f"[_resolve_collection_from_token_account] Could not resolve collection for NFT {nft_mint}")
            return None
            
        except Exception as e:
            logger.error(f"[_resolve_collection_from_token_account] Error: {e}", exc_info=True)
            return None

    async def _lookup_collection_in_db(self, nft_mint: str) -> Optional[str]:
        """Check if we already know this NFT's collection from database."""
        try:
            from nft_data.models import NFT
            nft = await sync_to_async(NFT.objects.filter(mint_address=nft_mint).select_related('collection').first)()
            if nft and nft.collection:
                logger.debug(f"[_lookup_collection_in_db] Found {nft_mint} -> {nft.collection.address}")
                return nft.collection.address
            return None
        except Exception as e:
            logger.debug(f"[_lookup_collection_in_db] Not found: {e}")
            return None

    async def _fetch_collection_from_das_api(self, nft_mint: str) -> Optional[str]:
        """
        Fetch collection address from Helius DAS API.

        This supports both MPL Core assets and traditional Token Metadata.
        Uses the 'grouping' field to extract collection information.

        Args:
            nft_mint: The NFT mint address

        Returns:
            Collection address if found, None otherwise
        """
        try:
            provider = await self.provider_manager.get_rpc_provider()
            if not provider:
                logger.debug(f"[_fetch_collection_das] No provider available")
                return None

            # Check if provider supports DAS API (Helius)
            if not hasattr(provider, '_async_post'):
                logger.debug(f"[_fetch_collection_das] Provider does not support DAS API")
                return None

            # Call Helius getAsset method
            payload = {
                "jsonrpc": "2.0",
                "id": "get-asset-collection",
                "method": "getAsset",
                "params": {"id": nft_mint}
            }

            logger.debug(f"[_fetch_collection_das] Calling Helius DAS API for {nft_mint}")
            response = await provider._async_post(provider.rpc_url, json_data=payload, timeout=15)

            if not response or "result" not in response:
                logger.debug(f"[_fetch_collection_das] No result from DAS API")
                return None

            result = response["result"]

            # Extract collection from grouping field
            # Format: grouping: [{"group_key": "collection", "group_value": "<address>"}]
            grouping = result.get("grouping", [])
            if not isinstance(grouping, list):
                logger.debug(f"[_fetch_collection_das] Invalid grouping format")
                return None

            for group in grouping:
                if isinstance(group, dict) and group.get("group_key") == "collection":
                    collection_address = group.get("group_value")
                    if collection_address:
                        logger.info(f"[_fetch_collection_das] Found collection {collection_address} for mint {nft_mint}")
                        return collection_address

            logger.debug(f"[_fetch_collection_das] No collection found in grouping for {nft_mint}")
            return None

        except Exception as e:
            logger.debug(f"[_fetch_collection_das] Error fetching from DAS API for {nft_mint}: {e}")
            return None

    async def _fetch_collection_from_metadata(self, nft_mint: str) -> Optional[str]:
        """
        Fetch NFT metadata from Metaplex to get collection address.
        This is the slowest but most reliable method.
        """
        try:
            provider = await self.provider_manager.get_rpc_provider()
            if not provider:
                return None
            
            # Derive Metaplex metadata PDA
            # Seeds: ["metadata", metadata_program, mint]
            metadata_program = Pubkey.from_string("metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s")
            mint_pubkey = Pubkey.from_string(nft_mint)
            
            # Find PDA
            metadata_seeds = [
                b"metadata",
                bytes(metadata_program),
                bytes(mint_pubkey)
            ]
            
            metadata_pda, _ = Pubkey.find_program_address(metadata_seeds, metadata_program)
            metadata_address = str(metadata_pda)
            
            logger.debug(f"[_fetch_collection] Metadata PDA: {metadata_address}")
            
            # Fetch metadata account
            metadata_info = await provider.get_account_info(metadata_address)
            if not metadata_info or not metadata_info.get('value'):
                logger.warning(f"[_fetch_collection] No metadata found for {nft_mint}")
                return None
            
            # Parse metadata account
            import base64
            import struct
            metadata_data = base64.b64decode(metadata_info['value']['data'][0])

            # Metaplex Token Metadata v1.1.0+ structure:
            # 0-1: key (u8) - should be 4 for Metadata
            # 1-33: update_authority (32 bytes)
            # 33-65: mint (32 bytes)
            # Then variable length name, symbol, uri strings...
            # Collection field is at a fixed offset after these strings

            if len(metadata_data) < 326:
                logger.debug(f"[_fetch_collection] Metadata too short ({len(metadata_data)} bytes)")
                return None

            # Check metadata key type (should be 4 for Metadata)
            key_type = metadata_data[0]
            if key_type != 4:
                logger.debug(f"[_fetch_collection] Invalid metadata key type: {key_type}")
                return None

            try:
                # Collection struct starts around byte 326-358 (depending on string lengths)
                # Structure: Option<Collection> where Collection = { verified: bool, key: Pubkey }
                # Option is 1 byte (0=None, 1=Some) + data

                # Try common offsets for collection field
                for offset in [326, 322, 330, 318]:
                    if offset + 33 > len(metadata_data):
                        continue

                    is_some = metadata_data[offset]
                    if is_some == 1:  # Option::Some
                        # Next byte is verified (bool)
                        is_verified = metadata_data[offset + 1] == 1
                        # Next 32 bytes is the collection pubkey
                        collection_bytes = metadata_data[offset + 2:offset + 34]

                        if len(collection_bytes) == 32:
                            # Verify it looks like a valid pubkey (not all zeros)
                            if any(b != 0 for b in collection_bytes):
                                collection_pubkey = Pubkey(collection_bytes)
                                collection_address = str(collection_pubkey)

                                if is_verified:
                                    logger.info(f"[_fetch_collection] ✅ Found verified collection: {collection_address}")
                                    return collection_address
                                else:
                                    logger.debug(f"[_fetch_collection] Found unverified collection: {collection_address}")
                                    # Return it anyway - some projects don't verify
                                    return collection_address

                logger.debug(f"[_fetch_collection] No collection field found in metadata")
                return None

            except Exception as parse_error:
                logger.debug(f"[_fetch_collection] Error parsing collection field: {parse_error}")
                return None

        except Exception as e:
            logger.error(f"[_fetch_collection] Error: {e}", exc_info=True)
            return None

    async def _is_compressed_nft(self, mint_address: str) -> bool:
        """
        Detect if an NFT is compressed (cNFT) by checking for its mint account.

        Compressed NFTs (cNFTs) don't have traditional mint accounts on-chain.
        They use Merkle trees and only store proofs, not full accounts.

        Args:
            mint_address: The NFT mint address to check

        Returns:
            True if this is a compressed NFT, False otherwise
        """
        try:
            provider = await self.provider_manager.get_rpc_provider()
            if not provider:
                logger.debug(f"[_is_compressed_nft] No provider available")
                return False

            account_info = await provider.get_account_info(mint_address)

            # If the mint account doesn't exist on-chain, it's very likely a cNFT
            if not account_info or not account_info.get("value"):
                logger.debug(f"🗜️ Detected compressed NFT (no mint account): {mint_address[:8]}...")
                return True

            # Standard NFTs have a mint account with specific program owner
            # cNFTs don't have this
            return False

        except Exception as e:
            logger.debug(f"Error checking if {mint_address[:8]}... is compressed: {e}")
            # On error, assume it's not compressed to allow fallback attempts
            return False

    async def _parse_whitelist_for_collection(self, raw_data: bytes, whitelist_address: str) -> Optional[str]:
        """
        Helper: Parse TensorList whitelist account to extract collection address.
        Used for collection-wide bids.
        """
        import struct
        
        try:
            # Try multiple offsets to find conditions vector
            potential_offsets = [135, 139, 143]
            offset = None
            
            for test_offset in potential_offsets:
                if len(raw_data) >= test_offset + 37:
                    vec_len = struct.unpack('<I', raw_data[test_offset:test_offset+4])[0]
                    logger.debug(f"[_parse_whitelist] Offset {test_offset}: vec_len={vec_len}")
                    
                    if vec_len == 1:  # Found conditions vector!
                        offset = test_offset
                        logger.info(f"[_parse_whitelist] Found conditions vector at offset {offset}")
                        break
            
            if offset is None:
                logger.error(f"[_parse_whitelist] Could not find conditions vector")
                return None
            
            # Read conditions vector length
            conditions_count = struct.unpack('<I', raw_data[offset:offset+4])[0]
            logger.debug(f"[_parse_whitelist] Conditions vector contains {conditions_count} items")
            offset += 4
            
            if conditions_count == 0:
                logger.warning(f"[_parse_whitelist] No conditions in whitelist")
                return None
            
            # Read first condition: mode (1 byte) + pubkey (32 bytes)
            mode = raw_data[offset]
            offset += 1
            logger.debug(f"[_parse_whitelist] Condition mode: {mode}")
            
            if len(raw_data) < offset + 32:
                logger.error(f"[_parse_whitelist] Not enough data for pubkey")
                return None
            
            pubkey_bytes = raw_data[offset:offset+32]
            collection_address = str(Pubkey(pubkey_bytes))
            
            logger.info(f"[_parse_whitelist] ✅ Resolved collection {collection_address} from whitelist {whitelist_address}")
            return collection_address
            
        except Exception as e:
            logger.error(f"[_parse_whitelist] Error: {e}", exc_info=True)
            return None


    async def _parse_token_account_for_nft(self, raw_data: bytes, token_account: str, tx_details: dict) -> tuple[str, Optional[str]]:
        """
        Helper: Parse SPL token account to extract NFT mint and resolve its collection.
        Used for direct NFT bids.
        
        Returns: (nft_mint, collection_address)
        """
        try:
            # Token account structure: mint is first 32 bytes
            if len(raw_data) < 32:
                logger.error(f"[_parse_token_account] Token account data too short: {len(raw_data)} bytes")
                return '', None
            
            mint_bytes = raw_data[0:32]
            nft_mint = str(Pubkey(mint_bytes))
            logger.info(f"[_parse_token_account] 🎨 Extracted NFT mint: {nft_mint}")
            
            # Strategy 1: Check our database (fastest)
            collection_address = await self._lookup_collection_in_db(nft_mint)
            if collection_address:
                logger.info(f"[_parse_token_account] ✅ Found in DB: {collection_address}")
                return nft_mint, collection_address
            
            # Strategy 2: Check transaction accounts for collection info (fast)
            collection_address = await self._extract_collection_from_transaction(tx_details, nft_mint)
            if collection_address:
                logger.info(f"[_parse_token_account] ✅ Found in transaction: {collection_address}")
                return nft_mint, collection_address
            
            # Strategy 3: Fetch metadata on-chain (slower)
            logger.info(f"[_parse_token_account] Fetching metadata on-chain...")
            collection_address = await self._fetch_collection_from_metadata(nft_mint)
            if collection_address:
                logger.info(f"[_parse_token_account] ✅ Found via metadata: {collection_address}")
                return nft_mint, collection_address
            
            logger.warning(f"[_parse_token_account] Could not resolve collection for NFT {nft_mint}")
            return nft_mint, None
            
        except Exception as e:
            logger.error(f"[_parse_token_account] Error: {e}", exc_info=True)
            return '', None

    async def _extract_collection_from_transaction(self, tx_details: dict, nft_mint: str) -> Optional[str]:
        """
        Try to extract collection from transaction metadata or logs.
        Many NFT transactions include collection info that we can parse.
        """
        try:
            # Check if transaction has metadata that mentions collection
            # This is a quick heuristic - not always available
            meta = tx_details.get('meta', {})
            
            # Look through post token balances for collection hints
            post_balances = meta.get('postTokenBalances', [])
            for balance in post_balances:
                if balance.get('mint') == nft_mint:
                    # Some transactions include collection in the balance info
                    owner = balance.get('owner')
                    logger.debug(f"[_extract_collection] Found NFT owner: {owner}")
                    # Could check if owner is a known collection authority
            
            # Could also check logs for collection mentions
            # logs = meta.get('logMessages', [])

            return None  # Placeholder - expand based on actual data patterns

        except Exception as e:
            logger.debug(f"[_extract_collection] Error: {e}")
            return None

    # ===================================================================
    # METAPLEX CORE (MPL CORE) PARSERS - Mint/Burn Detection
    # ===================================================================

    async def _parse_mpl_core_instruction(self, tx_details: Dict, ix: Dict, decoded_data: bytes,
                                         collection_address: str, timestamp: Any) -> Optional[dict]:
        """
        Parse Metaplex Core instructions (mint, burn, transfer).

        Metaplex Core is the new standard for NFTs on Solana.
        Example transaction: 24RPxtPHuFksx8vdJWdUvC633rK6B1HS6qHxn1Cw7WfV41rgCdDRsMhMSTmHHWVdQGhiy28gdXPt725N3BCCdHmg
        """
        from indexer.nft_constants import (
            MARKETPLACE_DISCRIMINATORS,
            MPL_CORE_CREATE_V1_LAYOUT,
            MPL_CORE_BURN_LAYOUT,
            MPL_CORE_TRANSFER_LAYOUT
        )

        accounts = ix.get('accounts', [])
        discriminator = decoded_data[:8] if len(decoded_data) >= 8 else b''

        # Discriminator → (parser_function, layout) mapping
        mpl_core_parsers = {
            MARKETPLACE_DISCRIMINATORS['mpl_core']['create_v1']:
                (self._parse_mpl_core_create_v1, MPL_CORE_CREATE_V1_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['mpl_core']['burn']:
                (self._parse_mpl_core_burn, MPL_CORE_BURN_LAYOUT),
            MARKETPLACE_DISCRIMINATORS['mpl_core']['transfer']:
                (self._parse_mpl_core_transfer, MPL_CORE_TRANSFER_LAYOUT),
        }

        parser_tuple = mpl_core_parsers.get(discriminator)
        if not parser_tuple:
            logger.warning(f"Unknown Mpl Core discriminator: {discriminator.hex()}")
            return None

        parser_func, layout = parser_tuple
        try:
            parsed_data = layout.parse(decoded_data)
            return await parser_func(tx_details, accounts, parsed_data, collection_address, timestamp, decoded_data)
        except Exception as e:
            logger.error(f"Error parsing Mpl Core instruction {discriminator.hex()}: {e}", exc_info=True)
            return None

    async def _parse_mpl_core_create_v1(self, tx_details: dict, accounts: list,
                                       parsed_data: Any, collection: str, ts: Any, decoded_data: bytes) -> Optional[dict]:
        """
        Parse Mpl Core createV1 instruction (NFT mint).

        Account structure:
        - accounts[0]: Asset (newly minted NFT)
        - accounts[1]: Collection
        - accounts[2]: Authority
        - accounts[3]: Payer
        - accounts[4]: Owner (recipient)
        """
        try:
            # Extract mint address (the newly created NFT)
            mint_address = accounts[0] if len(accounts) > 0 else ''

            # Extract collection from accounts or use provided
            collection_address = accounts[1] if len(accounts) > 1 else collection

            # Extract owner (minter/recipient)
            owner = accounts[4] if len(accounts) > 4 else (accounts[3] if len(accounts) > 3 else '')

            # Try to parse name and URI from instruction data
            # Format after discriminator: name_length (u32) + name + uri_length (u32) + uri
            nft_name = ''
            nft_uri = ''
            try:
                data_after_disc = decoded_data[8:]  # Skip 8-byte discriminator
                if len(data_after_disc) > 0:
                    # Parse name (variable length string)
                    # The format is complex with packed data, extract from logs instead
                    pass
            except:
                pass

            # Get price if this was part of a mint transaction with payment
            mint_price = None
            for transfer in tx_details.get('nativeTransfers', []):
                if transfer.get('toUserAccount') != owner:  # Payment to treasury/creator
                    mint_price = transfer.get('amount', 0) / 1e9
                    break

            logger.info(f"[Mpl Core] Mint detected: {mint_address[:8]}... in collection {collection_address[:8]}...")

            return {
                'event_type': 'MINT',
                'mint_address': mint_address,
                'amount': mint_price,
                'buyer': owner,  # The one who minted/received
                'seller': None,  # No seller in a mint
                'timestamp': ts,
                'collection_address': collection_address,
                'marketplace': 'mpl_core',
                'traits': {}
            }

        except Exception as e:
            logger.error(f"Error parsing Mpl Core createV1: {e}", exc_info=True)
            return None

    async def _parse_mpl_core_burn(self, tx_details: dict, accounts: list,
                                  parsed_data: Any, collection: str, ts: Any, decoded_data: bytes) -> Optional[dict]:
        """
        Parse Mpl Core burn instruction (NFT burn).

        Account structure:
        - accounts[0]: Asset (NFT being burned)
        - accounts[1]: Collection
        - accounts[2]: Payer/Authority
        """
        try:
            # Extract mint address (the NFT being burned)
            mint_address = accounts[0] if len(accounts) > 0 else ''

            # Extract collection
            collection_address = accounts[1] if len(accounts) > 1 else collection

            # Extract burner (the one burning the NFT)
            burner = accounts[2] if len(accounts) > 2 else ''

            logger.info(f"[Mpl Core] Burn detected: {mint_address[:8]}... from collection {collection_address[:8]}...")

            return {
                'event_type': 'BURN',
                'mint_address': mint_address,
                'amount': None,
                'buyer': None,
                'seller': burner,  # The one who burned it
                'timestamp': ts,
                'collection_address': collection_address,
                'marketplace': 'mpl_core',
                'traits': {}
            }

        except Exception as e:
            logger.error(f"Error parsing Mpl Core burn: {e}", exc_info=True)
            return None

    async def _parse_mpl_core_transfer(self, tx_details: dict, accounts: list,
                                      parsed_data: Any, collection: str, ts: Any, decoded_data: bytes) -> Optional[dict]:
        """
        Parse Mpl Core transfer instruction (NFT transfer).

        Account structure:
        - accounts[0]: Asset (NFT being transferred)
        - accounts[1]: Collection
        - accounts[2]: Payer
        - accounts[3]: Authority (from)
        - accounts[4]: New Owner (to)
        """
        try:
            # Extract mint address
            mint_address = accounts[0] if len(accounts) > 0 else ''

            # Extract collection
            collection_address = accounts[1] if len(accounts) > 1 else collection

            # Extract from/to addresses
            from_address = accounts[3] if len(accounts) > 3 else ''
            to_address = accounts[4] if len(accounts) > 4 else ''

            logger.info(f"[Mpl Core] Transfer detected: {mint_address[:8]}... from {from_address[:8]}... to {to_address[:8]}...")

            return {
                'event_type': 'TRANSFER',
                'mint_address': mint_address,
                'amount': None,
                'buyer': to_address,  # Recipient
                'seller': from_address,  # Sender
                'timestamp': ts,
                'collection_address': collection_address,
                'marketplace': 'mpl_core',
                'traits': {}
            }

        except Exception as e:
            logger.error(f"Error parsing Mpl Core transfer: {e}", exc_info=True)
            return None

    # ===================================================================
    # METAPLEX TOKEN METADATA (LEGACY) PARSERS - Mint/Burn Detection
    # ===================================================================

    async def _parse_token_metadata_instruction(self, tx_details: Dict, ix: Dict, decoded_data: bytes,
                                                collection_address: str, timestamp: Any) -> Optional[dict]:
        """
        Parse Metaplex Token Metadata instructions (legacy standard).

        Token Metadata uses 1-byte discriminators instead of 8-byte.
        Example transaction: 4QhvVb9uC21uyTKkoVC5h2CKRh9mBF6chcAHMHjSvUey4hNX2UutBnK7ZYJZcnTRqoBuic22gHQoGRhN72t5jb6f
        """
        from indexer.nft_constants import MARKETPLACE_DISCRIMINATORS

        accounts = ix.get('accounts', [])
        discriminator = decoded_data[:1] if len(decoded_data) >= 1 else b''  # 1-byte discriminator

        # Check discriminator
        if discriminator == MARKETPLACE_DISCRIMINATORS['token_metadata']['create']:
            return await self._parse_token_metadata_create(tx_details, ix, accounts, collection_address, timestamp)
        elif discriminator == MARKETPLACE_DISCRIMINATORS['token_metadata']['mint']:
            return await self._parse_token_metadata_mint(tx_details, ix, accounts, collection_address, timestamp)
        elif discriminator == MARKETPLACE_DISCRIMINATORS['token_metadata']['burn']:
            return await self._parse_token_metadata_burn(tx_details, ix, accounts, collection_address, timestamp)
        else:
            # No discriminator match - try fallback by looking for mintTo inner instruction
            return await self._parse_token_metadata_fallback(tx_details, ix, accounts, collection_address, timestamp)

    async def _parse_token_metadata_create(self, tx_details: dict, ix: dict, accounts: list,
                                          collection: str, ts: Any) -> Optional[dict]:
        """
        Parse Token Metadata Create instruction (creates metadata + initializes mint).

        Account structure (varies by version):
        - accounts[0]: Metadata account
        - accounts[1]: Master Edition account (optional)
        - accounts[2]: Mint
        - accounts[3]: Mint authority
        - accounts[4]: Payer
        """
        try:
            # Look for the mint address in accounts or inner instructions
            mint_address = ''

            # Check accounts for mint
            if len(accounts) > 2:
                mint_address = accounts[2]

            # If not found, look for initializeMint2 inner instruction
            if not mint_address:
                for inner_ix in ix.get('innerInstructions', []):
                    if inner_ix.get('parsed', {}).get('type') == 'initializeMint2':
                        mint_address = inner_ix.get('parsed', {}).get('info', {}).get('mint', '')
                        break

            # Extract collection from metadata or use provided
            collection_address = collection or (accounts[1] if len(accounts) > 1 else '')

            # Extract owner/minter
            owner = accounts[4] if len(accounts) > 4 else (accounts[3] if len(accounts) > 3 else '')

            # Get mint price from native transfers
            mint_price = None
            for transfer in tx_details.get('nativeTransfers', []):
                if transfer.get('fromUserAccount') == owner and transfer.get('amount', 0) > 1000000:  # > 0.001 SOL
                    mint_price = transfer.get('amount', 0) / 1e9
                    break

            logger.info(f"[Token Metadata] Create detected: {mint_address[:8] if mint_address else 'unknown'}...")

            return {
                'event_type': 'MINT',
                'mint_address': mint_address,
                'amount': mint_price,
                'buyer': owner,
                'seller': None,
                'timestamp': ts,
                'collection_address': collection_address,
                'marketplace': 'token_metadata',
                'traits': {}
            }

        except Exception as e:
            logger.error(f"Error parsing Token Metadata create: {e}", exc_info=True)
            return None

    async def _parse_token_metadata_mint(self, tx_details: dict, ix: dict, accounts: list,
                                        collection: str, ts: Any) -> Optional[dict]:
        """
        Parse Token Metadata Mint instruction (mints tokens to account).

        Account structure:
        - accounts[0]: Token account (destination)
        - accounts[1]: Token owner
        - accounts[2]: Metadata
        - accounts[3]: Master Edition
        - accounts[5]: Mint
        """
        try:
            # Extract mint address
            mint_address = accounts[5] if len(accounts) > 5 else ''

            # Look for mintTo inner instruction to confirm
            if not mint_address:
                for inner_ix in ix.get('innerInstructions', []):
                    if inner_ix.get('parsed', {}).get('type') == 'mintTo':
                        mint_address = inner_ix.get('parsed', {}).get('info', {}).get('mint', '')
                        break

            # Extract collection
            collection_address = accounts[2] if len(accounts) > 2 else collection

            # Extract owner
            owner = accounts[1] if len(accounts) > 1 else ''

            logger.info(f"[Token Metadata] Mint detected: {mint_address[:8] if mint_address else 'unknown'}...")

            return {
                'event_type': 'MINT',
                'mint_address': mint_address,
                'amount': None,
                'buyer': owner,
                'seller': None,
                'timestamp': ts,
                'collection_address': collection_address,
                'marketplace': 'token_metadata',
                'traits': {}
            }

        except Exception as e:
            logger.error(f"Error parsing Token Metadata mint: {e}", exc_info=True)
            return None

    async def _parse_token_metadata_burn(self, tx_details: dict, ix: dict, accounts: list,
                                        collection: str, ts: Any) -> Optional[dict]:
        """
        Parse Token Metadata Burn instruction.
        """
        try:
            # Extract mint from accounts or inner instructions
            mint_address = accounts[0] if len(accounts) > 0 else ''
            burner = accounts[1] if len(accounts) > 1 else ''

            logger.info(f"[Token Metadata] Burn detected: {mint_address[:8] if mint_address else 'unknown'}...")

            return {
                'event_type': 'BURN',
                'mint_address': mint_address,
                'amount': None,
                'buyer': None,
                'seller': burner,
                'timestamp': ts,
                'collection_address': collection,
                'marketplace': 'token_metadata',
                'traits': {}
            }

        except Exception as e:
            logger.error(f"Error parsing Token Metadata burn: {e}", exc_info=True)
            return None

    async def _parse_token_metadata_fallback(self, tx_details: dict, ix: dict, accounts: list,
                                            collection: str, ts: Any) -> Optional[dict]:
        """
        Fallback parser for Token Metadata when discriminator doesn't match.
        Looks for mintTo inner instruction to detect mints.
        """
        try:
            # Look through inner instructions for mintTo
            for inner_ix in ix.get('innerInstructions', []):
                parsed_inner = inner_ix.get('parsed', {})
                if parsed_inner.get('type') == 'mintTo':
                    # This is a mint operation!
                    info = parsed_inner.get('info', {})
                    mint_address = info.get('mint', '')
                    token_account = info.get('account', '')
                    amount = info.get('amount', '0')

                    # Find the token owner from accounts
                    owner = ''
                    for acc_ix in ix.get('innerInstructions', []):
                        if acc_ix.get('parsed', {}).get('info', {}).get('account') == token_account:
                            owner = acc_ix.get('parsed', {}).get('info', {}).get('owner', '')
                            break

                    logger.info(f"[Token Metadata Fallback] Mint detected via mintTo: {mint_address[:8]}...")

                    return {
                        'event_type': 'MINT',
                        'mint_address': mint_address,
                        'amount': None,
                        'buyer': owner or accounts[1] if len(accounts) > 1 else '',
                        'seller': None,
                        'timestamp': ts,
                        'collection_address': collection,
                        'marketplace': 'token_metadata',
                        'traits': {}
                    }

            # No mintTo found
            return None

        except Exception as e:
            logger.error(f"Error in Token Metadata fallback: {e}", exc_info=True)
            return None