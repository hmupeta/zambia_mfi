# Mobile Money Provider Setup

Each provider requires a commercial agreement before API access.
Below is the signup process, required credentials, and webhook URL format.

---

## Sandbox Signup Order

1. **Broadpay (Lenco)** — self-service signup, instant sandbox access
2. **Kazang** — fastest to approve, redirect flow
3. **Zynle Pay** — modest KYC, good for cards + mobile
4. **Airtel Money** — 2-3 weeks for merchant agreement
5. **Zamtel Money** — 3-4 weeks, dedicated sales contact
6. **IZwe** — POS-only in some regions
7. **MTN MoMo** — skip; covered by Kazang & Broadpay

---

## Broadpay (Lenco)

- **Website:** https://lenco.co
- **Signup:** https://lenco.co/signup (self-service)
- **Flow:** Webhook-based
- **Required:** Bearer API token
- **Webhook signature:** X-Lenco-Signature HMAC SHA256

### Config fields

| Field | Value |
|---|---|
| Provider code | BROADPAY |
| API key | your Lenco access token |
| Webhook secret | Lenco webhook secret |
| Is active | yes |
| Is sandbox | yes |

---

## Kazang

- **Website:** https://kazang.com
- **Contact:** merchant@kazang.com
- **Flow:** Redirect (client browser goes to Kazang, comes back)
- **Required:** api_key, callback_url (their base URL)
- **Webhook:** None — uses success_url/cancel_url redirect

### Config fields

| Field | Value |
|---|---|
| Provider code | KAZANG |
| API key | from Kazang merchant portal |
| Callback URL | their API base URL |
| Is active | yes |
| Is sandbox | yes |

---

## Zynle Pay

- **Website:** https://zynlepay.com
- **Contact:** support@zynlepay.com
- **Flow:** Webhook-based
- **Required:** API ID + Private Key

### Config fields

| Field | Value |
|---|---|
| Provider code | ZYNLE |
| API key | API ID |
| API secret | Private Key |
| Webhook secret | from Zynle dashboard |
| Is active | yes |
| Is sandbox | yes |

---

## Airtel Money

- **Developer portal:** https://developers.airtel.africa
- **Flow:** OAuth2 + Webhook
- **Region:** Zambia (ZM)
- **Currency:** ZMW

### Config fields

| Field | Value |
|---|---|
| Provider code | AIRTEL_MONEY |
| API key | client_id |
| API secret | client_secret |
| Webhook secret | set after webhook agreement |
| Is active | yes |
| Is sandbox | yes |

---

## Zamtel Money

- **Website:** https://www.zamtel.zm/mobile-money
- **Contact:** business@zamtel.zm
- **Flow:** Bearer token + Webhook
- **Required:** API key, merchant ID, base URL

### Config fields

| Field | Value |
|---|---|
| Provider code | ZAMTEL |
| API key | Bearer token |
| Merchant ID | merchant short code |
| Callback URL | their API base URL |
| Webhook secret | set after webhook agreement |
| Is active | yes |
| Is sandbox | yes |

---

## IZwe

- **Website:** https://izwe.com
- **Contact:** support@izwe.com
- **Flow:** POS-terminal based (API access varies)

### Config fields

| Field | Value |
|---|---|
| Provider code | IZWE |
| API key | API key |
| Merchant ID | merchant code |
| Callback URL | their API base URL |
| Is active | yes |
| Is sandbox | yes |

---

## Webhook URLs

Hand these to each provider. Replace your-domain.zm with your real domain.

| Provider | Webhook URL |
|---|---|
| Kazang | https://your-domain.zm/api/momo/webhook/collection/KAZANG/ |
| Broadpay | https://your-domain.zm/api/momo/webhook/collection/BROADPAY/ |
| Zynle | https://your-domain.zm/api/momo/webhook/collection/ZYNLE/ |
| Airtel | https://your-domain.zm/api/momo/webhook/collection/AIRTEL_MONEY/ |
| Zamtel | https://your-domain.zm/api/momo/webhook/collection/ZAMTEL/ |
| IZwe | https://your-domain.zm/api/momo/webhook/collection/IZWE/ |

Disbursement webhooks (if provider supports async payouts):

    https://your-domain.zm/api/momo/webhook/disbursement/PROVIDER_CODE/

---

## Testing Credentials

Once credentials are entered in the admin, run:

    python manage.py test_provider --all

This makes a live sandbox call for each provider and reports pass/fail.

---

## Common Issues

| Error | Fix |
|---|---|
| No active config | Enable provider in admin (Is Active) |
| Unknown provider code | Install provider app or check provider_code |
| 401 Unauthorized | Wrong API key |
| Webhook signature mismatch | Check webhook_secret matches provider dashboard |
| Callback URL not reachable | Provider needs a public HTTPS URL — deploy first |
| Redirect URL blank | Kazang must return a URL — check raw_response |

---

## Admin Access

Provider configurations live at:

    http://your-domain.zm/admin/momo/momoproviderconfig/

Each config form shows:
- Field hints specific to that provider
- The exact webhook URL to hand to the provider

---

## Going Live Checklist

- [ ] Provider agreement signed (commercial terms)
- [ ] Sandbox credentials received
- [ ] Credentials entered in Django admin
- [ ] python manage.py test_provider --all passes
- [ ] Public HTTPS URL available (Phase AG deployment)
- [ ] Webhook URL handed to provider
- [ ] Callback IP allowlist configured (if required)
- [ ] Production credentials obtained
- [ ] is_sandbox switched to False in admin
- [ ] Client portal Pay Now tested end-to-end
- [ ] Staff monitoring page (/app/momo/) tested
- [ ] Reconciliation of first 10 live payments vs provider statement
