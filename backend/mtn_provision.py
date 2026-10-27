#!/usr/bin/env python
"""
MTN MoMo sandbox API user provisioning — standalone.

Usage:
    python mtn_provision.py <subscription_key> [callback_host]

Example:
    python mtn_provision.py 1c3bfaa48e8543d8985263e5e9c87d3a webhook.site

What it does:
    1. Creates an API user on MTN's sandbox  (POST /v1_0/apiuser)
    2. Fetches the API key for that user     (POST /v1_0/apiuser/{uuid}/apikey)
    3. Prints both credentials

Exit code 0 on success, 1 on any failure.
"""
import json
import sys
import urllib.error
import urllib.request
import uuid


SANDBOX_BASE = 'https://sandbox.momodeveloper.mtn.com'


def _describe_key(key):
    """Print a safe summary of a key without leaking the whole value."""
    if not key:
        return '(empty)'
    if len(key) <= 12:
        return f'{key}  (len={len(key)})'
    return f'{key[:8]}...{key[-4:]}  (len={len(key)})'


def _http(method, url, headers=None, body=None, timeout=30):
    """
    Perform an HTTP request and return (status, body_text).
    Never raises for HTTP errors — the caller inspects the status.
    """
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='replace')
    except urllib.error.URLError as e:
        return 0, f'Network error: {e.reason}'
    except Exception as e:
        return 0, f'Unexpected error: {e!r}'


def provision(subscription_key, callback_host='example.com'):
    print('=' * 68)
    print('MTN MoMo sandbox — API user provisioning')
    print('=' * 68)
    print(f'Subscription key : {_describe_key(subscription_key)}')
    print(f'Callback host    : {callback_host}')
    print(f'Base URL         : {SANDBOX_BASE}')
    print()

    # ------------------------------------------------------------------
    # Step 1: create the API user
    # ------------------------------------------------------------------
    api_user = str(uuid.uuid4())
    print(f'[1/2] Creating API user')
    print(f'      X-Reference-Id : {api_user}')

    status, body = _http(
        method='POST',
        url=f'{SANDBOX_BASE}/v1_0/apiuser',
        headers={
            'X-Reference-Id':           api_user,
            'Ocp-Apim-Subscription-Key': subscription_key,
            'Content-Type':              'application/json',
        },
        body={'providerCallbackHost': callback_host},
    )

    print(f'      Response       : HTTP {status}')
    if body.strip():
        print(f'      Body           : {body.strip()}')

    if status not in (200, 201):
        print()
        print('FAILED at step 1 — MTN rejected API user creation.')
        _print_diagnosis(status, body)
        return None

    print('      ✓ API user created')

    # ------------------------------------------------------------------
    # Step 2: fetch the API key
    # ------------------------------------------------------------------
    print()
    print(f'[2/2] Fetching API key')

    status, body = _http(
        method='POST',
        url=f'{SANDBOX_BASE}/v1_0/apiuser/{api_user}/apikey',
        headers={
            'Ocp-Apim-Subscription-Key': subscription_key,
        },
    )

    print(f'      Response       : HTTP {status}')
    if body.strip():
        print(f'      Body           : {body.strip()}')

    if status not in (200, 201):
        print()
        print('FAILED at step 2 — MTN rejected the API key request.')
        _print_diagnosis(status, body)
        return None

    try:
        api_key = json.loads(body).get('apiKey', '')
    except json.JSONDecodeError:
        api_key = ''

    if not api_key:
        print()
        print('FAILED — MTN returned no apiKey in the response.')
        return None

    print('      ✓ API key retrieved')
    print()
    print('=' * 68)
    print('SUCCESS — save these into your MomoProviderConfig:')
    print('=' * 68)
    print(f'  merchant_id  (API user UUID) : {api_user}')
    print(f'  api_key      (API secret)    : {api_key}')
    print()
    return {'api_user': api_user, 'api_key': api_key}


def _print_diagnosis(status, body):
    """Map MTN's error codes to actionable next steps."""
    print()
    print('Diagnosis:')

    if status == 401:
        print('  MTN says the subscription key is invalid or belongs to')
        print('  an inactive/deprecated product.')
        print()
        print('  • Confirm you copied the PRIMARY key from the')
        print('    "Collections" row (not "Collection Widget").')
        print('  • Confirm the subscription shows State = Active.')
        print('  • If you clicked Regenerate, the old value is dead —')
        print('    copy the new one.')

    elif status == 404:
        print('  MTN says the endpoint does not exist for this product.')
        print('  You may be using a key for the wrong product.')

    elif status == 409:
        print('  MTN says this X-Reference-Id already exists.')
        print('  (Should never happen — we generate a fresh UUID each run.)')

    elif status == 429:
        print('  MTN is rate-limiting this subscription key.')
        print('  Wait a few minutes and retry.')

    elif status == 500:
        print('  MTN\'s backend returned an internal error.')
        print('  This is almost always one of:')
        print('    • No registered developer application on your')
        print('      MTN profile (register one at')
        print('      https://momodeveloper.mtn.com/developer).')
        print('    • An MTN-side sandbox outage (transient — retry in')
        print('      an hour, or check their community forum).')
        print()
        print('  Copy the activityId from the body above and include it')
        print('  in any support ticket — it is MTN\'s server-side trace.')

    elif status == 0:
        print('  Network-level failure — the request never reached MTN.')
        print('  Check your internet connection, VPN, or corporate proxy.')

    else:
        print(f'  Unhandled status {status}. Read the body above.')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    subscription_key = sys.argv[1].strip()
    callback_host = sys.argv[2].strip() if len(sys.argv) > 2 else 'example.com'

    result = provision(subscription_key, callback_host)
    sys.exit(0 if result else 1)


if __name__ == '__main__':
    main()