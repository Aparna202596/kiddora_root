from __future__ import annotations

from decimal import Decimal

from accounts.decorators import admin_login_required, user_login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from payments.models import Payment, Wallet, WalletTransaction
from payments.views.paypal_views import _finalize_order_after_payment
from payments.views.wallet_helpers import (_restore_inventory_for_order,
                                           debit_from_wallet)
from shopcore.models import Order

#   ────────────────────────────────────────────────── INTERNAL HELPER ──────────────────────────────────────────────────


def _wallet_balance(user) -> Decimal:
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet.balance


#   ────────────────────────────────────────────────── USER: PAY WITH WALLET ──────────────────────────────────────────────────
@never_cache
@user_login_required
@require_POST
def pay_with_wallet(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.payment_status == "PAID":
        messages.info(request, "Order already paid.")
        return redirect("shopcore:order_success", order_id=order.order_id)

    balance = _wallet_balance(request.user)
    if balance < order.final_amount:
        messages.error(
            request,
            f"Insufficient wallet balance (₹{balance:.2f}). "
            "Please choose another payment method.",
        )

        order.order_status = "ORDER NOT PLACED"
        order.payment_status = "FAILED"
        order.save(update_fields=["order_status", "payment_status"])
        _restore_inventory_for_order(order)
        return redirect("payments:wallet_payment_failure", order_id=order.order_id)

    success, msg, txn = debit_from_wallet(
        user=request.user,
        amount=order.final_amount,
        description=f"Payment for order {order.order_id}",
        reference_type="ORDER",
        reference_id=str(order.order_id),
        order=order,
    )

    if not success:
        messages.error(request, msg)
        order.order_status = "ORDER NOT PLACED"
        order.payment_status = "FAILED"
        order.save(update_fields=["order_status", "payment_status"])
        _restore_inventory_for_order(order)
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
    order.save(update_fields=["payment_status"])

    _finalize_order_after_payment(request, order)

    messages.success(
        request, f"₹{order.final_amount} paid from wallet. Order confirmed!"
    )
    return redirect("shopcore:order_success", order_id=order.order_id)


#   ────────────────────────────────────────────────── USER: WALLET PAYMENT FAILURE ──────────────────────────────────────────────────
@never_cache
@user_login_required
def wallet_payment_failure(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    return render(
        request,
        "payments/wallet_failure.html",
        {
            "order": order,
            "wallet_balance": _wallet_balance(request.user),
        },
    )


#   ────────────────────────────────────────────────── ADMIN: WALLET TRANSACTIONS LIST ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_wallet_list(request):
    search = request.GET.get("search", "").strip()
    type_f = request.GET.get("type", "")
    ref_f = request.GET.get("ref", "")

    qs = WalletTransaction.objects.select_related("wallet__user", "order").order_by(
        "-created_at"
    )

    if search:
        qs = qs.filter(
            Q(wallet__user__email__icontains=search)
            | Q(wallet__user__full_name__icontains=search)
            | Q(reference_id__icontains=search)
            | Q(description__icontains=search)
        )
    if type_f:
        qs = qs.filter(txn_type=type_f)
    if ref_f:
        qs = qs.filter(reference_type=ref_f)

    page_obj = Paginator(qs, 15).get_page(request.GET.get("page"))

    return render(
        request,
        "payments/admin_wallet_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "type_f": type_f,
            "ref_f": ref_f,
            "txn_types": WalletTransaction.TRANSACTION_TYPE_CHOICES,
            "ref_types": WalletTransaction.REFERENCE_TYPE_CHOICES,
        },
    )


#   ────────────────────────────────────────────────── ADMIN: WALLET TRANSACTION DETAIL ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_wallet_detail(request, txn_id):
    txn = get_object_or_404(
        WalletTransaction.objects.select_related("wallet__user", "order"),
        txn_id=txn_id,
    )

    recent_txns = WalletTransaction.objects.filter(wallet=txn.wallet).order_by(
        "-created_at"
    )[:10]

    return render(
        request,
        "payments/admin_wallet_detail.html",
        {
            "txn": txn,
            "user": txn.wallet.user,
            "wallet": txn.wallet,
            "recent_txns": recent_txns,
        },
    )


#   ───────────────────────────────── DEBIT  (used when customer pays with wallet) ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_payment_list(request):

    search = request.GET.get("search", "").strip()
    method_f = request.GET.get("method", "")
    status_f = request.GET.get("status", "")

    payment_qs = Payment.objects.select_related("order__user").order_by("-created_at")
    if search:
        payment_qs = payment_qs.filter(
            Q(order__order_id__icontains=search)
            | Q(order__user__email__icontains=search)
            | Q(order__user__full_name__icontains=search)
            | Q(paypal_order_id__icontains=search)
            | Q(paypal_capture_id__icontains=search)
        )
    if method_f and method_f != "COD":
        payment_qs = payment_qs.filter(payment_method=method_f)
    elif method_f == "COD":
        payment_qs = payment_qs.none()

    if status_f:
        payment_qs = payment_qs.filter(payment_status=status_f)

    # Convert Payment queryset rows to unified dicts
    online_rows = []
    for p in payment_qs:
        online_rows.append(
            {
                "source": "payment",
                "txn_id_display": p.txn_id_display,
                "order": p.order,
                "payment_method": p.payment_method,
                "amount": p.amount,
                "payment_status": p.payment_status,
                "paypal_capture_id": p.paypal_capture_id or "",
                "initiated_at": p.initiated_at,
                "completed_at": p.completed_at,
                "sort_dt": p.created_at,
            }
        )

    cod_rows = []
    if not method_f or method_f == "COD":
        cod_qs = (
            Order.objects.filter(payment_method="COD")
            .select_related("user")
            .order_by("-order_date")
        )
        if search:
            cod_qs = cod_qs.filter(
                Q(order_id__icontains=search)
                | Q(user__email__icontains=search)
                | Q(user__full_name__icontains=search)
            )

        def _cod_pay_status(order):
            if order.order_status == "DELIVERED":
                return "PAID"
            elif order.order_status == "CANCELLED":
                return "CANCELLED"
            return "PENDING"

        for o in cod_qs:
            ps = _cod_pay_status(o)
            if status_f and ps != status_f:
                continue
            cod_rows.append(
                {
                    "source": "cod",
                    "txn_id_display": f"COD-{o.order_id}",
                    "order": o,
                    "payment_method": "COD",
                    "amount": o.final_amount,
                    "payment_status": ps,
                    "paypal_capture_id": "",
                    "initiated_at": o.order_date,
                    "completed_at": o.delivered_at,
                    "sort_dt": o.order_date,
                }
            )

    all_rows = sorted(
        online_rows + cod_rows,
        key=lambda r: (
            r["sort_dt"] if r["sort_dt"] else timezone.now().replace(year=2000)
        ),
        reverse=True,
    )

    paginator = Paginator(all_rows, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    method_choices = [
        ("PAYPAL", "PayPal"),
        ("WALLET", "Wallet"),
        ("COD", "Cash on Delivery"),
    ]
    status_choices = Payment.PAYMENT_STATUS_CHOICES

    return render(
        request,
        "payments/admin_payment_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "method_f": method_f,
            "status_f": status_f,
            "method_choices": method_choices,
            "status_choices": status_choices,
        },
    )


#   ────────────────────────────────────────────────── INTERNAL HELPERS ──────────────────────────────────────────────────
@never_cache
@user_login_required
def wallet_balance(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)

    transactions = (
        WalletTransaction.objects.filter(wallet=wallet)
        .select_related("order")
        .order_by("-created_at")
    )

    page_obj = Paginator(transactions, 15).get_page(request.GET.get("page"))

    return render(
        request,
        "payments/wallet_balance.html",
        {
            "wallet": wallet,
            "page_obj": page_obj,
        },
    )
