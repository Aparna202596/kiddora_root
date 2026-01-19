from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib import messages
from accounts.models import CustomUser
from django.contrib.auth import authenticate, login, logout
from django.utils.crypto import get_random_string
from datetime import timedelta
from django.core .mail import send_mail
from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.cache import never_cache

OTP_EXPIRY_MINUTES = 5

def generate_otp():
    return get_random_string(length=6, allowed_chars="0123456789")

@never_cache
def verify_otp(request):
    user_id = request.session.get("verify_user_id")
    if not user_id:
        return redirect("accounts:signup")
    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == "POST":
        otp_entered = request.POST.get("otp")
        # EXPIRY CHECK
        if timezone.now() - user.otp_created_at > timedelta(minutes=2):
            messages.error(request, "OTP expired")
            return redirect("accounts:resend_otp")
        # OTP MATCH CHECK
        if otp_entered != user.otp:
            messages.error(request, "Invalid OTP")
            return redirect("accounts:verify_otp")
        # SUCCESS
        user.is_active = True
        user.email_verified = True
        user.otp = None
        user.otp_created_at = None
        user.save()
        del request.session["verify_user_id"]
        messages.success(request, "Account verified. Please login.")
        return redirect("accounts:login")
    return render(request, "accounts/auth/verify_otp.html")


# Resend OTP View, for resending OTP if expired or lost
@never_cache
def resend_otp(request):
    user_id = request.session.get("verify_user_id")
    if not user_id:
        return redirect("accounts:signup")
    user = get_object_or_404(CustomUser, id=user_id)
    # TIMER CHECK (60 seconds)
    if user.otp_created_at and timezone.now() - user.otp_created_at < timedelta(seconds=60):
        messages.error(request, "Please wait 60 seconds before resending OTP")
        return redirect("accounts:verify_otp")
    otp = generate_otp()
    user.otp = otp
    user.otp_created_at = timezone.now()
    user.save()
    send_mail(
        "Resend OTP - Kiddora",
        f"Your new OTP is {otp}. Valid for 2 minutes.",
        settings.EMAIL_HOST_USER,
        [user.email],
    )
    messages.success(request, "OTP resent successfully")
    return redirect("accounts:verify_otp")


def verify_forgot_password_otp(request):
    if request.method == "POST":
        entered_otp = request.POST.get("otp")
        fp_user_id = request.session.get("fp_user_id")
        otp = request.session.get("fp_otp")
        otp_expiry = request.session.get("fp_otp_expiry")
        if not all([entered_otp, fp_user_id, otp, otp_expiry]):
            messages.error(request, "Session expired. Please try again.")
            return redirect("accounts:forgot_password")
        if timezone.now() > parse_datetime(otp_expiry):
            messages.error(request, "OTP expired. Please request a new one.")
            return redirect("accounts:forgot_password")
        if entered_otp != otp:
            messages.error(request, "Invalid OTP")
            return redirect("accounts:verify_forgot_password_otp")
        request.session["fp_otp_verified"] = True
        return redirect("accounts:reset_password")
    return render(request, "accounts/auth/verify_forgot_password_otp.html")


def reset_password(request):
    if not request.session.get("fp_otp_verified"):
        messages.error(request, "OTP verification required")
        return redirect("accounts:forgot_password")
    if request.method == "POST":
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")
        if not password or not confirm_password:
            messages.error(request, "All fields are required")
            return redirect("accounts:reset_password")
        if password != confirm_password:
            messages.error(request, "Passwords do not match")
            return redirect("accounts:reset_password")
        user_id = request.session.get("fp_user_id")
        user = get_object_or_404(CustomUser, id=user_id)
        user.set_password(password)
        user.save()
        for key in ["fp_user_id", "fp_otp", "fp_otp_expiry", "fp_otp_verified"]:
            request.session.pop(key, None)
        messages.success(request, "Password reset successful. You can now login.")
        return redirect("accounts:login")
    return render(request, "accounts/auth/reset_password.html")

