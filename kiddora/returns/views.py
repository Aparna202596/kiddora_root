from django.shortcuts import render
from accounts.decorators import user_login_required,admin_login_required
from django.shortcuts import render, redirect, get_object_or_404

from django.contrib import messages
from django.db import transaction
from datetime import timedelta
from django.utils import timezone
from .models import Return
from orders.models import Order, OrderItem
from products.models import Product
from django.db.models import Q

RETURN_WINDOW_DAYS = 10 

@user_login_required
def request_return(request, order_item_id):
    order_item = get_object_or_404(
        OrderItem,
        id=order_item_id,
        order__user=request.user
    )
    delivered_at = order_item.order.delivered_at
    if not delivered_at:
        messages.error(request, "Order not delivered yet. Cannot request return.")
        return redirect("orders:order_detail", order_item.order.id)

    if timezone.now() > delivered_at + timedelta(days=RETURN_WINDOW_DAYS):
        messages.error(request, f"Return period expired ({RETURN_WINDOW_DAYS} days).")
        return redirect("orders:order_detail", order_item.order.id)
    if Return.objects.filter(order_item=order_item).exists():
        messages.error(request, "Return already requested for this item.")
        return redirect("orders:order_detail", order_item.order.id)

    if request.method == "POST":
        reason = request.POST.get("reason")

        if not reason:
            messages.error(request, "Reason is required.")
            return redirect(request.path)

        Return.objects.create(
            order=order_item.order,
            order_item=order_item,
            product=order_item.product,
            reason=reason,
            status="REQUESTED"
        )

        messages.success(request, "Return request submitted.")
        return redirect("returns:return_status_view")

    return render(request, "returns/return_request.html", {
        "order_item": order_item
    })

@user_login_required
def return_status_view(request):
    returns = Return.objects.filter(order__user=request.user).order_by("-created_at")

    return render(request, "returns/return_status.html", {
        "returns": returns
    })

@user_login_required
def return_detail_view(request, return_id):
    return_obj = get_object_or_404(
        Return,
        id=return_id,
        order__user=request.user
    )

    return render(request, "returns/return_detail.html", {
        "return_obj": return_obj
    })

# @admin_login_required
# def admin_return_list(request):
#     returns = Return.objects.select_related(
#         "order", "product", "order_item"
#     ).order_by("-created_at")

#     return render(request, "returns/admin_return_list.html", {
#         "returns": returns
#     })

@admin_login_required
def admin_return_list(request):
    # Base queryset: latest returns first
    returns_qs = Return.objects.select_related("order", "product", "order_item").order_by("-created_at")

    # ----- FILTER BY STATUS -----
    status = request.GET.get("status")  # e.g., "APPROVED", "REJECTED"
    if status:
        returns_qs = returns_qs.filter(status=status)

    # ----- FILTER BY DATE RANGE -----
    start_date = request.GET.get("start_date")  # format: "YYYY-MM-DD"
    end_date = request.GET.get("end_date")
    if start_date and end_date:
        returns_qs = returns_qs.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )

    # ----- SEARCH BY ORDER ID or Product Name -----
    query = request.GET.get("q")
    if query:
        returns_qs = returns_qs.filter(
            Q(order__order_id__icontains=query) |
            Q(product__product_name__icontains=query)
        )

    # Pagination can be added here if needed (optional)
    # Example using Django Paginator:
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    paginator = Paginator(returns_qs, 20)  # 20 per page
    page = request.GET.get("page")
    try:
        returns = paginator.page(page)
    except PageNotAnInteger:
        returns = paginator.page(1)
    except EmptyPage:
        returns = paginator.page(paginator.num_pages)

    return render(request, "returns/admin_return_list.html", {
        "returns": returns,
        "status_filter": status,
        "start_date": start_date,
        "end_date": end_date,
        "query": query,
    })