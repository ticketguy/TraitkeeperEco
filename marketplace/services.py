# marketplace/services.py

import logging
from decimal import Decimal
import uuid
from typing import Dict, Any, Optional

from django.utils import timezone
from datetime import timedelta

# Use the async version of the Solana client
from solana.rpc.async_api import AsyncClient
from asgiref.sync import sync_to_async
from django.db import transaction

# Import your models and other services
from nft_data.models import NFT, NFTCollection # Correct import for NFT models
from indexer.models import NFTEvent
# Correct import for marketplace models, including AuctionEvent
from .models import PrivateBid, MarketplaceTransaction, AuctionEvent
from .bid_validation_service import BidValidationService
from .safety_validation import SafetyValidationService
# from notifications.services import PrivacyNotificationService # To be integrated

logger = logging.getLogger(__name__)


class MarketplaceService:
    """
    Handles privacy-preserving marketplace operations.
    This service is now fully asynchronous.
    """
    def __init__(self):
        self.solana_client = AsyncClient("https://api.mainnet-beta.solana.com")
        self.bid_validation_service = BidValidationService()
        self.safety_validator = SafetyValidationService()
        # self.notification_service = PrivacyNotificationService()

# --- Private Bidding Actions (Unsolicited Offers) ---

    async def place_private_bid(
        self,
        bidder_wallet: str,
        nft_mint: str,
        amount: Decimal,
        expiry_hours: int = 72
    ) -> dict:
        """
        Places a private, encrypted bid on an NFT.

        This workflow validates the bid, interacts with the smart contract (placeholder),
        and records the bid in the database.
        """
        logger.info(f"Initiating private bid for NFT {nft_mint} from {bidder_wallet} for {amount} SOL.")

        # --- 1. Fetch NFT and Validate the Bid ---
        try:
            # Use sync_to_async + thread_sensitive for ORM call
            nft = await sync_to_async(
                NFT.objects.select_related('collection').get,
                thread_sensitive=False
            )(mint_address=nft_mint)

            # CRITICAL SAFETY CHECK: Bid spam prevention and ownership check (BLOCKS action)
            is_safe, safety_error = await self.safety_validator.validate_bid_placement_safety(
                bidder_wallet=bidder_wallet,
                nft=nft,
                bid_amount=amount
            )
            if not is_safe:
                raise ValueError(safety_error)

            # validate_bid is already async, no sync_to_async needed
            is_valid, error_message = await self.bid_validation_service.validate_bid(nft, amount)

            if not is_valid:
                raise ValueError(error_message)

        except NFT.DoesNotExist:
            logger.error(f"place_bid failed: NFT with mint address {nft_mint} not found.")
            raise ValueError("NFT not found.")
        
        # --- 2. On-Chain Interaction (Placeholder) ---
        logger.info("Simulating on-chain transaction to escrow funds...")
        mock_signature = f"mock_tx_{uuid.uuid4()}"
        mock_encrypted_state_account = f"mock_enc_acct_{uuid.uuid4()}"

        # --- 3. Update Database Records ---
        # Use sync_to_async + thread_sensitive for the transaction block
        @sync_to_async(thread_sensitive=False) 
        def _create_bid_in_transaction():
            with transaction.atomic():
                expires_at = timezone.now() + timedelta(hours=expiry_hours)
                
                # ORM create call inside the sync function
                bid = PrivateBid.objects.create(
                    bid_id=mock_signature,
                    nft=nft,
                    collection=nft.collection,
                    bidder=bidder_wallet,
                    owner_at_creation=nft.owner,
                    encrypted_state_account=mock_encrypted_state_account,
                    expires_at=expires_at,
                    status=PrivateBid.Status.ACTIVE
                )
                return bid
        
        bid = await _create_bid_in_transaction()

        # --- 4. Send Notification to Owner (Placeholder) ---
        logger.info(f"Notification sent to owner {nft.owner} for new private bid.")

        logger.info(f"Successfully placed and recorded private bid {bid.bid_id}.")
        return {
            'success': True,
            'bid_id': bid.bid_id,
            'transaction_signature': mock_signature
        }

# --- Owner Actions on Private Bids ---

    async def accept_private_bid(self, owner_wallet: str, bid_id: str) -> dict:
        """
        Owner accepts an encrypted bid, executing the sale.
        """
        logger.info(f"Owner {owner_wallet} is attempting to accept bid {bid_id}.")

        # --- 1. Fetch Bid and Validate ---
        try:
            # Use sync_to_async + thread_sensitive for ORM call
            bid = await sync_to_async(
                PrivateBid.objects.select_related('nft', 'collection').get,
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
                bid.status = PrivateBid.Status.EXPIRED
                # Use sync_to_async + thread_sensitive for ORM call
                await sync_to_async(bid.save, thread_sensitive=False)(update_fields=['status'])
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

        # --- 3. Decrypt Amount & Execute On-Chain Sale (Placeholder) ---
        mock_decrypted_amount = Decimal('1.30')
        logger.info(f"Simulating on-chain sale for {mock_decrypted_amount} SOL...")
        logger.info(f"Passing is_quest_eligible={is_quest_eligible} to blockchain transaction")
        mock_sale_signature = f"mock_sale_tx_{uuid.uuid4()}"

        # --- 3. Update All Database Records Atomically ---
        # Use sync_to_async + thread_sensitive for the transaction block
        @sync_to_async(thread_sensitive=False) 
        def _update_db_after_sale(bid_instance, sale_signature, sale_amount):
            with transaction.atomic():
                # ORM call inside sync function
                nft_to_update = NFT.objects.select_for_update().get(pk=bid_instance.nft.pk)

                # a. Update the PrivateBid status
                bid_instance.status = PrivateBid.Status.ACCEPTED
                bid_instance.resolved_at = timezone.now()
                bid_instance.save() # save() is okay inside the atomic block

                # b. Create the official NFTEvent for analytics
                nft_event = NFTEvent.objects.create( # create() is okay inside the atomic block
                    event_id=sale_signature,
                    collection_address=nft_to_update.collection.address, # Correct field
                    nft_mint=nft_to_update.mint_address,               # Correct field
                    event_type='SALE',
                    marketplace='traitkeeper',
                    amount=sale_amount,
                    buyer=bid_instance.bidder,
                    seller=owner_wallet,
                    timestamp=timezone.now()
                )

                # c. Create the detailed MarketplaceTransaction record
                MarketplaceTransaction.objects.create( # create() is okay inside the atomic block
                    transaction_id=sale_signature,
                    nft_event=nft_event,
                    transaction_type=MarketplaceTransaction.TransactionType.BID_ACCEPTED,
                    was_encrypted=True,
                    reveal_timestamp=timezone.now(),
                    nft_vitality_at_sale=getattr(nft_to_update, 'vitality_score', None) or 50.0, # Safer access
                    suggested_price_at_sale=Decimal('1.25'), # Placeholder
                    vs_vitality_suggested=Decimal('1.04'),   # Placeholder
                    vs_collection_floor=Decimal('1.36')      # Placeholder
                )

                # d. Update the NFT's ownership and clear listings
                nft_to_update.owner = bid_instance.bidder
                nft_to_update.has_buy_price = False
                nft_to_update.buy_price = None # Ensure price is cleared too
                nft_to_update.is_open_to_offers = False
                nft_to_update.has_sell_intent = False
                nft_to_update.asking_price = None
                nft_to_update.save(update_fields=[ # save() is okay inside the atomic block
                    'owner', 
                    'has_buy_price', 
                    'buy_price',
                    'is_open_to_offers',
                    'has_sell_intent',
                    'asking_price'
                ])

                # e. Invalidate other open bids on this NFT
                PrivateBid.objects.filter( # filter() and update() are okay inside the atomic block
                    nft=nft_to_update,
                    status=PrivateBid.Status.ACTIVE
                ).update(status=PrivateBid.Status.CANCELLED)

        await _update_db_after_sale(bid, mock_sale_signature, mock_decrypted_amount)

        # --- 4. Send Notifications (Placeholder) ---
        logger.info(f"Sale complete. Bid {bid.bid_id} accepted. NFT {bid.nft.mint_address} transferred to {bid.bidder}.")

        return {
            'success': True,
            'transaction_signature': mock_sale_signature,
            'sale_price': mock_decrypted_amount
        }

    async def reject_private_bid(self, owner_wallet: str, bid_id: str) -> dict:
        """
        Allows the NFT owner to reject an active bid.
        """
        logger.info(f"Owner {owner_wallet} is attempting to reject bid {bid_id}.")

            # --- 1. Fetch Bid and Validate ---
        try:
            # Add thread_sensitive=False HERE
            bid = await sync_to_async(
                PrivateBid.objects.select_related('nft').get, 
                thread_sensitive=False # <-- ADD THIS
            )(bid_id=bid_id)

            if bid.status != PrivateBid.Status.ACTIVE:
                raise ValueError("This bid is no longer active.")

            # --- ADD LOGGING HERE ---
            logger.info(f"Reject Bid - Ownership Check: DB Owner='{bid.nft.owner}', Provided Wallet='{owner_wallet}'")
            # --- END LOGGING ---

            if bid.nft.owner != owner_wallet: # This is the check failing
                raise PermissionError("Only the NFT owner can reject a bid.")

        except PrivateBid.DoesNotExist:
            raise ValueError("Bid not found.")

        # --- 2. On-Chain Interaction (Placeholder) ---
        logger.info(f"Simulating on-chain transaction to release escrow for bid {bid_id}...")
        mock_refund_signature = f"mock_refund_tx_{uuid.uuid4()}"

        # --- 3. Update Database Record ---
        # Use sync_to_async + thread_sensitive for ORM call
        @sync_to_async(thread_sensitive=False) 
        def _update_bid_status():
            bid.status = PrivateBid.Status.REJECTED
            bid.resolved_at = timezone.now()
            bid.save(update_fields=['status', 'resolved_at']) # Specify fields
        
        await _update_bid_status()
        
        # --- 4. Send Notification (Placeholder) ---
        logger.info(f"Bid {bid_id} has been rejected. Notifying bidder {bid.bidder}.")

        return {
            'success': True,
            'status': 'rejected',
            'transaction_signature': mock_refund_signature
        }

    async def cancel_private_bid(self, bidder_wallet: str, bid_id: str) -> dict:
        """
        Allows the bidder to cancel their own active bid.
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

        # --- 2. On-Chain Interaction (Placeholder) ---
        logger.info(f"Simulating on-chain transaction to release escrow for bid {bid_id}...")
        mock_refund_signature = f"mock_refund_tx_{uuid.uuid4()}"

        # --- 3. Update Database Record ---
        # Use sync_to_async + thread_sensitive for ORM call
        @sync_to_async(thread_sensitive=False) 
        def _update_bid_status():
            bid.status = PrivateBid.Status.CANCELLED
            bid.resolved_at = timezone.now()
            bid.save(update_fields=['status', 'resolved_at']) # Specify fields
        
        await _update_bid_status()

        logger.info(f"Bid {bid_id} has been successfully cancelled by the bidder.")

        return {
            'success': True,
            'status': 'cancelled',
            'transaction_signature': mock_refund_signature
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
                raise ValueError(f"Price validation failed: {error_message}")

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
        
        # --- 3. Update Database ---
        nft.has_buy_price = True   # Correct field
        nft.buy_price = price      # Correct field
        nft.has_sell_intent = False
        nft.asking_price = None
        
        update_fields = [
            'has_buy_price',       # Correct field
            'buy_price',           # Correct field
            'has_sell_intent',
            'asking_price'
        ]
        
        # Use sync_to_async + thread_sensitive for ORM call
        await sync_to_async(nft.save, thread_sensitive=False)(update_fields=update_fields)
        
        logger.info(f"NFT {nft_mint} is now listed for direct sell at {price} SOL.")
        
        return {
            'success': True,
            'nft_mint': nft_mint,
            # Returning 'buy_price' might be clearer, but keep 'direct_sell_price' if test script expects it
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

            if not nft.has_buy_price: # Correct field
                logger.warning(f"NFT {nft_mint} is not listed for direct sell. No action taken.")
                return {'success': True, 'message': 'Listing was already inactive.'}

        except NFT.DoesNotExist:
            raise ValueError("NFT not found.")

        # --- 2. On-Chain Interaction (Placeholder) ---
        logger.info(f"Simulating on-chain transaction to remove direct sell listing...")
        mock_signature = f"mock_remove_list_tx_{uuid.uuid4()}"

        # --- 3. Update Database ---
        nft.has_buy_price = False # Correct field
        nft.buy_price = None      # Correct field
        update_fields = ['has_buy_price', 'buy_price'] # Correct fields

        # Use sync_to_async + thread_sensitive for ORM call
        await sync_to_async(nft.save, thread_sensitive=False)(update_fields=update_fields) 

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
        
        original_owner = None # Define variable outside try block
        # --- 1. Fetch NFT and Validate ---
        try:
            # Use sync_to_async + thread_sensitive for ORM call
            nft = await sync_to_async(
                NFT.objects.select_related('collection').get, 
                thread_sensitive=False
            )(mint_address=nft_mint)
            
            if not nft.has_buy_price or not nft.buy_price: # Correct fields
                raise ValueError("This NFT is not listed for direct sale.")
            
            if nft.owner == buyer_wallet:
                raise ValueError("You cannot buy your own NFT.")
                
            sale_price = nft.buy_price # Correct field
            original_owner = nft.owner # Store original owner
            
        except NFT.DoesNotExist:
            raise ValueError("NFT not found.")

        # --- 2. Check Quest Eligibility (Does NOT block action) ---
        is_quest_eligible = await self.safety_validator.check_quest_eligibility(
            nft=nft,
            actor_wallet=original_owner,
            action_type='sale'
        )
        logger.info(f"Quest eligibility for direct buy: {is_quest_eligible}")

        # --- 3. On-Chain Interaction (Placeholder) ---
        logger.info(f"Simulating on-chain purchase for {sale_price} SOL...")
        logger.info(f"Passing is_quest_eligible={is_quest_eligible} to blockchain transaction")
        mock_sale_signature = f"mock_buy_tx_{uuid.uuid4()}"
        
        # --- 3. Update Database ---
        # Use sync_to_async + thread_sensitive for the transaction block
        @sync_to_async(thread_sensitive=False) 
        def _execute_sale_in_db(): 
            with transaction.atomic():
                # ORM call inside sync function
                nft_to_update = NFT.objects.select_for_update().get(pk=nft.pk)
                
                # Create NFTEvent
                nft_event = NFTEvent.objects.create( # create() is okay inside atomic block
                    event_id=mock_sale_signature,
                    collection_address=nft_to_update.collection.address, # Correct field
                    nft_mint=nft_to_update.mint_address,               # Correct field
                    event_type='SALE',
                    marketplace='traitkeeper',
                    amount=sale_price,
                    buyer=buyer_wallet,
                    seller=original_owner, # Use stored owner
                    timestamp=timezone.now()
                )
                
                # Create MarketplaceTransaction
                MarketplaceTransaction.objects.create( # create() is okay inside atomic block
                    transaction_id=mock_sale_signature,
                    nft_event=nft_event,
                    transaction_type=MarketplaceTransaction.TransactionType.DIRECT_SALE,
                    was_encrypted=False,
                    nft_vitality_at_sale=getattr(nft_to_update, 'vitality_score', None) or 50.0, # Safer access
                    suggested_price_at_sale=sale_price, # Placeholder
                    vs_vitality_suggested=Decimal('1.0'), # Placeholder
                    vs_collection_floor=Decimal('1.0') # Placeholder
                )
                
                # Update NFT ownership and clear listing
                nft_to_update.owner = buyer_wallet
                nft_to_update.has_buy_price = False # Correct field
                nft_to_update.buy_price = None      # Correct field
                nft_to_update.save(update_fields=[ # save() is okay inside atomic block
                    'owner', 
                    'has_buy_price',                # Correct field
                    'buy_price'                     # Correct field
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
            reserve_price: Optional[Decimal] = None # Still accept reserve_price for potential future use or logging
        ) -> dict:
            """
            Allows an owner to create a new private auction for their NFT.
            Updated to match AuctionEvent model fields.
            """
            logger.info(f"Owner {owner_wallet} is creating an auction for {nft_mint}.")

            # --- 1. Fetch NFT and Validate ---
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

                # Check correct fields for listing status
                if nft.has_buy_price or nft.has_sell_intent or nft.is_listed:
                    raise ValueError("Cannot start an auction for an NFT that is already listed or has a sell intent.")

                # Check for active auction safely using sync_to_async
                async def check_existing_auction(nft_instance):
                    try:
                        # Check if the related AuctionEvent exists via the foreign key's ID field
                        return nft_instance.active_auction_id is not None
                    except AttributeError:
                        # Fallback: Check the reverse relation if active_auction_id doesn't exist
                        try:
                            # Ensure this check is also async safe
                            exists = await sync_to_async(nft_instance.auctions.filter(status=AuctionEvent.Status.ACTIVE).exists, thread_sensitive=False)()
                            return exists
                        except AttributeError:
                            # If neither way works, assume no active auction tracking on NFT model
                            logger.warning(f"NFT model {nft_instance.pk} lacks expected auction relation fields.")
                            return False # Proceed cautiously

                # Explicitly run the check asynchronously
                has_existing_auction = await check_existing_auction(nft)

                if has_existing_auction:
                    raise ValueError("This NFT is already in an active auction.")

                if starting_price <= 0 or duration_hours <= 0:
                    raise ValueError("Starting price and duration must be positive numbers.")

            except NFT.DoesNotExist:
                raise ValueError("NFT not found.")

            # --- 2. Handle Reserve Price (Placeholder/Logging Only for now) ---
            # NOTE: AuctionEvent model doesn't store reserve price info currently.
            # This section is kept for potential future logic or logging.
            has_reserve = reserve_price is not None and reserve_price > 0
            mock_encrypted_reserve_ref = None # Not saved to DB model currently
            if has_reserve:
                logger.info(f"Reserve price provided ({reserve_price} SOL), but AuctionEvent model does not store it.")
                # TODO: If using Arcium/on-chain reserve, encryption logic would go here.
                # mock_encrypted_reserve_ref = f"mock_reserve_acct_{uuid.uuid4()}"

            # --- 3. Check Quest Eligibility (Does NOT block action) ---
            is_quest_eligible = await self.safety_validator.check_quest_eligibility(
                nft=nft,
                actor_wallet=owner_wallet,
                action_type='list'
            )
            logger.info(f"Quest eligibility for auction creation: {is_quest_eligible}")

            # --- 4. On-Chain Interaction (Placeholder) ---
            logger.info(f"Simulating on-chain transaction to create auction for {nft_mint}...")
            logger.info(f"Passing is_quest_eligible={is_quest_eligible} to blockchain transaction")
            mock_auction_creation_signature = f"mock_auction_tx_{uuid.uuid4()}"

            # --- 4. Update Database Record ---
            # Use sync_to_async + thread_sensitive for the transaction block
            @sync_to_async(thread_sensitive=False)
            def _create_auction_in_db():
                with transaction.atomic():
                    start_time = timezone.now()
                    end_time = start_time + timedelta(hours=duration_hours)

                    # ORM call inside sync function - uses fields from the provided AuctionEvent model
                    auction = AuctionEvent.objects.create(
                        auction_id=mock_auction_creation_signature,
                        nft=nft,
                        collection=nft.collection,
                        creator=owner_wallet,
                        start_time=start_time,
                        end_time=end_time,
                        starting_price=starting_price,
                        status=AuctionEvent.Status.ACTIVE,
                        # Removed fields not present in the model:
                        # privacy_mode, has_reserve_price, reserve_price_encrypted_ref
                    )

                    # Link the auction to the NFT using the defined ForeignKey field
                    nft.active_auction = auction
                    nft.save(update_fields=['active_auction']) # save() okay inside atomic block
                    return auction

            auction = await _create_auction_in_db()

            logger.info(f"Successfully created auction {auction.auction_id} for NFT {nft_mint}.")
            return {
                'success': True,
                'auction_id': auction.auction_id,
                'transaction_signature': mock_auction_creation_signature,
                'end_time': auction.end_time.isoformat()
            }

    async def place_auction_bid(self, bidder_wallet: str, auction_id: str, amount: Decimal) -> dict:
        """
        Places a private, encrypted bid on an active auction.
        """
        logger.info(f"Bidder {bidder_wallet} is placing a bid on auction {auction_id} for {amount} SOL.")

        auction = None # Define outside try block
        previous_high_bidder = None # Define outside try block

        # --- 1. Fetch Auction to get NFT for safety check ---
        auction_for_check = await sync_to_async(
            AuctionEvent.objects.select_related('nft').get,
            thread_sensitive=False
        )(auction_id=auction_id)

        # CRITICAL SAFETY CHECK: Bid spam prevention (BLOCKS action)
        is_safe, safety_error = await self.safety_validator.validate_bid_placement_safety(
            bidder_wallet=bidder_wallet,
            nft=auction_for_check.nft,
            bid_amount=amount
        )
        if not is_safe:
            raise ValueError(safety_error)

        # --- 2. Fetch Auction and Validate Bid ---
        # Use sync_to_async + thread_sensitive for the transaction block
        @sync_to_async(thread_sensitive=False)
        def _get_and_lock_auction():
            # Need to pass auction_id to this scope
            nonlocal auction, previous_high_bidder
            with transaction.atomic():
                # ORM call inside sync function
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
                
                # Capture previous bidder before updating
                prev_bidder = auction_obj.current_bidder 
                
                # Update auction state within the transaction
                auction_obj.current_bid = amount
                auction_obj.current_bidder = bidder_wallet
                # Check if bid_count attribute exists before incrementing
                if hasattr(auction_obj, 'bid_count'):
                    auction_obj.bid_count += 1
                auction_obj.save() # save() okay inside atomic block

                return auction_obj, prev_bidder # Return fetched object and previous bidder
        
        # Execute the sync function and get results
        auction, previous_high_bidder = await _get_and_lock_auction()

        # --- 2. On-Chain Interaction (Placeholder) ---
        logger.info(f"Simulating Arcium encryption for bid amount of {amount} SOL...")
        logger.info(f"Simulating on-chain transaction to place auction bid...")
        mock_bid_signature = f"mock_auction_bid_tx_{uuid.uuid4()}"

        # --- 3. Send Notifications (Placeholder) ---
        if previous_high_bidder and previous_high_bidder != bidder_wallet:
            logger.info(f"Notifying previous bidder {previous_high_bidder} that they have been outbid.")

        logger.info(f"Successfully placed bid on auction {auction_id} by {bidder_wallet}.")
        return {
            'success': True,
            'transaction_signature': mock_bid_signature,
            'is_highest_bid': True
        }

    async def finalize_auction(self, auction_id: str) -> dict:
        """
        Finalizes an auction after its end time has passed.
        """
        logger.info(f"Attempting to finalize auction {auction_id}.")

        auction = None # Define outside try block
        
        # --- 1. Fetch Auction and Validate ---
        # Use sync_to_async + thread_sensitive for the transaction block
        @sync_to_async(thread_sensitive=False) 
        def _get_and_lock_auction_for_finalize():
            nonlocal auction
            with transaction.atomic():
                # ORM call inside sync function
                auction_obj = AuctionEvent.objects.select_for_update().get(auction_id=auction_id)

                if auction_obj.status != AuctionEvent.Status.ACTIVE:
                    raise ValueError("Auction is not active.")
                if timezone.now() < auction_obj.end_time:
                    raise ValueError("Auction has not ended yet.")
                
                return auction_obj # Return the fetched object
        
        auction = await _get_and_lock_auction_for_finalize()
        
        # --- 2. Determine Outcome ---
        if auction.current_bidder is None:
            # --- SCENARIO A: NO BIDS ---
            logger.info(f"Auction {auction_id} ended with no bids. Canceling.")
            mock_close_signature = f"mock_close_tx_{uuid.uuid4()}"
            
            # Use sync_to_async + thread_sensitive for DB update
            @sync_to_async(thread_sensitive=False) 
            def _cancel_auction_in_db():
                # Need to fetch NFT again inside sync context if related object access is needed
                auction_to_cancel = AuctionEvent.objects.select_related('nft').get(auction_id=auction.auction_id)
                auction_to_cancel.status = AuctionEvent.Status.CANCELLED
                if auction_to_cancel.nft and hasattr(auction_to_cancel.nft, 'active_auction'):
                    auction_to_cancel.nft.active_auction = None
                    auction_to_cancel.nft.save(update_fields=['active_auction']) # save() okay inside atomic block
                auction_to_cancel.save() # save() okay inside atomic block

            await _cancel_auction_in_db()
            
            return {'success': True, 'status': 'cancelled', 'reason': 'No bids were placed.'}

        else:
            # --- SCENARIO B: THERE IS A WINNER ---
            logger.info(f"Auction {auction_id} ended. Winner: {auction.current_bidder} at {auction.current_bid} SOL.")
            logger.info("Simulating on-chain finalization of the auction...")
            mock_sale_signature = f"mock_auction_sale_tx_{uuid.uuid4()}"

            # Use sync_to_async + thread_sensitive for the transaction block
            @sync_to_async(thread_sensitive=False) 
            def _finalize_sale_in_db():
                with transaction.atomic():
                    # Fetch auction again within transaction for safety
                    auction_to_finalize = AuctionEvent.objects.select_related('nft', 'collection').get(auction_id=auction.auction_id)

                    # a. Update the AuctionEvent
                    auction_to_finalize.status = AuctionEvent.Status.COMPLETED
                    auction_to_finalize.winner = auction_to_finalize.current_bidder
                    auction_to_finalize.final_price = auction_to_finalize.current_bid
                    auction_to_finalize.save() # save() okay inside atomic block

                    # b. Create the NFTEvent for analytics
                    NFTEvent.objects.create( # create() okay inside atomic block
                        event_id=mock_sale_signature,
                        collection_address=auction_to_finalize.collection.address, # <-- CORRECT
                        nft_mint=auction_to_finalize.nft.mint_address,           # <-- CORRECT
                        event_type='SALE',
                        marketplace='traitkeeper',
                        amount=auction_to_finalize.final_price,
                        buyer=auction_to_finalize.winner,
                        seller=auction_to_finalize.creator,
                        timestamp=timezone.now()
                    )
                    
                    # c. Update the NFT's ownership and state
                    if auction_to_finalize.nft:
                        auction_to_finalize.nft.owner = auction_to_finalize.winner
                        if hasattr(auction_to_finalize.nft, 'active_auction'):
                             auction_to_finalize.nft.active_auction = None
                        auction_to_finalize.nft.save(update_fields=['owner', 'active_auction']) # save() okay inside atomic block
            
            await _finalize_sale_in_db()

            logger.info(f"Finalized auction {auction_id}. NFT transferred to {auction.winner}.")

            return {
                'success': True,
                'status': 'completed',
                'winner': auction.winner,
                'final_price': auction.final_price,
                'transaction_signature': mock_sale_signature
            }

# --- Sell Intent Actions ---

    async def set_sell_intent(
        self,
        owner_wallet: str,
        nft_mint: str,
        asking_price: Decimal
    ) -> dict:
        """
        Sets an ASKING PRICE with openness to negotiations.
        """
        logger.info(f"Owner {owner_wallet} is setting sell intent for {nft_mint} at {asking_price} SOL.")
        
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

            if asking_price <= 0:
                raise ValueError("Asking price must be greater than 0 SOL.")
            
            # validate_bid is async, no sync_to_async needed
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

        # --- 3. Update Database ---
        nft.has_sell_intent = True
        nft.asking_price = asking_price
        nft.has_buy_price = False  # Correct field
        nft.buy_price = None       # Correct field
        
        update_fields = [
            'has_sell_intent',
            'asking_price',
            'has_buy_price',       # Correct field
            'buy_price'            # Correct field
        ]
        
        # Use sync_to_async + thread_sensitive for ORM call
        await sync_to_async(nft.save, thread_sensitive=False)(update_fields=update_fields)
        
        logger.info(f"Sell intent set for {nft_mint} at asking price {asking_price} SOL.")
        
        return {
            'success': True,
            'nft_mint': nft_mint,
            'asking_price': asking_price,
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
            # Use sync_to_async + thread_sensitive for ORM call
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
        nft.has_sell_intent = False
        nft.asking_price = None
        update_fields=['has_sell_intent', 'asking_price']

        # Use sync_to_async + thread_sensitive for ORM call
        await sync_to_async(nft.save, thread_sensitive=False)(update_fields=update_fields) 

        logger.info(f"NFT {nft_mint} sell intent has been removed.")

        return {
            'success': True,
            'nft_mint': nft_mint,
            'message': 'Sell intent removed.',
            'transaction_signature': mock_signature
        }
        
    async def owner_counter_bid(
        self,
        owner_wallet: str,
        bid_id: str,
        counter_amount: Decimal
    ) -> Dict[str, Any]:
        """
        Owner counters a private bid by setting NFT asking price.
        """
        # Use sync_to_async + thread_sensitive for ORM call
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
        
        nft_to_update = bid.nft
        nft_to_update.asking_price = counter_amount
        nft_to_update.has_sell_intent = True
        nft_to_update.has_buy_price = False # Correct field
        nft_to_update.buy_price = None      # Correct field

        update_fields = [
            'asking_price', 
            'has_sell_intent', 
            'has_buy_price', # Correct field
            'buy_price'      # Correct field
        ]

        # Use sync_to_async + thread_sensitive for ORM call
        await sync_to_async(nft_to_update.save, thread_sensitive=False)(update_fields=update_fields)
        
        return {
            'success': True,
            'nft_mint': nft_to_update.mint_address,
            'asking_price': str(counter_amount),
            'message': f'Counter-offer set at {counter_amount} SOL'
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
        # Use sync_to_async + thread_sensitive for ORM call
        nft = await sync_to_async(
            NFT.objects.select_related('collection').get,
            thread_sensitive=False
        )(mint_address=nft_mint)
        
        if not nft.has_sell_intent or not nft.asking_price:
            raise ValueError("This NFT is not listed with a negotiable asking price to counter.")
        
        if counter_amount <= 0:
            raise ValueError("Counter amount must be positive")
        
        logger.info(f"Bidder {bidder_wallet} is countering sell intent for {nft_mint} with {counter_amount} SOL.")
        
        # place_private_bid already handles its own sync_to_async calls
        bid_result = await self.place_private_bid(
            bidder_wallet=bidder_wallet,
            nft_mint=nft_mint,
            amount=counter_amount,
            expiry_hours=72 
        )
        
        return {
            'success': True,
            'bid_id': bid_result['bid_id'],
            'amount': str(counter_amount),
            'message': f'Counter-bid placed at {counter_amount} SOL'
        }

    async def accept_asking_price(
        self,
        buyer_wallet: str,
        nft_mint: str
    ) -> dict:
        """
        Buyer accepts the owner's asking price immediately.
        """
        logger.info(f"Buyer {buyer_wallet} is accepting asking price for NFT {nft_mint}.")
        
        original_owner = None # Define outside try block
        # --- 1. Fetch NFT and Validate ---
        try:
            # Use sync_to_async + thread_sensitive for ORM call
            nft = await sync_to_async(
                NFT.objects.select_related('collection').get, 
                thread_sensitive=False
            )(mint_address=nft_mint)
            
            if not nft.has_sell_intent or not nft.asking_price:
                raise ValueError("This NFT does not have a sell intent with asking price set.")
            
            if nft.owner == buyer_wallet:
                raise ValueError("You cannot buy your own NFT.")
                
            sale_price = nft.asking_price
            original_owner = nft.owner # Store original owner
            
        except NFT.DoesNotExist:
            raise ValueError("NFT not found.")

        # --- 2. Check Quest Eligibility (Does NOT block action) ---
        is_quest_eligible = await self.safety_validator.check_quest_eligibility(
            nft=nft,
            actor_wallet=original_owner,
            action_type='sale'
        )
        logger.info(f"Quest eligibility for accepting asking price: {is_quest_eligible}")

        # --- 3. On-Chain Interaction (Placeholder) ---
        logger.info(f"Simulating on-chain purchase at asking price {sale_price} SOL...")
        logger.info(f"Passing is_quest_eligible={is_quest_eligible} to blockchain transaction")
        mock_sale_signature = f"mock_accept_asking_tx_{uuid.uuid4()}"
        
        # --- 3. Update Database ---
        # Use sync_to_async + thread_sensitive for the transaction block
        @sync_to_async(thread_sensitive=False) 
        def _execute_sale():
            with transaction.atomic():
                # ORM call inside sync function
                nft_to_update = NFT.objects.select_for_update().get(pk=nft.pk)
                
                # Create NFTEvent
                nft_event = NFTEvent.objects.create( # create() okay inside atomic block
                    event_id=mock_sale_signature,
                    collection_address=nft_to_update.collection.address, # Correct field
                    nft_mint=nft_to_update.mint_address,               # Correct field
                    event_type='SALE',
                    marketplace='traitkeeper',
                    amount=sale_price,
                    buyer=buyer_wallet,
                    seller=original_owner, # Use stored owner
                    timestamp=timezone.now()
                )
                
                # Create MarketplaceTransaction
                MarketplaceTransaction.objects.create( # create() okay inside atomic block
                    transaction_id=mock_sale_signature,
                    nft_event=nft_event,
                    transaction_type=MarketplaceTransaction.TransactionType.DIRECT_SALE, # Should be consistent?
                    was_encrypted=False,
                    nft_vitality_at_sale=getattr(nft_to_update, 'vitality_score', None) or 50.0, # Safer access
                    suggested_price_at_sale=sale_price,  # Placeholder
                    vs_vitality_suggested=Decimal('1.0'),  # Placeholder
                    vs_collection_floor=Decimal('1.0')  # Placeholder
                )
                
                # Update NFT ownership and clear sell intent
                nft_to_update.owner = buyer_wallet
                nft_to_update.has_sell_intent = False
                nft_to_update.asking_price = None
                nft_to_update.save(update_fields=[ # save() okay inside atomic block
                    'owner',
                    'has_sell_intent',
                    'asking_price'
                ])
        
        await _execute_sale()
        
        logger.info(f"Asking price accepted. NFT {nft_mint} transferred to {buyer_wallet} for {sale_price} SOL.")
        
        return {
            'success': True,
            'nft_mint': nft_mint,
            'buyer': buyer_wallet,
            'sale_price': sale_price,
            'transaction_signature': mock_sale_signature
        }

    async def cancel_auction(
        self,
        owner_wallet: str,
        auction_id: str
    ) -> dict:
        """
        Owner cancels their auction (only allowed if no bids have been placed).
        """
        logger.info(f"Owner {owner_wallet} is attempting to cancel auction {auction_id}.")
        
        # --- 1. Fetch Auction and Validate ---
        try:
            # Use sync_to_async + thread_sensitive for ORM call
            auction = await sync_to_async(
                AuctionEvent.objects.select_related('nft', 'collection').get,
                thread_sensitive=False
            )(auction_id=auction_id)

            # CRITICAL SAFETY CHECK: Ownership verification (BLOCKS action)
            is_owner, ownership_error = self.safety_validator.verify_ownership(
                nft=auction.nft,
                seller_wallet=owner_wallet
            )
            if not is_owner:
                raise PermissionError(ownership_error)

            if auction.creator != owner_wallet:
                raise PermissionError("Only the auction creator can cancel it.")
            
            if auction.status != AuctionEvent.Status.ACTIVE:
                raise ValueError(f"Cannot cancel auction with status: {auction.status}")
            
            if auction.current_bid is not None:
                raise ValueError(
                    "Cannot cancel auction after bids have been placed. "
                    "You must wait for the auction to end."
                )
                
        except AuctionEvent.DoesNotExist:
            raise ValueError("Auction not found.")
        
        # --- 2. On-Chain Interaction (Placeholder) ---
        logger.info(f"Simulating on-chain auction cancellation...")
        
        # --- 3. Update Database ---
        # Use sync_to_async + thread_sensitive for DB update
        @sync_to_async(thread_sensitive=False) 
        def _cancel_auction_db():
             # Need to fetch NFT again inside sync context if related object access is needed
            auction_to_cancel = AuctionEvent.objects.select_related('nft').get(auction_id=auction.auction_id)
            auction_to_cancel.status = AuctionEvent.Status.CANCELLED
            if auction_to_cancel.nft and hasattr(auction_to_cancel.nft, 'active_auction'):
                 auction_to_cancel.nft.active_auction = None
                 auction_to_cancel.nft.save(update_fields=['active_auction']) # save() okay inside atomic block? Yes.
            auction_to_cancel.save() # save() okay inside atomic block? Yes.

        await _cancel_auction_db()
        
        logger.info(f"Auction {auction_id} cancelled successfully.")
        
        return {
            'success': True,
            'auction_id': auction_id,
            'status': 'cancelled',
            'message': 'Auction cancelled successfully.'
        }