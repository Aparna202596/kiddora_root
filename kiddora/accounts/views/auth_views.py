from accounts.decorators import user_login_required,admin_login_required,staff_login_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib import messages
from accounts.models import CustomUser
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from accounts.utils import generate_otp
import re
from django.db.models import Q
from django.conf import settings

User = get_user_model()
OTP_EXPIRY_MINUTES=5
#User_logout
@never_cache
def user_logout(request):
    logout(request)
    request.session.flush()
    response = redirect("store:anonymous_home")
    response.delete_cookie("remember_user")
    return response

#User_login
@never_cache
def user_login(request):
    if request.user.is_authenticated and request.user.role == CustomUser.ROLE_CUSTOMER:
        return redirect("store:home")
    
    remembered_user = request.COOKIES.get("remember_user", "")

    if request.method == "POST":
        identifier = request.POST.get("identifier")
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me")

        try:
            user_obj=User.objects.get(Q(email__iexact=identifier) | Q(username__iexact=identifier))
            user = authenticate(request, email=user_obj.email, password=password)
        except User.DoesNotExist:
            user=None

        if user and user.role == CustomUser.ROLE_CUSTOMER:
            if not user.email_verified:
                messages.error(request, "Please verify your email first")
                return redirect("accounts:login")
            
            elif not user.is_active:
                messages.error(request, "Your account is blocked")
                return redirect("accounts:blocked")
            
            login(request, user)
            response = redirect("store:home")

            if remember_me:
                response.set_cookie("remember_user",identifier,max_age=7 * 24 * 60 * 60)
            else:
                response.delete_cookie("remember_user")
            return response
        
        messages.error(request, "Invalid username or password")
    return render(request,"accounts/auth/login.html",{"remembered_user": remembered_user},)

#Signup
@never_cache
def signup_page(request):
    error=''
    success=''
    if request.method=='POST':
        #username=request.POST['username']
        username=request.POST.get('username','').strip()
        email=request.POST['email']
        password1=request.POST['password1']
        password2=request.POST['password2']
        if User.objects.filter(username__iexact=username).exists():
            messages.error(request,"Username already exists!")
            return redirect("accounts:signup")
        elif len(username)<6:
            messages.error(request,"Username atleast contain 6 characters, Retry!")
            return redirect("accounts:signup")
        elif re.search(r'\s',username):
            messages.error(request,"Username cannot contain spaces!")
            return redirect("accounts:signup")
        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request,"Email already exists, Try new!")
            return redirect("accounts:signup")
        elif len(password1) < 6:
            messages.error(request,"Password must be at least 6 characters, Retry!")
            return redirect("accounts:signup")
        elif re.search(r'\s', password1):
            messages.error(request,"Password cannot contain spaces!")
            return redirect("accounts:signup")
        elif password1 != password2:
            messages.error(request,"Passwords do not match!")
            return redirect("accounts:signup")
        
        user = User.objects.create_user(
            #username=username,
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
                message=f"Your OTP is {user.otp}. It is valid for {OTP_EXPIRY_MINUTES} minutes.",
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[user.email],
                fail_silently=False
            )
        except Exception as e:
            print("EMAIL ERROR:", e)
            messages.error(request, "Failed to send OTP. Try again later.")
            return redirect("accounts:signup")
        
        request.session["verify_user_id"] = user.id
        return redirect("accounts:verify_otp")
    return render(request,'accounts/auth/signup.html',{'error':error,'success':success})

@never_cache
def admin_staff_login(request):
    # If already logged in, redirect based on role
    if request.user.is_authenticated:
        if request.user.role == CustomUser.ROLE_ADMIN:
            return redirect("accounts:admin_dashboard")
        if request.user.role == CustomUser.ROLE_STAFF:
            return redirect("accounts:staff_dashboard")
    if request.method == "POST":
        identifier = request.POST.get("username") or request.POST.get("email")
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me")
        # Authenticate user
        user = authenticate(request, username=identifier, password=password)
        if not user:
            messages.error(request, "Invalid credentials")
            return redirect("accounts:auth_login")
        # Block inactive accounts
        if not user.is_active:
            messages.error(request, "Your account is blocked")
            return redirect("accounts:blocked")
        # ROLE CHECK
        if user.role not in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_STAFF]:
            messages.error(request, "Access denied")
            return redirect("accounts:auth_login")
        # Admin domain validation
        if user.role == CustomUser.ROLE_ADMIN and not user.email.endswith("@kiddora.com"):
            messages.error(
                request,
                "Admin email must be <admin_name>@kiddora.com",
            )
            return redirect("accounts:auth_login")
        # LOGIN
        login(request, user)
        # Remember-me cookie
        response = (redirect("accounts:admin_dashboard") if user.role == CustomUser.ROLE_ADMIN else redirect("accounts:staff_dashboard"))
        if remember_me:
            cookie_name = ("remember_admin"if user.role == CustomUser.ROLE_ADMIN else "remember_staff")
            response.set_cookie(cookie_name,identifier, max_age=7 * 24 * 60 * 60,)
        return response
    return render(request, "accounts/auth/admin_staff_login.html")

@never_cache
@login_required
def admin_staff_logout(request):
    role = request.user.role
    # Only admin or staff can access this logout
    if role not in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_STAFF]:
        return redirect("store:home")
    logout(request)
    response = redirect("accounts:auth_login")
    # Remove role-specific remember-me cookie
    if role == CustomUser.ROLE_ADMIN:
        response.delete_cookie("remember_admin")
    elif role == CustomUser.ROLE_STAFF:
        response.delete_cookie("remember_staff")
    return response
    