# marketplace/services.py

import logging
from decimal import Decimal
import uuid
from typing import Dict, Any, Optional

from django.utils import timezone
from datetime import timedelta

# Use the async version of the Solana client
from marketplace.solana_client import SolanaClient
from solana.rpc.async_api import AsyncClient
from asgiref.sync import sync_to_async
from django.db import transaction

# Import your models and other services
from nft_data.models import NFT
from indexer.models import NFTEvent
from .models import PrivateBid, MarketplaceTransaction, AuctionEvent, TransactionMonitoring
from .bid_validation_service import BidValidationService
from .safety_validation import SafetyValidationService
# from notifications.services import PrivacyNotificationService # To be integrated
from .solana_client import SolanaClient

logger = logging.getLogger(__name__)


class MarketplaceService:
    """
    Handles privacy-preserving marketplace operations.
    This service is now fully asynchronous.
    """
    def __init__(self):

        # Initialize the custom Solana client
        self.solana_client = SolanaClient()
        self.bid_validation_service = BidValidationService()
        self.bid_validation_service = BidValidationService()
        self.safety_validator = SafetyValidationService()
        # self.notification_service = PrivacyNotificationService()

    async def _create_transaction_record(
        self,
        signature: str,
        action_type: str,
        nft_mint: str = '',
        user_wallet: str = ''
    ) -> TransactionMonitoring:
        """Helper method to create transaction monitoring records"""
        return await sync_to_async(
            TransactionMonitoring.create_from_transaction,
            thread_sensitive=False
        )(
            signature=signature,
            action_type=action_type,
            nft_mint=nft_mint,
            user_wallet=user_wallet,
            rpc_provider=self.solana_client.current_provider_name or 'unknown'
        )

# --- Private Bidding Actions (Unsolicited Offers) ---

    async def place_private_bid(
        self,
        bidder_wallet: str,
        nft_mint: str,
        amount: Decimal,
        expiry_hours: int = 72,
        signed_transaction: Optional[str] = None
    ) -> dict:
        """
        Step 1 (signed_transaction=None): Build instruction and return to frontend for signing
        Step 2 (signed_transaction provided): Confirm transaction and update database
        """
        logger.info(f"Initiating private bid for NFT {nft_mint} from {bidder_wallet} for {amount} SOL.")

        # --- 1. Fetch NFT and Validate the Bid ---
        try:
            # Use sync_to_async + thread_sensitive for ORM call
            nft = await sync_to_async(
                NFT.objects.select_related('collection').get,
                thread_sensitive=False
            )(mint_address=nft_mint)

            # CRITICAL SAFETY CHECK 1: Bid spam prevention and ownership check (BLOCKS action)
            is_safe, safety_error = await self.safety_validator.validate_bid_placement_safety(
                bidder_wallet=bidder_wallet,
                nft=nft,
                bid_amount=amount
            )
            if not is_safe:
                raise ValueError(safety_error)

            # CRITICAL SAFETY CHECK 2: Bid amount validation
            is_valid, error_message = await self.bid_validation_service.validate_bid(nft, amount)

            if not is_valid:
                raise ValueError(error_message)

        except NFT.DoesNotExist:
            logger.error(f"place_bid failed: NFT with mint address {nft_mint} not found.")
            raise ValueError("NFT not found.")

        # --- 2. Check Quest Eligibility (Does NOT block action) ---
        is_quest_eligible = await self.safety_validator.check_quest_eligibility(
            nft=nft,
            actor_wallet=bidder_wallet,
            action_type='bid'
        )
        logger.info(f"Quest eligibility for bid: {is_quest_eligible}")

        # --- STEP 1: Build instruction and return to frontend ---
        if signed_transaction is None:
            logger.info("Building place_private_bid instruction for client signing...")

            # Convert SOL amount to lamports (1 SOL = 1,000,000,000 lamports)
            amount_lamports = int(amount * 1_000_000_000)

            # Get instruction data from Solana client
            instruction_data = await self.solana_client.get_place_private_bid_instruction(
                bidder_wallet=bidder_wallet,
                nft_mint_addr=nft_mint,
                seller_wallet=nft.owner,
                amount_lamports=amount_lamports,
                expiry_hours=expiry_hours,
                nft_vitality_score=int(getattr(nft, 'vitality_score', 50)),
                negotiation_count=getattr(nft, 'negotiation_count', 0)
            )

            # Return instruction to frontend for signing
            return {
                'success': True,
                'instruction_data': instruction_data,
                'requires_signature': True,
                'action_type': 'place_bid',
                'nft_mint': nft_mint,
                'amount': str(amount),
                'bidder_wallet': bidder_wallet
            }

        # --- STEP 2: Process signed transaction ---
        logger.info("Processing signed transaction from frontend...")

        # TODO: Submit signed transaction to Solana blockchain via RPC
        # For now, we'll simulate this and use the signed_transaction as the signature
        transaction_signature = signed_transaction  # This would be the actual tx signature from the blockchain
        mock_encrypted_state_account = f"bid_acct_{uuid.uuid4()}"

        # --- 3. Update Database Records ---
        @sync_to_async(thread_sensitive=False)
        def _create_bid_in_transaction(nft_instance):
            with transaction.atomic():
                expires_at = timezone.now() + timedelta(hours=expiry_hours)

                # ORM create call inside the sync function
                bid = PrivateBid.objects.create(
                    bid_id=transaction_signature, # Using tx sig as bid_id
                    nft=nft_instance,
                    collection=nft_instance.collection,
                    bidder=bidder_wallet,
                    owner_at_creation=nft_instance.owner,
                    encrypted_state_account=mock_encrypted_state_account,
                    expires_at=expires_at,
                    status=PrivateBid.Status.ACTIVE
                )
                # Increment negotiation count on NFT if it exists
                if nft_instance.has_sell_intent:
                    nft_instance.negotiation_count = (nft_instance.negotiation_count or 0) + 1
                    nft_instance.save(update_fields=['negotiation_count'])

                return bid

        bid = await _create_bid_in_transaction(nft)  # type: ignore

        # --- 4. Send Notification to Owner (Placeholder) ---
        logger.info(f"Notification sent to owner {nft.owner} for new private bid.")

        logger.info(f"Successfully placed and recorded private bid {bid.bid_id}.")
        return {
            'success': True,
            'bid_id': bid.bid_id,
            'transaction_signature': transaction_signature
        }
    
    async def confirm_private_bid_tx(
            self,
            bidder_wallet: str,
            temp_bid_id: str,
            transaction_signature: str,
            amount: Decimal,
        ) -> Dict[str, Any]:
            """
            Finalizes a PENDING bid record after the client has confirmed the
            transaction signature on the Solana network, using delete-then-create
            due to bid_id being the Primary Key.
            """
            logger.info(f"Confirming PENDING bid {temp_bid_id} with signature {transaction_signature[:10]}...")

            # --- CREATE TRANSACTION MONITORING RECORD ---
            tx_record = await self._create_transaction_record(
                signature=transaction_signature,
                action_type='place_bid_confirm',
                user_wallet=bidder_wallet
            )

            # --- 1. CRITICAL: Verify transaction on Solana ---
            try:
                # Call the live client method to wait for and verify confirmation
                is_confirmed_on_chain = await self.solana_client.confirm_transaction(transaction_signature)

                if not is_confirmed_on_chain:
                    await sync_to_async(tx_record.mark_failed, thread_sensitive=False)(
                        "Transaction failed on-chain or could not be finalized by the RPC."
                    )
                    raise Exception("Transaction failed on-chain or could not be finalized by the RPC.")

                # Mark as confirmed
                await sync_to_async(tx_record.mark_confirmed, thread_sensitive=False)()

            except Exception as e:
                logger.error(f"Solana Confirmation Failure for {transaction_signature}: {e}")
                await sync_to_async(tx_record.mark_failed, thread_sensitive=False)(str(e))
                raise ValueError(f"Transaction confirmation failed: {e}")

            # --- 2. Database Finalization (Atomic Write: Delete Temp, Create Permanent) ---
            @sync_to_async(thread_sensitive=True)
            def _finalize_bid_in_transaction():
                with transaction.atomic():
                    # 2a. Retrieve and lock the PENDING record
                    try:
                        bid = PrivateBid.objects.select_for_update().get(
                            bid_id=temp_bid_id,
                            status=PrivateBid.Status.PENDING,
                            bidder=bidder_wallet
                        )
                    except PrivateBid.DoesNotExist:
                        raise ValueError(f"Pending bid not found or already processed: {temp_bid_id}")

                    # 2b. Sanity Check
                    if bid.amount != amount:
                        raise ValueError(f"Amount mismatch. Stored DB amount: {bid.amount}, Client confirmed amount: {amount}. Aborting.")

                    # 2c. Store and Delete Temporary Record
                    temp_bid_data = {
                        'nft': bid.nft,
                        'collection': bid.collection,
                        'bidder': bid.bidder,
                        'owner_at_creation': bid.owner_at_creation,
                        'encrypted_state_account': bid.encrypted_state_account,
                        'amount': amount,
                        'expires_at': bid.expires_at,
                        'resolved_at': timezone.now()
                    }
                    
                    bid.delete() 
                    
                    # 2d. Create the new permanent record with the Transaction Signature as PK
                    final_bid = PrivateBid.objects.create(
                        bid_id=transaction_signature,
                        status=PrivateBid.Status.ACTIVE,
                        created_at=bid.created_at, 
                        **temp_bid_data
                    )

                    return final_bid.bid_id

            final_bid_id = await _finalize_bid_in_transaction()

            logger.info(f"✅ Bid {final_bid_id[:10]}... successfully moved from PENDING to ACTIVE (Final PK).")

            return {
                'success': True,
                'transaction_signature': final_bid_id,
                'status': 'active',
                'message': 'Bid confirmed on-chain and recorded.'
            }

# --- Owner Actions on Private Bids ---

    async def accept_private_bid(self, owner_wallet: str, bid_id: str, signed_transaction: Optional[str] = None) -> dict:
        """
        Step 1 (signed_transaction=None): Build instruction and return to frontend for signing
        Step 2 (signed_transaction provided): Confirm transaction and update database
        """
        logger.info(f"Owner {owner_wallet} is attempting to accept bid {bid_id}.")

        # --- 1. Fetch Bid and Validate ---
        try:
            # Fetch bid with NFT/Collection to check ownership and prevent stale data
            bid = await sync_to_async(
                PrivateBid.objects.select_related('nft__collection').get,
                thread_sensitive=False
            )(bid_id=bid_id)

            if bid.status != PrivateBid.Status.ACTIVE:
                raise ValueError("Bid is not active.")

            # CRITICAL SAFETY CHECK: Ownership verification (BLOCKS action)
            is_owner, ownership_error = self.safety_validator.verify_ownership(
                nft=bid.nft,
                seller_wallet=owner_wallet
            )
            if not is_owner:
                raise PermissionError(ownership_error)

            if timezone.now() > bid.expires_at:
                # Use sync_to_async to update status before raising error
                @sync_to_async(thread_sensitive=False)
                def _mark_expired(bid_instance):
                    bid_instance.status = PrivateBid.Status.EXPIRED
                    bid_instance.save(update_fields=['status'])
                await _mark_expired(bid)
                raise ValueError("This bid has expired.")

        except PrivateBid.DoesNotExist:
            logger.error(f"accept_bid failed: Bid with ID {bid_id} not found.")
            raise ValueError("Bid not found.")

        # --- 2. Check Quest Eligibility (Does NOT block action) ---
        is_quest_eligible = await self.safety_validator.check_quest_eligibility(
            nft=bid.nft,
            actor_wallet=owner_wallet,
            action_type='sale'
        )
        logger.info(f"Quest eligibility for sale: {is_quest_eligible}")

        # --- STEP 1: Build instruction and return to frontend ---
        if signed_transaction is None:
            logger.info("Building accept_private_bid instruction for client signing...")

            instruction_data = await self.solana_client.get_accept_bid_instruction(
                seller_wallet=owner_wallet,
                bidder_wallet=bid.bidder,
                nft_mint_addr=bid.nft.mint_address
            )

            return {
                'success': True,
                'instruction_data': instruction_data,
                'requires_signature': True,
                'action_type': 'accept_bid',
                'bid_id': bid_id
            }

        # --- STEP 2: Process signed transaction ---
        logger.info("Processing signed transaction from frontend...")
        transaction_signature = signed_transaction

        # --- CREATE TRANSACTION MONITORING RECORD ---
        tx_record = await self._create_transaction_record(
            signature=transaction_signature,
            action_type='accept_bid',
            nft_mint=bid.nft.mint_address,
            user_wallet=owner_wallet
        )

        try:
            # --- 3. Decrypt Amount & Execute On-Chain Sale ---
            mock_decrypted_amount = Decimal('1.30') # Placeholder for final bid price
            logger.info(f"Processing on-chain sale for {mock_decrypted_amount} SOL...")
            logger.info(f"Passing is_quest_eligible={is_quest_eligible} to blockchain transaction")

            # Mark transaction as confirmed (in production, wait for actual confirmation)
            await sync_to_async(tx_record.mark_confirmed, thread_sensitive=False)()

            # --- 4. Update All Database Records Atomically ---
            # The entire update sequence must be atomic to prevent a race condition where
            # the NFT is sold twice or the bid is accepted twice.
            @sync_to_async(thread_sensitive=False)
            def _update_db_after_sale(bid_instance, sale_signature, sale_amount, seller_wallet):
                with transaction.atomic():
                    # Lock NFT and Bid
                    nft_to_update = NFT.objects.select_for_update().get(pk=bid_instance.nft.pk)
                    # Re-fetch the bid inside the lock to ensure state hasn't changed (though passed instance should be fine)
                    # For maximum safety, re-check status if we didn't lock it earlier, but here we just update the passed instance

                    # a. Update the PrivateBid status
                    bid_instance.status = PrivateBid.Status.ACCEPTED
                    bid_instance.resolved_at = timezone.now()
                    bid_instance.save()

                    # b. Create the official NFTEvent for analytics
                    nft_event = NFTEvent.objects.create(
                        event_id=sale_signature,
                        collection_address=nft_to_update.collection.address,
                        nft_mint=nft_to_update.mint_address,
                        event_type='SALE',
                        marketplace='traitkeeper',
                        amount=sale_amount,
                        buyer=bid_instance.bidder,
                        seller=seller_wallet,
                        timestamp=timezone.now()
                    )

                    # c. Create the detailed MarketplaceTransaction record
                    MarketplaceTransaction.objects.create(
                        transaction_id=sale_signature,
                        nft_event=nft_event,
                        transaction_type=MarketplaceTransaction.TransactionType.BID_ACCEPTED,
                        was_encrypted=True,
                        reveal_timestamp=timezone.now(),
                        nft_vitality_at_sale=getattr(nft_to_update, 'vitality_score', None) or 50.0,
                        suggested_price_at_sale=Decimal('1.25'), # Placeholder
                        vs_vitality_suggested=Decimal('1.04'),   # Placeholder
                        vs_collection_floor=Decimal('1.36')      # Placeholder
                    )

                    # d. Update the NFT's ownership and clear listings/intents
                    nft_to_update.owner = bid_instance.bidder
                    nft_to_update.has_buy_price = False
                    nft_to_update.buy_price = None
                    nft_to_update.is_open_to_offers = False
                    nft_to_update.has_sell_intent = False
                    nft_to_update.asking_price = None
                    nft_to_update.save(update_fields=[
                        'owner',
                        'has_buy_price',
                        'buy_price',
                        'is_open_to_offers',
                        'has_sell_intent',
                        'asking_price'
                    ])

                    # e. Invalidate other open bids on this NFT
                    PrivateBid.objects.filter(
                        nft=nft_to_update,
                        status=PrivateBid.Status.ACTIVE
                    ).exclude(pk=bid_instance.pk).update(status=PrivateBid.Status.CANCELLED)

            await _update_db_after_sale(bid, transaction_signature, mock_decrypted_amount, owner_wallet)  # type: ignore

            # --- 5. Send Notifications (Placeholder) ---
            logger.info(f"Sale complete. Bid {bid.bid_id} accepted. NFT {bid.nft.mint_address} transferred to {bid.bidder}.")

            return {
                'success': True,
                'transaction_signature': transaction_signature,
                'sale_price': mock_decrypted_amount
            }

        except Exception as e:
            # Mark transaction as failed
            await sync_to_async(tx_record.mark_failed, thread_sensitive=False)(str(e))
            raise

    async def reject_private_bid(self, owner_wallet: str, bid_id: str, signed_transaction: Optional[str] = None) -> dict:
        """
        Step 1 (signed_transaction=None): Build instruction and return to frontend for signing
        Step 2 (signed_transaction provided): Confirm transaction and update database
        """
        logger.info(f"Owner {owner_wallet} is attempting to reject bid {bid_id}.")

        # --- 1. Fetch Bid and Validate ---
        try:
            bid = await sync_to_async(
                PrivateBid.objects.select_related('nft').get, 
                thread_sensitive=False
            )(bid_id=bid_id)

            if bid.status != PrivateBid.Status.ACTIVE:
                raise ValueError("This bid is no longer active.")

            # CRITICAL SAFETY CHECK: Ownership verification (BLOCKS action)
            is_owner, ownership_error = self.safety_validator.verify_ownership(
                nft=bid.nft,
                seller_wallet=owner_wallet
            )
            if not is_owner:
                raise PermissionError(ownership_error)

        except PrivateBid.DoesNotExist:
            raise ValueError("Bid not found.")

        # --- STEP 1: Build instruction and return to frontend ---
        if signed_transaction is None:
            logger.info("Building reject_private_bid instruction for client signing...")

            instruction_data = await self.solana_client.get_reject_bid_instruction(
                seller_wallet=owner_wallet,
                bidder_wallet=bid.bidder,
                nft_mint_addr=bid.nft.mint_address
            )

            return {
                'success': True,
                'instruction_data': instruction_data,
                'requires_signature': True,
                'action_type': 'reject_bid',
                'bid_id': bid_id
            }

        # --- STEP 2: Process signed transaction ---
        logger.info("Processing signed transaction from frontend...")
        transaction_signature = signed_transaction

        # --- 3. Update Database Record ---
        @sync_to_async(thread_sensitive=False) 
        def _update_bid_status(bid_instance):
            bid_instance.status = PrivateBid.Status.REJECTED
            bid_instance.resolved_at = timezone.now()
            bid_instance.save(update_fields=['status', 'resolved_at'])
        
        await _update_bid_status(bid)
        
        # --- 4. Send Notification (Placeholder) ---
        logger.info(f"Bid {bid_id} has been rejected. Notifying bidder {bid.bidder}.")

        return {
            'success': True,
            'status': 'rejected',
            'transaction_signature': transaction_signature
        }

    async def cancel_private_bid(self, bidder_wallet: str, bid_id: str, signed_transaction: Optional[str] = None) -> dict:
        """
        Step 1 (signed_transaction=None): Build instruction and return to frontend for signing
        Step 2 (signed_transaction provided): Confirm transaction and update database
        """
        logger.info(f"Bidder {bidder_wallet} is attempting to cancel bid {bid_id}.")

        # --- 1. Fetch Bid and Validate ---
        try:
            # Use sync_to_async + thread_sensitive for ORM call
            bid = await sync_to_async(PrivateBid.objects.get, thread_sensitive=False)(bid_id=bid_id)

            if bid.status != PrivateBid.Status.ACTIVE:
                raise ValueError("This bid is no longer active and cannot be cancelled.")

            if bid.bidder != bidder_wallet:
                raise PermissionError("You can only cancel your own bids.")

        except PrivateBid.DoesNotExist:
            raise ValueError("Bid not found.")

        # --- STEP 1: Build instruction and return to frontend ---
        if signed_transaction is None:
            logger.info("Building cancel_private_bid instruction for client signing...")

            # Get NFT and seller info for PDA derivation
            nft = await sync_to_async(lambda: bid.nft, thread_sensitive=False)()
            seller_wallet = bid.owner_at_creation

            instruction_data = await self.solana_client.get_cancel_bid_instruction(
                bidder_wallet=bidder_wallet,
                nft_mint_addr=nft.mint_address,
                seller_wallet=seller_wallet
            )

            return {
                'success': True,
                'instruction_data': instruction_data,
                'requires_signature': True,
                'action_type': 'cancel_bid',
                'bid_id': bid_id
            }

        # --- STEP 2: Process signed transaction ---
        logger.info("Processing signed transaction from frontend...")
        transaction_signature = signed_transaction

        # --- 3. Update Database Record ---
        # Use sync_to_async + thread_sensitive for ORM call
        @sync_to_async(thread_sensitive=False) 
        def _update_bid_status(bid_instance):
            bid_instance.status = PrivateBid.Status.CANCELLED
            bid_instance.resolved_at = timezone.now()
            bid_instance.save(update_fields=['status', 'resolved_at'])
        
        await _update_bid_status(bid)

        logger.info(f"Bid {bid_id} has been successfully cancelled by the bidder.")

        return {
            'success': True,
            'status': 'cancelled',
            'transaction_signature': transaction_signature
        }

# --- Direct Sell Actions (Fixed Price, Non-Negotiable) ---

    async def set_direct_sell(
        self,
        owner_wallet: str,
        nft_mint: str,
        price: Decimal
    ) -> dict:
        """
        Sets a FIXED, NON-NEGOTIABLE price for direct purchase.
        """
        logger.info(f"Owner {owner_wallet} is setting direct sell price {price} SOL for {nft_mint}.")
        
        # --- 1. Fetch NFT and Validate ---
        try:
            # Add select_related('collection')
            nft = await sync_to_async(
                NFT.objects.select_related('collection').get,
                thread_sensitive=False
            )(mint_address=nft_mint)

            # CRITICAL SAFETY CHECK: Ownership verification (BLOCKS action)
            is_owner, ownership_error = self.safety_validator.verify_ownership(
                nft=nft,
                seller_wallet=owner_wallet
            )
            if not is_owner:
                raise PermissionError(ownership_error)

            if price <= 0:
                raise ValueError("Price must be greater than 0 SOL.")

            # validate_bid is async, no sync_to_async needed
            is_valid, error_message = await self.bid_validation_service.validate_bid(nft, price)
            if not is_valid:
                # NOTE: Allowing a user to list outside the vitality range is okay, but we warn.
                logger.warning(f"Price validation warning: {error_message}")

        except NFT.DoesNotExist:
            raise ValueError("NFT not found.")
        
        # --- 2. Check Quest Eligibility (Does NOT block action) ---
        is_quest_eligible = await self.safety_validator.check_quest_eligibility(
            nft=nft,
            actor_wallet=owner_wallet,
            action_type='list'
        )
        logger.info(f"Quest eligibility for listing: {is_quest_eligible}")

        # --- 3. On-Chain Interaction (Placeholder) ---
        logger.info(f"Simulating on-chain transaction to list NFT for {price} SOL...")
        logger.info(f"Passing is_quest_eligible={is_quest_eligible} to blockchain transaction")
        mock_signature = f"mock_list_tx_{uuid.uuid4()}"
        
        # --- 4. Update Database ---
        # Use sync_to_async + thread_sensitive for the transaction block
        @sync_to_async(thread_sensitive=False)
        def _update_nft_listing():
            # Get NFT object inside the sync scope to ensure it's up-to-date and in the correct thread
            nft_to_update = NFT.objects.get(pk=nft.pk) 
            
            nft_to_update.has_buy_price = True
            nft_to_update.buy_price = price
            nft_to_update.has_sell_intent = False
            nft_to_update.asking_price = None
            
            update_fields = [
                'has_buy_price',
                'buy_price',
                'has_sell_intent',
                'asking_price'
            ]
            nft_to_update.save(update_fields=update_fields)
            
        await _update_nft_listing()
        
        logger.info(f"NFT {nft_mint} is now listed for direct sell at {price} SOL.")
        
        return {
            'success': True,
            'nft_mint': nft_mint,
            'direct_sell_price': price, 
            'transaction_signature': mock_signature
        }
    
    async def remove_direct_sell(
        self,
        owner_wallet: str,
        nft_mint: str
    ) -> dict:
        """
        Removes a FIXED, NON-NEGOTIABLE direct sell listing.
        """
        logger.info(f"Owner {owner_wallet} is removing direct sell listing for {nft_mint}.")

        # --- 1. Fetch NFT and Validate Ownership ---
        try:
            # Use sync_to_async + thread_sensitive for ORM call
            nft = await sync_to_async(NFT.objects.get, thread_sensitive=False)(mint_address=nft_mint)

            # CRITICAL SAFETY CHECK: Ownership verification (BLOCKS action)
            is_owner, ownership_error = self.safety_validator.verify_ownership(
                nft=nft,
                seller_wallet=owner_wallet
            )
            if not is_owner:
                raise PermissionError(ownership_error)

            if not nft.has_buy_price:
                logger.warning(f"NFT {nft_mint} is not listed for direct sell. No action taken.")
                return {'success': True, 'message': 'Listing was already inactive.'}

        except NFT.DoesNotExist:
            raise ValueError("NFT not found.")

        # --- 2. On-Chain Interaction (Placeholder) ---
        logger.info(f"Simulating on-chain transaction to remove direct sell listing...")
        mock_signature = f"mock_remove_list_tx_{uuid.uuid4()}"

        # --- 3. Update Database ---
        @sync_to_async(thread_sensitive=False)
        def _update_nft_removal():
            nft_to_update = NFT.objects.get(pk=nft.pk) 
            nft_to_update.has_buy_price = False
            nft_to_update.buy_price = None
            update_fields = ['has_buy_price', 'buy_price'] 
            nft_to_update.save(update_fields=update_fields)
            
        await _update_nft_removal()

        logger.info(f"NFT {nft_mint} direct sell listing has been removed.")

        return {
            'success': True,
            'nft_mint': nft_mint,
            'message': 'Direct sell listing removed.',
            'transaction_signature': mock_signature
        }

    async def execute_direct_buy(
        self,
        buyer_wallet: str,
        nft_mint: str
    ) -> dict:
        """
        Executes a direct purchase at the fixed direct sell price.
        """
        logger.info(f"Buyer {buyer_wallet} is attempting to buy NFT {nft_mint} at direct sell price.")
        
        original_owner = None
        sale_price = None
        
        # --- 1. Fetch NFT and Validate ---
        try:
            # Use sync_to_async + thread_sensitive for ORM call
            nft = await sync_to_async(
                NFT.objects.select_related('collection').get, 
                thread_sensitive=False
            )(mint_address=nft_mint)
            
            if not nft.has_buy_price or not nft.buy_price:
                raise ValueError("This NFT is not listed for direct sale.")
            
            if nft.owner == buyer_wallet:
                raise ValueError("You cannot buy your own NFT.")
                
            sale_price = nft.buy_price
            original_owner = nft.owner
            
        except NFT.DoesNotExist:
            raise ValueError("NFT not found.")

        # --- 2. Check Quest Eligibility (Does NOT block action) ---
        is_quest_eligible = await self.safety_validator.check_quest_eligibility(
            nft=nft,
            actor_wallet=original_owner, # Check seller's eligibility for listing/sale
            action_type='sale'
        )
        # Also check buyer's eligibility for the buy action
        is_quest_eligible = is_quest_eligible and await self.safety_validator.check_quest_eligibility(
             nft=nft,
             actor_wallet=buyer_wallet,
             action_type='buy'
        )
        logger.info(f"Quest eligibility for direct buy: {is_quest_eligible}")

        # --- 3. On-Chain Interaction (Placeholder) ---
        logger.info(f"Simulating on-chain purchase for {sale_price} SOL...")
        logger.info(f"Passing is_quest_eligible={is_quest_eligible} to blockchain transaction")
        mock_sale_signature = f"mock_buy_tx_{uuid.uuid4()}"
        
        # --- 4. Update Database ---
        @sync_to_async(thread_sensitive=False) 
        def _execute_sale_in_db(): 
            with transaction.atomic():
                nft_to_update = NFT.objects.select_for_update().get(pk=nft.pk)
                
                # Create NFTEvent
                nft_event = NFTEvent.objects.create(
                    event_id=mock_sale_signature,
                    collection_address=nft_to_update.collection.address,
                    nft_mint=nft_to_update.mint_address,
                    event_type='SALE',
                    marketplace='traitkeeper',
                    amount=sale_price,
                    buyer=buyer_wallet,
                    seller=original_owner,
                    timestamp=timezone.now()
                )
                
                # Create MarketplaceTransaction
                MarketplaceTransaction.objects.create(
                    transaction_id=mock_sale_signature,
                    nft_event=nft_event,
                    transaction_type=MarketplaceTransaction.TransactionType.DIRECT_SALE,
                    was_encrypted=False,
                    nft_vitality_at_sale=getattr(nft_to_update, 'vitality_score', None) or 50.0,
                    suggested_price_at_sale=sale_price,
                    vs_vitality_suggested=Decimal('1.0'),
                    vs_collection_floor=Decimal('1.0')
                )
                
                # Update NFT ownership and clear listing
                nft_to_update.owner = buyer_wallet
                nft_to_update.has_buy_price = False
                nft_to_update.buy_price = None
                nft_to_update.save(update_fields=[
                    'owner', 
                    'has_buy_price', 
                    'buy_price'
                ])
        
        await _execute_sale_in_db()
        
        logger.info(f"Direct sale completed. NFT {nft_mint} transferred to {buyer_wallet} for {sale_price} SOL.")
        
        return {
            'success': True,
            'nft_mint': nft_mint,
            'buyer': buyer_wallet,
            'sale_price': sale_price,
            'transaction_signature': mock_sale_signature
        }

# --- Auction Actions ---

    async def create_private_auction(
            self,
            owner_wallet: str,
            nft_mint: str,
            starting_price: Decimal,
            duration_hours: int,
            reserve_price: Optional[Decimal] = None,
            signed_transaction: Optional[str] = None
        ) -> dict:
            """
            Allows an owner to create a new private auction for their NFT.
            Two-step pattern: builds instruction OR processes signed transaction.
            """
            logger.info(f"Owner {owner_wallet} is creating an auction for {nft_mint}.")

            # --- 1. Fetch NFT and Validate ---
            try:
                nft = await sync_to_async(NFT.objects.get, thread_sensitive=False)(mint_address=nft_mint)

                # CRITICAL SAFETY CHECK: Ownership verification (BLOCKS action)
                is_owner, ownership_error = self.safety_validator.verify_ownership(
                    nft=nft,
                    seller_wallet=owner_wallet
                )
                if not is_owner:
                    raise PermissionError(ownership_error)

                # Check correct fields for listing status
                if nft.has_buy_price or nft.has_sell_intent:
                    raise ValueError("Cannot start an auction for an NFT that is already listed or has a sell intent.")

                # Check for active auction safely
                @sync_to_async(thread_sensitive=False)
                def check_existing_auction(nft_instance):
                    return AuctionEvent.objects.filter(nft=nft_instance, status=AuctionEvent.Status.ACTIVE).exists()

                if await check_existing_auction(nft):
                    raise ValueError("This NFT is already in an active auction.")

                if starting_price <= 0 or duration_hours <= 0:
                    raise ValueError("Starting price and duration must be positive numbers.")

            except NFT.DoesNotExist:
                raise ValueError("NFT not found.")

            # --- STEP 1: Build instruction if no signature provided ---
            if signed_transaction is None:
                logger.info(f"Building create_auction instruction for {nft_mint}...")

                starting_price_lamports = int(starting_price * 1_000_000_000)
                reserve_price_lamports = int(reserve_price * 1_000_000_000) if reserve_price else 0

                instruction_data = await self.solana_client.get_create_auction_instruction(
                    seller_wallet=owner_wallet,
                    nft_mint_addr=nft_mint,
                    starting_price_lamports=starting_price_lamports,
                    reserve_price_lamports=reserve_price_lamports,
                    duration_hours=duration_hours
                )

                return {
                    'success': True,
                    'instruction_data': instruction_data,
                    'requires_signature': True,
                    'message': 'Please sign the transaction in your wallet to create auction.'
                }

            # --- STEP 2: Process signed transaction ---
            logger.info(f"Processing signed create_auction transaction for {nft_mint}...")
            transaction_signature = signed_transaction

            # --- 2. Check Quest Eligibility (Does NOT block action) ---
            is_quest_eligible = await self.safety_validator.check_quest_eligibility(
                nft=nft,
                actor_wallet=owner_wallet,
                action_type='list'
            )
            logger.info(f"Quest eligibility for auction creation: {is_quest_eligible}")

            # --- 3. Update Database Record ---
            @sync_to_async(thread_sensitive=False)
            def _create_auction_in_db():
                with transaction.atomic():
                    # Re-fetch NFT inside transaction lock to avoid race conditions on related fields
                    nft_to_lock = NFT.objects.select_for_update().get(pk=nft.pk)
                    start_time = timezone.now()
                    end_time = start_time + timedelta(hours=duration_hours)

                    auction = AuctionEvent.objects.create(
                        auction_id=transaction_signature,
                        nft=nft_to_lock,
                        collection=nft_to_lock.collection,
                        creator=owner_wallet,
                        start_time=start_time,
                        end_time=end_time,
                        starting_price=starting_price,
                        status=AuctionEvent.Status.ACTIVE,
                    )

                    # Link the auction to the NFT
                    nft_to_lock.active_auction = auction
                    nft_to_lock.is_listed = True
                    nft_to_lock.save(update_fields=['active_auction', 'is_listed'])

                    return auction

            auction = await _create_auction_in_db()

            logger.info(f"Successfully created auction {auction.auction_id} for NFT {nft_mint}.")
            return {
                'success': True,
                'auction_id': auction.auction_id,
                'transaction_signature': transaction_signature,
                'end_time': auction.end_time.isoformat()
            }

    async def place_auction_bid(
        self,
        bidder_wallet: str,
        auction_id: str,
        amount: Decimal,
        signed_transaction: Optional[str] = None
    ) -> dict:
        """
        Places a private, encrypted bid on an active auction.
        Two-step pattern: builds instruction OR processes signed transaction.
        """
        logger.info(f"Bidder {bidder_wallet} is placing a bid on auction {auction_id} for {amount} SOL.")

        # --- 1. Fetch Auction for immediate checks (outside lock) ---
        auction_for_check = await sync_to_async(
            AuctionEvent.objects.select_related('nft').get,
            thread_sensitive=False
        )(auction_id=auction_id)

        # CRITICAL SAFETY CHECK 1: Bid spam prevention
        is_safe, safety_error = await self.safety_validator.validate_bid_placement_safety(
            bidder_wallet=bidder_wallet,
            nft=auction_for_check.nft,
            bid_amount=amount
        )
        if not is_safe:
            raise ValueError(safety_error)

        # --- STEP 1: Build instruction if no signature provided ---
        if signed_transaction is None:
            logger.info(f"Building place_auction_bid instruction for auction {auction_id}...")

            bid_amount_lamports = int(amount * 1_000_000_000)

            instruction_data = await self.solana_client.get_place_auction_bid_instruction(
                bidder_wallet=bidder_wallet,
                auction_id=auction_id,
                nft_mint_addr=auction_for_check.nft.mint_address,
                seller_wallet=auction_for_check.creator,
                bid_amount_lamports=bid_amount_lamports
            )

            return {
                'success': True,
                'instruction_data': instruction_data,
                'requires_signature': True,
                'message': 'Please sign the transaction in your wallet to place auction bid.'
            }

        # --- STEP 2: Process signed transaction ---
        logger.info(f"Processing signed place_auction_bid transaction...")
        transaction_signature = signed_transaction

        # --- 2. Fetch Auction, Validate Bid, and Update DB Atomically ---
        @sync_to_async(thread_sensitive=False)
        def _get_lock_and_update_auction():
            with transaction.atomic():
                # Lock the AuctionEvent object
                auction_obj = AuctionEvent.objects.select_for_update().get(auction_id=auction_id)

                if auction_obj.status != AuctionEvent.Status.ACTIVE:
                    raise ValueError("This auction is no longer active.")
                if timezone.now() >= auction_obj.end_time:
                    raise ValueError("This auction has already ended.")
                if bidder_wallet == auction_obj.creator:
                    raise ValueError("The auction creator cannot bid on their own auction.")

                min_bid = auction_obj.current_bid or auction_obj.starting_price
                if amount <= min_bid:
                    raise ValueError(f"Your bid must be higher than the current bid/start price of {min_bid} SOL.")

                prev_bidder = auction_obj.current_bidder

                # Update auction state
                auction_obj.current_bid = amount
                auction_obj.current_bidder = bidder_wallet

                if hasattr(auction_obj, 'bid_count'):
                    auction_obj.bid_count += 1

                auction_obj.save()

                return auction_obj, prev_bidder

        auction_obj, previous_high_bidder = await _get_lock_and_update_auction()

        # --- 3. Send Notifications (Placeholder) ---
        if previous_high_bidder and previous_high_bidder != bidder_wallet:
            logger.info(f"Notifying previous bidder {previous_high_bidder} that they have been outbid.")

        logger.info(f"Successfully placed bid on auction {auction_id} by {bidder_wallet}.")
        return {
            'success': True,
            'transaction_signature': transaction_signature,
            'is_highest_bid': True,
            'current_bid': amount
        }

    async def finalize_auction(
        self,
        auction_id: str,
        signed_transaction: Optional[str] = None
    ) -> dict:
        """
        Finalizes an auction after its end time has passed.
        Two-step pattern: builds instruction OR processes signed transaction.
        """
        logger.info(f"Attempting to finalize auction {auction_id}.")

        # --- 1. Fetch Auction and Validate Time ---
        @sync_to_async(thread_sensitive=False)
        def _get_and_lock_auction_for_finalize():
            with transaction.atomic():
                auction_obj = AuctionEvent.objects.select_for_update().select_related('nft').get(auction_id=auction_id)

                if auction_obj.status != AuctionEvent.Status.ACTIVE:
                    raise ValueError("Auction is not active.")
                if timezone.now() < auction_obj.end_time:
                    raise ValueError("Auction has not ended yet.")

                return auction_obj

        auction = await _get_and_lock_auction_for_finalize()

        # --- 2. Determine Outcome ---
        if not auction.current_bidder:
            # --- SCENARIO A: NO BIDS - No Solana transaction needed ---
            logger.info(f"Auction {auction_id} ended with no bids. Canceling.")
            mock_close_signature = f"mock_close_tx_{uuid.uuid4()}"

            @sync_to_async(thread_sensitive=False)
            def _cancel_auction_in_db():
                auction.status = AuctionEvent.Status.CANCELLED
                auction.nft.active_auction = None
                auction.nft.is_listed = False
                auction.nft.save(update_fields=['active_auction', 'is_listed'])
                auction.save(update_fields=['status'])

            await _cancel_auction_in_db()

            return {
                'success': True,
                'status': 'cancelled',
                'reason': 'No bids were placed.',
                'transaction_signature': mock_close_signature
            }

        else:
            # --- SCENARIO B: THERE IS A WINNER ---
            logger.info(f"Auction {auction_id} ended. Winner: {auction.current_bidder} at {auction.current_bid} SOL.")

            # --- STEP 1: Build instruction if no signature provided ---
            if signed_transaction is None:
                logger.info(f"Building finalize_auction instruction for auction {auction_id}...")

                instruction_data = await self.solana_client.get_finalize_auction_instruction(
                    seller_wallet=auction.creator,
                    nft_mint_addr=auction.nft.mint_address,
                    winner_wallet=auction.current_bidder
                )

                return {
                    'success': True,
                    'instruction_data': instruction_data,
                    'requires_signature': True,
                    'message': 'Please sign the transaction in your wallet to finalize auction.'
                }

            # --- STEP 2: Process signed transaction ---
            logger.info(f"Processing signed finalize_auction transaction...")
            transaction_signature = signed_transaction

            # Check Quest Eligibility
            is_quest_eligible = await self.safety_validator.check_quest_eligibility(
                nft=auction.nft,
                actor_wallet=auction.creator,
                action_type='sale'
            )
            is_quest_eligible = is_quest_eligible and await self.safety_validator.check_quest_eligibility(
                 nft=auction.nft,
                 actor_wallet=auction.current_bidder,
                 action_type='buy'
            )
            logger.info(f"Quest eligibility for auction sale: {is_quest_eligible}")

            # Update Database Atomically
            @sync_to_async(thread_sensitive=False)
            def _finalize_sale_in_db(auction_to_finalize):
                with transaction.atomic():
                    # Re-lock/Re-fetch the auction object
                    auction_locked = AuctionEvent.objects.select_for_update().select_related('nft__collection').get(pk=auction_to_finalize.pk)
                    nft_to_update = auction_locked.nft

                    # a. Update the AuctionEvent
                    auction_locked.status = AuctionEvent.Status.COMPLETED
                    auction_locked.winner = auction_locked.current_bidder
                    auction_locked.final_price = auction_locked.current_bid
                    auction_locked.save()

                    # b. Create the NFTEvent for analytics
                    NFTEvent.objects.create(
                        event_id=transaction_signature,
                        collection_address=nft_to_update.collection.address,
                        nft_mint=nft_to_update.mint_address,
                        event_type='SALE',
                        marketplace='traitkeeper',
                        amount=auction_locked.final_price,
                        buyer=auction_locked.winner,
                        seller=auction_locked.creator,
                        timestamp=timezone.now()
                    )

                    # c. Update the NFT's ownership and state
                    nft_to_update.owner = auction_locked.winner
                    nft_to_update.active_auction = None
                    nft_to_update.is_listed = False
                    nft_to_update.save(update_fields=['owner', 'active_auction', 'is_listed'])

            await _finalize_sale_in_db(auction)

            logger.info(f"Finalized auction {auction_id}. NFT transferred to {auction.current_bidder}.")

            return {
                'success': True,
                'status': 'completed',
                'winner': auction.current_bidder,
                'final_price': auction.final_price,
                'transaction_signature': transaction_signature
            }

# --- Sell Intent Actions ---

    async def set_sell_intent(
        self,
        owner_wallet: str,
        nft_mint: str,
        asking_price: Decimal,
        signed_transaction: Optional[str] = None
    ) -> dict:
        """
        Step 1 (signed_transaction=None): Build instruction and return to frontend for signing
        Step 2 (signed_transaction provided): Confirm transaction and update database
        """
        logger.info(f"Owner {owner_wallet} is setting sell intent for {nft_mint} at {asking_price} SOL.")
        
        # --- 1. Fetch NFT and Validate ---
        try:
            nft = await sync_to_async(
                NFT.objects.select_related('collection').get,
                thread_sensitive=False
            )(mint_address=nft_mint)

            # CRITICAL SAFETY CHECK: Ownership verification (BLOCKS action)
            is_owner, ownership_error = self.safety_validator.verify_ownership(
                nft=nft,
                seller_wallet=owner_wallet
            )
            if not is_owner:
                raise PermissionError(ownership_error)

            if asking_price <= 0:
                raise ValueError("Asking price must be greater than 0 SOL.")
            
            is_valid, error_message = await self.bid_validation_service.validate_bid(nft, asking_price) 
            if not is_valid:
                logger.warning(
                    f"Asking price {asking_price} SOL for {nft_mint} is outside "
                    f"vitality-suggested range: {error_message}"
                )
                
        except NFT.DoesNotExist:
            raise ValueError("NFT not found.")

        # --- 2. Check Quest Eligibility (Does NOT block action) ---
        is_quest_eligible = await self.safety_validator.check_quest_eligibility(
            nft=nft,
            actor_wallet=owner_wallet,
            action_type='list'
        )
        logger.info(f"Quest eligibility for sell intent: {is_quest_eligible}")

        # --- STEP 1: Build instruction and return to frontend ---
        if signed_transaction is None:
            logger.info("Building set_sell_intent instruction for client signing...")

            asking_price_lamports = int(asking_price * 1_000_000_000)

            instruction_data = await self.solana_client.get_set_sell_intent_instruction(
                owner_wallet=owner_wallet,
                nft_mint_addr=nft_mint,
                asking_price_lamports=asking_price_lamports
            )

            return {
                'success': True,
                'instruction_data': instruction_data,
                'requires_signature': True,
                'action_type': 'set_sell_intent',
                'nft_mint': nft_mint,
                'asking_price': str(asking_price)
            }

        # --- STEP 2: Process signed transaction ---
        logger.info("Processing signed transaction from frontend...")
        logger.info(f"Passing is_quest_eligible={is_quest_eligible} to blockchain transaction")
        transaction_signature = signed_transaction

        # --- 4. Update Database ---
        @sync_to_async(thread_sensitive=False)
        def _update_nft_intent():
            nft_to_update = NFT.objects.get(pk=nft.pk) 
            nft_to_update.has_sell_intent = True
            nft_to_update.asking_price = asking_price
            nft_to_update.has_buy_price = False
            nft_to_update.buy_price = None
            nft_to_update.is_listed = True # General listing flag
            
            update_fields = [
                'has_sell_intent',
                'asking_price',
                'has_buy_price',
                'buy_price',
                'is_listed'
            ]
            nft_to_update.save(update_fields=update_fields)
            
        await _update_nft_intent()

        logger.info(f"Sell intent set for {nft_mint} at asking price {asking_price} SOL. TX: {transaction_signature}")

        return {
            'success': True,
            'nft_mint': nft_mint,
            'asking_price': asking_price,
            'transaction_signature': transaction_signature,
            'message': 'Sell intent set. Buyers can accept your asking price or make counter-offers.'
        }

    async def remove_sell_intent(
        self,
        owner_wallet: str,
        nft_mint: str
    ) -> dict:
        """
        Removes a NEGOTIABLE sell intent listing.
        """
        logger.info(f"Owner {owner_wallet} is removing sell intent for {nft_mint}.")

        # --- 1. Fetch NFT and Validate Ownership ---
        try:
            nft = await sync_to_async(NFT.objects.get, thread_sensitive=False)(mint_address=nft_mint)

            # CRITICAL SAFETY CHECK: Ownership verification (BLOCKS action)
            is_owner, ownership_error = self.safety_validator.verify_ownership(
                nft=nft,
                seller_wallet=owner_wallet
            )
            if not is_owner:
                raise PermissionError(ownership_error)

            if not nft.has_sell_intent:
                logger.warning(f"NFT {nft_mint} has no active sell intent. No action taken.")
                return {'success': True, 'message': 'Sell intent was already inactive.'}

        except NFT.DoesNotExist:
            raise ValueError("NFT not found.")

        # --- 2. On-Chain Interaction (Placeholder) ---
        logger.info(f"Simulating on-chain transaction to remove sell intent listing...")
        mock_signature = f"mock_remove_intent_tx_{uuid.uuid4()}"

        # --- 3. Update Database ---
        @sync_to_async(thread_sensitive=False)
        def _update_nft_intent_removal():
            nft_to_update = NFT.objects.get(pk=nft.pk) 
            nft_to_update.has_sell_intent = False
            nft_to_update.asking_price = None
            nft_to_update.is_listed = False
            update_fields=['has_sell_intent', 'asking_price', 'is_listed']

            # Invalidate/Cancel any active private bids on this NFT
            PrivateBid.objects.filter(
                nft=nft_to_update,
                status=PrivateBid.Status.ACTIVE
            ).update(status=PrivateBid.Status.CANCELLED)

            nft_to_update.save(update_fields=update_fields) 
            
        await _update_nft_intent_removal()

        logger.info(f"NFT {nft_mint} sell intent has been removed. TX: {mock_signature}")

        return {
            'success': True,
            'nft_mint': nft_mint,
            'message': 'Sell intent removed, and all open bids were cancelled.',
            'transaction_signature': mock_signature
        }

    async def owner_counter_bid(
        self,
        owner_wallet: str,
        bid_id: str,
        counter_amount: Decimal,
        signed_transaction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Owner counters a private bid by setting NFT asking price.
        Two-step pattern: builds instruction OR processes signed transaction.
        """
        # --- 1. Fetch Bid and Validate ---
        try:
            bid = await sync_to_async(
                PrivateBid.objects.select_related('nft').get,
                thread_sensitive=False
            )(bid_id=bid_id, status=PrivateBid.Status.ACTIVE)

            # CRITICAL SAFETY CHECK: Ownership verification (BLOCKS action)
            is_owner, ownership_error = self.safety_validator.verify_ownership(
                nft=bid.nft,
                seller_wallet=owner_wallet
            )
            if not is_owner:
                raise PermissionError(ownership_error)

            if counter_amount <= 0:
                raise ValueError("Counter amount must be positive")

            nft_to_update = bid.nft # Use for fetching in sync block

        except PrivateBid.DoesNotExist:
            raise ValueError("Active bid not found.")

        # --- STEP 1: Build instruction if no signature provided ---
        if signed_transaction is None:
            logger.info(f"Building counter_bid instruction for bid {bid_id}...")

            counter_amount_lamports = int(counter_amount * 1_000_000_000)

            instruction_data = await self.solana_client.get_counter_bid_instruction(
                seller_wallet=owner_wallet,
                bidder_wallet=bid.bidder_wallet,
                nft_mint_addr=nft_to_update.mint_address,
                counter_amount_lamports=counter_amount_lamports
            )

            return {
                'success': True,
                'instruction_data': instruction_data,
                'requires_signature': True,
                'message': 'Please sign the transaction in your wallet to counter this bid.'
            }

        # --- STEP 2: Process signed transaction ---
        logger.info(f"Processing signed counter-bid transaction for bid {bid_id}...")
        transaction_signature = signed_transaction

        # --- 3. Update Database Atomically ---
        @sync_to_async(thread_sensitive=False)
        def _update_db_counter():
            with transaction.atomic():
                # Lock NFT and Bid
                nft_locked = NFT.objects.select_for_update().get(pk=nft_to_update.pk)
                bid_locked = PrivateBid.objects.select_for_update().get(pk=bid.pk)

                # a. Reject/Close the current bid
                bid_locked.status = PrivateBid.Status.REJECTED
                bid_locked.resolved_at = timezone.now()
                bid_locked.save(update_fields=['status', 'resolved_at'])

                # b. Update NFT with new asking price/intent
                nft_locked.asking_price = counter_amount
                nft_locked.has_sell_intent = True
                nft_locked.has_buy_price = False
                nft_locked.buy_price = None
                nft_locked.is_listed = True
                nft_locked.save(update_fields=[
                    'asking_price',
                    'has_sell_intent',
                    'has_buy_price',
                    'buy_price',
                    'is_listed'
                ])

        await _update_db_counter()

        return {
            'success': True,
            'nft_mint': nft_to_update.mint_address,
            'asking_price': str(counter_amount),
            'transaction_signature': transaction_signature,
            'message': f'Counter-offer set at {counter_amount} SOL. Previous bid {bid_id} rejected.'
        }

    async def bidder_counter_sell_intent(
        self,
        bidder_wallet: str,
        nft_mint: str,
        counter_amount: Decimal
    ) -> Dict[str, Any]:
        """
        Bidder counters owner's asking price by creating new private bid.
        """
        # --- 1. Fetch NFT and Validate ---
        nft = await sync_to_async(
            NFT.objects.select_related('collection').get,
            thread_sensitive=False
        )(mint_address=nft_mint)
        
        if not nft.has_sell_intent or not nft.asking_price:
            raise ValueError("This NFT is not listed with a negotiable asking price to counter.")
        
        if counter_amount <= 0:
            raise ValueError("Counter amount must be positive")
        
        logger.info(f"Bidder {bidder_wallet} is countering sell intent for {nft_mint} with {counter_amount} SOL.")
        
        # --- 2. Place New Bid ---
        # The place_private_bid function already handles all validation, spam checks,
        # transaction creation (placeholder), and database recording.
        bid_result = await self.place_private_bid(
            bidder_wallet=bidder_wallet,
            nft_mint=nft_mint,
            amount=counter_amount,
            expiry_hours=72 # Default expiry for new counter-bid
        )
        
        return {
            'success': True,
            'bid_id': bid_result['bid_id'],
            'amount': str(counter_amount),
            'transaction_signature': bid_result['transaction_signature'],
            'message': f'Counter-bid placed at {counter_amount} SOL'
        }

    async def accept_asking_price(
        self,
        buyer_wallet: str,
        nft_mint: str,
        signed_transaction: Optional[str] = None
    ) -> dict:
        """
        Step 1 (signed_transaction=None): Build instruction and return to frontend for signing
        Step 2 (signed_transaction provided): Confirm transaction and update database
        """
        logger.info(f"Buyer {buyer_wallet} is accepting asking price for NFT {nft_mint}.")
        
        original_owner = None
        sale_price = None
        
        # --- 1. Fetch NFT and Validate ---
        try:
            nft = await sync_to_async(
                NFT.objects.select_related('collection').get, 
                thread_sensitive=False
            )(mint_address=nft_mint)
            
            if not nft.has_sell_intent or not nft.asking_price:
                raise ValueError("This NFT does not have a sell intent with asking price set.")
            
            if nft.owner == buyer_wallet:
                raise ValueError("You cannot buy your own NFT.")
                
            sale_price = nft.asking_price
            original_owner = nft.owner 
            
        except NFT.DoesNotExist:
            raise ValueError("NFT not found.")

        # --- 2. Check Quest Eligibility (Does NOT block action) ---
        is_quest_eligible = await self.safety_validator.check_quest_eligibility(
            nft=nft,
            actor_wallet=original_owner,
            action_type='sale'
        ) and await self.safety_validator.check_quest_eligibility(
             nft=nft,
             actor_wallet=buyer_wallet,
             action_type='buy'
        )
        logger.info(f"Quest eligibility for accepting asking price: {is_quest_eligible}")

        # --- STEP 1: Build instruction and return to frontend ---
        if signed_transaction is None:
            logger.info("Building accept_asking_price instruction for client signing...")

            instruction_data = await self.solana_client.get_accept_asking_price_instruction(
                buyer_wallet=buyer_wallet,
                seller_wallet=original_owner,
                nft_mint_addr=nft_mint
            )

            return {
                'success': True,
                'instruction_data': instruction_data,
                'requires_signature': True,
                'action_type': 'accept_asking_price',
                'nft_mint': nft_mint,
                'asking_price': str(sale_price)
            }

        # --- STEP 2: Process signed transaction ---
        logger.info("Processing signed transaction from frontend...")
        logger.info(f"Passing is_quest_eligible={is_quest_eligible} to blockchain transaction")
        transaction_signature = signed_transaction
        
        # --- 4. Update Database ---
        @sync_to_async(thread_sensitive=False)
        def _execute_sale():
            with transaction.atomic():
                nft_to_update = NFT.objects.select_for_update().get(pk=nft.pk)

                # Create NFTEvent
                nft_event = NFTEvent.objects.create(
                    event_id=transaction_signature,
                    collection_address=nft_to_update.collection.address,
                    nft_mint=nft_to_update.mint_address,
                    event_type='SALE',
                    marketplace='traitkeeper',
                    amount=sale_price,
                    buyer=buyer_wallet,
                    seller=original_owner,
                    timestamp=timezone.now()
                )

                # Create MarketplaceTransaction
                MarketplaceTransaction.objects.create(
                    transaction_id=transaction_signature,
                    nft_event=nft_event,
                    transaction_type=MarketplaceTransaction.TransactionType.DIRECT_SALE, 
                    was_encrypted=False,
                    nft_vitality_at_sale=getattr(nft_to_update, 'vitality_score', None) or 50.0,
                    suggested_price_at_sale=sale_price,
                    vs_vitality_suggested=Decimal('1.0'),
                    vs_collection_floor=Decimal('1.0')
                )
                
                # Update NFT ownership and clear sell intent
                nft_to_update.owner = buyer_wallet
                nft_to_update.has_sell_intent = False
                nft_to_update.asking_price = None
                nft_to_update.is_listed = False
                nft_to_update.save(update_fields=[
                    'owner',
                    'has_sell_intent',
                    'asking_price',
                    'is_listed'
                ])
        
        await _execute_sale()
        
        logger.info(f"Asking price accepted. NFT {nft_mint} transferred to {buyer_wallet} for {sale_price} SOL. TX: {transaction_signature}")

        return {
            'success': True,
            'nft_mint': nft_mint,
            'buyer': buyer_wallet,
            'sale_price': sale_price,
            'transaction_signature': transaction_signature
        }

    async def cancel_auction(
        self,
        owner_wallet: str,
        auction_id: str,
        signed_transaction: Optional[str] = None
    ) -> dict:
        """
        Owner cancels their auction (only allowed if no bids have been placed).
        Two-step pattern: builds instruction OR processes signed transaction.
        """
        logger.info(f"Owner {owner_wallet} is attempting to cancel auction {auction_id}.")

        # --- 1. Fetch Auction and Validate ---
        try:
            auction = await sync_to_async(
                AuctionEvent.objects.select_related('nft').get,
                thread_sensitive=False
            )(auction_id=auction_id)

            # CRITICAL SAFETY CHECK: Ownership verification (BLOCKS action)
            is_owner, ownership_error = self.safety_validator.verify_ownership(
                nft=auction.nft,
                seller_wallet=owner_wallet
            )
            if not is_owner:
                raise PermissionError(ownership_error)

            if auction.status != AuctionEvent.Status.ACTIVE:
                raise ValueError(f"Cannot cancel auction with status: {auction.status}")

            if auction.current_bid is not None:
                raise ValueError(
                    "Cannot cancel auction after bids have been placed. "
                    "You must wait for the auction to end."
                )

        except AuctionEvent.DoesNotExist:
            raise ValueError("Auction not found.")

        # --- STEP 1: Build instruction if no signature provided ---
        if signed_transaction is None:
            logger.info(f"Building cancel_auction instruction for auction {auction_id}...")

            instruction_data = await self.solana_client.get_cancel_auction_instruction(
                seller_wallet=owner_wallet,
                nft_mint_addr=auction.nft.mint_address
            )

            return {
                'success': True,
                'instruction_data': instruction_data,
                'requires_signature': True,
                'message': 'Please sign the transaction in your wallet to cancel auction.'
            }

        # --- STEP 2: Process signed transaction ---
        logger.info(f"Processing signed cancel_auction transaction...")
        transaction_signature = signed_transaction

        # --- 3. Update Database ---
        @sync_to_async(thread_sensitive=False)
        def _cancel_auction_db():
            # Lock the NFT and update the Auction status
            with transaction.atomic():
                nft_locked = NFT.objects.select_for_update().get(pk=auction.nft.pk)
                auction_locked = AuctionEvent.objects.select_for_update().get(pk=auction.pk)

                auction_locked.status = AuctionEvent.Status.CANCELLED
                auction_locked.save(update_fields=['status'])

                nft_locked.active_auction = None
                nft_locked.is_listed = False
                nft_locked.save(update_fields=['active_auction', 'is_listed'])

        await _cancel_auction_db()

        logger.info(f"Auction {auction_id} cancelled successfully. TX: {transaction_signature}")

        return {
            'success': True,
            'auction_id': auction_id,
            'status': 'cancelled',
            'transaction_signature': transaction_signature,
            'message': 'Auction cancelled successfully.'
        }


# admin
    def initialize_marketplace_config_sync(self, **kwargs) -> Dict[str, Any]:
            """
            Synchronous entry point for initializing the marketplace configuration.
            Calls the underlying async client.
            """
            # Note: kwargs must contain all fields required by initialize_config
            
            async def _run_tx():
                return await self.solana_client.send_admin_config_tx(
                    instruction_name="initialize_config",
                    admin_args=kwargs,
                    # Pass kwargs directly as arguments for simplicity, relying on dictionary unpacking logic 
                    # inside the client method to map the arguments correctly.
                    **kwargs 
                )

            try:
                signature = async_to_sync(_run_tx)()
                return {'success': True, 'signature': signature}
            except PermissionError as e:
                return {'success': False, 'error': f"Key Error: {e}"}
            except Exception as e:
                return {'success': False, 'error': f"Solana Error: {e}"}

    def update_marketplace_config_sync(self, instruction_type: str, **kwargs) -> Dict[str, Any]:
        """
        Synchronous entry point for updating marketplace configuration rules or wallets.
        """
        
        async def _run_tx():
            return await self.solana_client.send_admin_config_tx(
                instruction_name=instruction_type, # e.g., "update_config_rules"
                admin_args=kwargs,
                **kwargs
            )

        try:
            signature = async_to_sync(_run_tx)()
            return {'success': True, 'signature': signature}
        except PermissionError as e:
            return {'success': False, 'error': f"Key Error: {e}"}
        except Exception as e:
            return {'success': False, 'error': f"Solana Error: {e}"}