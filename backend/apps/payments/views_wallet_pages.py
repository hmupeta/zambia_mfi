# apps/payments/views_wallet_pages.py
from django.shortcuts import render


def wallets_list(request):
    return render(request, 'app/payments/wallets.html')


def wallet_detail(request, branch_id):
    return render(request, 'app/payments/wallet_detail.html', {
        'branch_id': str(branch_id),
    })