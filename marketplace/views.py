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
from .perception_service import perception_service
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


# ==========================================
# PARALLEL LINES PERCEPTION ENGINE WEBHOOK
# ==========================================

@api_view(['POST'])
@permission_classes([AllowAny])  # Authentication handled by service
def api_parallel_lines_webhook(request):
    """
    Webhook endpoint for receiving perception data from Parallel Lines.

    Parallel Lines is TraitKeeper's world perception engine - an LLM-based
    system that analyzes community sentiment, behavioral patterns, and
    perception across multiple platforms.

    Expected payload structure:
    {
        "entity_type": "collection" | "nft" | "trait",
        "entity_id": "address or ID",
        "perception_data": {
            "perception_index": 0.78,  # 0-1 score
            "timestamp": "2025-01-08T12:34:56Z",
            "submind": {
                "raw_score": 0.72,
                "hidden_sentiment": "positive",
                "manipulation_probability": 0.12,
                "behavioral_patterns": {...}
            },
            "intuone": {
                "emotional_resonance": 0.85,
                "language_tone": "enthusiastic",
                "community_awareness": 0.76
            },
            "perception_graph_id": "graph_123",
            "confidence": 0.95,
            "data_sources": ["twitter", "discord"],
            "sample_size": 5420
        },
        "perception_graph": {  # Optional
            "nodes": [...],
            "edges": [...]
        }
    }
    """
    # Use async_to_sync to call async perception service
    return async_to_sync(_process_parallel_lines_webhook_async)(request)


async def _process_parallel_lines_webhook_async(request):
    """
    Async handler for Parallel Lines webhook processing.
    """
    try:
        # Parse request
        payload = request.data if hasattr(request, 'data') else json.loads(request.body)
        headers = dict(request.headers)

        # Process webhook via perception service
        success, message, snapshot = await perception_service.process_webhook(
            payload=payload,
            headers=headers,
            endpoint='/api/perception/webhook'
        )

        if success:
            return Response({
                'success': True,
                'message': message,
                'perception_index': snapshot.perception_index if snapshot else None,
                'entity_type': snapshot.entity_type if snapshot else None
            }, status=status.HTTP_200_OK)
        else:
            # Determine appropriate status code based on error message
            if 'authentication' in message.lower():
                status_code = status.HTTP_401_UNAUTHORIZED
            elif 'validation' in message.lower() or 'not found' in message.lower():
                status_code = status.HTTP_400_BAD_REQUEST
            else:
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

            return Response({
                'success': False,
                'error': message
            }, status=status_code)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in Parallel Lines webhook: {e}")
        return Response({
            'success': False,
            'error': 'Invalid JSON payload'
        }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.exception(f"Unexpected error in Parallel Lines webhook: {e}")
        return Response({
            'success': False,
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_get_marketplace_config(request):
    """
    Fetches the marketplace configuration from the blockchain.
    Returns fee percentages, rebate settings, and wallet addresses.
    Falls back to defaults if blockchain fetch fails.
    """
    try:
        from .solana_client import MarketplaceSolanaClient
        import asyncio

        async def fetch_config():
            try:
                logger.info("Fetching marketplace config from blockchain...")
                client = MarketplaceSolanaClient()
                state = await client.get_state()
                config_pda = state["config_pda"]
                program = state["program"]

                # Fetch config account
                config_account = await program.account["config"].fetch(config_pda)
                logger.info(f"✅ Config fetched: platform_fee_bps={config_account.platform_fee_bps}")

                return {
                    'platform_fee_bps': config_account.platform_fee_bps,
                    'platform_fee_percent': config_account.platform_fee_bps / 100,
                    'max_royalty_subsidy_bps': config_account.max_royalty_subsidy_bps,
                    'max_royalty_subsidy_percent': config_account.max_royalty_subsidy_bps / 100,
                    'min_vitality_for_rebate': config_account.min_vitality_for_rebate,
                    'rebate_counter_min': config_account.rebate_counter_min,
                    'auction_loser_rebate_lamports': config_account.auction_loser_rebate_lamports,
                    'rejection_counter_min': config_account.rejection_counter_min,
                    'rejection_rebate_lamports': config_account.rejection_rebate_lamports,
                    'from_blockchain': True
                }
            except Exception as inner_e:
                logger.warning(f"Blockchain config fetch failed: {inner_e}, using defaults")
                # Return default config if blockchain fetch fails
                return {
                    'platform_fee_bps': 250,  # 2.5%
                    'platform_fee_percent': 2.5,
                    'max_royalty_subsidy_bps': 0,
                    'max_royalty_subsidy_percent': 0,
                    'min_vitality_for_rebate': 70,
                    'rebate_counter_min': 3,
                    'auction_loser_rebate_lamports': 5000,
                    'rejection_counter_min': 5,
                    'rejection_rebate_lamports': 5000,
                    'from_blockchain': False
                }

        config = asyncio.run(fetch_config())

        return Response({
            'success': True,
            'data': config
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"❌ CRITICAL: Failed to fetch marketplace config: {e}")
        logger.exception(f"Error type: {type(e).__name__}")
        logger.exception(f"Error details: {str(e)}")

        # Return defaults even on total failure
        return Response({
            'success': True,
            'data': {
                'platform_fee_bps': 250,
                'platform_fee_percent': 2.5,
                'max_royalty_subsidy_bps': 0,
                'max_royalty_subsidy_percent': 0,
                'min_vitality_for_rebate': 70,
                'rebate_counter_min': 3,
                'auction_loser_rebate_lamports': 5000,
                'rejection_counter_min': 5,
                'rejection_rebate_lamports': 5000,
                'from_blockchain': False
            }
        }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_get_priority_fees(request):
    """
    Fetches real-time priority fees from Solana blockchain.
    Uses REAL blockchain data like Magic Eden.
    Returns low/medium/high priority fee options with estimated confirmation times.
    """
    try:
        from core.api_provider.api_providers import APIProviderManager
        import asyncio

        async def fetch_priority_fees():
            try:
                logger.info("Fetching REAL priority fees from Solana blockchain...")
                provider_manager = APIProviderManager()
                rpc_provider = await provider_manager.get_rpc_provider()

                if not rpc_provider:
                    raise Exception("No RPC provider available")

                # Get recent prioritization fees from blockchain
                fees_response = await rpc_provider.connection.get_recent_prioritization_fees()
                logger.info(f"Fetched {len(fees_response) if fees_response else 0} priority fee samples")

                # Calculate percentiles from REAL blockchain fees
                if fees_response and len(fees_response) > 0:
                    fees = [f['prioritizationFee'] for f in fees_response]
                    fees.sort()

                    # Calculate low (10th), medium (50th), high (90th) percentiles for better spread
                    low_fee = fees[len(fees) // 10] if len(fees) >= 10 else fees[0]
                    medium_fee = fees[len(fees) // 2]
                    high_fee = fees[len(fees) * 9 // 10] if len(fees) >= 10 else fees[-1]

                    logger.info(f"✅ Priority fees: Low={low_fee}, Medium={medium_fee}, High={high_fee} microLamports")
                else:
                    # Conservative defaults if no data
                    low_fee = 1000  # 0.000001 SOL
                    medium_fee = 10000  # 0.00001 SOL
                    high_fee = 100000  # 0.0001 SOL
                    logger.warning("No priority fee data, using conservative defaults")

                return {
                    'low': {
                        'microLamports': low_fee,
                        'sol': low_fee / 1_000_000,  # Correct: microLamports to SOL
                        'label': 'Low',
                        'time': '~60s'
                    },
                    'medium': {
                        'microLamports': medium_fee,
                        'sol': medium_fee / 1_000_000,  # Correct: microLamports to SOL
                        'label': 'Medium (Recommended)',
                        'time': '~30s'
                    },
                    'high': {
                        'microLamports': high_fee,
                        'sol': high_fee / 1_000_000,  # Correct: microLamports to SOL
                        'label': 'High',
                        'time': '~10s'
                    },
                    'from_blockchain': True
                }
            except Exception as e:
                logger.warning(f"Blockchain priority fee fetch failed: {e}, using defaults")
                # Return realistic defaults based on current Solana network
                return {
                    'low': {
                        'microLamports': 1000,
                        'sol': 0.000001,
                        'label': 'Low',
                        'time': '~60s'
                    },
                    'medium': {
                        'microLamports': 10000,
                        'sol': 0.00001,
                        'label': 'Medium (Recommended)',
                        'time': '~30s'
                    },
                    'high': {
                        'microLamports': 100000,
                        'sol': 0.0001,
                        'label': 'High',
                        'time': '~10s'
                    },
                    'from_blockchain': False
                }

        priority_fees = asyncio.run(fetch_priority_fees())

        return Response({
            'success': True,
            'data': priority_fees
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"❌ CRITICAL: Failed to fetch priority fees: {e}")
        # Return defaults even on total failure
        return Response({
            'success': True,
            'data': {
                'low': {
                    'microLamports': 1000,
                    'sol': 0.000001,
                    'label': 'Low',
                    'time': '~60s'
                },
                'medium': {
                    'microLamports': 10000,
                    'sol': 0.00001,
                    'label': 'Medium (Recommended)',
                    'time': '~30s'
                },
                'high': {
                    'microLamports': 100000,
                    'sol': 0.0001,
                    'label': 'High',
                    'time': '~10s'
                },
                'from_blockchain': False
            }
        }, status=status.HTTP_200_OK)