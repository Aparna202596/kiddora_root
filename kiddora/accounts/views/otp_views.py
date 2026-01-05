from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib import messages
from accounts.models import CustomUser
from django.contrib.auth import authenticate, login, logout
import random
from datetime import timedelta
from django.core .mail import send_mail
from django.conf import settings
from django.utils.dateparse import parse_datetime

OTP_EXPIRY_MINUTES = 5

def generate_otp():
    return f"{random.randint(100000, 999999)}"

def verify_otp(request):
    if request.method == "POST":
        entered_otp = request.POST.get("otp")
        session_otp = request.session.get("otp")
        otp_user_id = request.session.get("otp_user_id")
        otp_expiry = request.session.get("otp_expiry")
        if not all([entered_otp, session_otp, otp_user_id, otp_expiry]):
            messages.error(request, "OTP session expired")
            return redirect("accounts:signup")
        if timezone.now() > parse_datetime(otp_expiry):
            messages.error(request, "OTP expired")
            return redirect("accounts:resend_otp")
        if entered_otp != session_otp:
            messages.error(request, "Invalid OTP")
            return redirect("accounts:verify_otp")
        user = get_object_or_404(CustomUser, id=otp_user_id)
        user.is_active = True
        user.save()
        # Cleanup only OTP session keys
        for key in ["otp", "otp_user_id", "otp_expiry"]:
            request.session.pop(key, None)
        login(request, user)
        return redirect("store:home")
    return render(request, "verify_otp.html")


# Resend OTP View, for resending OTP if expired or lost
def resend_otp(request):
    otp_user_id = request.session.get("otp_user_id")
    if not otp_user_id:
        messages.error(request, "Session expired. Please signup again.")
        return redirect("accounts:signup")
    user = get_object_or_404(CustomUser, id=otp_user_id)
    otp = generate_otp()
    request.session["otp"] = otp
    request.session["otp_expiry"] = (
        timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat()
    display_name = user.get_full_name() or user.username
    try:
        send_mail(
            subject="Your new OTP for Kiddora Signup",
            message=(
                f"Hello {display_name},\n\n"
                f"Your OTP is {otp}. "
                f"It is valid for {OTP_EXPIRY_MINUTES} minutes."),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],)
        messages.success(request, "A new OTP has been sent to your email.")
    except Exception:
        messages.error(request, "Failed to send OTP. Please try again.")
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

