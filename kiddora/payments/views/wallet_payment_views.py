
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.utils.timezone import now
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from accounts.decorators import admin_login_required, user_login_required
from shopcore.models import *
from django.db import transaction
from ..models import *

@user_login_required
@transaction.atomic
def wallet_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    wallet = request.user.wallet

    if wallet.balance <= 0:
        messages.error(request, "Insufficient wallet balance.")
        return redirect("cart:checkout")

    payable = min(wallet.balance, order.final_amount)

    wallet.balance -= payable
    wallet.save(update_fields=["balance"])

    WalletTransaction.objects.create(
        wallet=wallet,
        txn_type="DEBIT",
        amount=payable,
        reference_type="ORDER",
        reference_id=str(order.id)
    )

    Payment.objects.create(
        order=order,
        payment_method="WALLET",
        payment_status="PAID",
        paid_at=now(),
        retry_allowed=False
    )

    order.payment_status = "PAID"
    order.save(update_fields=["payment_status"])

    messages.success(request, "Payment completed using wallet.")
    return redirect("payments:payment_success", order.id)