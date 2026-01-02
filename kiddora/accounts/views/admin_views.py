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

# ADMIN USER LIST
@admin_login_required
def admin_user_list(request):
    query = request.GET.get("q", "").strip()
    users = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER)

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

    context = {
        "users": page_obj,
        "query": query,
    }

    return render(request, "accounts/admin/user_list.html",context)

# BLOCK USER
@admin_login_required
def block_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    if request.method == "POST":
        user.is_active = False
        user.save()
        messages.success(request, f"{user.username} has been blocked")
        return redirect("accounts:admin_user_list")

    return render(request, "accounts/admin/user_confirm_block.html", {"user": user})

# UNBLOCK USER
@admin_login_required
def unblock_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    if request.method == "POST":
        user.is_active = True
        user.save()
        messages.success(request, f"{user.username} has been unblocked")
        return redirect("accounts:admin_user_list")

    return render(request, "accounts/admin/user_confirm_unblock.html", {"user": user})

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

@admin_login_required
def user_management_view(request):
    search_query = request.GET.get('q', '').strip()

    users = CustomUser.objects.filter(
        role=CustomUser.ROLE_CUSTOMER
    ).order_by('-date_joined')

    if search_query:
        users = users.filter(
            Q(email__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(phone__icontains=search_query)
        )

    paginator = Paginator(users, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/admin/customer_list.html', {
        'users': page_obj,
        'search_query': search_query
    })

# @admin_login_required
# def block_unblock_user_view(request, user_id):
#     user = get_object_or_404(CustomUser,id=user_id,role=CustomUser.ROLE_CUSTOMER)

#     if request.user.id == user.id:
#         messages.error(request, "You cannot block your own account.")
#         return redirect('accounts:user_list')

#     if request.method == 'POST':
#         user.is_active = not user.is_active
#         user.save()

#         status = "blocked" if not user.is_active else "unblocked"
#         messages.success(request, f"User has been {status} successfully.")

#     return redirect('accounts:admin_user_management')