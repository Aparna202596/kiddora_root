# shopcore/views/return_views.py
# Handles: user return requests, admin return list/detail/approve/reject.

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from accounts.decorators import admin_login_required
from products.utils.pagination import paginate_queryset
from shopcore.models import Order, OrderItem, Return


# ─────────────────────────────────────────────────────────────────────────────
# USER: REQUEST RETURN
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
@transaction.atomic
def request_return(request, order_id, item_id):
    """
    Only allowed when:
      - The parent order is DELIVERED.
      - The OrderItem is ACTIVE (not already cancelled or returned).
      - No prior return request exists for this item.
    Reason is mandatory per the project spec.
    """
    order      = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_item = get_object_or_404(
        OrderItem, id=item_id, order=order, item_status="ACTIVE"
    )

    # Guard: only deliverd orders can be returned
    if order.order_status != "DELIVERED":
        messages.error(
            request,
            "Returns can only be requested after the order has been delivered.",
        )
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    # Guard: already has a return request
    if hasattr(order_item, "return_request"):
        messages.info(request, "A return request already exists for this item.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "A reason is required for a return request.")
            return render(
                request,
                "orders/request_return.html",
                {"order": order, "order_item": order_item},
            )

        Return.objects.create(
            order_item = order_item,
            reason     = reason,
            status     = "REQUESTED",
        )

        # Mark the item as return-requested
        order_item.item_status = "RETURN_REQUESTED"
        order_item.save()

        messages.success(
            request,
            f"Return request submitted for "
            f"'{order_item.variant.product.product_name}'. "
            "We will review it shortly.",
        )
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    return render(
        request,
        "orders/request_return.html",
        {"order": order, "order_item": order_item},
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN: RETURN LIST
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_return_list(request):
    """List all return requests with search and status filter."""
    from django.db.models import Q

    search   = request.GET.get("search", "").strip()
    status_f = request.GET.get("status", "").strip()

    returns = Return.objects.select_related(
        "order_item",
        "order_item__order",
        "order_item__order__user",
        "order_item__variant",
        "order_item__variant__product",
    ).order_by("-created_at")

    if search:
        returns = returns.filter(
            Q(order_item__order__order_id__icontains=search)
            | Q(order_item__order__user__email__icontains=search)
            | Q(order_item__variant__product__product_name__icontains=search)
        )

    if status_f:
        returns = returns.filter(status=status_f)

    page_obj = paginate_queryset(request, returns, 20)

    context = {
        "page_obj":      page_obj,
        "search":        search,
        "status_f":      status_f,
        "status_choices": Return.STATUS_CHOICES,
    }
    return render(request, "returns/admin_return_list.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN: RETURN DETAIL
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_return_detail(request, return_id):
    ret = get_object_or_404(
        Return.objects.select_related(
            "order_item",
            "order_item__order",
            "order_item__order__user",
            "order_item__order__address",
            "order_item__variant__product",
            "order_item__variant__color",
            "order_item__variant__age_group",
        ),
        id=return_id,
    )
    return render(
        request,
        "returns/admin_return_detail.html",
        {"ret": ret},
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN: APPROVE RETURN
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
@transaction.atomic
def admin_approve_return(request, return_id):
    """
    Approve a return request:
      - Sets Return.status = APPROVED.
      - Sets OrderItem.item_status = RETURN_APPROVED.
      - Restores inventory (quantity_available += qty, quantity_sold -= qty).
      - Admin remark is optional.
    """
    if request.method != "POST":
        return redirect("shopcore:admin_return_detail", return_id=return_id)

    ret = get_object_or_404(Return, id=return_id, status="REQUESTED")

    remark = request.POST.get("admin_remark", "").strip()

    # Restore stock
    order_item = ret.order_item
    try:
        inv = order_item.variant.inventory
        inv.quantity_available += order_item.quantity
        inv.quantity_sold       = max(0, inv.quantity_sold - order_item.quantity)
        inv.save()
    except Exception:
        pass

    # Update OrderItem
    order_item.item_status = "RETURN_APPROVED"
    order_item.save()

    # Update Return
    ret.status       = "APPROVED"
    ret.admin_remark = remark
    ret.reviewed_at  = timezone.now()
    ret.refund_amount = order_item.total_price  # full item refund by default
    ret.save()

    messages.success(
        request,
        f"Return approved for order item "
        f"'{order_item.variant.product.product_name}'.",
    )
    return redirect("shopcore:admin_return_list")


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN: REJECT RETURN
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
@transaction.atomic
def admin_reject_return(request, return_id):
    """
    Reject a return request:
      - Sets Return.status = REJECTED.
      - Sets OrderItem.item_status = RETURN_REJECTED.
      - Admin remark is optional.
      - Inventory is NOT restored.
    """
    if request.method != "POST":
        return redirect("shopcore:admin_return_detail", return_id=return_id)

    ret = get_object_or_404(Return, id=return_id, status="REQUESTED")

    remark = request.POST.get("admin_remark", "").strip()

    # Update OrderItem back to ACTIVE (rejection means item is not returned)
    order_item = ret.order_item
    order_item.item_status = "RETURN_REJECTED"
    order_item.save()

    # Update Return
    ret.status       = "REJECTED"
    ret.admin_remark = remark
    ret.reviewed_at  = timezone.now()
    ret.save()

    messages.success(
        request,
        f"Return request rejected for "
        f"'{order_item.variant.product.product_name}'.",
    )
    return redirect("shopcore:admin_return_list")