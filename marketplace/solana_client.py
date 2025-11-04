# marketplace/solana_client.py

from typing import Dict, Any, Optional
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from anchorpy import Program, Provider, Wallet, Idl
import base58
from django.conf import settings
import os
import json
import logging
import asyncio

# --- EXTERNAL IMPORTS ---
from core.api_provider.api_providers import APIProviderManager
# ------------------------

logger = logging.getLogger(__name__)

# --- PROGRAM CONSTANTS (Derived from your Anchor code) ---
MARKETPLACE_PROGRAM_ID = Pubkey.from_string("tra1TUu99co1Fs7VTnT4GY9ECQcUTKrG2NC5kSHrU5o")
QUEST_PROGRAM_ID = Pubkey.from_string("QuestwwsVeGELdnSHJGcWpFD6Z4T8TonhX45EmoJciX")
SYSTEM_PROGRAM_ID = Pubkey.from_string("11111111111111111111111111111111")
RENT_SYSVAR = Pubkey.from_string("SysvarRent111111111111111111111111111111111")
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

# --- PDA SEEDS ---
CONFIG_SEED = b"config_v2"
PROGRAM_AUTHORITY_SEED = b"authority"
BID_SEED = b"bid"
SELL_INTENT_SEED = b"sell_intent"
QUEST_USER_SEED = b"quest_user"


class SolanaClient:
    """
    Handles all on-chain instruction building for the Marketplace program.
    Implemented as a Singleton with asynchronous, lazy initialization.
    """
    _instance = None
    _initialized_state = None

    def __new__(cls, *args, **kwargs):
        # Enforce Singleton pattern
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Lazy initialization via get_state
        pass

    async def _initialize_client(self, marketplace_idl_path: str = "./target/idl/marketplace.json"):
        """Asynchronously initializes the client and loads configurations."""
        if self._initialized_state is not None:
            return
        
        # 1. --- SECURE KEY LOADING FROM ENCRYPTED STORAGE ---
        self.program_authority_keypair = None
        self.current_provider_name = None

        try:
            # Load from encrypted storage instead of environment variable
            from asgiref.sync import sync_to_async

            pk_b58 = await sync_to_async(self._get_program_authority_key)()

            if pk_b58:
                # Decode Base58 private key
                private_key_bytes = base58.b58decode(pk_b58)
                self.program_authority_keypair = Keypair.from_secret_key(private_key_bytes)
                logger.info("✅ Program Authority Keypair loaded from encrypted storage.")
            else:
                logger.warning("⚠️  No program authority key configured. Some operations may fail.")

        except Exception as e:
            logger.error(f"❌ Failed to load Program Authority Keypair: {e}")
            # Don't fail initialization - allow read-only operations

        logger.info("Initializing SolanaClient: Loading RPC configuration and Anchor IDL.")
        
        # 1. Get dynamic RPC URL from your Manager
        provider_manager = APIProviderManager()
        rpc_provider = await provider_manager.get_rpc_provider()
        
        if not rpc_provider:
            raise Exception("Cannot initialize SolanaClient: No active RPC provider available.")

        rpc_url = rpc_provider.rpc_url
        self.current_provider_name = rpc_provider.name  # Store for transaction monitoring
        http_client = AsyncClient(rpc_url)
        
        # 2. Setup Anchor Provider and Program (Dummy Wallet is a requirement for anchorpy)
        dummy_keypair = Keypair() 
        provider = Provider(http_client, Wallet(dummy_keypair))
        
        # NOTE: Ensure the IDL path is correct relative to where Django runs
        try:
            with open(marketplace_idl_path, 'r') as f:
                idl = Idl.from_json(f.read())
        except FileNotFoundError:
            logger.error(f"FATAL: Anchor IDL not found at {marketplace_idl_path}")
            raise

        program = Program(idl, MARKETPLACE_PROGRAM_ID, provider)
        
        # 3. Resolve Global PDAs
        config_pda, _ = Pubkey.find_program_address([CONFIG_SEED], MARKETPLACE_PROGRAM_ID)
        program_authority_pda, _ = Pubkey.find_program_address([PROGRAM_AUTHORITY_SEED], MARKETPLACE_PROGRAM_ID)
        quest_wallet_pda, _ = Pubkey.find_program_address([b"quest_wallet"], QUEST_PROGRAM_ID)

        self._initialized_state = {
            "program": program,
            "instructions": program.instruction,
            "config_pda": config_pda,
            "program_authority_pda": program_authority_pda,
            "quest_wallet_pda": quest_wallet_pda,
        }
        logger.info(f"SolanaClient initialized successfully using RPC: {rpc_url}")

    async def get_state(self):
        """Ensures initialization runs before returning state."""
        if self._initialized_state is None:
            await self._initialize_client()
        return self._initialized_state

    async def resolve_bid_pdas(self, bidder_wallet: str, nft_mint: str, seller_wallet: str) -> Dict[str, Pubkey]:
        """Resolves PDAs for a specific bid."""
        bidder_pubkey = Pubkey.from_string(bidder_wallet)
        nft_mint_pubkey = Pubkey.from_string(nft_mint)
        seller_pubkey = Pubkey.from_string(seller_wallet)
        
        bid_account_pda, _ = Pubkey.find_program_address(
            [BID_SEED, bidder_pubkey.to_bytes(), nft_mint_pubkey.to_bytes()],
            MARKETPLACE_PROGRAM_ID
        )
        sell_intent_account_pda, _ = Pubkey.find_program_address(
            [SELL_INTENT_SEED, seller_pubkey.to_bytes(), nft_mint_pubkey.to_bytes()],
            MARKETPLACE_PROGRAM_ID
        )
        quest_user_account_pda, _ = Pubkey.find_program_address(
            [QUEST_USER_SEED, bidder_pubkey.to_bytes()],
            QUEST_PROGRAM_ID
        )
        
        return {
            "bid_account": bid_account_pda,
            "sell_intent_account": sell_intent_account_pda,
            "quest_user_account": quest_user_account_pda,
        }

    async def get_place_private_bid_instruction(
        self,
        bidder_wallet: str,
        nft_mint_addr: str,
        seller_wallet: str,
        amount_lamports: int,
        expiry_hours: int,
        nft_vitality_score: int,
        negotiation_count: int,
    ) -> Dict[str, Any]:
        """
        Builds the raw instruction data for the client to sign.
        """
        state = await self.get_state()
        pdas = await self.resolve_bid_pdas(bidder_wallet, nft_mint_addr, seller_wallet)
        
        # 1. Instruction Arguments (match Anchor instruction args)
        args = {
            'amount_lamports': amount_lamports,
            'expiry_hours': expiry_hours,
            'nft_vitality_score': nft_vitality_score,
            'negotiation_count': negotiation_count,
            'is_quest_eligible': True, 
        }

        # 2. Accounts Structure (match Anchor context)
        accounts = {
            "bidder": Pubkey.from_string(bidder_wallet),
            "bid_account": pdas["bid_account"],
            "sell_intent_account": pdas["sell_intent_account"],
            "nft_mint": Pubkey.from_string(nft_mint_addr),
            "config": state["config_pda"],
            "program_authority": state["program_authority_pda"],
            "quest_user_account": pdas["quest_user_account"],
            "quest_program": QUEST_PROGRAM_ID,
            "system_program": SYSTEM_PROGRAM_ID,
            "rent": RENT_SYSVAR,
        }

        # 3. Build the Instruction
        instruction = await state["instructions"]["place_private_bid"](
            args,
            accounts
        )
        
        # 4. Return data needed for client-side transaction creation
        return {
            # Raw instruction data (bytes as hex string)
            "instruction_data": instruction.data.hex(),
            # List of account pubkeys and metadata (is_signer, is_writable)
            "accounts_meta": [key.to_json() for key in instruction.keys],
            "bid_account_pda": pdas["bid_account"].to_base58(),
            "amount_lamports": amount_lamports,
        }

    async def confirm_transaction(self, signature: str) -> bool:
            """
            Confirms a transaction signature on the Solana network using the current RPC client.
            
            Args:
                signature: The base58 encoded transaction signature.

            Returns:
                True if the transaction is finalized and successful, False otherwise.
            """
            state = await self.get_state()
            http_client = state["program"].provider.connection # Get the AsyncClient connection object
            
            try:
                signature_bytes = signature # Assuming signature is already validated/encoded string
                
                # Wait for the transaction to be confirmed
                # NOTE: Commitment 'confirmed' or 'finalized' is safest for marketplace transactions.
                await http_client.confirm_transaction(signature_bytes, commitment="confirmed")
                
                # Optionally check the transaction status explicitly after confirmation
                status_check = await http_client.get_signature_statuses([signature_bytes])
                
                if status_check.value and status_check.value[0]:
                    tx_status = status_check.value[0]
                    
                    # Check for successful confirmation (status == null) and not an error
                    if tx_status.confirmation_status in ['confirmed', 'finalized'] and tx_status.err is None:
                        logger.info(f"Transaction {signature[:10]} confirmed successfully.")
                        return True
                    
                    logger.error(f"Transaction {signature[:10]} confirmed but failed on-chain: {tx_status.err}")
                    return False
                    
                return False # Should not happen if confirm_transaction awaited successfully

            except Exception as e:
                logger.error(f"RPC Error during transaction confirmation for {signature[:10]}: {e}")
                return False
        
    async def get_accept_bid_instruction(
        self,
        seller_wallet: str,
        bidder_wallet: str,
        nft_mint_addr: str,
    ) -> Dict[str, Any]:
        """Builds the accept_private_bid instruction for seller to accept a bid"""
        state = await self.get_state()
        pdas = await self.resolve_bid_pdas(bidder_wallet, nft_mint_addr, seller_wallet)

        accounts = {
            "seller": Pubkey.from_string(seller_wallet),
            "bidder": Pubkey.from_string(bidder_wallet),
            "bid_account": pdas["bid_account"],
            "sell_intent_account": pdas["sell_intent_account"],
            "nft_mint": Pubkey.from_string(nft_mint_addr),
            "config": state["config_pda"],
            "program_authority": state["program_authority_pda"],
            "quest_user_account": pdas["quest_user_account"],
            "quest_program": QUEST_PROGRAM_ID,
            "system_program": SYSTEM_PROGRAM_ID,
        }

        instruction = await state["instructions"]["accept_private_bid"](
            {},  # No args needed
            accounts
        )

        return {
            "instruction_data": instruction.data.hex(),
            "accounts_meta": [key.to_json() for key in instruction.keys],
        }

    async def get_set_sell_intent_instruction(
        self,
        owner_wallet: str,
        nft_mint_addr: str,
        asking_price_lamports: int,
    ) -> Dict[str, Any]:
        """Builds the set_sell_intent instruction"""
        state = await self.get_state()

        sell_intent_pda, _ = Pubkey.find_program_address(
            [SELL_INTENT_SEED, Pubkey.from_string(owner_wallet).to_bytes(), Pubkey.from_string(nft_mint_addr).to_bytes()],
            MARKETPLACE_PROGRAM_ID
        )

        args = {
            'asking_price_lamports': asking_price_lamports,
            'is_quest_eligible': True,
        }

        accounts = {
            "owner": Pubkey.from_string(owner_wallet),
            "sell_intent_account": sell_intent_pda,
            "nft_mint": Pubkey.from_string(nft_mint_addr),
            "config": state["config_pda"],
            "system_program": SYSTEM_PROGRAM_ID,
            "rent": RENT_SYSVAR,
        }

        instruction = await state["instructions"]["set_sell_intent"](args, accounts)

        return {
            "instruction_data": instruction.data.hex(),
            "accounts_meta": [key.to_json() for key in instruction.keys],
            "sell_intent_pda": sell_intent_pda.to_base58(),
        }

    async def get_accept_asking_price_instruction(
        self,
        buyer_wallet: str,
        seller_wallet: str,
        nft_mint_addr: str,
    ) -> Dict[str, Any]:
        """Builds the accept_asking_price instruction for direct purchase"""
        state = await self.get_state()

        sell_intent_pda, _ = Pubkey.find_program_address(
            [SELL_INTENT_SEED, Pubkey.from_string(seller_wallet).to_bytes(), Pubkey.from_string(nft_mint_addr).to_bytes()],
            MARKETPLACE_PROGRAM_ID
        )

        quest_user_pda, _ = Pubkey.find_program_address(
            [QUEST_USER_SEED, Pubkey.from_string(buyer_wallet).to_bytes()],
            QUEST_PROGRAM_ID
        )

        accounts = {
            "buyer": Pubkey.from_string(buyer_wallet),
            "seller": Pubkey.from_string(seller_wallet),
            "sell_intent_account": sell_intent_pda,
            "nft_mint": Pubkey.from_string(nft_mint_addr),
            "config": state["config_pda"],
            "program_authority": state["program_authority_pda"],
            "quest_user_account": quest_user_pda,
            "quest_program": QUEST_PROGRAM_ID,
            "system_program": SYSTEM_PROGRAM_ID,
        }

        instruction = await state["instructions"]["accept_asking_price"]({}, accounts)

        return {
            "instruction_data": instruction.data.hex(),
            "accounts_meta": [key.to_json() for key in instruction.keys],
        }

    async def get_cancel_bid_instruction(
        self,
        bidder_wallet: str,
        nft_mint_addr: str,
        seller_wallet: str,
    ) -> Dict[str, Any]:
        """Builds the cancel_bid instruction"""
        state = await self.get_state()
        pdas = await self.resolve_bid_pdas(bidder_wallet, nft_mint_addr, seller_wallet)

        accounts = {
            "bidder": Pubkey.from_string(bidder_wallet),
            "bid_account": pdas["bid_account"],
            "system_program": SYSTEM_PROGRAM_ID,
        }

        instruction = await state["instructions"]["cancel_bid"]({}, accounts)

        return {
            "instruction_data": instruction.data.hex(),
            "accounts_meta": [key.to_json() for key in instruction.keys],
        }

    async def get_reject_bid_instruction(
        self,
        seller_wallet: str,
        bidder_wallet: str,
        nft_mint_addr: str,
    ) -> Dict[str, Any]:
        """Builds the reject_bid instruction for seller to reject a bid"""
        state = await self.get_state()
        pdas = await self.resolve_bid_pdas(bidder_wallet, nft_mint_addr, seller_wallet)

        accounts = {
            "seller": Pubkey.from_string(seller_wallet),
            "bidder": Pubkey.from_string(bidder_wallet),
            "bid_account": pdas["bid_account"],
            "system_program": SYSTEM_PROGRAM_ID,
        }

        instruction = await state["instructions"]["reject_bid"]({}, accounts)

        return {
            "instruction_data": instruction.data.hex(),
            "accounts_meta": [key.to_json() for key in instruction.keys],
        }

    async def get_counter_bid_instruction(
        self,
        seller_wallet: str,
        bidder_wallet: str,
        nft_mint_addr: str,
        counter_amount_lamports: int,
    ) -> Dict[str, Any]:
        """Builds the counter_bid instruction for seller to counter an existing bid"""
        state = await self.get_state()
        pdas = await self.resolve_bid_pdas(bidder_wallet, nft_mint_addr, seller_wallet)

        accounts = {
            "seller": Pubkey.from_string(seller_wallet),
            "bidder": Pubkey.from_string(bidder_wallet),
            "bid_account": pdas["bid_account"],
            "system_program": SYSTEM_PROGRAM_ID,
        }

        # Counter-bid instruction with new amount
        args = {
            "counter_amount": counter_amount_lamports,
        }

        instruction = await state["instructions"]["counter_bid"](args, accounts)

        return {
            "instruction_data": instruction.data.hex(),
            "accounts_meta": [key.to_json() for key in instruction.keys],
            "counter_amount_lamports": counter_amount_lamports,
        }

    async def get_create_auction_instruction(
        self,
        seller_wallet: str,
        nft_mint_addr: str,
        starting_price_lamports: int,
        reserve_price_lamports: int,
        duration_hours: int,
    ) -> Dict[str, Any]:
        """Builds the create_auction instruction"""
        state = await self.get_state()

        # Derive auction PDA
        auction_pda, _ = Pubkey.find_program_address(
            [b"auction", Pubkey.from_string(nft_mint_addr).to_bytes(), Pubkey.from_string(seller_wallet).to_bytes()],
            MARKETPLACE_PROGRAM_ID
        )

        accounts = {
            "seller": Pubkey.from_string(seller_wallet),
            "nft_mint": Pubkey.from_string(nft_mint_addr),
            "auction_account": auction_pda,
            "system_program": SYSTEM_PROGRAM_ID,
            "rent": RENT_SYSVAR,
        }

        args = {
            "starting_price": starting_price_lamports,
            "reserve_price": reserve_price_lamports,
            "duration_hours": duration_hours,
        }

        instruction = await state["instructions"]["create_auction"](args, accounts)

        return {
            "instruction_data": instruction.data.hex(),
            "accounts_meta": [key.to_json() for key in instruction.keys],
            "auction_pda": auction_pda.to_base58(),
        }

    async def get_place_auction_bid_instruction(
        self,
        bidder_wallet: str,
        auction_id: str,
        nft_mint_addr: str,
        seller_wallet: str,
        bid_amount_lamports: int,
    ) -> Dict[str, Any]:
        """Builds the place_auction_bid instruction"""
        state = await self.get_state()

        # Derive auction PDA
        auction_pda, _ = Pubkey.find_program_address(
            [b"auction", Pubkey.from_string(nft_mint_addr).to_bytes(), Pubkey.from_string(seller_wallet).to_bytes()],
            MARKETPLACE_PROGRAM_ID
        )

        accounts = {
            "bidder": Pubkey.from_string(bidder_wallet),
            "seller": Pubkey.from_string(seller_wallet),
            "auction_account": auction_pda,
            "system_program": SYSTEM_PROGRAM_ID,
        }

        args = {
            "bid_amount": bid_amount_lamports,
        }

        instruction = await state["instructions"]["place_auction_bid"](args, accounts)

        return {
            "instruction_data": instruction.data.hex(),
            "accounts_meta": [key.to_json() for key in instruction.keys],
        }


    async def get_cancel_auction_instruction(
        self,
        seller_wallet: str,
        nft_mint_addr: str,
    ) -> Dict[str, Any]:
        """Builds the cancel_auction instruction"""
        state = await self.get_state()

        # Derive auction PDA
        auction_pda, _ = Pubkey.find_program_address(
            [b"auction", Pubkey.from_string(nft_mint_addr).to_bytes(), Pubkey.from_string(seller_wallet).to_bytes()],
            MARKETPLACE_PROGRAM_ID
        )

        accounts = {
            "seller": Pubkey.from_string(seller_wallet),
            "auction_account": auction_pda,
            "system_program": SYSTEM_PROGRAM_ID,
        }

        instruction = await state["instructions"]["cancel_auction"]({}, accounts)

        return {
            "instruction_data": instruction.data.hex(),
            "accounts_meta": [key.to_json() for key in instruction.keys],
        }

    async def get_finalize_auction_instruction(
        self,
        seller_wallet: str,
        nft_mint_addr: str,
        winner_wallet: str,
    ) -> Dict[str, Any]:
        """Builds the finalize_auction instruction"""
        state = await self.get_state()

        # Derive auction PDA
        auction_pda, _ = Pubkey.find_program_address(
            [b"auction", Pubkey.from_string(nft_mint_addr).to_bytes(), Pubkey.from_string(seller_wallet).to_bytes()],
            MARKETPLACE_PROGRAM_ID
        )

        accounts = {
            "seller": Pubkey.from_string(seller_wallet),
            "winner": Pubkey.from_string(winner_wallet),
            "auction_account": auction_pda,
            "nft_mint": Pubkey.from_string(nft_mint_addr),
            "system_program": SYSTEM_PROGRAM_ID,
            "token_program": TOKEN_PROGRAM_ID,
        }

        instruction = await state["instructions"]["finalize_auction"]({}, accounts)

        return {
            "instruction_data": instruction.data.hex(),
            "accounts_meta": [key.to_json() for key in instruction.keys],
        }


# marketplace/solana_client.py (Add this method)

    async def send_admin_config_tx(
        self,
        instruction_name: str,
        admin_args: Dict[str, Any],
        fee_wallet: str,
        quest_wallet: str,
        vault_wallet: str,
        quest_program: str,
        # Only required for initialize_config:
        platform_fee_bps: Optional[int] = None, 
        max_royalty_subsidy_bps: Optional[int] = None,
        min_vitality_for_rebate: Optional[int] = None,
        rebate_counter_min: Optional[int] = None,
        auction_loser_rebate_lamports: Optional[int] = None,
        rejection_counter_min: Optional[int] = None,
        rejection_rebate_lamports: Optional[int] = None,
    ) -> str:
        """
        Builds, signs, and sends an admin-level configuration transaction 
        (e.g., initialize_config or update_config_wallets).
        """
        state = await self.get_state()
        program = state["program"]
        
        # --- CRITICAL SECURITY CHECK ---
        admin_signer_keypair = state["admin_signer"]
        if admin_signer_keypair is None:
            raise PermissionError("Admin keypair is not loaded. Cannot sign transaction.")
            
        admin_pubkey = admin_signer_keypair.public_key
        
        # 1. Prepare Arguments
        # Combine base accounts (for init) with rules (for update)
        
        # The arguments passed to the Anchor instruction (init needs all fields, update needs rules only)
        if instruction_name == "initialize_config":
            # Initialize requires all fields
            args = [
                platform_fee_bps, max_royalty_subsidy_bps, min_vitality_for_rebate, 
                rebate_counter_min, auction_loser_rebate_lamports, 
                rejection_counter_min, rejection_rebate_lamports
            ]
        elif instruction_name == "update_config_rules":
             args = [
                platform_fee_bps, max_royalty_subsidy_bps, min_vitality_for_rebate, 
                rebate_counter_min, auction_loser_rebate_lamports, 
                rejection_counter_min, rejection_rebate_lamports
            ]
        elif instruction_name == "update_config_wallets":
            args = [Pubkey.from_string(fee_wallet), Pubkey.from_string(quest_wallet), Pubkey.from_string(vault_wallet), Pubkey.from_string(quest_program)]
        else:
            raise ValueError(f"Unknown instruction: {instruction_name}")

        
        # 2. Prepare Accounts (Accounts differ based on the instruction)
        base_accounts = {
            "config": state["config_pda"],
            "admin": admin_pubkey,
            "program_authority": state["program_authority_pda"],
            "system_program": SYSTEM_PROGRAM_ID,
            "rent": RENT_SYSVAR,
        }

        if instruction_name == "initialize_config":
             accounts = {
                **base_accounts,
                "fee_wallet": Pubkey.from_string(fee_wallet),
                "quest_wallet": Pubkey.from_string(quest_wallet),
                "vault_wallet": Pubkey.from_string(vault_wallet),
                "quest_program": Pubkey.from_string(quest_program),
            }
        elif instruction_name == "update_config_rules":
             accounts = base_accounts
        elif instruction_name == "update_config_wallets":
             accounts = base_accounts
        else:
            accounts = base_accounts # Should be covered above

        # 3. Build and Sign Transaction on Server
        instruction = await state["instructions"][instruction_name](
            args,
            accounts
        )
        
        tx = Transaction()
        tx.add(instruction)
        
        # Send transaction, signing with the server-loaded Keypair
        signature = await program.provider.send(tx, [admin_signer_keypair])
        
        logger.info(f"Admin TX {instruction_name} sent. Signature: {signature}")

        # Wait for confirmation before returning success
        await state["program"].provider.connection.confirm_transaction(signature, commitment="finalized")

        return signature

    def _get_program_authority_key(self) -> str:
        """
        Retrieve program authority key from encrypted storage.

        Returns:
            Base58 encoded private key string

        Raises:
            ValueError: If key not found or cannot be decrypted
        """
        from django.core.cache import cache

        # Check cache first (5 minute TTL for performance)
        cache_key = 'program_authority_key_b58'
        cached_key = cache.get(cache_key)

        if cached_key:
            return cached_key

        try:
            # Try encrypted storage first (production)
            from admin_secure.models import EncryptedSecret

            key_b58 = EncryptedSecret.get_secret_value(
                secret_name='marketplace_program_authority',
                requesting_component='solana_client'
            )

            # Cache for 5 minutes
            cache.set(cache_key, key_b58, timeout=300)

            return key_b58

        except Exception as encrypted_error:
            # Fallback to environment variable (development/backwards compatibility)
            logger.warning(
                f"Could not load key from encrypted storage: {encrypted_error}. "
                f"Falling back to environment variable."
            )

            pk_b58 = settings.PROGRAM_AUTHORITY_PRIVATE_KEY_B58

            if pk_b58:
                logger.info("✅ Program Authority key loaded from environment variable (not recommended for production)")
                # Cache environment variable too
                cache.set(cache_key, pk_b58, timeout=300)
                return pk_b58
            else:
                raise ValueError(
                    "Program authority key not found in encrypted storage or environment. "
                    "Store key using: python manage.py shell → "
                    "EncryptedSecret(name='marketplace_program_authority').encrypt_and_save(key, admin)"
                )