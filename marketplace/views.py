# marketplace/views.py
import logging
import json
from decimal import Decimal
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
# Import DRF Response
from rest_framework.response import Response
# Import async utilities
from asgiref.sync import sync_to_async, async_to_sync
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView # For the class-based view

from .services import MarketplaceService
from nft_data.models import NFT 
from django.utils import timezone
from datetime import timedelta

# Import models used by service methods for context, even if not directly used here
from .models import PrivateBid, MarketplaceTransaction, AuctionEvent

logger = logging.getLogger(__name__)

# --- Create a single, shared instance of your service ---
marketplace_service = MarketplaceService()

# ==========================================
# ASYNC HELPER (For getting user wallet)
# ==========================================

@sync_to_async
def get_user_wallet(user):
    """
    Safely gets the public_key from a request's user object.
    This must be async-safe as it touches the database (lazy user/wallet_profile).
    """
    # Use standard Django user checks
    if not user or not user.is_authenticated:
         raise PermissionError("User is not authenticated.")
    # Check for the related wallet profile safely
    wallet_profile = getattr(user, 'wallet_profile', None)
    if not wallet_profile or not wallet_profile.public_key:
         raise PermissionError("User has no associated wallet profile or public key.")
    return wallet_profile.public_key

# ==========================================
# ASYNC WRAPPER FOR API LOGIC
# ==========================================

async def api_view_wrapper(request, service_method, data_extractor):
    """
    A generic ASYNC wrapper to handle boilerplate code in our API views.
    It gets the wallet, parses data, calls the async service, and handles errors.
    Returns a DRF Response.
    """
    try:
        # Use request.data with DRF @api_view
        data = request.data
        wallet_address = await get_user_wallet(request.user)

        # Call the provided function to get specific args from the data
        kwargs = data_extractor(data)

        # Call the actual async service method (e.g., marketplace_service.place_private_bid)
        result = await service_method(wallet_address, **kwargs)

        # Return DRF Response on success
        return Response({'success': True, 'data': result}, status=status.HTTP_200_OK)

    except (ValueError, PermissionError) as e:
        logger.warning(f"API validation error in {getattr(service_method, '__name__', 'N/A')}: {e}")
        # Return DRF Response on validation error
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except KeyError as e:
        logger.warning(f"API missing field error in {getattr(service_method, '__name__', 'N/A')}: Missing key {e}")
        # Return DRF Response on missing key
        return Response({'success': False, 'error': f'Missing required field: {e}'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"API server error in {getattr(service_method, '__name__', 'N/A')}: {e}", exc_info=True)
        # Return DRF Response on server error
        return Response({'success': False, 'error': 'An unexpected server error occurred.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==========================================
# PRODUCTION API VIEWS (Synchronous Wrappers)
# ==========================================

# --- Direct Sell ---
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_set_direct_sell(request): # Synchronous function
    # Call the async wrapper using async_to_sync
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.set_direct_sell,
        lambda data: {
            'nft_mint': data.get('mint'),
            'price': Decimal(data.get('price'))
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_remove_direct_sell(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.remove_direct_sell,
        lambda data: {
            'nft_mint': data.get('mint')
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_buy_direct_sell(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.execute_direct_buy,
        lambda data: {
            'nft_mint': data.get('mint')
        }
    )

# --- Sell Intent ---
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_set_sell_intent(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.set_sell_intent,
        lambda data: {
            'nft_mint': data.get('mint'),
            'asking_price': Decimal(data.get('asking_price')),
            'signed_transaction': data.get('signed_transaction')
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_remove_sell_intent(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.remove_sell_intent,
        lambda data: {
            'nft_mint': data.get('mint')
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_accept_asking_price(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.accept_asking_price,
        lambda data: {
            'nft_mint': data.get('mint'),
            'signed_transaction': data.get('signed_transaction')
        }
    )

# --- Private Bidding ---
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_place_bid(request): # Synchronous function
    return async_to_sync(api_view_wrapper)( # Use async_to_sync
        request,
        marketplace_service.place_private_bid,
        lambda data: {
            # FIX: Use 'mint' as the input key for consistency across all listing actions
            'nft_mint': data.get('mint'),
            'amount': Decimal(data.get('amount')),
            'expiry_hours': int(data.get('expiry_hours', 72)),
            'signed_transaction': data.get('signed_transaction')  # Optional: for step 2
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_confirm_bid(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.confirm_private_bid_tx, 
        lambda data: {
            'temp_bid_id': data.get('temp_bid_id'),
            'transaction_signature': data.get('transaction_signature'),
            'amount': Decimal(data.get('amount')) # Required for sanity check
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_accept_bid(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.accept_private_bid,
        lambda data: {
            'bid_id': data.get('bid_id'),
            'signed_transaction': data.get('signed_transaction')
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_reject_bid(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.reject_private_bid,
        lambda data: {
            'bid_id': data.get('bid_id'),
            'signed_transaction': data.get('signed_transaction')
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_cancel_bid(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.cancel_private_bid,
        lambda data: {
            'bid_id': data.get('bid_id'),
            'signed_transaction': data.get('signed_transaction')
        }
    )

# --- Private Auction ---
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_create_auction(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.create_private_auction,
        lambda data: {
            'nft_mint': data.get('nft_mint'),
            'starting_price': Decimal(data.get('starting_price')),
            'duration_hours': int(data.get('duration_hours')),
            'reserve_price': Decimal(data.get('reserve_price')) if data.get('reserve_price') else None,
            'signed_transaction': data.get('signed_transaction')
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_place_auction_bid(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.place_auction_bid,
        lambda data: {
            'auction_id': data.get('auction_id'),
            'amount': Decimal(data.get('amount')),
            'signed_transaction': data.get('signed_transaction')
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_cancel_auction(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.cancel_auction,
        lambda data: {
            'auction_id': data.get('auction_id'),
            'signed_transaction': data.get('signed_transaction')
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_finalize_auction(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.finalize_auction,
        lambda data: {
            'auction_id': data.get('auction_id'),
            'signed_transaction': data.get('signed_transaction')
        }
    )

# --- Counter Offers ---
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_owner_counter_bid(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.owner_counter_bid,
        lambda data: {
            'bid_id': data.get('bid_id'),
            'counter_amount': Decimal(data.get('counter_amount')),
            'signed_transaction': data.get('signed_transaction')
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_bidder_counter_sell_intent(request): # Synchronous function
    return async_to_sync(api_view_wrapper)(
        request,
        marketplace_service.bidder_counter_sell_intent,
        lambda data: {
            # FIX: Use 'mint' as the input key for consistency
            'nft_mint': data.get('mint'),
            'counter_amount': Decimal(data.get('counter_amount'))
        }
    )

# --- Get NFT Offers ---
@api_view(['GET'])
@permission_classes([AllowAny])
def api_get_nft_offers(request, nft_mint):
    """
    Fetch all bids/offers for a specific NFT.
    Returns list of bids with their status, amount, bidder, timestamps.
    """
    try:
        # Get all bids for this NFT
        bids = PrivateBid.objects.filter(nft__mint_address=nft_mint).order_by('-created_at')

        # Serialize bid data
        offers_data = []
        for bid in bids:
            offers_data.append({
                'bid_id': str(bid.bid_id),
                'amount': str(bid.amount),
                'bidder': bid.bidder_wallet,
                'status': bid.status,
                'created_at': bid.created_at.isoformat() if bid.created_at else None,
                'expires_at': bid.expires_at.isoformat() if bid.expires_at else None,
            })

        return JsonResponse({
            'success': True,
            'offers': offers_data
        })
    except Exception as e:
        logger.error(f"Error fetching NFT offers: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)