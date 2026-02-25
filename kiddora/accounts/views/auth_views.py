from django.views.decorators.cache import never_cache
from django.contrib.auth import login, logout, authenticate, get_user_model
from accounts.decorators import user_login_required,admin_login_required
from django.utils.crypto import get_random_string
from django.shortcuts import render, redirect
from django.core.mail import send_mail
from accounts.models import *
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.db import transaction 
import re


User = get_user_model()

OTP_EXPIRY_MINUTES=5

def generate_otp():
    """Return a 6-digit numeric OTP."""
    return get_random_string(length=6, allowed_chars="0123456789")

#User_logout
@never_cache
@user_login_required
def user_logout(request):
    logout(request)
    request.session.flush()
    response = redirect("shopcore:anonymous_home")
    response.delete_cookie("remember_user")
    return response

#Google_login
@never_cache
def google_login(request):
    return redirect("/accounts/google/login/")

#User_login
@never_cache
def user_login(request):
    if request.user.is_authenticated and request.user.role == CustomUser.ROLE_CUSTOMER:
        return redirect("shopcore:home")

    remembered_user = request.COOKIES.get("remember_user", "")

    context = {"remembered_user": remembered_user}

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me")

        context["form_data"] = {"email": email, "remember_me": remember_me}

        user=authenticate(request,username=email,password=password)

        if user is None:
            messages.error(request, "Invalid username or password")
            return render(request, "accounts/auth/login.html", context)

        if user.role != CustomUser.ROLE_CUSTOMER:
            messages.error(request, "Access denied")
            return render(request, "accounts/auth/login.html", context)
            
        if not user.is_active:
            return redirect("accounts:blocked")
        
        if not user.email_verified:
            messages.error(request, "Please verify your email")
            return render(request, "accounts/auth/login.html", context)
            
        login(request, user)

        response = redirect("shopcore:home")
        
        if remember_me:
            response.set_cookie("remember_user",email,max_age=7 * 24 * 60 * 60)
        else:
            response.delete_cookie("remember_user")

        return response
    
    return render(request,"accounts/auth/login.html",context)

#Signup
@never_cache
def user_signup(request):
    error=''
    success=''
    context = {}

    if request.method=='POST':
        form_data = request.POST.dict()     #preserve field
        context["form_data"] = form_data

        username=request.POST.get('username','').strip()
        email=request.POST['email']
        password1=request.POST['password1']
        password2=request.POST['password2']

        # Validation checks

        if User.objects.filter(username__iexact=username).exists():
            messages.error(request,"Username already exists!")
            return render(request,'accounts/auth/signup.html',context)
        elif len(username)<6:
            messages.error(request,"Username atleast contain 6 characters, Retry!")
            return render(request,'accounts/auth/signup.html',context)
        elif re.search(r'\s',username):
            messages.error(request,"Username cannot contain spaces!")
            return render(request,'accounts/auth/signup.html',context)
        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request,"Email already exists, Try new!")
            return render(request,'accounts/auth/signup.html',context)
        elif len(password1) < 6:
            messages.error(request,"Password must be at least 6 characters, Retry!")
            return render(request,'accounts/auth/signup.html',context)
        elif re.search(r'\s', password1):
            messages.error(request,"Password cannot contain spaces!")
            return render(request,'accounts/auth/signup.html',context)
        elif password1 != password2:
            messages.error(request,"Passwords do not match!")
            return render(request,'accounts/auth/signup.html',context)
        
        with transaction.atomic():
            user = User.objects.create_user(
                username=email.split("@")[0],
                email=email,
                password=password1,
                role=CustomUser.ROLE_CUSTOMER,
                is_active=False,
                email_verified=False,
            )

        user.otp = generate_otp()
        user.otp_created_at = timezone.now()
        user.save()

        try:
            send_mail(
                subject="Verify your Kiddora account",
                message=(
                    "Hi,\n\n"
                    "Welcome to Kiddora.\n\n"
                    f"Your One-Time Password (OTP) is {user.otp}.\n"
                    f"This OTP is valid for {OTP_EXPIRY_MINUTES} minutes.\n\n"
                    "If you did not request this, please ignore this email.\n\n"
                    "Best regards,\n"
                    "Kiddora Team"
                ),
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[user.email],
                fail_silently=False
            )
        except Exception as e:
            print("EMAIL ERROR:", e)
            messages.error(request, "Failed to send OTP. Try again later.")
            return redirect("accounts:signup")

        request.session["verify_user_id"] = user.id
        return redirect("accounts:verify_signup_otp")
    return render(request,'accounts/auth/signup.html',{'error':error,'success':success})

@never_cache
def admin_login(request):
    # Already logged in as ADMIN
    if request.user.is_authenticated:
        if request.user.role == CustomUser.ROLE_ADMIN:
            return redirect("accounts:admin_dashboard")
        logout(request)
        return redirect("accounts:blocked")

    if request.method == "POST":
        email= request.POST.get("email")
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me")
        print("Identifier:", email)

        user = authenticate(request, username=email, password=password)

        if user is None:
            messages.error(request, "Invalid credentials")
            return render(request,"accounts/admin/admin_login.html",{"form_data":{"email":email}})

        if not user.is_active:
            messages.error(request, "Your account is blocked")
            return redirect("accounts:blocked")

        if user.role != CustomUser.ROLE_ADMIN:
            messages.error(request, "Access denied")
            return redirect("accounts:admin_login")

        if not user.email.endswith("@kiddora.com"):
            messages.error(request, "Admin email must be <name>@kiddora.com")
            return redirect("accounts:admin_login")

        login(request, user)

        response = redirect("accounts:admin_dashboard")

        if remember_me:
            response.set_cookie("remember_admin",email,max_age=7 * 24 * 60 * 60)
        
        return response
    return render(request, "accounts/admin/admin_login.html")

@never_cache
@admin_login_required
def admin_logout(request):
    role = request.user.role
    if role not in [CustomUser.ROLE_ADMIN]:
        return redirect("shopcore:home")
    logout(request)
    response = redirect("accounts:admin_login")
    # Remove role-specific remember-me cookie
    if role == CustomUser.ROLE_ADMIN:
        response.delete_cookie("remember_admin")
    return response