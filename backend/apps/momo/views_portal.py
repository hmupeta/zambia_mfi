# apps/momo/views_portal.py
"""Client-facing MoMo payment endpoints (JSON, session or JWT authenticated)."""
import json
import logging
import base64
import uuid
import requests
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import AllowAny

from apps.portal.auth import get_current_client
from apps.clients.models import Client
from apps.loans.models import Loan
from apps.momo.models import MomoProviderConfig, PaymentIntent
from apps.momo.services import CollectionService
from apps.payments.models import Payment

logger = logging.getLogger(__name__)

# ── Universal Auth Helper (Handles Web Session + Flutter JWT) ──
def _get_authenticated_client(request):
    client = get_current_client(request)
    if client:
        return client
        
    if hasattr(request, 'auth') and request.auth:
        client_id = None
        if hasattr(request.auth, 'payload'):
            client_id = request.auth.payload.get('client_id')
        elif isinstance(request.auth, dict):
            client_id = request.auth.get('client_id')
            
        if client_id:
            try:
                return Client.objects.get(id=client_id)
            except Client.DoesNotExist:
                pass
    return None


# ═══════════════════════════════════════════════════════════
# EXISTING ENDPOINTS (Legacy / Generic)
# ═══════════════════════════════════════════════════════════

@api_view(['GET'])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([AllowAny])
def list_providers(request):
    client = _get_authenticated_client(request)
    if not client:
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)

    configs = MomoProviderConfig.objects.filter(
        organization=client.organization, 
        is_active=True,
        transaction_type='COLLECTION' # <--- Filter by COLLECTION
    ).values('id', 'provider_code', 'display_name')

    return Response({'providers': list(configs)})


@api_view(['POST'])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([AllowAny])
def create_payment(request):
    client = _get_authenticated_client(request)
    if not client:
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)

    loan_id = request.data.get('loan_id')
    amount_raw = request.data.get('amount')
    provider_code = (request.data.get('provider_code') or '').upper()
    phone = (request.data.get('phone') or client.phone or '').strip()

    if not loan_id or not amount_raw or not provider_code:
        return Response({'error': 'loan_id, amount, and provider_code are required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        loan = Loan.objects.get(id=loan_id, client=client, is_fully_repaid=False)
    except Loan.DoesNotExist:
        return Response({'error': 'Loan not found or already paid off.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return Response({'error': 'Invalid amount.'}, status=status.HTTP_400_BAD_REQUEST)

    if amount > float(loan.balance_due):
        return Response({'error': f'Amount exceeds outstanding balance of K {loan.balance_due:.2f}.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        intent = CollectionService.initiate(
            org=client.organization,
            client=client,
            amount=amount,
            phone=phone,
            provider_code=provider_code,
            loan=loan,
            branch=loan.branch, 
            description=f'Loan repayment {loan.loan_number}',
            user=None,
        )
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(f'Payment intent failed: {e}')
        return Response({'error': f'Payment failed: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'ok': True,
        'reference': intent.reference,
        'status': intent.status,
        'amount': float(intent.amount),
        'redirect_url': getattr(intent, 'redirect_url', '') or '',
        'provider_txn_id': intent.provider_txn_id,
        'branch': intent.branch.code if getattr(intent, 'branch', None) else None,
    })


@api_view(['GET'])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([AllowAny])
def intent_status(request, reference):
    client = _get_authenticated_client(request)
    if not client:
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)

    intent = PaymentIntent.objects.filter(reference=reference, client=client).first()
    if not intent:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    # If the intent is already recorded, return SUCCESSFUL immediately
    if intent.payment_id:
        return Response({
            'reference': intent.reference,
            'status': 'CONFIRMED',
            'amount': float(intent.amount),
            'confirmed_at': intent.confirmed_at.isoformat() if intent.confirmed_at else None,
        })

    # Otherwise, check with MTN
    config = MomoProviderConfig.objects.filter(
        organization=client.organization, 
        provider_code='MTN_MOMO', 
        is_active=True,
        transaction_type='COLLECTION' # <--- Filter by COLLECTION
    ).first()

    if config and intent.provider_txn_id:
        try:
            token, sub_key = _get_mtn_token(config)
            base_url = 'https://sandbox.momodeveloper.mtn.com' if config.is_sandbox else 'https://momodeveloper.mtn.com'
            url = f'{base_url}/collection/v1_0/requesttopay/{intent.provider_txn_id}'
            
            headers = {
                'Authorization': f'Bearer {token}',
                'X-Target-Environment': 'sandbox' if config.is_sandbox else 'mtnzambia',
                'Ocp-Apim-Subscription-Key': sub_key
            }
            
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                mtn_status = data.get('status', '')
                
                if mtn_status == 'SUCCESSFUL':
                    # Mark as confirmed and record payment
                    intent.status = 'CONFIRMED'
                    intent.confirmed_at = timezone.now()
                    intent.save()
                    
                    User = get_user_model()
                    branch = intent.loan.branch if intent.loan else intent.branch
                    if not branch and intent.client:
                        branch = intent.client.branch
                        
                    system_user, _ = User.objects.get_or_create(
                        username=f'system@{intent.organization.code}',
                        defaults={'role': 'HQ_ADMIN', 'organization': intent.organization, 'branch': branch, 'is_active': True}
                    )
                    
                    # Record the payment
                    CollectionService._record_payment(intent, system_user)
                    
                    return Response({
                        'reference': intent.reference,
                        'status': 'CONFIRMED',
                        'amount': float(intent.amount),
                        'confirmed_at': intent.confirmed_at.isoformat(),
                    })
                elif mtn_status == 'FAILED':
                    intent.status = 'FAILED'
                    intent.error = data.get('reason', 'Payment failed')
                    intent.save()
                    return Response({
                        'reference': intent.reference,
                        'status': 'FAILED',
                        'error': intent.error,
                    })
        except Exception as e:
            logger.error(f"Error checking MTN status in intent_status: {e}")

    # If still pending, return PENDING
    return Response({
        'reference': intent.reference,
        'status': intent.status,
        'amount': float(intent.amount),
        'confirmed_at': intent.confirmed_at.isoformat() if intent.confirmed_at else None,
        'error': intent.error,
        'payment_id': str(intent.payment_id) if intent.payment_id else None,
    })


# ═══════════════════════════════════════════════════════════
# MTN MOBILE MONEY REQUEST TO PAY
# ═══════════════════════════════════════════════════════════

def _get_mtn_token(config):
    subscription_key = (config.plain_credential('subscription_key') or '').strip()
    api_user = (config.merchant_id or '').strip()
    api_key = (config.plain_credential('api_key') or '').strip()

    if not subscription_key or not api_user or not api_key:
        raise Exception('Missing MTN credentials in config. Please update the provider settings.')

    base_url = 'https://sandbox.momodeveloper.mtn.com' if config.is_sandbox else 'https://momodeveloper.mtn.com'
    # Since this view handles Collections, always use the collection token endpoint
    url = f'{base_url}/collection/token/'
    
    auth_str = f"{api_user}:{api_key}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        'Authorization': f'Basic {b64_auth}',
        'Ocp-Apim-Subscription-Key': subscription_key
    }
    
    res = requests.post(url, headers=headers)
    if res.status_code != 200:
        raise Exception(f"MTN Token Error: {res.text}")
    
    return res.json().get('access_token'), subscription_key


@api_view(['POST'])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([AllowAny])
def mtn_request_to_pay(request):
    client = _get_authenticated_client(request)
    if not client:
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)

    loan_id = request.data.get('loan_id')
    amount = request.data.get('amount')
    phone = request.data.get('phone')

    if not loan_id or not amount or not phone:
        return Response({'error': 'loan_id, amount, and phone are required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        loan = Loan.objects.get(id=loan_id, client=client, is_fully_repaid=False)
    except Loan.DoesNotExist:
        return Response({'error': 'Loan not found or already paid off.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        # CollectionService saves the PaymentIntent and calls MTN via mtn_provider
        intent = CollectionService.initiate(
            org=client.organization,
            client=client,
            amount=float(amount),
            phone=phone,
            provider_code='MTN_MOMO',
            loan=loan,
            branch=loan.branch,
            description=f'Loan repayment {loan.loan_number}',
            user=None,
        )
    except Exception as e:
        logger.error(f"MTN request to pay failed: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Return the internal reference so the Flutter app can poll using it
    return Response({
        'ok': True, 
        'reference_id': intent.reference, 
        'message': 'Payment prompt sent to your phone. Please enter your PIN.'
    })


@api_view(['GET'])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([AllowAny])
def mtn_check_status(request, reference_id):
    client = _get_authenticated_client(request)
    if not client:
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)

    config = MomoProviderConfig.objects.filter(
        organization=client.organization, 
        provider_code='MTN_MOMO', 
        is_active=True,
        transaction_type='COLLECTION' # <--- Filter by COLLECTION
    ).first()

    if not config:
        return Response({'error': 'MTN config missing.'}, status=status.HTTP_400_BAD_REQUEST)

    # Find the intent using the internal reference the Flutter app sent
    intent = PaymentIntent.objects.filter(reference=reference_id).first()
    if not intent:
        return Response({'error': 'Payment intent not found.'}, status=status.HTTP_404_NOT_FOUND)

    # If the intent is already recorded, return SUCCESSFUL immediately
    if intent.payment_id:
        return Response({
            'status': 'SUCCESSFUL',
            'reason': 'Payment already recorded.',
        })

    try:
        token, sub_key = _get_mtn_token(config)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Use the provider_txn_id (MTN UUID) to check status with MTN
    base_url = 'https://sandbox.momodeveloper.mtn.com' if config.is_sandbox else 'https://momodeveloper.mtn.com'
    url = f'{base_url}/collection/v1_0/requesttopay/{intent.provider_txn_id}'

    headers = {
        'Authorization': f'Bearer {token}',
        'X-Target-Environment': 'sandbox' if config.is_sandbox else 'mtnzambia',
        'Ocp-Apim-Subscription-Key': sub_key
    }

    res = requests.get(url, headers=headers)
    
    if res.status_code != 200:
        return Response({'error': 'Could not fetch status from MTN.'}, status=status.HTTP_400_BAD_REQUEST)

    data = res.json()
    mtn_status = data.get('status', '')
    reason = data.get('reason', '')

    # ── IF SUCCESSFUL, RECORD THE PAYMENT IN THE SYSTEM ──
    if mtn_status == 'SUCCESSFUL':
        if not intent.payment_id:
            try:
                intent.status = 'CONFIRMED'
                intent.confirmed_at = timezone.now()
                intent.save()

                User = get_user_model()
                branch = intent.loan.branch if intent.loan else intent.branch
                
                if not branch and intent.client:
                    branch = intent.client.branch

                system_user, _ = User.objects.get_or_create(
                    username=f'system@{intent.organization.code}',
                    defaults={
                        'role': 'HQ_ADMIN',
                        'organization': intent.organization,
                        'branch': branch,
                        'is_active': True
                    }
                )
                
                if not system_user.branch:
                    system_user.branch = branch
                    system_user.save()

                # Record payment (creates Payment, posts GL, updates wallet)
                payment = CollectionService._record_payment(intent, system_user)
                
                if payment:
                    logger.info(f"MTN payment recorded successfully for reference {reference_id} -> Payment ID {payment.id}")
                else:
                    logger.error(f"Failed to record MTN payment for {reference_id}: _record_payment returned None")
                    return Response({'error': 'Payment succeeded on MTN but failed to save locally. Check server logs.'}, status=500)
                
            except Exception as e:
                logger.error(f"❌ ERROR RECORDING MTN PAYMENT: {str(e)}", exc_info=True)
                return Response({'error': f'Error recording payment: {str(e)}'}, status=500)

    return Response({
        'status': mtn_status,
        'reason': reason,
    })