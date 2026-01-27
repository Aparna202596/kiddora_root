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
    orders = Order.objects.filter(created_at__gte=start_date)
    top_products = (OrderItem.objects.values("variant__product__product_name").annotate(total=Sum("quantity")).order_by("-total")[:10])
    top_categories = (OrderItem.objects.values("variant__product__subcategory__category__category_name").annotate(total=Sum("quantity")).order_by("-total")[:10])
    top_brands = (OrderItem.objects.values("variant__product__brand").annotate(total=Sum("quantity")).order_by("-total")[:10])

    if previous_users > 0:
        customer_growth = round(((current_users - previous_users) / previous_users) * 100, 2)
    else:
        customer_growth = 100 if current_users > 0 else 0
    
    filter_type = request.GET.get("filter", "monthly")

    if filter_type == "yearly":
        start_date = now() - timedelta(days=365)
    else:
        start_date = now() - timedelta(days=30)

    context = {
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "total_revenue": total_revenue,
        "products_sold": products_sold,
        "total_stock": total_stock,
        "low_stock_count": low_stock_count,
        "new_customers": new_customers,
        "customer_growth": customer_growth,
        "orders":orders,
        "top_products": top_products,
        "top_categories": top_categories,
        "top_brands": top_brands,
        "filter_type": filter_type,
    }
    return render(request, "accounts/admin/admin_dashboard.html", context)

# ADMIN USER LIST
@never_cache
@admin_login_required
def admin_user_list(request):
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
def admin_block_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    if request.method == "POST":
        user.is_active = False
        user.save()
        messages.success(request, f"{user.username} has been blocked")
        return redirect("accounts:admin_user_list")
    return render(request, "accounts/admin/user_confirm_block.html", {"user": user})

# UNBLOCK USER
@never_cache
@admin_login_required
def admin_unblock_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    if request.method == "POST":
        user.is_active = True
        user.save()
        messages.success(request, f"{user.username} has been unblocked")
        return redirect("accounts:admin_user_list")
    return render(request, "accounts/admin/user_confirm_unblock.html", {"user": user})

@never_cache
@admin_login_required
def delete_user_view(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    if request.user.id == user.id:
        messages.error(request, "You cannot delete your own account.")
        return redirect("accounts:admin_user_list")
    if request.method == "POST":
        username = user.username
        user.delete()
        messages.success(request, f"User {username} has been deleted successfully.")
        return redirect("accounts:admin_user_list")
    return render(request, "accounts/admin/delete_user.html", {"user": user})

@never_cache
@admin_login_required
def admin_user_detail(request, user_id):
    user = get_object_or_404(
        CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER
    )
    return render(request,"accounts/admin/customer_detail.html",{"user": user})

@admin_login_required
def admin_sales_report(request):
    orders = Order.objects.all().order_by("-order_date")

    # Daily, Weekly, Yearly filters
    report_type = request.GET.get("type")  # "daily", "weekly", "yearly"
    if report_type == "daily":
        start = now().date()
        orders = orders.filter(order_date__date=start)
    elif report_type == "weekly":
        start = now() - timedelta(days=7)
        orders = orders.filter(order_date__gte=start)
    elif report_type == "yearly":
        start = now() - timedelta(days=365)
        orders = orders.filter(order_date__gte=start)

    # Custom date range
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    if start_date and end_date:
        orders = orders.filter(order_date__date__gte=start_date,
                                order_date__date__lte=end_date)

    # Aggregates
    total_sales = orders.aggregate(total=Sum("final_amount"))["total"] or 0
    total_orders = orders.count()

    return render(request, "wallet/admin_sales_report.html", {
        "orders": orders,
        "total_sales": total_sales,
        "total_orders": total_orders,
        "report_type": report_type,
        "start_date": start_date,
        "end_date": end_date,
    })