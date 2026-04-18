from __future__ import annotations

import json
import logging
import re
from decimal import ROUND_HALF_UP, Decimal

import requests
from accounts.decorators import user_login_required
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from payments.models import Payment, PaymentLog, Wallet
from payments.views.wallet_helpers import (_finalize_order_after_payment,
                                        _restore_inventory_for_order)
from shopcore.models import Order
from utils.currency import convert_currency

logger = logging.getLogger(__name__)


#   ────────────────────────────────────────────────── WALLET HELPER ──────────────────────────────────────────────────
def _get_wallet_balance(user) -> Decimal:
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet.balance


def _paypal_base_url() -> str:
    mode = getattr(settings, "PAYPAL_MODE", "sandbox")
    return (
        "https://api-m.sandbox.paypal.com"
        if mode == "sandbox"
        else "https://api-m.paypal.com"
    )

def _paypal_access_token() -> str:
    url = f"{_paypal_base_url()}/v1/oauth2/token"
    resp = requests.post(
        url,
        data={"grant_type": "client_credentials"},
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def _paypal_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_paypal_access_token()}",
    }

def _sanitise_reference_id(order_id: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9\-]", "", order_id)
    return clean[:128]

def _format_amount(amount: Decimal) -> str:
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def _paypal_create_order(amount: Decimal, currency: str, reference_id: str) -> dict:
    url = f"{_paypal_base_url()}/v2/checkout/orders"
    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": _sanitise_reference_id(reference_id),
                "amount": {
                    "currency_code": currency,
                    "value": _format_amount(amount),
                },
            }
        ],
        "application_context": {
            "return_url": "http://localhost:8000/payments/paypal/callback/",
            "cancel_url": "http://localhost:8000/payments/paypal/cancel/",
        },
    }

    resp = requests.post(url, headers=_paypal_headers(), json=body, timeout=15)

    if not resp.ok:
        logger.error(
            "PayPal create order %s — response body: %s",
            resp.status_code,
            resp.text,
        )

    resp.raise_for_status()
    return resp.json()


def _paypal_capture_order(paypal_order_id: str) -> dict:
    url = f"{_paypal_base_url()}/v2/checkout/orders/{paypal_order_id}/capture"
    resp = requests.post(url, headers=_paypal_headers(), timeout=15)

    if not resp.ok:
        logger.error(
            "PayPal capture order %s — response body: %s",
            resp.status_code,
            resp.text,
        )
    resp.raise_for_status()
    return resp.json()

#   ────────────────────────────────────────────────── INITIATE PAYPAL PAYMENT ──────────────────────────────────────────────────
@never_cache
@user_login_required
def initiate_paypal_payment(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    if order.payment_status == "PAID":
        return redirect("shopcore:order_success", order_id=order.order_id)

    currency = getattr(settings, "PAYPAL_CURRENCY", "USD")

    try:
        amount_usd = Decimal(
            str(
                convert_currency(
                    amount=order.final_amount,
                    from_currency="INR",
                    to_currency=currency,
                )
            )
        )
    except Exception as exc:
        logger.exception("Currency conversion failed: %s", exc)

        amount_usd = (order.final_amount * Decimal("0.012")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    try:
        pp_data = _paypal_create_order(
            amount=amount_usd,
            currency=currency,
            reference_id=str(order.order_id),
        )
    except Exception as exc:
        logger.exception("PayPal create order failed for order %s: %s", order_id, exc)
        payment = Payment.objects.create(
            order=order,
            payment_method="PAYPAL",
            payment_status="FAILED",
            amount=order.final_amount,
            failure_reason=str(exc),
            initiated_at=timezone.now(),
        )
        PaymentLog.objects.create(
            payment=payment,
            gateway="PAYPAL",
            event_type="PAYPAL_CALLBACK",
            payload={"error": str(exc)},
        )
        order.order_status = "ORDER NOT PLACED"
        order.payment_status = "FAILED"
        order.save(update_fields=["order_status", "payment_status"])
        return redirect("payments:paypal_failure", order_id=order.order_id)

    paypal_order_id = pp_data.get("id")
    approve_url = next(
        (link["href"] for link in pp_data.get("links", []) if link["rel"] == "approve"),
        None,
    )

    if not approve_url:
        logger.error(
            "PayPal did not return an approve URL for order %s: %s",
            order_id,
            pp_data,
        )
        return redirect("payments:paypal_failure", order_id=order.order_id)

    payment = Payment.objects.create(
        order=order,
        payment_method="PAYPAL",
        payment_status="INITIATED",
        amount=order.final_amount,
        paypal_order_id=paypal_order_id,
        initiated_at=timezone.now(),
    )
    PaymentLog.objects.create(
        payment=payment,
        gateway="PAYPAL",
        event_type="PAYPAL_CALLBACK",
        payload=pp_data,
        gateway_event_id=paypal_order_id,
    )
    request.session["pending_paypal_order_id"] = paypal_order_id
    request.session["pending_kiddora_order_id"] = order.order_id

    return redirect(approve_url)

# ────────────────────────────────────────────────── PAYPAL CALLBACK ──────────────────────────────────────────────────
@never_cache
@transaction.atomic
def paypal_callback(request):
    paypal_order_id = request.GET.get("token")
    payer_id = request.GET.get("PayerID")

    print("=== PAYPAL CALLBACK START ===")
    print("User authenticated?", request.user.is_authenticated)
    print("Session keys:", list(request.session.keys()))
    print("paypal_order_id from URL:", paypal_order_id)

    payment = None
    order = None

    if paypal_order_id:
        try:
            payment = Payment.objects.select_related("order", "order__user").get(
                paypal_order_id=paypal_order_id
            )
            order = payment.order
            print(f"Found order via paypal_order_id: {order.order_id}")
        except Payment.DoesNotExist:
            print("Payment record not found using paypal_order_id")

    if not order:
        kiddora_order_id = request.session.get("pending_kiddora_order_id")
        if kiddora_order_id:
            try:
                order = Order.objects.select_related("user").get(
                    order_id=kiddora_order_id
                )
                print(f"Found order via session: {order.order_id}")
            except Order.DoesNotExist:
                pass

    if not order:
        messages.error(request, "Order not found. Please try again.")
        return redirect("shopcore:user_order_list")

    if not request.user.is_authenticated and order.user:
        try:
            from django.contrib.auth import login

            login(
                request, order.user, backend="django.contrib.auth.backends.ModelBackend"
            )
            print(f"✅ User recovered: {order.user.email}")
        except Exception as e:
            print(f"User recovery failed: {e}")

    if request.user.is_authenticated and order.user != request.user:
        messages.error(request, "This order does not belong to you.")
        return redirect("shopcore:user_order_list")

    if order.payment_status == "PAID":
        return redirect("shopcore:order_success", order_id=order.order_id)

    try:
        capture_data = _paypal_capture_order(paypal_order_id)
    except Exception as exc:
        logger.exception("PayPal capture failed for order %s: %s", order.order_id, exc)
        if payment:
            payment.payment_status = "FAILED"
            payment.failure_reason = str(exc)
            payment.save(update_fields=["payment_status", "failure_reason"])
        order.order_status = "ORDER NOT PLACED"
        order.payment_status = "FAILED"
        order.save(update_fields=["order_status", "payment_status"])
        return redirect("payments:paypal_failure", order_id=order.order_id)

    capture_status = capture_data.get("status", "")
    if payment:
        PaymentLog.objects.create(
            payment=payment,
            gateway="PAYPAL",
            event_type="PAYPAL_CALLBACK",
            payload=capture_data,
            gateway_event_id=paypal_order_id,
        )

    if capture_status == "COMPLETED":
        capture_id = None
        try:
            capture_id = capture_data["purchase_units"][0]["payments"]["captures"][0][
                "id"
            ]
        except (KeyError, IndexError):
            pass

        payer_email = capture_data.get("payer", {}).get("email_address", "")

        if payment:
            payment.payment_status = "PAID"
            payment.paypal_capture_id = capture_id
            payment.paypal_payer_id = payer_id
            payment.paypal_payer_email = payer_email
            payment.completed_at = timezone.now()
            payment.save(
                update_fields=[
                    "payment_status",
                    "paypal_capture_id",
                    "paypal_payer_id",
                    "paypal_payer_email",
                    "completed_at",
                ]
            )

        order.payment_status = "PAID"
        order.save(update_fields=["payment_status"])

        _finalize_order_after_payment(request, order)

        print("✅ Payment completed - redirecting to order success")
        return redirect("shopcore:order_success", order_id=order.order_id)

    else:
        failure_reason = (
            capture_data.get("details", [{}])[0].get("description", "")
            or capture_status
        )
        if payment:
            payment.payment_status = "FAILED"
            payment.failure_reason = failure_reason
            payment.save(update_fields=["payment_status", "failure_reason"])

        order.order_status = "ORDER NOT PLACED"
        order.payment_status = "FAILED"
        order.save(update_fields=["order_status", "payment_status"])

        _restore_inventory_for_order(order)
        return redirect("payments:paypal_failure", order_id=order.order_id)


@never_cache
def paypal_cancel(request):
    kiddora_order_id = request.session.get("pending_kiddora_order_id")
    paypal_order_id = request.GET.get("token")

    order = None
    if kiddora_order_id:
        order = Order.objects.filter(order_id=kiddora_order_id).first()
    elif paypal_order_id:
        try:
            payment = Payment.objects.select_related("order").get(
                paypal_order_id=paypal_order_id
            )
            order = payment.order
        except Payment.DoesNotExist:
            pass

    if order:
        Payment.objects.filter(order=order, payment_status="INITIATED").update(
            payment_status="FAILED"
        )

        order.order_status = "ORDER NOT PLACED"
        order.payment_status = "FAILED"
        order.save(update_fields=["order_status", "payment_status"])
        return redirect("payments:paypal_failure", order_id=order.order_id)

    messages.warning(request, "Payment was cancelled.")
    return redirect("shopcore:user_order_list")

#   ────────────────────────────────────────────────── PAYPAL SUCCESS PAGE ──────────────────────────────────────────────────
@never_cache
@user_login_required
def paypal_success(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    latest_payment = order.payments.filter(payment_status="PAID").first()
    return render(
        request,
        "payments/paypal_success.html",
        {
            "order": order,
            "latest_payment": latest_payment,
        },
    )

#   ────────────────────────────────────────────────── PAYPAL FAILURE PAGE ──────────────────────────────────────────────────
@never_cache
@user_login_required
def paypal_failure(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    latest_payment = (
        order.payments.filter(payment_method="PAYPAL").order_by("-created_at").first()
    )
    return render(
        request,
        "payments/paypal_failure.html",
        {
            "order": order,
            "latest_payment": latest_payment,
        },
    )

#   ────────────────────────────────────────────────── RETRY PAYMENT ──────────────────────────────────────────────────
@never_cache
@user_login_required
def retry_payment(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    if order.payment_status == "PAID":
        return redirect("shopcore:order_success", order_id=order.order_id)
    return redirect("payments:initiate_paypal_payment", order_id=order.order_id)

#   ────────────────────────────────────────────────── PAYPAL WEBHOOK ──────────────────────────────────────────────────
@csrf_exempt
@require_POST
def paypal_webhook(request):
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event_type = payload.get("event_type", "")
    resource = payload.get("resource", {})
    paypal_order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get(
        "order_id"
    ) or resource.get("id")

    PaymentLog.objects.create(
        gateway="PAYPAL",
        event_type="PAYPAL_WEBHOOK",
        payload=payload,
        gateway_event_id=paypal_order_id or "",
    )

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        capture_id = resource.get("id")
        try:
            payment = Payment.objects.get(paypal_capture_id=capture_id)
            if payment.payment_status != "PAID":
                payment.payment_status = "PAID"
                payment.completed_at = timezone.now()
                payment.save(update_fields=["payment_status", "completed_at"])
                payment.order.payment_status = "PAID"
                payment.order.save(update_fields=["payment_status"])
        except Payment.DoesNotExist:
            pass

    elif event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"):
        capture_id = resource.get("id")
        try:
            payment = Payment.objects.get(paypal_capture_id=capture_id)
            payment.payment_status = "FAILED"
            payment.failure_reason = event_type
            payment.save(update_fields=["payment_status", "failure_reason"])
        except Payment.DoesNotExist:
            pass

    return HttpResponse(status=200)
