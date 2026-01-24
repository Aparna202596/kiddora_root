from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from datetime import timedelta
from django.utils.dateparse import parse_datetime
from django.contrib import messages
from accounts.models import CustomUser
from django.utils.crypto import get_random_string
from django.core .mail import send_mail
from django.conf import settings
from django.views.decorators.cache import never_cache
from django.db.models import F

OTP_EXPIRY_MINUTES = 5

def generate_otp():
    return get_random_string(length=6, allowed_chars="0123456789")

@never_cache
def verify_signup_otp(request):
    user_id = request.session.get("verify_user_id")
    if not user_id:
        return redirect("accounts:signup")
    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == "POST":
        otp_entered = request.POST.get("otp")
        # EXPIRY CHECK
        if timezone.now() - user.otp_created_at > timedelta(minutes=OTP_EXPIRY_MINUTES):
            user.delete()  # CLEANUP inactive account
            request.session.pop("verify_user_id", None)
            messages.error(request, "OTP expired. Please register again.")
            return redirect("accounts:signup")
        # OTP MATCH CHECK
        if otp_entered != user.otp:
            messages.error(request, "Invalid OTP")
            return redirect("accounts:verify_signup_otp")
        # SUCCESS
        user.is_active = True
        user.email_verified = True
        user.otp = None
        user.otp_created_at = None
        user.save()

        request.session.pop("verify_user_id", None)
        messages.success(request, "Account verified. Please login.")
        return redirect("accounts:login")
    return render(request, "accounts/auth/verify_signup_otp.html")


# Resend OTP View, for resending OTP if expired or lost
# @never_cache
# def resend_signup_otp(request):
#     user_id = request.session.get("verify_user_id")
#     if not user_id:
#         return redirect("accounts:signup")
#     user = get_object_or_404(CustomUser, id=user_id)
#     # TIMER CHECK (60 seconds)
#     if user.otp_created_at and timezone.now() - user.otp_created_at < timedelta(minutes=OTP_EXPIRY_MINUTES):
#         messages.error(request, "Please wait 60 seconds before resending OTP")
#         return redirect("accounts:verify_signup_otp")
#     otp = generate_otp()
#     user.otp = otp
#     user.otp_created_at = timezone.now()
#     user.save()
#     send_mail(
#         "Resend OTP - Kiddora",
#         f"Your new OTP is {otp}. Valid for 5 minutes.",
#         settings.EMAIL_HOST_USER,
#         [user.email],
#     )
#     messages.success(request, "OTP resent successfully")
#     return redirect("accounts:verify_signup_otp")
@never_cache
def resend_signup_otp(request):
    user_id = request.session.get("verify_user_id")
    if not user_id:
        return redirect("accounts:signup")
    now = timezone.now()
    cooldown_time = now - timedelta(seconds=60)
    updated = CustomUser.objects.filter(id=user_id).filter(
        otp_created_at__lte=cooldown_time).update(otp=generate_otp(),otp_created_at=now)
    # If update() returns 0 → cooldown not finished
    if updated == 0:
        messages.error(request, "Please wait 60 seconds before resending OTP")
        return redirect("accounts:verify_signup_otp")

    user = CustomUser.objects.get(id=user_id)
    try:
        send_mail(
            "Resend OTP - Kiddora",
            message=f"Your OTP is {user.otp}. It is valid for {OTP_EXPIRY_MINUTES} minutes.",
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            fail_silently=False
        )
    except Exception as e:
        messages.error(request, "Failed to send OTP. Try again later.")
        return redirect("accounts:signup")

    messages.success(request, "OTP resent successfully")
    return redirect("accounts:verify_signup_otp")
# FORGOT PASSWORD
def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email")

        if not email:
            messages.error(request, "Please enter your email address.")
            return redirect("accounts:forgot_password")

        try:
            user = CustomUser.objects.get(email=email)
            # Blocked user check
            if not user.is_active:
                messages.error(request, "Your account is blocked.")
                return redirect("accounts:blocked")

            # Generate OTP
            user.otp = generate_otp()
            otp_expiry = timezone.now() + timedelta(minutes=5)

            # Store OTP data in session (used by verify_forgot_password_otp)
            request.session["fp_user_id"] = user.id
            request.session["fp_otp"] = user.otp
            request.session["fp_otp_expiry"] = otp_expiry.isoformat()
            request.session.pop("fp_otp_verified", None)  # reset if exists

            # Send OTP email
            try:
                send_mail(
                "Resend OTP - Kiddora",
                message=f"Your Password reset OTP is {user.otp}. It is valid for {OTP_EXPIRY_MINUTES} minutes.",
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[user.email],
                fail_silently=False
            )
            except Exception as e:
                messages.error(request, "Failed to send OTP. Try again later.")
                return redirect("accounts:signup")

            messages.success(request, "An OTP has been sent to your email.")
            return redirect("accounts:verify_forgot_password_otp")

        except CustomUser.DoesNotExist:
            messages.error(request, "No account found with this email.")

    return render(request, "accounts/auth/forgot_password.html")

def verify_forgot_password_otp(request):
    if request.method == "POST":
        entered_otp = request.POST.get("otp")
        fp_user_id = request.session.get("fp_user_id")
        otp = request.session.get("fp_otp")
        otp_expiry_str = request.session.get("fp_otp_expiry")

        # Basic session safety check
        if not all([entered_otp, fp_user_id, otp, otp_expiry_str]):
            messages.error(request, "Session expired. Please try again.")
            return redirect("accounts:forgot_password")

        # Safely parse expiry datetime
        otp_expiry = parse_datetime(otp_expiry_str)
        if not otp_expiry:
            messages.error(request, "Session expired. Please request a new OTP.")
            return redirect("accounts:forgot_password")

        # Expiry check
        if timezone.now() > otp_expiry:
            messages.error(request, "OTP expired. Please request a new one.")
            return redirect("accounts:forgot_password")

        # OTP match check
        if entered_otp != otp:
            messages.error(request, "Invalid OTP")
            return redirect("accounts:verify_forgot_password_otp")

        # Mark OTP verified
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

