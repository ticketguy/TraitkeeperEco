from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import logging
import asyncio

from .services.webhook_service import WebhookService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def webhook_handler(request):
    """
    Handle incoming webhook events from Helius or QuickNode.

    This endpoint receives HTTP POST requests when blockchain events occur.
    Both Helius and QuickNode streams can use this same endpoint.

    Expected payload formats:
    - Helius: Array of enhanced transaction objects
    - QuickNode: Single or array of transaction objects

    Returns:
        200 OK with processing stats (Helius/QuickNode expect 200 response)
        500 on error
    """
    try:
        # Parse JSON payload
        payload = json.loads(request.body.decode('utf-8'))

        # Log webhook received (but don't log entire payload - too large)
        signature = 'batch' if isinstance(payload, list) else payload.get('signature', 'unknown')
        logger.info(f"📨 Webhook received: {signature}")

        # Process webhook asynchronously
        webhook_service = WebhookService()
        stats = asyncio.run(webhook_service.process_webhook_payload(payload))

        # Return success with stats
        return JsonResponse({
            'status': 'success',
            'stats': stats
        }, status=200)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook payload: {e}")
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON'
        }, status=400)

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': 'Internal server error'
        }, status=500)