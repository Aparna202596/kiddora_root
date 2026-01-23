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
from products.models import Inventory
from accounts.decorators import admin_login_required,user_login_required
from django.contrib.auth import get_user_model
from django.views.decorators.cache import never_cache
from accounts.decorators import user_login_required,admin_login_required
import re
from django.db.models import Sum, Count
from orders.models import Order
from django.utils.timezone import now

User = get_user_model()

@never_cache
@admin_login_required
def admin_dashboard_view(request):
    today = now().date()
    last_30_days = today - timedelta(days=30)
    previous_30_days = today - timedelta(days=60)
    
    total_orders = Order.objects.count()
    completed_orders = Order.objects.filter(order_status="DELIVERED").count()
    
    total_revenue = Payment.objects.filter(payment_status='PAID').aggregate(total=Sum('order__final_amount'))['total'] or 0
    
    products_sold = OrderItem.objects.aggregate(total=Sum('quantity')).get("total") or 0
    
    total_stock = Inventory.objects.aggregate(total=Sum("stock")).get("total") or 0
    
    low_stock_count = Inventory.objects.filter(stock__lte=5).count()

    new_customers = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER,date_joined__gte=last_30_days).count()
    
    current_users = new_customers
    
    previous_users = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER,date_joined__gte=previous_30_days,date_joined__lt=last_30_days).count()
    
    if previous_users > 0:
        customer_growth = round(((current_users - previous_users) / previous_users) * 100, 2)
    else:
        customer_growth = 100 if current_users > 0 else 0
    context = {
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "total_revenue": total_revenue,
        "products_sold": products_sold,
        "total_stock": total_stock,
        "low_stock_count": low_stock_count,
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
