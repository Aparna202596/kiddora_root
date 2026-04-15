from accounts.decorators import admin_login_required
from accounts.models import CustomUser
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from payments.models import Payment
from shopcore.models import Order, OrderItem

User = get_user_model()


#  ────────────────────────────────────────────────── ADMIN USER LIST ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_user_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    users = CustomUser.objects.filter(
        role=CustomUser.ROLE_CUSTOMER, is_deleted=False
    ).order_by("-date_joined")
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )

    if status == "active":
        users = users.filter(is_active=True)
    elif status == "blocked":
        users = users.filter(is_active=False)

    users = users.order_by("-date_joined")

    paginator = Paginator(users, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    context = {"users": page_obj, "query": query, "status": status}
    return render(request, "accounts/admin/customer_list.html", context)


#  ────────────────────────────────────────────────── ADMIN - USER DETAIL ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_user_detail(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    orders = Order.objects.filter(user=user).order_by("-order_date")
    return render(
        request,
        "accounts/admin/customer_detail.html",
        {"user": user, "orders": orders},
    )


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
        user.delete()  # This now calls the soft delete method
        messages.success(request, f"Customer {username} has been deleted successfully.")
        return redirect("accounts:admin_user_list")

    return render(request, "accounts/admin/delete_user.html", {"user": user})
