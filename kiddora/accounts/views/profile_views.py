from django.shortcuts import render, redirect
from django.contrib import messages
from accounts.decorators import user_login_required
from django.utils import timezone
from accounts.views.otp_views import generate_otp
from django.contrib.auth.forms import PasswordChangeForm
from accounts.models import UserAddress
from django.contrib.auth import update_session_auth_hash
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
from accounts.models import CustomUser

@user_login_required
def profile_view(request):
    addresses = UserAddress.objects.filter(user=request.user)
    return render(
        request,
        "accounts/profile/profile.html",
        {"user": request.user, "addresses": addresses},)

@user_login_required
def profile_edit(request):
    user = request.user
    if request.method == "POST":
        user.full_name = request.POST.get("full_name")
        user.phone = request.POST.get("phone")
        user.gender = request.POST.get("gender")
        if "profile_image" in request.FILES:
            user.profile_image = request.FILES["profile_image"]
        user.save()
        messages.success(request, "Profile updated")
        return redirect("accounts:profile")
    return render(request, "accounts/profile/edit_profile.html", {"user": user})

@user_login_required
def change_password(request):
    if request.method == "POST":
        user = request.user
        if user.check_password(request.POST["current_password"]):
            if request.POST["new_password"] == request.POST["confirm_password"]:
                user.set_password(request.POST["new_password"])
                user.save()
                update_session_auth_hash(request, user)  # FIX
                messages.success(request, "Password changed successfully")
                return redirect("accounts:profile")

@user_login_required
def change_email(request):
    if request.method == "POST":
        new_email = request.POST.get("email")
        # Optional: prevent duplicate email usage
        if CustomUser.objects.filter(email=new_email).exclude(id=request.user.id).exists():
            messages.error(request, "Email already in use")
            return redirect("accounts:change_email")
        user = request.user
        user.pending_email = new_email
        user.otp = generate_otp()
        user.otp_created_at = timezone.now()
        user.save()
        # SEND OTP EMAIL (CRITICAL FIX)
        send_mail(
            subject="Email Change OTP",
            message=f"Your OTP is {user.otp}. It is valid for 10 minutes.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[new_email],
            fail_silently=False,
        )
        messages.success(request, "OTP sent to your new email address")
        return redirect("accounts:verify_email_otp")
    return render(request, "accounts/profile/change_email.html")

@user_login_required
def verify_email_otp(request):
    user = request.user
    if request.method == "POST":
        entered_otp = request.POST.get("otp")
        # SAFETY CHECKS
        if not user.otp or not user.otp_created_at or not user.pending_email:
            messages.error(request, "Invalid or expired session")
            return redirect("accounts:change_email")
        # OTP EXPIRY VALIDATION (CRITICAL FIX)
        if timezone.now() > user.otp_created_at + timedelta(minutes=10):
            user.otp = None
            user.otp_created_at = None
            user.pending_email = None
            user.save()
            messages.error(request, "OTP expired. Please try again.")
            return redirect("accounts:change_email")
        # OTP MATCH VALIDATION
        if entered_otp != user.otp:
            messages.error(request, "Invalid OTP")
            return redirect("accounts:verify_email_otp")
        # SUCCESS: UPDATE EMAIL
        user.email = user.pending_email
        user.pending_email = None
        user.otp = None
        user.otp_created_at = None
        user.save()
        messages.success(request, "Email updated successfully")
        return redirect("accounts:profile")
    return render(request, "accounts/profile/verify_email_otp.html")
