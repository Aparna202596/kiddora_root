import razorpay
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.utils.timezone import now
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from accounts.decorators import admin_login_required, user_login_required

from shopcore.models import *
from ..models import Payment

razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)

@user_login_required
def initiate_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    payment, created = Payment.objects.get_or_create(
        order=order,
        payment_status="PENDING",
        defaults={"payment_method": "RAZORPAY"}
    )

    razorpay_order = razorpay_client.order.create({
        "amount": int(order.final_amount * 100),
        "currency": "INR",
        "payment_capture": 1,
    })

    payment.razorpay_order_id = razorpay_order["id"]
    payment.save()

    return render(request, "payments/initiate_payment.html", {
        "order": order,
        "payment": payment,
        "razorpay_key": settings.RAZORPAY_KEY_ID,
        "razorpay_order_id": razorpay_order["id"],
        "amount": int(order.final_amount * 100),
    })

@csrf_exempt
def payment_success(request):
    if request.method != "POST":
        return redirect("home")

    razorpay_payment_id = request.POST.get("razorpay_payment_id")
    razorpay_order_id = request.POST.get("razorpay_order_id")
    razorpay_signature = request.POST.get("razorpay_signature")

    payment = get_object_or_404(Payment, razorpay_order_id=razorpay_order_id)

    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_order_id": razorpay_order_id,
            "razorpay_signature": razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        return redirect("payments:payment_failed", payment_id=payment.id)

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
def payment_failed(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id, order__user=request.user)

    payment.payment_status = "FAILED"
    payment.failure_reason = "Payment failed or cancelled by user"
    payment.retry_allowed = True
    payment.save()

    return render(request, "payments/payment_failed.html", {
        "payment": payment,
        "order": payment.order
    })

@user_login_required
def retry_payment(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id, order__user=request.user)

    if payment.payment_status == "PAID":
        messages.error(request, "Payment already completed.")
        return redirect("orders:order_detail", payment.order.id)

    if not payment.retry_allowed:
        messages.error(request, "Retry not allowed.")
        return redirect("payments:payment_failed", payment_id=payment.id)

    payment.payment_status = "PENDING"
    payment.failure_reason = ""
    payment.save()

    return redirect("payments:initiate_payment", order_id=payment.order.id)