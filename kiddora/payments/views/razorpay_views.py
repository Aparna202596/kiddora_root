from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import Decimal

import razorpay
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.decorators import user_login_required, admin_login_required
from payments.models import Payment, PaymentLog, Wallet, WalletTransaction
from payments.views.wallet_helpers import credit_refund_to_wallet, debit_from_wallet
from shopcore.models import Order, OrderItem, Cart

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# RAZORPAY CLIENT  (lazy init — fails gracefully if key absent)
# ─────────────────────────────────────────────────────────────

def _razorpay_client():
    key_id     = getattr(settings, "RAZORPAY_KEY_ID", "")
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        raise ValueError("Razorpay credentials not configured in settings.")
    return razorpay.Client(auth=(key_id, key_secret))


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _get_cart(user):
    try:
        return user.cart
    except Cart.DoesNotExist:
        return None


def _variant_is_available(variant) -> bool:
    try:
        p   = variant.product
        sub = p.subcategory
        cat = sub.category
        return (
            variant.is_active
            and p.is_active   and not p.is_deleted
            and sub.is_active and not sub.is_deleted
            and cat.is_active and not cat.is_deleted
        )
    except Exception:
        return False


def _stock_for(variant) -> int:
    try:
        return variant.inventory.quantity_available
    except Exception:
        return 0


def _mark_payment_failed(payment: Payment, reason: str = ""):
    """Atomically mark a Payment record as FAILED."""
    payment.payment_status = "FAILED"
    payment.failure_reason = reason or "Payment failed"
    payment.save(update_fields=["payment_status", "failure_reason", "updated_at"])


def _restore_stock(order: Order):
    """Return reserved stock to inventory when payment fails."""
    for oi in order.order_items.select_related("variant__inventory").all():
        try:
            inv = oi.variant.inventory
            inv.quantity_available += oi.quantity
            inv.quantity_sold = max(0, inv.quantity_sold - oi.quantity)
            inv.save(update_fields=["quantity_available", "quantity_sold"])
        except Exception as e:
            logger.error("Stock restore failed for OrderItem %s: %s", oi.id, e)


# ─────────────────────────────────────────────────────────────
# INITIATE RAZORPAY PAYMENT
# Creates a Razorpay order and renders the payment page.
# Called from checkout when user selects ONLINE payment.
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@transaction.atomic
def initiate_razorpay_payment(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    # Guard: don't re-initiate if already paid
    if order.payment_status == "PAID":
        messages.info(request, "This order is already paid.")
        return redirect("shopcore:order_success", order_id=order.order_id)

    # Check for an existing pending Razorpay payment record
    existing = Payment.objects.filter(
        order=order,
        payment_method="RAZORPAY",
        payment_status__in=["PENDING", "INITIATED"],
    ).first()

    if existing and existing.razorpay_order_id:
        # Reuse the same Razorpay order (user clicked back / refreshed)
        payment = existing
    else:
        try:
            client = _razorpay_client()
            amount_paise = int(order.final_amount * 100)   # Razorpay uses paise

            rp_order = client.order.create({
                "amount":   amount_paise,
                "currency": "INR",
                "receipt":  str(order.order_id),
                "notes": {
                    "order_id":   str(order.order_id),
                    "user_email": request.user.email,
                },
            })

            payment = Payment.objects.create(
                order              = order,
                payment_method     = "RAZORPAY",
                payment_status     = "INITIATED",
                amount             = order.final_amount,
                razorpay_order_id  = rp_order["id"],
                initiated_at       = timezone.now(),
            )

            PaymentLog.objects.create(
                payment        = payment,
                gateway        = "INTERNAL",
                event_type     = "PAYPAL_CALLBACK",   # closest available choice
                payload        = rp_order,
                gateway_event_id = rp_order["id"],
            )

            # Update order payment status
            order.payment_status = "PENDING"
            order.save(update_fields=["payment_status"])

        except ValueError as e:
            messages.error(request, str(e))
            return redirect("shopcore:checkout")
        except Exception as e:
            logger.error("Razorpay order creation failed: %s", e)
            messages.error(request, "Could not initiate payment. Please try again.")
            return redirect("shopcore:checkout")

    return render(request, "payments/razorpay_checkout.html", {
        "order":              order,
        "payment":            payment,
        "razorpay_order_id":  payment.razorpay_order_id,
        "razorpay_key_id":    getattr(settings, "RAZORPAY_KEY_ID", ""),
        "amount_paise":       int(order.final_amount * 100),
        "user_name":          request.user.full_name or request.user.email,
        "user_email":         request.user.email,
        "user_phone":         request.user.phone or "",
    })


# ─────────────────────────────────────────────────────────────
# RAZORPAY PAYMENT VERIFICATION (callback after JS payment)
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@require_POST
@transaction.atomic
def verify_razorpay_payment(request):
    """
    Called by the front-end JS after Razorpay's checkout.handler fires.
    Verifies HMAC signature and marks order as PAID.
    """
    razorpay_order_id   = request.POST.get("razorpay_order_id", "")
    razorpay_payment_id = request.POST.get("razorpay_payment_id", "")
    razorpay_signature  = request.POST.get("razorpay_signature", "")
    order_id            = request.POST.get("order_id", "")

    order   = get_object_or_404(Order, order_id=order_id, user=request.user)
    payment = get_object_or_404(
        Payment,
        order=order,
        razorpay_order_id=razorpay_order_id,
        payment_method="RAZORPAY",
    )

    # ── Signature verification ────────────────────────────────
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "").encode()
    message    = f"{razorpay_order_id}|{razorpay_payment_id}".encode()
    expected   = hmac.new(key_secret, message, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, razorpay_signature):
        _mark_payment_failed(payment, "Signature mismatch")
        order.payment_status = "FAILED"
        order.save(update_fields=["payment_status"])
        PaymentLog.objects.create(
            payment    = payment,
            gateway    = "INTERNAL",
            event_type = "MANUAL",
            payload    = {"error": "signature_mismatch"},
        )
        messages.error(request, "Payment verification failed. Please contact support.")
        return redirect("payments:payment_failure", order_id=order.order_id)

    # ── Mark as PAID ──────────────────────────────────────────
    payment.payment_status      = "PAID"
    payment.razorpay_payment_id = razorpay_payment_id
    payment.razorpay_signature  = razorpay_signature
    payment.completed_at        = timezone.now()
    payment.save(update_fields=[
        "payment_status", "razorpay_payment_id",
        "razorpay_signature", "completed_at", "updated_at",
    ])

    order.payment_status = "PAID"
    order.save(update_fields=["payment_status"])

    PaymentLog.objects.create(
        payment          = payment,
        gateway          = "INTERNAL",
        event_type       = "PAYPAL_CALLBACK",
        payload          = {
            "razorpay_order_id":   razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
        },
        gateway_event_id = razorpay_payment_id,
    )

    # Clear session coupon
    request.session.pop("applied_coupon_code", None)
    request.session.pop("applied_coupon_discount", None)

    messages.success(request, "Payment successful! Your order has been placed.")
    return redirect("shopcore:order_success", order_id=order.order_id)


# ─────────────────────────────────────────────────────────────
# RAZORPAY WEBHOOK  (server-to-server event from Razorpay)
# ─────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Razorpay sends signed webhook events here.
    Register this URL in Razorpay dashboard → Webhooks.
    """
    webhook_secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "").encode()
    received_sig   = request.headers.get("X-Razorpay-Signature", "")

    expected = hmac.new(webhook_secret, request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_sig):
        logger.warning("Razorpay webhook: invalid signature")
        return HttpResponse(status=400)

    try:
        payload    = json.loads(request.body)
        event      = payload.get("event", "")
        entity     = payload.get("payload", {}).get("payment", {}).get("entity", {})
        rp_pay_id  = entity.get("id", "")
        rp_ord_id  = entity.get("order_id", "")

        payment = Payment.objects.filter(razorpay_order_id=rp_ord_id).first()
        if not payment:
            return HttpResponse(status=200)   # unknown order — ack anyway

        PaymentLog.objects.create(
            payment          = payment,
            gateway          = "INTERNAL",
            event_type       = "PAYPAL_WEBHOOK",
            payload          = payload,
            gateway_event_id = rp_pay_id,
        )

        with transaction.atomic():
            if event == "payment.captured":
                payment.payment_status      = "PAID"
                payment.razorpay_payment_id = rp_pay_id
                payment.completed_at        = timezone.now()
                payment.save(update_fields=[
                    "payment_status", "razorpay_payment_id", "completed_at", "updated_at"
                ])
                order = payment.order
                order.payment_status = "PAID"
                order.save(update_fields=["payment_status"])

            elif event == "payment.failed":
                _mark_payment_failed(payment, entity.get("error_description", ""))
                order = payment.order
                order.payment_status = "FAILED"
                order.save(update_fields=["payment_status"])
                _restore_stock(order)

            elif event == "refund.created":
                payment.payment_status = "REFUNDED"
                payment.save(update_fields=["payment_status", "updated_at"])

    except Exception as e:
        logger.error("Razorpay webhook error: %s", e)
        return HttpResponse(status=500)

    return HttpResponse(status=200)


# ─────────────────────────────────────────────────────────────
# COD CONFIRMATION
# Marks a COD order as confirmed and decrements stock.
# (Stock is reserved in place_order; this just finalises status.)
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
def cod_confirmation(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.payment_method != "COD":
        return redirect("shopcore:order_success", order_id=order.order_id)

    if order.payment_status not in ("PENDING", "INITIATED"):
        return redirect("shopcore:order_success", order_id=order.order_id)

    # Create a COD payment record if it doesn't exist yet
    Payment.objects.get_or_create(
        order=order,
        payment_method="COD",
        defaults={
            "payment_status": "PENDING",
            "amount":         order.final_amount,
            "initiated_at":   timezone.now(),
        },
    )

    return render(request, "payments/cod_confirmation.html", {"order": order})


# ─────────────────────────────────────────────────────────────
# PAYMENT FAILURE PAGE
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
def payment_failure(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    latest_payment = order.payments.filter(
        payment_method="RAZORPAY"
    ).order_by("-created_at").first()

    return render(request, "payments/payment_failure.html", {
        "order":          order,
        "latest_payment": latest_payment,
    })


# ─────────────────────────────────────────────────────────────
# RETRY PAYMENT
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@transaction.atomic
def retry_payment(request, order_id):
    """
    User clicks "Retry Payment" on the failure page.
    Increments retry_count, resets payment status, and
    redirects to Razorpay initiation.
    """
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.payment_status == "PAID":
        return redirect("shopcore:order_success", order_id=order.order_id)

    # Mark previous FAILED payments as CANCELLED to avoid confusion
    failed_payments = order.payments.filter(
        payment_method="RAZORPAY",
        payment_status="FAILED",
    )
    for p in failed_payments:
        p.payment_status = "CANCELLED"
        p.retry_count   += 1
        p.save(update_fields=["payment_status", "retry_count", "updated_at"])

    # Reset order payment status so initiation can proceed
    order.payment_status = "PENDING"
    order.save(update_fields=["payment_status"])

    return redirect("payments:initiate_razorpay_payment", order_id=order.order_id)


# ─────────────────────────────────────────────────────────────
# ADMIN: PAYMENT LIST
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_payment_list(request):
    from django.core.paginator import Paginator
    from django.db.models import Q

    search   = request.GET.get("search", "").strip()
    method_f = request.GET.get("method", "").strip()
    status_f = request.GET.get("status", "").strip()

    qs = Payment.objects.select_related("order__user").order_by("-created_at")

    if search:
        qs = qs.filter(
            Q(order__order_id__icontains=search)
            | Q(order__user__email__icontains=search)
            | Q(razorpay_payment_id__icontains=search)
        )
    if method_f:
        qs = qs.filter(payment_method=method_f)
    if status_f:
        qs = qs.filter(payment_status=status_f)

    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))

    return render(request, "payments/admin_payment_list.html", {
        "page_obj":       page_obj,
        "search":         search,
        "method_f":       method_f,
        "status_f":       status_f,
        "method_choices": Payment.PAYMENT_METHOD_CHOICES,
        "status_choices": Payment.PAYMENT_STATUS_CHOICES,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: PAYMENT DETAIL
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_payment_detail(request, txn_id):
    payment = get_object_or_404(
        Payment.objects.select_related("order__user", "order__address").prefetch_related("logs"),
        txn_id=txn_id,
    )
    return render(request, "payments/admin_payment_detail.html", {"payment": payment})


# ─────────────────────────────────────────────────────────────
# ADMIN: MANUAL REFUND TO WALLET
# For edge-cases where automatic refund did not trigger.
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
@require_POST
@transaction.atomic
def admin_manual_refund(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    try:
        amount = Decimal(request.POST.get("amount", "0"))
        if amount <= 0:
            raise ValueError
    except (ValueError, Exception):
        messages.error(request, "Enter a valid refund amount.")
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    description = (
        request.POST.get("description", "").strip()
        or f"Manual refund for order {order.order_id}"
    )

    credit_refund_to_wallet(
        user           = order.user,
        amount         = amount,
        description    = description,
        reference_type = "ORDER",
        reference_id   = str(order.order_id),
        order          = order,
    )

    # Update order payment status
    order.payment_status = "REFUNDED"
    order.save(update_fields=["payment_status"])

    # Also update Payment record if exists
    Payment.objects.filter(order=order, payment_status="PAID").update(
        payment_status="REFUNDED"
    )

    messages.success(
        request,
        f"₹{amount} manually refunded to {order.user.email}'s wallet."
    )
    return redirect("shopcore:admin_order_detail", order_id=order_id)