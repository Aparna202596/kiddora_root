from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from accounts.models import PasswordResetToken
from django.contrib import messages
from accounts.models import CustomUser
from django.urls import reverse
from accounts.decorators import user_login_required
from accounts.views.otp_views import generate_otp
from django.utils import timezone
import random 

# USER LOGIN
from django.contrib.auth import authenticate, login
from accounts.models import CustomUser

def login_view(request):
    if request.method == "POST":
        email = request.POST.get("username")  # field name is fine
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me") == "on"
        try:
            user_obj = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            messages.error(request, "Invalid credentials")
            return render(request, "accounts/auth/login.html")
        user = authenticate(request, username=user_obj.username, password=password)
        if user and user.role == CustomUser.ROLE_CUSTOMER:
            if not user.is_active:
                messages.error(request, "Your account is blocked")
                return redirect("accounts:blocked")
            login(request, user)
            if not remember_me:
                request.session.set_expiry(0)
            return redirect("store:home")
        messages.error(request, "Invalid credentials")
    return render(request, "accounts/auth/login.html")


# ADMIN LOGIN
def admin_login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me") == "on"
        if not email:
            messages.error(request, "Email is required")
            return redirect("accounts:admin_login")
        if not email.endswith("@kiddora.com"):
            messages.error(request, "Admin email must be <admin_name>@kiddora.com")
            return redirect("accounts:admin_login")
        user = authenticate(request, username=email, password=password)
        if user and user.role == CustomUser.ROLE_ADMIN:
            if not user.is_active:
                messages.error(request, "Your admin account is blocked")
                return redirect("accounts:blocked")
            login(request, user)
            if not remember_me:
                request.session.set_expiry(0)
            return redirect("accounts:dashboard")
        messages.error(request, "Invalid credentials")
    return render(request, "accounts/auth/admin_login.html")

# USER SIGNUP
# def signup(request):
#     if request.method == "POST":
#         email = request.POST.get("email")
#         password = request.POST.get("password")
#         username = email.split("@")[0]    # Auto-generate username from email
#         if CustomUser.objects.filter(email=email).exists():    # Check duplicates BEFORE creating user
#             messages.error(request, "Email already exists")
#             return render(request, "accounts/auth/signup.html")
#         if CustomUser.objects.filter(username=username).exists():   # Optional: check username conflict (rare with email-based generation)
#             username = f"{username}{random.randint(100, 999)}" # append random digits to avoid conflict
#         # Create user
#         user = CustomUser.objects.create_user(    
#             username=username,
#             email=email,
#             password=password,
#             role=CustomUser.ROLE_CUSTOMER,
#             email_verified=False
#         )
#         # Generate OTP for verification
#         user.otp = generate_otp()
#         user.otp_created_at = timezone.now()
#         user.save()
#         messages.success(request, "Signup successful. Verify OTP to continue.")
#         return redirect("accounts:verify_otp", user_id=user.id)
#     return render(request, "accounts/auth/signup.html")
import random
from django.contrib import messages
from django.shortcuts import render, redirect
from accounts.models import CustomUser

def signup(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        if not email or not password:
            messages.error(request, "Email and password are required")
            return render(request, "accounts/auth/signup.html")
        # Check duplicate email
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "Email already exists")
            return render(request, "accounts/auth/signup.html")
        # Auto-generate username from email
        base_username = email.split("@")[0]
        username = base_username
        # Ensure username uniqueness
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        # Create user (no email verification)
        CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            role=CustomUser.ROLE_CUSTOMER,
            is_active=True
        )
        messages.success(request, "Signup successful. Please login.")
        return redirect("accounts:login")
    return render(request, "accounts/auth/signup.html")


# LOGOUT
@user_login_required
def logout_view(request):
    logout(request)
    return redirect("store:anonymous_home")

# FORGOT PASSWORD
def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email")
        try:
            user = CustomUser.objects.get(email=email)
            if not user.is_active:
                messages.error(request, "Your account is blocked")
                return redirect("accounts:blocked")
            # Generate OTP for password reset
            user.otp = generate_otp()
            user.otp_created_at = timezone.now()
            user.save()
            token = PasswordResetToken.objects.create(user=user)
            reset_link = request.build_absolute_uri(
                reverse("accounts:reset_password", args=[token.token]))
            messages.success(request, "OTP sent to your email")
            return redirect("accounts:verify_otp", user_id=user.id)
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