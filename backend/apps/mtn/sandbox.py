# apps/mtn/sandbox.py
"""
MTN MoMo Sandbox provisioning.

In the sandbox environment MTN lets you create an API User and API Key
programmatically. This is NOT permitted in production — those credentials
come from the merchant onboarding process.

Flow:
  1. You have a subscription key from the MTN developer portal.
  2. Generate a UUID — this becomes the API User ID.
  3. POST /v1_0/apiuser with the UUID in X-Reference-Id.
  4. POST /v1_0/apiuser/{uuid}/apikey to retrieve the API Key.
"""
import json
import logging
import urllib.request
import urllib.error
import uuid as uuid_lib

logger = logging.getLogger(__name__)

SANDBOX_BASE = 'https://sandbox.momodeveloper.mtn.com'


class SandboxProvisioningError(Exception):
    pass


def provision_sandbox_user(subscription_key, callback_host='localhost'):
    """
    Create an MTN sandbox API User and API Key.
    Returns {'api_user': '<uuid>', 'api_key': '<key>'}.
    Raises SandboxProvisioningError on any failure.
    """
    if not subscription_key:
        raise SandboxProvisioningError('Subscription key is required.')

    api_user = str(uuid_lib.uuid4())

    # ── Step 1: register the API User with MTN ────────────────
    url = f'{SANDBOX_BASE}/v1_0/apiuser'
    payload = json.dumps({'providerCallbackHost': callback_host}).encode()
    req = urllib.request.Request(url, data=payload, method='POST')
    req.add_header('X-Reference-Id', api_user)
    req.add_header('Ocp-Apim-Subscription-Key', subscription_key)
    req.add_header('Content-Type', 'application/json')

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status not in (200, 201):
                raise SandboxProvisioningError(
                    f'MTN rejected API user creation: HTTP {resp.status}'
                )
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        logger.warning('Sandbox API user creation failed: %s %s', e.code, body)
        raise SandboxProvisioningError(
            f'MTN rejected API user creation ({e.code}): {body}'
        )
    except SandboxProvisioningError:
        raise
    except Exception as e:
        raise SandboxProvisioningError(f'Network error: {e}')

    # ── Step 2: request the API Key for that user ─────────────
    url = f'{SANDBOX_BASE}/v1_0/apiuser/{api_user}/apikey'
    req = urllib.request.Request(url, method='POST')
    req.add_header('Ocp-Apim-Subscription-Key', subscription_key)

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode('utf-8'))
            api_key = body.get('apiKey', '')
            if not api_key:
                raise SandboxProvisioningError(
                    'MTN returned an empty API key. Check your subscription key.'
                )
            return {'api_user': api_user, 'api_key': api_key}
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        logger.warning('Sandbox API key request failed: %s %s', e.code, body)
        raise SandboxProvisioningError(
            f'MTN rejected the API key request ({e.code}): {body}'
        )
    except SandboxProvisioningError:
        raise
    except Exception as e:
        raise SandboxProvisioningError(f'Network error: {e}')