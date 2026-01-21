from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from accounts.models import CustomUser
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from datetime import timedelta
from django.utils.timezone import now
from accounts.models import CustomUser
from orders.models import Order, OrderItem
from payments.models import Payment
from accounts.decorators import admin_login_required,user_login_required
from django.contrib.auth import get_user_model
from django.views.decorators.cache import never_cache
from accounts.decorators import user_login_required,admin_login_required,staff_login_required
import re

User = get_user_model()

@never_cache
@admin_login_required
def admin_dashboard_view(request):
    today = now()
    last_30_days = today - timedelta(days=30)
    previous_30_days = today - timedelta(days=60)
    total_orders = Order.objects.count()
    total_revenue = Payment.objects.filter(payment_status='PAID').aggregate(total=Sum('order__final_amount'))['total'] or 0
    products_sold = OrderItem.objects.aggregate(total=Sum('quantity'))['total'] or 0
    new_customers = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER,date_joined__gte=last_30_days).count()
    current_users = new_customers
    previous_users = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER,
        date_joined__gte=previous_30_days,
        date_joined__lt=last_30_days).count()
    if previous_users > 0:
        customer_growth = round(((current_users - previous_users) / previous_users) * 100, 2)
    else:
        customer_growth = 100 if current_users > 0 else 0
    context = {
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "total_sales": total_revenue,
        "products_sold": products_sold,
        "new_customers": new_customers,
        "customer_growth": customer_growth,
    }
    return render(request, "accounts/admin/admin_dashboard.html", context)

# ADMIN USER LIST
@never_cache
@admin_login_required
def customer_list(request):
    query = request.GET.get("q", "").strip()
    users = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER).order_by('-date_joined')
    if query:
        users = users.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        )
    users = users.order_by("-date_joined")
    paginator = Paginator(users, 10)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    context = {"users": page_obj,"query": query,}
    return render(request, "accounts/admin/customer_list.html",context)

# BLOCK USER
@never_cache
@admin_login_required
def block_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    if request.method == "POST":
        user.is_active = False
        user.save()
        messages.success(request, f"{user.username} has been blocked")
        return redirect("accounts:customer_list")
    return render(request, "accounts/admin/user_confirm_block.html", {"user": user})

# UNBLOCK USER
@never_cache
@admin_login_required
def unblock_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    if request.method == "POST":
        user.is_active = True
        user.save()
        messages.success(request, f"{user.username} has been unblocked")
        return redirect("accounts:customer_list")
    return render(request, "accounts/admin/user_confirm_unblock.html", {"user": user})

@never_cache
@admin_login_required
def delete_user_view(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    if request.user.id == user.id:
        messages.error(request, "You cannot delete your own account.")
        return redirect("accounts:customer_list")
    if request.method == "POST":
        username = user.username
        user.delete()
        messages.success(request, f"User {username} has been deleted successfully.")
        return redirect("accounts:customer_list")
    return render(request, "accounts/admin/delete_user.html", {"user": user})

@admin_login_required
def staff_list(request):
    query = request.GET.get("q","").strip()
    users = CustomUser.objects.filter(role=CustomUser.ROLE_STAFF).order_by('-date_joined')
    if query:
        users = users.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        )
            # Q(email__icontains=query) |
            # Q(full_name__icontains=query) |
            # Q(phone__icontains=query)
    users = users.order_by("-date_joined")
    paginator = Paginator(users, 10)
    page_number = request.GET.get("page",1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'accounts/admin/staff_list.html', {"users": page_obj,"query": query})

#admin add user
@never_cache
@admin_login_required
def admin_add(request):
    error = ""
    success = ""
    if request.method == "POST":
        username = request.POST.get("staffname", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password")
        c_password = request.POST.get("c_password")
        if re.search(r"\s", email):
            error = "Email cannot contain spaces."
        elif User.objects.filter(username__iexact=username).exists():
            error = "Staff already exists."
        elif len(username) < 6 or re.search(r"\s", username):
            error = "Username must be at least 6 characters and contain no spaces."
        elif User.objects.filter(email__iexact=email).exists():
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
                is_active=True,
            )
            success = "Staff user created successfully."
    return render(request,"accounts/auth/admin_add.html",{"error": error, "success": success},)

# ADMIN EDIT
@never_cache
@admin_login_required
def admin_edit(request, user_id):
    if request.user.role != CustomUser.ROLE_ADMIN:
        return redirect("accounts:staff_dashboard")
    user = get_object_or_404(User, id=user_id, role=CustomUser.ROLE_STAFF)
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
            return redirect("accounts:staff_list")
    return render(request,"accounts/admin/staff_edit.html",{"user": user, "error": error},)

# ADMIN  DELETE
@never_cache
@admin_login_required
def admin_delete(request, user_id):
    if request.user.role != CustomUser.ROLE_ADMIN:
        return redirect("store:home")
    user = get_object_or_404(User, id=user_id, role=CustomUser.ROLE_STAFF)
    if request.method == "POST":
        user.delete()
    return redirect("accounts:staff_list")

@never_cache
@staff_login_required
def staff_dashboard(request):
    if request.user.role != CustomUser.ROLE_STAFF:
        return redirect("accounts:admin_dashboard")
    return render(request,"accounts/admin/staff_dashboard.html",{"staff": request.user,},)

@never_cache
def blocked(request):
    return render(request, "accounts/blocked.html")