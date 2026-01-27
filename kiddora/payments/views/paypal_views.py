
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.utils.timezone import now
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from accounts.decorators import admin_login_required, user_login_required
import requests
from django.urls import reverse
from orders.models import Order
from ..models import Payment


def get_paypal_access_token():
    response = requests.post(
        "https://api-m.sandbox.paypal.com/v1/oauth2/token",
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET),
        data={"grant_type": "client_credentials"},
    )
    return response.json()["access_token"]

@user_login_required
def initiate_paypal_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    payment = Payment.objects.create(
        order=order,
        payment_method="PAYPAL",
        payment_status="PENDING"
    )

    token = get_paypal_access_token()

    response = requests.post(
        "https://api-m.sandbox.paypal.com/v2/checkout/orders",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        },
        json={
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": "USD",
                    "value": str(order.final_amount)
                }
            }],
            "application_context": {
                "return_url": request.build_absolute_uri(
                    reverse("payments:paypal_success", args=[payment.id])
                ),
                "cancel_url": request.build_absolute_uri(
                    reverse("payments:paypal_failed", args=[payment.id])
                )
            }
        }
    )

    data = response.json()
    approve_url = next(link["href"] for link in data["links"] if link["rel"] == "approve")

    payment.reference_id = data["id"]
    payment.save()

    return redirect(approve_url)

@user_login_required
def paypal_success(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)

    token = get_paypal_access_token()

    requests.post(
        f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{payment.reference_id}/capture",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
    )

    payment.payment_status = "PAID"
    payment.paid_at = now()
    payment.retry_allowed = False
    payment.save()

    payment.order.payment_status = "PAID"
    payment.order.save(update_fields=["payment_status"])

    return render(request, "payments/payment_success.html", {
        "order": payment.order,
        "payment": payment
    })

@user_login_required
def paypal_failed(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)

    payment.payment_status = "FAILED"
    payment.failure_reason = "PayPal payment cancelled"
    payment.retry_allowed = True
    payment.save()

    return render(request, "payments/payment_failed.html", {
        "payment": payment,
        "order": payment.order
    })
