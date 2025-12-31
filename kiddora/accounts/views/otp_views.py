from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib import messages
from accounts.models import CustomUser
import random

OTP_EXPIRY_MINUTES = 5

def generate_otp():
    return f"{random.randint(100000, 999999)}"


def verify_otp(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)

    if request.method == "POST":
        otp_input = request.POST.get("otp")
        if user.otp == otp_input and user.otp_created_at:
            delta = timezone.now() - user.otp_created_at
            if delta.total_seconds() <= OTP_EXPIRY_MINUTES * 60:
                user.email_verified = True
                user.otp = None
                user.otp_created_at = None
                user.save()
                messages.success(request, "OTP verified successfully")
                return redirect("accounts:login")
            else:
                messages.error(request, "OTP expired")
        else:
            messages.error(request, "Invalid OTP")

    return render(request, "accounts/auth/verify_otp.html", {"user": user})


def resend_otp(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    user.otp = generate_otp()
    user.otp_created_at = timezone.now()
    user.save()
    # send email logic here
    messages.success(request, "OTP resent successfully")
    return redirect("accounts:verify_otp", user_id=user.id)
