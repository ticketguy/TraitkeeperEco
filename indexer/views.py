from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import logging

from .services import NFTDataService
logger = logging.getLogger(__name__)



@csrf_exempt
@require_POST
def webhook_handler(request):
    """Handle incoming webhook events from Helius."""
    try:
        payload = json.loads(request.body.decode('utf-8'))
        logger.info(f"Received webhook payload: {payload}")

        service = NFTDataService()
        for event in payload:
            service.process_webhook_event(event)

        return HttpResponse(status=200)
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return HttpResponse(status=500)