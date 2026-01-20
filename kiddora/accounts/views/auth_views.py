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
from django.conf import settings

User = get_user_model()

#User_logout
@never_cache
@user_login_required
def user_logout(request):
    if request.user.is_authenticated:
        logout(request)
        response = redirect("store:anonymous_home")
        response.delete_cookie("remember_user")
        return response
    return redirect("store:anonymous_home")

#User_login
@never_cache
def user_login(request):
    if request.user.is_authenticated:
        return redirect("store:home")
    remembered_user = request.COOKIES.get("remember_user", "")
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me")
        user = authenticate(request, email=username, password=password)
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
                response.set_cookie("remember_user",username,max_age=7 * 24 * 60 * 60,)
            else:
                response.delete_cookie("remember_user")
            return response
        messages.error(request, "Invalid username or password")
    return render(request,"accounts/auth/login.html",{"remembered_user": remembered_user},)

#Signup
@never_cache
def signup_page(request):
    if request.user.is_authenticated:
        return redirect('store:home')
    error=''
    success=''
    if request.method=='POST':
        username=request.POST['username']
        email=request.POST['email']
        password1=request.POST['password1']
        password2=request.POST['password2']
        if User.objects.filter(username__iexact=username).exists():
            messages.error(request,"Username already exists!")
            return redirect("accounts:signup")
        elif len(username)<6:
            messages.error='Username atleast contain 6 characters, Retry!'
            return redirect("accounts:signup")
        elif re.search(r'\s',username):
            messages.error(request,"Username cannot contain spaces!")
            return redirect("accounts:signup")
        elif User.objects.filter(email=email).exists():
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
            username=username,
            email=email,
            password=password1,
            role=CustomUser.ROLE_CUSTOMER,
            is_active=False,
            email_verified=False,
        )
        otp=generate_otp()
        user.otp = otp
        user.otp_created_at = timezone.now()
        user.save()

        send_mail(
            subject="Verify your Kiddora account",
            message=f"Your OTP is {otp}. It is valid for 2 minutes.",
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
        )
        request.session["verify_user_id"] = user.id
        return redirect("accounts:verify_otp")
        # else:
        #     #User.objects.create_user(username=username, email=email, password=password1)
        #     success = 'Account created successfully. Please log in'
    return render(request,'accounts/auth/signup.html',{'error':error,'success':success})

#home page
@never_cache
@user_login_required
def home_page(request):
    if not request.user.is_authenticated:
        return redirect('account:login')
    # if request.user.is_superuser:
    #     return redirect('admin_page')
    return render(request, 'store/home.html')

@never_cache
def admin_staff_login(request):
    # If already logged in, redirect based on role
    if request.user.is_authenticated:
        if request.user.role == CustomUser.ROLE_ADMIN:
            return redirect("admin_page")
        if request.user.role == CustomUser.ROLE_STAFF:
            return redirect("staff_dashboard")

    if request.method == "POST":
        identifier = request.POST.get("username") or request.POST.get("email")
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me")

        # Authenticate user
        user = authenticate(request, username=identifier, password=password)

        if not user:
            messages.error(request, "Invalid credentials")
            return redirect("accounts:admin_staff_login")

        # Block inactive accounts
        if not user.is_active:
            messages.error(request, "Your account is blocked")
            return redirect("accounts:blocked")

        # ROLE CHECK
        if user.role not in [CustomUser.ROLE_ADMIN, CustomUser.ROLE_STAFF]:
            messages.error(request, "Access denied")
            return redirect("accounts:admin_staff_login")

        # Admin domain validation
        if user.role == CustomUser.ROLE_ADMIN and not user.email.endswith("@kiddora.com"):
            messages.error(
                request,
                "Admin email must be <admin_name>@kiddora.com",
            )
            return redirect("accounts:admin_staff_login")

        # LOGIN
        login(request, user)

        # Remember-me cookie
        response = (
            redirect("admin_page")
            if user.role == CustomUser.ROLE_ADMIN
            else redirect("staff_dashboard")
        )

        if remember_me:
            cookie_name = (
                "remember_admin"
                if user.role == CustomUser.ROLE_ADMIN
                else "remember_staff"
            )
            response.set_cookie(
                cookie_name,
                identifier,
                max_age=7 * 24 * 60 * 60,
            )

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
    response = redirect("accounts:admin_staff_login")
    # Remove role-specific remember-me cookie
    if role == CustomUser.ROLE_ADMIN:
        response.delete_cookie("remember_admin")
    elif role == CustomUser.ROLE_STAFF:
        response.delete_cookie("remember_staff")
    return response


#admin add user
@never_cache
@admin_login_required
def admin_add(request):
    # if request.user.role != CustomUser.ROLE_ADMIN:
    #     return redirect("store:home")
    error = ""
    success = ""
    if request.method == "POST":
        username = request.POST["staffname"]
        email = request.POST["email"]
        password = request.POST["password"]
        c_password = request.POST["c_password"]
        if User.objects.filter(username__iexact=username).exists():
            error = "Staff already exists."
        elif len(username) < 6:
            error = "Username must be at least 6 characters."
        elif re.search(r"\s", username):
            error = "Username cannot contain spaces."
        elif User.objects.filter(email=email).exists():
            error = "Email already exists."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != c_password:
            error = "Passwords do not match."
        else:
            User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role=CustomUser.ROLE_STAFF,
                is_staff=True,
                is_active=True,)
            success = "Staff user created successfully."
    return render(request,"accounts/auth/admin_add.html",{"error": error, "success": success},)

#admin page
@never_cache
@admin_login_required
def admin_page(request):
    if request.user.role != CustomUser.ROLE_ADMIN:
        return redirect("store:home")
    query = request.GET.get("q", "")
    staff_users = User.objects.filter(role=CustomUser.ROLE_STAFF)
    if query:
        staff_users = staff_users.filter(username__icontains=query)
    return render(request,"accounts/admin/admin_dashboard.html",{"users": staff_users,"query": query,},)

# ADMIN EDIT
@never_cache
@admin_login_required
def admin_edit(request, id):
    if request.user.role != CustomUser.ROLE_ADMIN:
        return redirect("store:home")
    user = get_object_or_404(User, id=id, role=CustomUser.ROLE_STAFF)
    error = ""
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]
        if User.objects.filter(username=username).exclude(id=user.id).exists():
            error = "Username already exists."
        elif len(username) < 6 or re.search(r"\s", username):
            error = "Username must be at least 6 characters and contain no spaces."
        elif User.objects.filter(email=email).exclude(id=user.id).exists():
            error = "Email already exists."
        else:
            user.username = username
            user.email = email
            user.save()
            return redirect("admin_page")
    return render(request,"staff_edit.html",{"user": user, "error": error},)

# ADMIN  DELETE
@never_cache
@admin_login_required
def admin_delete(request, id):
    if request.user.role != CustomUser.ROLE_ADMIN:
        return redirect("store:home")
    user = get_object_or_404(User, id=id, role=CustomUser.ROLE_STAFF)
    if request.method == "POST":
        user.delete()
    return redirect("admin_page")





@never_cache
@staff_login_required
def staff_dashboard(request):
    if request.user.role != CustomUser.ROLE_STAFF:
        return redirect("store:home")
    return render(request,"admin/staff_dashboard.html",{"staff": request.user,},)