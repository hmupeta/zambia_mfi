"""
Webhook receivers for mobile money providers.
"""
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services import CollectionService, DisbursementService

logger = logging.getLogger(__name__)


def _extract_headers(request):
    return {k: v for k, v in request.headers.items()}


@csrf_exempt
@require_http_methods(['POST'])
def collection_webhook(request, provider_code):
    """
    POST /api/momo/webhook/collection/<provider_code>/

    Each provider posts their confirmation here. We verify, find the
    pending intent, and either confirm it (auto-record payment) or mark
    it failed.
    """
    provider_code = provider_code.upper()

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception as e:
        logger.warning(f'Bad webhook JSON for {provider_code}: {e}')
        return JsonResponse({'ok': False, 'error': 'bad json'}, status=400)

    try:
        intent = CollectionService.process_webhook(
            provider_code=provider_code,
            payload=payload,
            headers=_extract_headers(request),
            body_bytes=request.body,
        )
    except Exception as e:
        logger.exception(f'Webhook processing failed: {e}')
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)

    if not intent:
        return JsonResponse({'ok': False, 'error': 'no matching intent'}, status=404)

    return JsonResponse({
        'ok': True,
        'reference': intent.reference,
        'status': intent.status,
    })


@csrf_exempt
@require_http_methods(['POST'])
def disbursement_webhook(request, provider_code):
    """
    POST /api/momo/webhook/disbursement/<provider_code>/
    """
    provider_code = provider_code.upper()

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'bad json'}, status=400)

    try:
        intent = DisbursementService.process_webhook(
            provider_code=provider_code,
            payload=payload,
            headers=_extract_headers(request),
            body_bytes=request.body,
        )
    except Exception as e:
        logger.exception(f'Disbursement webhook failed: {e}')
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)

    if not intent:
        return JsonResponse({'ok': False, 'error': 'no matching intent'}, status=404)

    return JsonResponse({
        'ok': True,
        'reference': intent.reference,
        'status': intent.status,
    })
