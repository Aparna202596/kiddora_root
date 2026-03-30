from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator
from accounts.decorators import admin_login_required
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect, get_object_or_404
from products.models import Inventory
from django.db.models import Q, Sum
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta

from shopcore.models import OrderItem, Order
from accounts.models import CustomUser
from payments.models import Payment

User = get_user_model()

#  ────────────────────────────────────────────────── ADMIN DASHBOARD ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_dashboard_view(request):
    today = timezone.now().date()

    # --- Date ranges ---
    ten_days_ago = today - timedelta(days=10)   # FIX: used for 10-day window (inclusive of today)
    last_30_days = today - timedelta(days=30)
    previous_30_days_start = today - timedelta(days=60)

    last_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    last_7_days_labels = [d.strftime("%d %b") for d in last_7_days]

    # --- Core KPIs ---
    total_orders = Order.objects.count()
    completed_orders = Order.objects.filter(order_status="DELIVERED").count()
    total_revenue = (
        Payment.objects.filter(payment_status='PAID')
        .aggregate(total=Sum('order__final_amount'))['total'] or 0
    )
    products_sold = OrderItem.objects.aggregate(total=Sum('quantity')).get("total") or 0
    total_stock = Inventory.objects.aggregate(total=Sum("quantity_available"))["total"] or 0
    low_stock_count = Inventory.objects.filter(quantity_available__lte=5).count()

    # --- Customer KPIs ---
    # Customers who joined today
    today_customers = CustomUser.objects.filter(
        role=CustomUser.ROLE_CUSTOMER,
        date_joined__date=today
    ).count()

    # FIX: include today in the 10-day window (lte=today, not lt=today)
    last_10_days_customers = CustomUser.objects.filter(
        role=CustomUser.ROLE_CUSTOMER,
        date_joined__date__gte=ten_days_ago,
        date_joined__date__lte=today          # was __lt=today — excluded today
    ).count()

    # New customers in the last 30 days (for the static card)
    new_customers = CustomUser.objects.filter(
        role=CustomUser.ROLE_CUSTOMER,
        date_joined__date__gte=last_30_days
    ).count()

    # Previous 30-day window for growth comparison
    previous_users = CustomUser.objects.filter(
        role=CustomUser.ROLE_CUSTOMER,
        date_joined__date__gte=previous_30_days_start,
        date_joined__date__lt=last_30_days
    ).count()

    # --- Customer growth (30-day) for static card ---
    if previous_users > 0:
        customer_growth_30days = round(
            ((new_customers - previous_users) / previous_users) * 100, 2
        )
    else:
        customer_growth_30days = 100 if new_customers > 0 else 0

    # --- Customer growth (10-day) for donut chart ---
    # Compare today's sign-ups against the daily average over the past 10 days
    average_last_10_days = last_10_days_customers / 10 if last_10_days_customers > 0 else 0

    if average_last_10_days > 0:
        customer_growth_10days = round(
            ((today_customers - average_last_10_days) / average_last_10_days) * 100, 2
        )
    else:
        customer_growth_10days = 100 if today_customers > 0 else 0

    # --- Products sold per day (last 7 days) ---
    products_sold_per_day = []
    for d in last_7_days:
        qty = (
            OrderItem.objects.filter(order__order_date__date=d)
            .aggregate(total=Sum("quantity"))["total"] or 0
        )
        products_sold_per_day.append(qty)

    # --- Recent orders filter ---
    filter_type = request.GET.get("filter", "monthly")
    if filter_type == "yearly":
        start_date = timezone.now() - timedelta(days=365)
    else:
        start_date = timezone.now() - timedelta(days=30)

    orders = Order.objects.filter(order_date__gte=start_date).order_by("-order_date")

    # --- Top performers ---
    top_products = (
        OrderItem.objects
        .values("variant__product__product_name")
        .annotate(total=Sum("quantity"))
        .order_by("-total")[:10]
    )
    top_categories = (
        OrderItem.objects
        .values("variant__product__subcategory__category__category_name")
        .annotate(total=Sum("quantity"))
        .order_by("-total")[:10]
    )
    top_brands = (
        OrderItem.objects
        .values("variant__product__brand")
        .annotate(total=Sum("quantity"))
        .order_by("-total")[:10]
    )

    context = {
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "total_revenue": total_revenue,
        "products_sold": products_sold,
        "total_stock": total_stock,
        "low_stock_count": low_stock_count,
        "new_customers": new_customers,                        # 30-day count  → static card
        "customer_growth_30days": customer_growth_30days,     # 30-day growth % → static card
        "customer_growth_10days": customer_growth_10days,     # 10-day growth % → donut chart
        "orders": orders,
        "top_products": top_products,
        "top_categories": top_categories,
        "top_brands": top_brands,
        "filter_type": filter_type,
        "last_7_days_labels": last_7_days_labels,
        "products_sold_per_day": products_sold_per_day,
    }
    return render(request, "accounts/admin/admin_dashboard.html", context)

#  ────────────────────────────────────────────────── SALES REPORT ──────────────────────────────────────────────────
@admin_login_required
def admin_sales_report(request):
    orders = Order.objects.filter(payment_status="PAID").order_by("-order_date")

    # Daily, Weekly, Yearly filters
    report_type = request.GET.get("type") 
    if report_type == "daily":
        start = timezone.now().date()
        orders = orders.filter(order_date__date=start)
    elif report_type == "weekly":
        start = timezone.now() - timedelta(days=7)
        orders = orders.filter(order_date__gte=start)
    elif report_type == "yearly":
        start = timezone.now() - timedelta(days=365)
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

    return render(request, "accounts/admin/admin_sales_report.html", {
        "orders": orders,
        "total_sales": total_sales,
        "total_orders": total_orders,
        "report_type": report_type,
        "start_date": start_date,
        "end_date": end_date,
    })

#  ────────────────────────────────────────────────── ADMIN USER LIST ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_user_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    users = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER, 
                                        is_deleted=False).order_by('-date_joined')
    if query:
        users = users.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        )

    if status == "active":
        users = users.filter(is_active=True)
    elif status == "blocked":
        users = users.filter(is_active=False)

    users = users.order_by("-date_joined") 

    paginator = Paginator(users, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    context = {"users": page_obj,"query": query, "status": status}
    return render(request, "accounts/admin/customer_list.html",context)

#  ────────────────────────────────────────────────── ADMIN - USER DETAIL ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_user_detail(request, user_id):
    user = get_object_or_404(
        CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER
    )
    orders = Order.objects.filter(user=user).order_by('-order_date')
    return render(request,"accounts/admin/customer_detail.html",{"user": user, "orders": orders},)


#   ────────────────────────────────────────────────── ADMIN - BLOCK USER ──────────────────────────────────────────────────
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

#   ────────────────────────────────────────────────── ADMIN - UNBLOCK USER ──────────────────────────────────────────────────
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

#  ────────────────────────────────────────────────── ADMIN - DELETE USER ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def delete_user_view(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)

    if request.user.id == user.id:
        messages.error(request, "You cannot delete your own account.")
        return redirect("accounts:admin_user_list")

    if request.method == "POST":
        # Soft delete only
        username = user.username or user.email
        user.delete()                     # This now calls the soft delete method
        messages.success(request, f"Customer {username} has been deleted successfully.")
        return redirect("accounts:admin_user_list")

    return render(request, "accounts/admin/delete_user.html", {"user": user})


