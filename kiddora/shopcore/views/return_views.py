from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from accounts.decorators import user_login_required, admin_login_required
from shopcore.models import *


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
        messages.error(request, "Order not delivered yet.")
        return redirect("orders:order_detail", order_item.order.id)

    if timezone.now() > delivered_at + timedelta(days=RETURN_WINDOW_DAYS):
        messages.error(request, f"Return window expired ({RETURN_WINDOW_DAYS} days).")
        return redirect("orders:order_detail", order_item.order.id)

    if Return.objects.filter(order_item=order_item).exists():
        messages.error(request, "Return already requested for this item.")
        return redirect("orders:order_detail", order_item.order.id)

    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "Return reason is required.")
            return redirect(request.path)

        Return.objects.create(
            order=order_item.order,
            order_item=order_item,
            product=order_item.product,
            reason=reason,
            status=Return.STATUS_REQUESTED
        )

        messages.success(request, "Return request submitted successfully.")
        return redirect("returns:return_status_view")

    return render(request, "returns/return_request.html", {
        "order_item": order_item
    })
# @user_login_required
# def request_order_return(request, order_id):
#     order = get_object_or_404(Order, order_id=order_id, user=request.user)
#     if request.method == "POST":
#         reason = request.POST.get("reason")
#         OrderReturn.objects.create(
#             order=order,
#             reason=reason,
#             status="RETURN_REQUESTED"
#         )
#         return redirect("orders:order_detail", order_id=order.order_id)
#     return render(request, "returns/request_return.html", {"order": order})
@user_login_required
def return_status_view(request):
    returns = Return.objects.filter(
        order__user=request.user
    ).order_by("-created_at")

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

@admin_login_required
def admin_return_list(request):
    returns_qs = Return.objects.select_related(
        "order", "order_item", "product"
    ).order_by("-created_at")

    status = request.GET.get("status")
    if status:
        returns_qs = returns_qs.filter(status=status)

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    if start_date and end_date:
        returns_qs = returns_qs.filter(
            created_at__date__range=[start_date, end_date]
        )

    query = request.GET.get("q")
    if query:
        returns_qs = returns_qs.filter(
            Q(order__order_id__icontains=query) |
            Q(product__product_name__icontains=query)
        )

    paginator = Paginator(returns_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "returns/admin_return_list.html", {
        "returns": page_obj,
        "status_filter": status,
        "query": query,
        "start_date": start_date,
        "end_date": end_date
    })

@admin_login_required
@transaction.atomic
def admin_verify_return(request, return_id):
    return_obj = get_object_or_404(Return, id=return_id)

    if return_obj.locked:
        messages.error(request, "This return is already processed.")
        return redirect("returns:admin_return_list")

    order_item = return_obj.order_item
    product = return_obj.product
    user = return_obj.order.user

    if request.method == "POST":
        action = request.POST.get("action")

        # ---------------- APPROVE RETURN ----------------
        if action == "approve":
            return_obj.status = "APPROVED"
            return_obj.save()

            # 🔁 AUTO STOCK RESTORE
            product.stock += order_item.quantity
            product.save(update_fields=["stock"])

            messages.success(request, "Return approved and stock restored.")

        # ---------------- REJECT RETURN ----------------
        elif action == "reject":
            return_obj.status = "REJECTED"
            return_obj.save()

            messages.success(request, "Return rejected.")

        # ---------------- REFUND ----------------
        elif action == "refund":
            wallet, _ = Wallet.objects.get_or_create(user=user)

            refund_amount = order_item.price * order_item.quantity

            wallet.balance += refund_amount
            wallet.save(update_fields=["balance"])

            return_obj.refund_amount = refund_amount
            return_obj.status = "REFUNDED"
            return_obj.locked = True
            return_obj.save()

            messages.success(request, f"₹{refund_amount} refunded to wallet.")

        return redirect("returns:admin_return_list")

    return render(request, "returns/admin_return_verify.html", {
        "return_obj": return_obj
    })

from django.db.models import Count, Sum, Avg
from django.utils.timezone import now
from datetime import timedelta

@admin_login_required
def return_analytics_dashboard(request):
    # ---------------- OVERALL COUNTS ----------------
    total_returns = Return.objects.count()

    status_breakdown = (
        Return.objects
        .values("status")
        .annotate(count=Count("id"))
    )

    # ---------------- REFUND METRICS ----------------
    refund_stats = Return.objects.filter(status="REFUNDED").aggregate(
        total_refund=Sum("refund_amount"),
        avg_refund=Avg("refund_amount")
    )

    # ---------------- TOP RETURNED PRODUCTS ----------------
    top_products = (
        Return.objects
        .values("product__product_name")
        .annotate(return_count=Count("id"))
        .order_by("-return_count")[:5]
    )

    # ---------------- RETURNS LAST 7 DAYS ----------------
    last_7_days = now() - timedelta(days=7)

    daily_returns = (
        Return.objects
        .filter(created_at__gte=last_7_days)
        .extra(select={'day': "DATE(created_at)"})
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )

    return render(request, "returns/admin_return_dashboard.html", {
        "total_returns": total_returns,
        "status_breakdown": status_breakdown,
        "refund_stats": refund_stats,
        "top_products": top_products,
        "daily_returns": daily_returns,
    })
