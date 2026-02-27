from django.views.decorators.cache import never_cache
from accounts.views.otp_views import generate_otp
from accounts.decorators import user_login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import get_user_model, logout
from shopcore.models import *
from django.shortcuts import render, redirect
from django.core.mail import send_mail
from accounts.models import *
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from datetime import timedelta

User = get_user_model()

OTP_EXPIRY_MINUTES = 5

@never_cache
@user_login_required
def user_profile(request):
    user = request.user
    addresses = UserAddress.objects.filter(user=user)
    orders = Order.objects.filter(user=user).order_by("-created_at")
    return render(
        request,
        "accounts/profile/profile.html",
        {"user": user, "addresses": addresses,"orders": orders,},)

@never_cache
@user_login_required
def delete_profile(request):
    user = request.user

    if request.method == "POST":
        password = request.POST.get("password")

        # Validate password input
        if not password:
            messages.error(request, "Password is required to delete your account.")
            return redirect("accounts:delete_profile")

        # Check password
        if not user.check_password(password):
            messages.error(request, "Incorrect password.")
            return redirect("accounts:delete_profile")

        # Delete user account
        username = user.username or user.email
        logout(request)
        user.delete()

        messages.success(request, f"Account {username} deleted successfully.")
        return redirect("shopcore:anonymous_home")

    return render(request, "accounts/profile/delete_profile.html", {"user": user})


@never_cache
@user_login_required
def edit_profile(request):
    user = request.user
    if request.method == "POST":

        form_data = request.POST.dict()

        full_name = request.POST.get("full_name")
        phone = request.POST.get("phone")

        if not full_name or not phone:
            messages.error(request,"Name & phone required")
            return render(request,"accounts/profile/edit_profile.html",{"user":user,"form_data":form_data})
        
        user.full_name = request.POST.get("full_name")
        user.phone = request.POST.get("phone")
        user.gender = request.POST.get("gender")

        if "profile_image" in request.FILES:
            user.profile_image = request.FILES["profile_image"]

        user.save()
        messages.success(request, "Profile updated successfully")
        return redirect("accounts:user_profile")
    return render(request, "accounts/profile/edit_profile.html", {"user": user})

@user_login_required
def change_password(request):
    if request.method == "POST":
        user = request.user
        current_password = request.POST.get("current_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        # CHECK CURRENT PASSWORD
        if not user.check_password(current_password):
            messages.error(request, "Current password is incorrect")
            return redirect("accounts:change_password")

        # CHECK PASSWORD MATCH
        if new_password != confirm_password:
            messages.error(request, "New passwords do not match")
            return redirect("accounts:change_password")

        # OPTIONAL: PASSWORD LENGTH CHECK
        if len(new_password) < 6:
            messages.error(request, "Password must be at least 6 characters")
            return redirect("accounts:change_password")

        # SUCCESS
        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, "Password changed successfully")
        return redirect("accounts:user_profile")
    return render(request, "accounts/profile/change_password.html")

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
        try:
            send_mail(
                subject="Email Change OTP",
                message=(
                    "Hi,\n\n"
                    "You requested to change the email address linked to your Kiddora account.\n\n"
                    f"Your verification OTP is {user.otp}.\n"
                    f"This OTP is valid for {OTP_EXPIRY_MINUTES} minutes.\n\n"
                    "If you did not request this change, please secure your account immediately or contact support.\n\n"
                    "Best regards,\n"
                    "Kiddora Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[new_email],
                fail_silently=False,
            )
        except Exception as e:
            messages.error(request, "Failed to send OTP. Try again later.")
            return redirect("accounts:user_profile")
        
        messages.success(request, "OTP sent to your new email address")
        return redirect("accounts:verify_email_update")
    
    return render(request, "accounts/profile/change_email.html")

@user_login_required
def verify_email_update(request):
    user = request.user
    if request.method == "POST":
        entered_otp = request.POST.get("otp")
        # SAFETY CHECKS
        if not user.otp or not user.otp_created_at or not user.pending_email:
            messages.error(request, "Invalid or expired session")
            return redirect("accounts:change_email")
        # OTP EXPIRY VALIDATION (CRITICAL FIX)
        if timezone.now() > user.otp_created_at + timedelta(minutes=OTP_EXPIRY_MINUTES):
            user.otp = None
            user.otp_created_at = None
            user.pending_email = None
            user.save()
            messages.error(request, "OTP expired. Please try again.")
            return redirect("accounts:change_email")
        # OTP MATCH VALIDATION
        if entered_otp != user.otp:
            messages.error(request, "Invalid OTP")
            return redirect("accounts:verify_email_update")
        # SUCCESS: UPDATE EMAIL
        user.email = user.pending_email
        user.pending_email = None
        user.otp = None
        user.otp_created_at = None
        user.save()
        messages.success(request, "Email updated successfully")
        return redirect("accounts:user_profile")
    return render(request, "accounts/otp/verification.html")
