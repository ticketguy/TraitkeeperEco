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

    CRITICAL: This endpoint ALWAYS returns 200 OK to prevent stream termination.
    Errors are logged but don't stop the stream.

    This endpoint receives HTTP POST requests when blockchain events occur.
    Both Helius and QuickNode streams can use this same endpoint.

    Expected payload formats:
    - Helius: Array of enhanced transaction objects
    - QuickNode: Single or array of transaction objects

    Returns:
        Always 200 OK (prevents stream termination)
        Stats indicate success/failure of individual events
    """
    stats = {
        'total_events': 0,
        'processed': 0,
        'failed': 0,
        'skipped': 0
    }

    try:
        # Parse JSON payload
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in webhook payload: {e}")
            # Still return 200 to prevent stream termination
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON',
                'stats': stats
            }, status=200)  # Changed from 400 to 200

        # Log webhook received (but don't log entire payload - too large)
        signature = 'batch' if isinstance(payload, list) else payload.get('signature', 'unknown')
        logger.info(f"📨 Webhook received: {signature}")

        # Process webhook asynchronously
        webhook_service = WebhookService()
        stats = asyncio.run(webhook_service.process_webhook_payload(payload))

        # Always return success with stats
        return JsonResponse({
            'status': 'success',
            'stats': stats
        }, status=200)

    except Exception as e:
        # Log error but STILL return 200 to prevent stream termination
        logger.error(f"Critical error in webhook handler: {str(e)}", exc_info=True)
        stats['failed'] = 1
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'stats': stats
        }, status=200)  # Changed from 500 to 200