"""
Cross-app shared constants.
"""

# ============================================================
# Payment Methods / Channels
# Shared across loans, payments, expenses, and wallets so that
# drf-spectacular sees ONE enum instead of many variants.
# ============================================================
PAYMENT_METHOD_CHOICES = [
    ('CASH', 'Cash'),
    ('MTN_MOMO', 'MTN Mobile Money'),
    ('AIRTEL_MONEY', 'Airtel Money'),
    ('BANK', 'Bank'),
]