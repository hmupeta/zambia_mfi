import requests
import base64
import os
import sys
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.momo.models import MomoProviderConfig

def check_disbursement_status(reference_id):
    # 1. Fetch the MTN DISBURSEMENT configuration
    config = MomoProviderConfig.objects.filter(
        provider_code='MTN_MOMO', 
        transaction_type='DISBURSEMENT',
        is_active=True
    ).first()
    
    if not config:
        print("Error: No active MTN DISBURSEMENT configuration found.")
        return

    # 2. Decrypt the credentials
    try:
        subscription_key = (config.plain_credential('subscription_key') or '').strip()
        api_user = (config.merchant_id or '').strip()
        api_key = (config.plain_credential('api_key') or '').strip()
    except Exception as e:
        print(f"Error decrypting credentials: {e}")
        return

    # 3. Get an Access Token (Note: Disbursement endpoint)
    base_url = 'https://sandbox.momodeveloper.mtn.com' if config.is_sandbox else 'https://momodeveloper.mtn.com'
    token_url = f'{base_url}/disbursement/token/'
    
    auth_str = f"{api_user}:{api_key}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        'Authorization': f'Basic {b64_auth}',
        'Ocp-Apim-Subscription-Key': subscription_key
    }
    
    print("Fetching access token for DISBURSEMENT...")
    token_res = requests.post(token_url, headers=headers)
    if token_res.status_code != 200:
        print(f"Failed to get token: {token_res.text}")
        return
    
    access_token = token_res.json().get('access_token')
    print(f"Token acquired.")

    # 4. Call the Disbursement Status endpoint
    status_url = f'{base_url}/disbursement/v1_0/transfer/{reference_id}'
    
    status_headers = {
        'Authorization': f'Bearer {access_token}',
        'X-Target-Environment': 'sandbox' if config.is_sandbox else 'mtnzambia',
        'Ocp-Apim-Subscription-Key': subscription_key
    }
    
    print(f"Checking status for reference_id: {reference_id}...")
    res = requests.get(status_url, headers=status_headers)
    
    print(f"\n--- Status Response ---")
    print(f"HTTP Status Code: {res.status_code}")
    print(f"Response Body: {res.text}")
    # --------------------------

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python check_mtn_trans.py <reference_id>")
    else:
        # Get the ID from the command line argument
        ref_id = sys.argv[1]
        check_disbursement_status(ref_id)