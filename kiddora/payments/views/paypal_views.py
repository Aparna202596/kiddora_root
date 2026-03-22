"""
payments/views/paypal_payment_views.py

Full PayPal REST API v2 (Orders API) integration:
  - initiate_paypal_payment   : creates a PayPal order, redirects to PayPal
  - paypal_return             : capture after user approves on PayPal
  - paypal_cancel             : user clicked "Cancel" on PayPal
  - paypal_webhook            : IPN/webhook for async events
  - paypal_payment_failure    : failure page

Settings required (settings.py):
    PAYPAL_CLIENT_ID     = "..."
    PAYPAL_CLIENT_SECRET = "..."
    PAYPAL_MODE          = "sandbox"   # or "live"
    # Base URL of your site (used for return/cancel URLs):
    SITE_BASE_URL        = "https://yourdomain.com"

Install: pip install paypalrestsdk  OR  pip install paypalcheckoutsdk
We use raw HTTP (requests) here to avoid SDK version conflicts.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal

import requests
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.decorators import user_login_required
from payments.models import Payment, PaymentLog
from shopcore.models import Order

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# PAYPAL API HELPERS
# ─────────────────────────────────────────────────────────────

def _paypal_base_url() -> str:
    mode = getattr(settings, "PAYPAL_MODE", "sandbox")
    return (
        "https://api-m.paypal.com"
        if mode == "live"
        else "https://api-m.sandbox.paypal.com"
    )


def _get_paypal_access_token() -> str:
    """Exchange client credentials for a Bearer token."""
    client_id = getattr(settings, "PAYPAL_CLIENT_ID", "")
    client_secret = getattr(settings, "PAYPAL_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise ValueError(
            "PayPal credentials not configured. "
            "Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to settings.py"
        )
    resp = requests.post(
        f"{_paypal_base_url()}/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _paypal_headers(token: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def _restore_stock(order: Order) -> None:
    for oi in order.order_items.select_related("variant__inventory").all():
        try:
            inv = oi.variant.inventory
            inv.quantity_available += oi.quantity
            inv.quantity_sold = max(0, inv.quantity_sold - oi.quantity)
            inv.save(update_fields=["quantity_available", "quantity_sold"])
        except Exception as exc:
            logger.error("PayPal stock restore failed for OrderItem %s: %s", oi.id, exc)


def _log(payment: Payment, payload: dict, event_id: str = "") -> None:
    PaymentLog.objects.create(
        payment=payment,
        gateway="PAYPAL",
        event_type="PAYPAL_CALLBACK",
        payload=payload,
        gateway_event_id=event_id,
    )


# ─────────────────────────────────────────────────────────────
# INITIATE PAYPAL PAYMENT
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@transaction.atomic
def initiate_paypal_payment(request, order_id):
    """
    GET  /payments/pay/paypal/<order_id>/
    Creates a PayPal order and redirects the user to PayPal's approval URL.
    """
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.payment_status == "PAID":
        messages.info(request, "This order has already been paid.")
        return redirect("shopcore:order_success", order_id=order.order_id)

    # Build absolute return / cancel URLs
    base = getattr(settings, "SITE_BASE_URL", request.build_absolute_uri("/").rstrip("/"))
    return_url = base + reverse("payments:paypal_return") + f"?order_id={order.order_id}"
    cancel_url = base + reverse("payments:paypal_cancel") + f"?order_id={order.order_id}"

    try:
        token = _get_paypal_access_token()

        # Convert INR amount to USD for PayPal (PayPal doesn't support INR directly).
        # For a real app, use a live exchange-rate API.
        # Here we store the INR amount on the Payment record and pass USD to PayPal.
        # Adjust INR_TO_USD_RATE in settings or fetch dynamically.
        inr_to_usd = Decimal(str(getattr(settings, "INR_TO_USD_RATE", "0.012")))
        usd_amount = (order.final_amount * inr_to_usd).quantize(Decimal("0.01"))

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": str(order.order_id),
                    "description": f"Kiddora Order #{order.order_id}",
                    "amount": {
                        "currency_code": "USD",
                        "value": str(usd_amount),
                    },
                }
            ],
            "application_context": {
                "return_url": return_url,
                "cancel_url": cancel_url,
                "brand_name": "Kiddora",
                "user_action": "PAY_NOW",
            },
        }

        resp = requests.post(
            f"{_paypal_base_url()}/v2/checkout/orders",
            headers=_paypal_headers(token),
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        pp_order = resp.json()

        paypal_order_id = pp_order["id"]
        approve_url = next(
            (link["href"] for link in pp_order.get("links", []) if link["rel"] == "approve"),
            None,
        )
        if not approve_url:
            raise ValueError("No approval URL returned by PayPal.")

        # Create / update Payment record
        payment = Payment.objects.create(
            order=order,
            payment_method="PAYPAL",
            payment_status="INITIATED",
            amount=order.final_amount,
            paypal_order_id=paypal_order_id,
            initiated_at=timezone.now(),
        )
        _log(payment, pp_order, paypal_order_id)

        order.payment_status = "INITIATED"
        order.save(update_fields=["payment_status"])

    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("shopcore:checkout")
    except Exception as exc:
        logger.error("PayPal order creation failed: %s", exc, exc_info=True)
        messages.error(request, "Could not initiate PayPal payment. Please try again.")
        return redirect("shopcore:checkout")

    return redirect(approve_url)


# ─────────────────────────────────────────────────────────────
# PAYPAL RETURN  (user approved on PayPal)
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@transaction.atomic
def paypal_return(request):
    """
    GET  /payments/pay/paypal/return/?order_id=...&token=...&PayerID=...
    PayPal redirects here after the user approves the payment.
    We capture the payment and mark the order PAID.
    """
    order_id = request.GET.get("order_id", "")
    pp_token = request.GET.get("token", "")       # PayPal's order token
    payer_id = request.GET.get("PayerID", "")

    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.payment_status == "PAID":
        return redirect("shopcore:order_success", order_id=order.order_id)

    payment = order.payments.filter(
        payment_method="PAYPAL",
        payment_status="INITIATED",
        paypal_order_id=pp_token,
    ).first()

    if not payment:
        messages.error(request, "Payment record not found. Please contact support.")
        return redirect("payments:paypal_payment_failure", order_id=order.order_id)

    try:
        token = _get_paypal_access_token()

        # Capture the payment
        resp = requests.post(
            f"{_paypal_base_url()}/v2/checkout/orders/{pp_token}/capture",
            headers=_paypal_headers(token),
            json={},
            timeout=20,
        )
        resp.raise_for_status()
        capture_data = resp.json()

        capture_status = capture_data.get("status", "")
        capture_id = (
            capture_data.get("purchase_units", [{}])[0]
            .get("payments", {})
            .get("captures", [{}])[0]
            .get("id", "")
        )

        _log(payment, capture_data, pp_token)

        if capture_status == "COMPLETED":
            payment.payment_status = "PAID"
            payment.paypal_capture_id = capture_id
            payment.completed_at = timezone.now()
            payment.save(update_fields=[
                "payment_status", "paypal_capture_id", "completed_at", "updated_at"
            ])

            order.payment_status = "PAID"
            order.save(update_fields=["payment_status"])

            request.session.pop("applied_coupon_code", None)
            request.session.pop("applied_coupon_discount", None)

            messages.success(request, "PayPal payment successful! Your order is confirmed. 🎉")
            return redirect("shopcore:order_success", order_id=order.order_id)
        else:
            raise ValueError(f"PayPal capture status: {capture_status}")

    except Exception as exc:
        logger.error("PayPal capture failed for order %s: %s", order_id, exc, exc_info=True)
        payment.payment_status = "FAILED"
        payment.failure_reason = str(exc)
        payment.save(update_fields=["payment_status", "failure_reason", "updated_at"])
        order.payment_status = "FAILED"
        order.save(update_fields=["payment_status"])
        _restore_stock(order)
        messages.error(request, "PayPal payment capture failed. Please try again.")
        return redirect("payments:paypal_payment_failure", order_id=order.order_id)


# ─────────────────────────────────────────────────────────────
# PAYPAL CANCEL  (user clicked "Cancel" on PayPal)
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
def paypal_cancel(request):
    """
    GET  /payments/pay/paypal/cancel/?order_id=...
    """
    order_id = request.GET.get("order_id", "")
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    # Mark any INITIATED PayPal payments as CANCELLED
    order.payments.filter(
        payment_method="PAYPAL",
        payment_status="INITIATED",
    ).update(payment_status="CANCELLED")

    order.payment_status = "PENDING"
    order.save(update_fields=["payment_status"])

    messages.warning(request, "PayPal payment was cancelled. You can retry below.")
    return render(request, "payments/paypal_cancel.html", {"order": order})


# ─────────────────────────────────────────────────────────────
# PAYPAL WEBHOOK  (IPN / REST Webhooks)
# ─────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def paypal_webhook(request):
    """
    POST  /payments/webhook/paypal/
    Register in PayPal Developer Dashboard → Webhooks.
    Handles: PAYMENT.CAPTURE.COMPLETED, PAYMENT.CAPTURE.DENIED, PAYMENT.CAPTURE.REFUNDED
    """
    try:
        payload = json.loads(request.body)
        event_type = payload.get("event_type", "")
        resource = payload.get("resource", {})

        pp_order_id = resource.get("supplementary_data", {}).get(
            "related_ids", {}
        ).get("order_id", "") or resource.get("id", "")

        payment = Payment.objects.filter(paypal_order_id=pp_order_id).first()
        if not payment:
            return HttpResponse(status=200)

        PaymentLog.objects.create(
            payment=payment,
            gateway="PAYPAL",
            event_type="PAYPAL_WEBHOOK",
            payload=payload,
            gateway_event_id=resource.get("id", ""),
        )

        with transaction.atomic():
            if event_type == "PAYMENT.CAPTURE.COMPLETED":
                if payment.payment_status != "PAID":
                    payment.payment_status = "PAID"
                    payment.paypal_capture_id = resource.get("id", "")
                    payment.completed_at = timezone.now()
                    payment.save(update_fields=[
                        "payment_status", "paypal_capture_id", "completed_at", "updated_at"
                    ])
                    order = payment.order
                    order.payment_status = "PAID"
                    order.save(update_fields=["payment_status"])

            elif event_type == "PAYMENT.CAPTURE.DENIED":
                if payment.payment_status not in ("PAID", "REFUNDED"):
                    payment.payment_status = "FAILED"
                    payment.failure_reason = "Capture denied by PayPal"
                    payment.save(update_fields=["payment_status", "failure_reason", "updated_at"])
                    order = payment.order
                    order.payment_status = "FAILED"
                    order.save(update_fields=["payment_status"])
                    _restore_stock(order)

            elif event_type == "PAYMENT.CAPTURE.REFUNDED":
                payment.payment_status = "REFUNDED"
                payment.save(update_fields=["payment_status", "updated_at"])

    except Exception as exc:
        logger.error("PayPal webhook error: %s", exc, exc_info=True)
        return HttpResponse(status=500)

    return HttpResponse(status=200)


# ─────────────────────────────────────────────────────────────
# PAYPAL PAYMENT FAILURE PAGE
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
def paypal_payment_failure(request, order_id):
    """
    GET  /payments/pay/paypal/failure/<order_id>/
    """
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    latest_payment = (
        order.payments.filter(payment_method="PAYPAL")
        .order_by("-created_at")
        .first()
    )
    return render(request, "payments/paypal_failure.html", {
        "order": order,
        "latest_payment": latest_payment,
    })