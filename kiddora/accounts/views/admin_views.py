from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from accounts.models import CustomUser
from django.core.paginator import Paginator
from django.db.models import Q
from accounts.decorators import admin_login_required


# ------------------------------
# ADMIN USER LIST (SEARCH + PAGINATION)
# ------------------------------
@admin_login_required
def user_list(request):
    query = request.GET.get("q", "")
    users = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER)

    if query:
        users = users.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        )

    users = users.order_by("-date_joined")

    # Pagination
    paginator = Paginator(users, 10)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    return render(request, "accounts/admin/user_list.html", {
        "users": page_obj,
        "query": query
    })


# ------------------------------
# BLOCK USER
# ------------------------------
@admin_login_required
def block_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    if request.method == "POST":
        user.is_active = False
        user.save()
        messages.success(request, f"{user.username} has been blocked")
        return redirect("accounts:admin_user_list")

    return render(request, "accounts/admin/user_confirm_block.html", {"user": user})


# ------------------------------
# UNBLOCK USER
# ------------------------------
@admin_login_required
def unblock_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id, role=CustomUser.ROLE_CUSTOMER)
    if request.method == "POST":
        user.is_active = True
        user.save()
        messages.success(request, f"{user.username} has been unblocked")
        return redirect("accounts:admin_user_list")

    return render(request, "accounts/admin/user_confirm_unblock.html", {"user": user})
