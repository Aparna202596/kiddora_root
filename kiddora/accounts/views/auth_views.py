from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from accounts.models import CustomUser
from accounts.decorators import user_login_required, admin_login_required


# User login with "remember me"
def login_view(request):
    if request.method == "POST":
        username_or_email = request.POST.get("username")
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me") == "on"

        user = authenticate(request, username=username_or_email, password=password)
        if user and user.role == CustomUser.ROLE_CUSTOMER:
            if not user.is_active:
                messages.error(request, "Your account is blocked")
                return redirect("accounts:blocked")
            login(request, user)
            if not remember_me:
                request.session.set_expiry(0)  # Expires on browser close
            return redirect("home")
        messages.error(request, "Invalid credentials")
    return render(request, "accounts/auth/login.html")


# Admin login restricted to @kiddora.com emails
def admin_login(request):
    if request.method == "POST":
        email = request.POST.get("username")
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me") == "on"

        if not email.endswith("@kiddora.com"):
            messages.error(request, "Admin login requires @kiddora.com email")
            return redirect("accounts:admin_login")

        user = authenticate(request, username=email, password=password)
        if user and user.role == CustomUser.ROLE_ADMIN:
            login(request, user)
            if not remember_me:
                request.session.set_expiry(0)
            return redirect("accounts:admin_user_list")
        messages.error(request, "Invalid credentials")
    return render(request, "accounts/auth/login.html")


# User signup
def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
        elif CustomUser.objects.filter(email=email).exists():
            messages.error(request, "Email already exists")
        else:
            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                password=password,
                role=CustomUser.ROLE_CUSTOMER
            )
            # redirect to OTP verification
            return redirect("accounts:verify_otp", user_id=user.id)
    return render(request, "accounts/auth/signup.html")


# Logout
@login_required
def logout_view(request):
    logout(request)
    return redirect("home")


# Forgot password
def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email")
        try:
            user = CustomUser.objects.get(email=email)
            # Generate OTP and send email
            return redirect("accounts:verify_otp", user_id=user.id)
        except CustomUser.DoesNotExist:
            messages.error(request, "Email not found")
    return render(request, "accounts/auth/forgot_password.html")


# Reset password
def reset_password(request, token):
    # validate token logic
    if request.method == "POST":
        new_password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")
        if new_password == confirm_password:
            # fetch user from token
            # set_password
            return redirect("accounts:login")
        messages.error(request, "Passwords do not match")
    return render(request, "accounts/auth/reset_password.html")
