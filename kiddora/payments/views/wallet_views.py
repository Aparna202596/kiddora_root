# payments/views/wallet_views.py
from __future__ import annotations

from decimal import Decimal
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from accounts.decorators import user_login_required
from payments.models import Payment, Order
from payments.views.wallet_helpers import debit_from_wallet
from shopcore.models import Order

@never_cache
@user_login_required
@require_POST
def pay_with_wallet(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    
    if order.payment_status == "PAID":
        messages.info(request, "Order already paid.")
        return redirect("shopcore:order_success", order_id=order.order_id)

    success, msg, txn = debit_from_wallet(
        user=request.user,
        amount=order.final_amount,
        description=f"Order payment {order.order_id}",
        reference_type="ORDER",
        reference_id=str(order.order_id),
        order=order,
    )

    if not success:
        messages.error(request, msg)
        return redirect("payments:wallet_payment_failure", order_id=order.order_id)

    Payment.objects.create(
        order=order,
        payment_method="WALLET",
        payment_status="PAID",
        amount=order.final_amount,
        initiated_at=timezone.now(),
        completed_at=timezone.now(),
    )

    order.payment_status = "PAID"
    order.payment_method = "WALLET"
    order.save(update_fields=["payment_status", "payment_method"])

    request.session.pop("applied_coupon_code", None)
    request.session.pop("applied_coupon_discount", None)

    messages.success(request, f"Paid ₹{order.final_amount} from wallet. Order confirmed.")
    return redirect("shopcore:order_success", order_id=order.order_id)


@never_cache
@user_login_required
def wallet_payment_failure(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    balance = getattr(request.user.wallet, 'balance', Decimal('0'))
    return render(request, "payments/wallet_failure.html", {
        "order": order,
        "wallet_balance": balance,
    })