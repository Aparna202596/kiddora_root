from accounts.decorators import user_login_required,admin_login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.core.mail import send_mail
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from accounts.models import PasswordResetToken
from accounts.models import CustomUser
from accounts.views.otp_views import generate_otp
from datetime import timedelta
import random

#User Signup
def signup(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")
        # Validation
        if not all([username, email, password, confirm_password]):
            messages.error(request, "All fields are required")
            return redirect("accounts:signup")
        if password != confirm_password:
            messages.error(request, "Passwords do not match")
            return redirect("accounts:signup")
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect("accounts:signup")
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "Email already registered")
            return redirect("accounts:signup")
        # Create inactive user
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            role=CustomUser.ROLE_CUSTOMER,
            is_active=False)
        # Generate OTP
        otp = random.randint(100000, 999999)
        # Store OTP data in session
        request.session["otp_user_id"] = user.id
        request.session["otp"] = str(otp)
        request.session["otp_expiry"] = (timezone.now() + timedelta(minutes=5)).isoformat()
        # Send OTP email
        send_mail(
            subject="Verify your account",
            message=f"Your OTP is {otp}. Valid for 5 minutes.",
            from_email=None,
            recipient_list=[email],)
        return redirect("accounts:verify_otp")
    return render(request, "signup.html")

#User login View
def login_view(request):
    if request.method == "POST":
        email = request.POST.get("identifier")  # identifier field now always represents email
        password = request.POST.get("password")
        if not email or not password:
            messages.error(request, "All fields are required")
            return redirect("accounts:login")
        # Authenticate via email
        user = authenticate(request, email=email, password=password)
        if user is None:
            messages.error(request, "Invalid credentials")
            return redirect("accounts:login")
        if not user.is_active:
            messages.error(request, "Account inactive")
            return redirect("accounts:login")
        login(request, user)
        return redirect("store:home")
    return render(request, "login.html")

# User logout
@user_login_required
def logout_view(request):
    logout(request)
    return redirect("store:anonymous_home")

#Admin Login View
def admin_login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me") == "on"
        user = authenticate(request,username=email,password=password)
        if user is None:
            messages.error(request, "Invalid credentials")
            return redirect("accounts:admin_login")
        if user.role != CustomUser.ROLE_ADMIN:
            messages.error(request, "Unauthorized access")
            return redirect("accounts:admin_login")
        login(request, user)
        return redirect("accounts:admin_dashboard")
    return render(request, "admin_login.html")

# Admin logout
@admin_login_required
def admin_logout_view(request):
    logout(request)
    return redirect("accounts:admin_login")

# FORGOT PASSWORD
def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email")
        try:
            user = CustomUser.objects.get(email=email)
            if not user.is_active:
                messages.error(request, "Your account is blocked")
                return redirect("accounts:blocked")
            # Generate OTP
            otp = random.randint(100000, 999999)
            request.session["fp_user_id"] = user.id
            request.session["fp_otp"] = str(otp)
            request.session["fp_otp_expiry"] = (timezone.now() + timedelta(minutes=10)).isoformat()
            # Send OTP email
            send_mail(
                subject="Your Password Reset OTP",
                message=f"Hello {user.username}, your OTP is {otp}. Valid for 10 minutes.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],)
            messages.success(request, "OTP sent to your email")
            return redirect("accounts:verify_forgot_password_otp")
        except CustomUser.DoesNotExist:
            messages.error(request, "Email not found")
    return render(request, "accounts/auth/forgot_password.html")

# RESET PASSWORD
def reset_password(request, token):
    reset_token = get_object_or_404(PasswordResetToken, token=token)
    if reset_token.is_expired():
        reset_token.delete()
        messages.error(request, "Reset link expired")
        return redirect("accounts:forgot_password")
    if request.method == "POST":
        p1 = request.POST.get("password")
        p2 = request.POST.get("confirm_password")
        if p1 != p2:
            messages.error(request, "Passwords do not match")
            return redirect(request.path)
        user = reset_token.user
        user.set_password(p1)
        user.save()
        reset_token.delete()
        messages.success(request, "Password reset successful")
        return redirect("accounts:login")
    return render(request, "accounts/auth/reset_password.html")