# indexer/integration_hooks.py
"""
Integration hooks for indexer to trigger notifications and achievements
when blockchain events are parsed and stored.

These hooks are called AFTER the indexer successfully parses a Solana transaction
and creates an NFTEvent in the database.
"""

import logging
from typing import Optional
from django.contrib.auth import get_user_model
from asgiref.sync import sync_to_async

from notifications.utils import (
    create_listing_notification,
    create_sale_notification,
    create_bid_notification,
    create_bid_accepted_notification,
    create_outbid_notification,
    create_watchlist_listing_notification,
)
from profiles.utils import (
    check_and_award_trading_achievements,
    check_and_award_collection_achievements,
)
from profiles.models import WatchlistItem
from wallet.models import WalletProfile
from .models import NFTEvent, BurnEvent

User = get_user_model()
logger = logging.getLogger(__name__)


async def create_collection_event_for_nft_event(nft_event: NFTEvent) -> None:
    """
    Create CollectionEvent (for NFT Memories) for significant blockchain events.

    This creates social/memorial records that users can interact with
    (likes, comments, tributes) separate from the core NFTEvent data.
    """
    from nftmemories.models import CollectionEvent

    try:
        # Check if CollectionEvent already exists for this NFTEvent
        existing = await sync_to_async(
            CollectionEvent.objects.filter(event=nft_event).exists
        )()

        if existing:
            logger.debug(f"CollectionEvent already exists for NFTEvent {nft_event.event_id}")
            return

        # Create CollectionEvent (significance auto-determined in model.save())
        collection_event = await sync_to_async(CollectionEvent.objects.create)(
            event=nft_event
        )

        logger.info(
            f"Created CollectionEvent for {nft_event.event_type} event {nft_event.event_id} "
            f"with significance {collection_event.significance}"
        )

    except Exception as e:
        logger.error(f"Failed to create CollectionEvent for NFTEvent {nft_event.event_id}: {e}")


async def create_nft_burn_record(burn_event: BurnEvent, nft_data: dict) -> None:
    """
    Create NFTBurn record (for NFT Memories) when an NFT is burned.

    Preserves historical data about the burned NFT including name, image,
    rarity snapshot, etc. for memorial/social purposes.

    Args:
        burn_event: The BurnEvent from indexer
        nft_data: Dictionary containing NFT metadata at time of burn:
            - name: NFT name
            - description: NFT description
            - image_url: Image URL
            - number: NFT number in collection
            - rarity: Rarity data dict
    """
    from nftmemories.models import NFTBurn

    try:
        # Check if NFTBurn already exists
        existing = await sync_to_async(
            NFTBurn.objects.filter(burn_event=burn_event).exists
        )()

        if existing:
            logger.debug(f"NFTBurn already exists for BurnEvent {burn_event.burn_id}")
            return

        # Create NFTBurn memorial record
        nft_burn = await sync_to_async(NFTBurn.objects.create)(
            burn_event=burn_event,
            name=nft_data.get('name', ''),
            description=nft_data.get('description', ''),
            image_url=nft_data.get('image_url', ''),
            number=nft_data.get('number'),
            rarity=nft_data.get('rarity', {}),
        )

        logger.info(
            f"Created NFTBurn memorial for {nft_data.get('name', 'Unknown NFT')} "
            f"(burn_id: {burn_event.burn_id})"
        )

    except Exception as e:
        logger.error(f"Failed to create NFTBurn for BurnEvent {burn_event.burn_id}: {e}")


async def get_user_from_wallet(wallet_address: str) -> Optional[User]:
    """
    Get User instance from wallet address.
    Returns None if no user found for this wallet.
    """
    try:
        wallet = await sync_to_async(WalletProfile.objects.select_related('user').get)(
            public_key=wallet_address
        )
        return wallet.user
    except WalletProfile.DoesNotExist:
        return None


async def process_nft_event(nft_event: NFTEvent) -> None:
    """
    Main entry point called by indexer after successfully parsing and storing an NFT event.
    Routes to appropriate handler based on event type.

    Args:
        nft_event: The NFTEvent instance that was just created/updated
    """
    event_type = nft_event.event_type

    logger.info(f"[INTEGRATION] Processing event {nft_event.event_id} of type {event_type}")

    try:
        # Create CollectionEvent for NFT Memories (social/memorial system)
        await create_collection_event_for_nft_event(nft_event)

        # Route to appropriate handler for notifications and achievements
        if event_type == 'LIST':
            await handle_listing_event(nft_event)
        elif event_type == 'SALE':
            await handle_sale_event(nft_event)
        elif event_type == 'BID':
            await handle_bid_event(nft_event)
        elif event_type == 'DELIST':
            # Delisting doesn't trigger notifications currently
            pass
        else:
            logger.debug(f"[INTEGRATION] No handler for event type: {event_type}")

    except Exception as e:
        logger.error(
            f"[INTEGRATION] Error processing event {nft_event.event_id}: {e}",
            exc_info=True
        )


async def handle_listing_event(nft_event: NFTEvent) -> None:
    """
    Handle LIST events - create notifications and check achievements.
    """
    seller_wallet = nft_event.seller
    if not seller_wallet:
        logger.warning(f"[INTEGRATION] LIST event {nft_event.event_id} has no seller")
        return

    # Get seller user
    seller_user = await get_user_from_wallet(seller_wallet)
    if not seller_user:
        logger.debug(f"[INTEGRATION] No user found for seller wallet {seller_wallet}")
        return

    # Get NFT
    from nft_data.models import NFT
    nft = await sync_to_async(NFT.objects.select_related('collection').filter(
        mint_address=nft_event.mint_address
    ).first)()

    if not nft:
        logger.warning(f"[INTEGRATION] NFT not found for mint {nft_event.mint_address}")
        return

    # Create mock listing object for notification (your marketplace models may differ)
    mock_listing = type('MockListing', (), {
        'price': nft_event.price,
        'seller': seller_wallet,
        'listing_id': nft_event.event_id,
        'listing_type': nft_event.source_listing or 'DIRECT_SELL',
        'listed_at': nft_event.timestamp,
    })()

    # Send notification to seller
    await sync_to_async(create_listing_notification)(seller_user, nft, mock_listing)
    logger.info(f"[INTEGRATION] Created listing notification for user {seller_user.username}")

    # Check and award trading achievements
    awarded = await sync_to_async(check_and_award_trading_achievements)(seller_user)
    if awarded:
        logger.info(f"[INTEGRATION] Awarded achievements to {seller_user.username}: {awarded}")

    # Notify watchers
    await notify_watchers_of_listing(nft, mock_listing, seller_user)


async def handle_sale_event(nft_event: NFTEvent) -> None:
    """
    Handle SALE events - create notifications and check achievements.
    """
    seller_wallet = nft_event.seller
    buyer_wallet = nft_event.buyer
    sale_price = nft_event.price

    if not seller_wallet or not buyer_wallet:
        logger.warning(f"[INTEGRATION] SALE event {nft_event.event_id} missing seller or buyer")
        return

    # Get users
    seller_user = await get_user_from_wallet(seller_wallet)
    buyer_user = await get_user_from_wallet(buyer_wallet)

    # Get NFT
    from nft_data.models import NFT
    nft = await sync_to_async(NFT.objects.select_related('collection').filter(
        mint_address=nft_event.mint_address
    ).first)()

    if not nft:
        logger.warning(f"[INTEGRATION] NFT not found for mint {nft_event.mint_address}")
        return

    # Create mock listing for notification
    mock_listing = type('MockListing', (), {
        'price': sale_price,
        'seller': seller_wallet,
        'listing_id': nft_event.event_id,
    })()

    # Send notifications to both parties (if they have accounts)
    if seller_user or buyer_user:
        await sync_to_async(create_sale_notification)(
            seller_user, buyer_user, nft, mock_listing, sale_price
        )
        logger.info(f"[INTEGRATION] Created sale notifications")

    # Award achievements to buyer
    if buyer_user:
        trading_achievements = await sync_to_async(check_and_award_trading_achievements)(buyer_user)
        collection_achievements = await sync_to_async(check_and_award_collection_achievements)(buyer_user)

        awarded = trading_achievements + collection_achievements
        if awarded:
            logger.info(f"[INTEGRATION] Awarded achievements to buyer {buyer_user.username}: {awarded}")


async def handle_bid_event(nft_event: NFTEvent) -> None:
    """
    Handle BID events - create notifications and check achievements.
    """
    bidder_wallet = nft_event.buyer  # In bid events, buyer is the bidder

    if not bidder_wallet:
        logger.warning(f"[INTEGRATION] BID event {nft_event.event_id} has no bidder")
        return

    # Get NFT
    from nft_data.models import NFT
    nft = await sync_to_async(NFT.objects.select_related('collection').filter(
        mint_address=nft_event.mint_address
    ).first)()

    if not nft:
        logger.warning(f"[INTEGRATION] NFT not found for mint {nft_event.mint_address}")
        return

    # Get NFT owner
    if not nft.owner:
        logger.debug(f"[INTEGRATION] NFT {nft.mint_address} has no owner")
        return

    owner_user = await get_user_from_wallet(nft.owner)
    if owner_user:
        # Create mock bid object
        mock_bid = type('MockBid', (), {
            'amount': nft_event.price,
            'bidder': bidder_wallet,
            'bid_id': nft_event.event_id,
            'bid_placed_at': nft_event.timestamp,
        })()

        # Notify owner
        await sync_to_async(create_bid_notification)(owner_user, mock_bid, nft)
        logger.info(f"[INTEGRATION] Created bid notification for owner {owner_user.username}")

    # Check achievements for bidder
    bidder_user = await get_user_from_wallet(bidder_wallet)
    if bidder_user:
        awarded = await sync_to_async(check_and_award_trading_achievements)(bidder_user)
        if awarded:
            logger.info(f"[INTEGRATION] Awarded achievements to bidder {bidder_user.username}: {awarded}")


async def notify_watchers_of_listing(nft, listing, seller_user: Optional[User]) -> None:
    """
    Notify users who are watching this NFT or its collection about the listing.
    """
    from notifications.utils import create_watchlist_listing_notification

    # Get NFT watchers
    nft_watchers = await sync_to_async(list)(
        WatchlistItem.objects.filter(
            item_type=WatchlistItem.ItemType.NFT,
            nft=nft
        ).select_related('user')
    )

    for watchlist_item in nft_watchers:
        # Don't notify seller about their own listing
        if seller_user and watchlist_item.user == seller_user:
            continue

        await sync_to_async(create_watchlist_listing_notification)(
            watchlist_item.user, watchlist_item, listing
        )
        logger.info(f"[INTEGRATION] Notified watcher {watchlist_item.user.username}")

    # Get collection watchers
    if nft.collection:
        collection_watchers = await sync_to_async(list)(
            WatchlistItem.objects.filter(
                item_type=WatchlistItem.ItemType.COLLECTION,
                collection=nft.collection
            ).select_related('user')
        )

        for watchlist_item in collection_watchers:
            if seller_user and watchlist_item.user == seller_user:
                continue

            await sync_to_async(create_watchlist_listing_notification)(
                watchlist_item.user, watchlist_item, listing
            )
            logger.info(f"[INTEGRATION] Notified collection watcher {watchlist_item.user.username}")


# ============================================================================
# INTEGRATION POINT FOR INDEXER
# ============================================================================

async def on_event_parsed(nft_event: NFTEvent) -> None:
    """
    Main integration hook to be called by indexer after parsing and storing event.

    Call this in indexer/services/parser.py after successfully creating NFTEvent:

    ```python
    # In parse_and_store_event method, after creating nft_event:
    nft_event, created = await sync_to_async(NFTEvent.objects.update_or_create)(...)

    if created:
        # Import the hook
        from indexer.integration_hooks import on_event_parsed

        # Call integration hook
        await on_event_parsed(nft_event)
    ```

    Args:
        nft_event: The NFTEvent that was just created
    """
    await process_nft_event(nft_event)
