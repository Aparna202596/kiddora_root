from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib import messages
from accounts.models import CustomUser
import random
from datetime import timedelta
from django.core .mail import send_mail
from django.conf import settings

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
    return render(request, "accounts/auth/verify_otp.html", {"user_id": user.id})

# Resend OTP View, for resending OTP if expired or lost
def resend_otp(request):
    user_id = request.session.get('otp_user_id')
    if not user_id:
        messages.error(request, "No OTP verification pending")
        return redirect('accounts:signup')
    user = CustomUser.objects.get(id=user_id)
    # Check if last OTP was sent less than 1 minute ago
    if user.otp_created_at and timezone.now() < user.otp_created_at + timedelta(seconds=60):
        messages.error(request, "Please wait before requesting a new OTP.")
        return redirect('accounts:verify_otp')
    # Generate new OTP
    otp = generate_otp()
    user.otp = otp
    user.otp_created_at = timezone.now()
    user.save()
    # Send OTP via email
    send_mail(
        subject="Your new OTP for Kiddora Signup",
        message=f"Hello {user.full_name}, your new OTP is {otp}. It is valid for 10 minutes.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False)
    messages.success(request, "A new OTP has been sent to your email.")
    return redirect('accounts:verify_otp')