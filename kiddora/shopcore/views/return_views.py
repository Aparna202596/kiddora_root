from __future__ import annotations

from decimal import Decimal

from accounts.decorators import admin_login_required, user_login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from payments.views.wallet_helpers import credit_refund_to_wallet
from shopcore.models import Order, OrderItem, Return
from shopcore.views.order_views import _recalculate_order_amount


# ────────────────────────────────────────────────── HELPER FUNCTIONS ──────────────────────────────────────────────────
def _restore_inventory_partial(order_item: OrderItem, qty: int) -> None:

    try:
        inv = order_item.variant.inventory
        inv.quantity_available += qty
        inv.quantity_sold = max(0, inv.quantity_sold - qty)
        inv.save(update_fields=["quantity_available", "quantity_sold"])
    except Exception:
        pass

# ────────────────────────────────────────────────── RETURN REQUEST VIEWS ──────────────────────────────────────────────────
@never_cache
@user_login_required
@transaction.atomic
def request_return(request, order_id, item_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order)

    if order.order_status != "DELIVERED":
        messages.error(request, "Returns are only allowed for delivered orders.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if order_item.item_status != "ACTIVE":
        messages.error(request, "This item is not eligible for return.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if Return.objects.filter(order_item=order_item).exists():
        messages.warning(request, "A return request already exists for this item.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if request.method == "GET":
        return render(
            request,
            "returns/request_return.html",
            {
                "order": order,
                "order_item": order_item,
                "max_qty": order_item.active_quantity,
            },
        )

    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "Please provide a reason for the return.")
        return render(
            request,
            "returns/request_return.html",
            {
                "order": order,
                "order_item": order_item,
                "max_qty": order_item.active_quantity,
                "error": "Reason is required.",
            },
        )

    try:
        return_qty = int(
            request.POST.get("return_quantity", order_item.active_quantity)
        )
    except (ValueError, TypeError):
        return_qty = order_item.active_quantity

    return_qty = max(1, min(return_qty, order_item.active_quantity))

    order_items_total = sum(
        oi.total_price for oi in order.order_items.all()
    ) or Decimal("1") 

    if order_item.final_paid_price:
        paid_for_item = order_item.final_paid_price
    else:
        order_items_total = sum(
            oi.total_price for oi in order.order_items.all()
        ) or Decimal("1")
        paid_for_item = (order_item.total_price / order_items_total) * order.final_amount

    per_unit_paid = (
        paid_for_item / order_item.quantity
        if order_item.quantity
        else Decimal("0")
    )
    refund_amount = (per_unit_paid * return_qty).quantize(Decimal("0.01"))
    Return.objects.create(
        order_item=order_item,
        reason=reason,
        status="REQUESTED",
        return_quantity=return_qty,
        refund_amount=refund_amount,
    )

    order_item.item_status = "RETURN_REQUESTED"
    order_item.save(update_fields=["item_status"])

    messages.success(
        request,
        f"Return request submitted for {return_qty} unit(s) of "
        f"'{order_item.variant.product.product_name}'. We will review it shortly.",
    )
    return redirect("shopcore:user_order_detail", order_id=order.order_id)


# ──────────────────────────────────────────────── ADMIN: RETURN REQUEST LIST ────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_return_list(request):
    search = request.GET.get("search", "").strip()
    status_f = request.GET.get("status", "").strip()

    qs = Return.objects.select_related(
        "order_item__order__user",
        "order_item__variant__product",
        "order_item__order",
    ).order_by("-created_at")

    if search:
        qs = qs.filter(
            Q(order_item__order__order_id__icontains=search)
            | Q(order_item__order__user__email__icontains=search)
            | Q(order_item__variant__product__product_name__icontains=search)
        )
    if status_f:
        qs = qs.filter(status=status_f)

    page_obj = Paginator(qs, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "returns/admin_return_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "status_f": status_f,
            "status_choices": Return.STATUS_CHOICES,
        },
    )


# ─────────────────────────────────────────────── ADMIN: RETURN REQUEST DETAIL ───────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_return_detail(request, return_id):
    ret = get_object_or_404(
        Return.objects.select_related(
            "order_item__order__user",
            "order_item__order__address",
            "order_item__variant__product",
            "order_item__variant__color",
            "order_item__variant__age_group",
        ).prefetch_related("order_item__variant__product__images"),
        id=return_id,
    )

    oi = ret.order_item
    img_url = None
    img_obj = (
        oi.variant.product.images.filter(is_default=True).first()
        or oi.variant.product.images.first()
    )
    if img_obj:
        for field in ("image1", "image2", "image3", "image4", "image5"):
            val = getattr(img_obj, field)
            if val:
                img_url = val.url
                break

    return render(
        request,
        "returns/admin_return_detail.html",
        {
            "ret": ret,
            "img_url": img_url,
        },
    )


# ─────────────────────────────────────────────── ADMIN: APPROVE RETURN ───────────────────────────────────────────────
@never_cache
@admin_login_required
@transaction.atomic
def admin_approve_return(request, return_id):
    if request.method != "POST":
        return redirect("shopcore:admin_return_detail", return_id=return_id)

    ret = get_object_or_404(Return, id=return_id, status="REQUESTED")
    oi = ret.order_item
    order = oi.order

    return_qty = ret.return_quantity or oi.active_quantity

    if ret.refund_amount:
        refund_amount = ret.refund_amount
    else:
        if oi.final_paid_price:
            per_unit_paid = (oi.final_paid_price / oi.quantity) if oi.quantity else Decimal("0")
        else:
            oi_total = sum(
                x.total_price for x in order.order_items.all()
            ) or Decimal("1")
            item_paid_total = (oi.total_price / oi_total) * order.final_amount
            per_unit_paid = item_paid_total / oi.quantity if oi.quantity else Decimal("0")
        refund_amount = (per_unit_paid * return_qty).quantize(Decimal("0.01"))

    ret.status = "APPROVED"
    ret.admin_note = request.POST.get("admin_note", "Return approved.").strip()
    ret.refund_amount = refund_amount
    ret.updated_at = timezone.now()
    ret.approved_at = timezone.now()
    ret.save(
        update_fields=["status", "admin_note", "refund_amount", "updated_at", "approved_at"]
    )

    is_full_return = return_qty >= oi.active_quantity
    if is_full_return:
        oi.item_status = "RETURN_APPROVED"
    else:
        oi.cancelled_quantity = (oi.cancelled_quantity or 0) + return_qty
        oi.item_status = "ACTIVE"
    oi.save(update_fields=["item_status", "cancelled_quantity"])

    messages.success(
        request,
        f"Return approved for {return_qty} unit(s) of "
        f"'{oi.variant.product.product_name}'. "
        f"Proceed to 'Process Refund' to credit ₹{refund_amount} to the customer's wallet.",
    )
    return redirect("shopcore:admin_return_detail", return_id=return_id)

# ─────────────────────────────────────────────── ADMIN: PROCESS REFUND ───────────────────────────────────────────────

@never_cache
@admin_login_required
@transaction.atomic
def admin_process_refund(request, return_id):
    if request.method != "POST":
        return redirect("shopcore:admin_return_detail", return_id=return_id)

    ret = get_object_or_404(Return, id=return_id)

    if ret.status != "APPROVED":
        if ret.status == "REFUNDED":
            messages.warning(request, "Refund was already processed for this return.")
        else:
            messages.error(
                request,
                f"Cannot process refund: return is in '{ret.status}' status.",
            )
        return redirect("shopcore:admin_return_detail", return_id=return_id)

    oi = ret.order_item
    order = oi.order

    refund_amount = ret.refund_amount or ret.calculated_refund_amount

    txn = credit_refund_to_wallet(
        user=order.user,
        amount=refund_amount,
        description=(
            f"Refund for return of '{oi.variant.product.product_name}' "
            f"in order {order.order_id}"
        ),
        reference_type="RETURN",
        reference_id=f"{order.order_id}-return-{ret.id}",
        order=order,
    )

    if txn is None:
        messages.warning(request, "Refund was already processed for this return.")
        return redirect("shopcore:admin_return_detail", return_id=return_id)

    ret.locked = True
    ret.save(update_fields=["locked"])

    ret.status = "REFUNDED"
    ret.refunded_at = timezone.now()
    ret.save(update_fields=["status", "refunded_at"])

    if oi.item_status == "RETURN_APPROVED":
        oi.item_status = "REFUNDED"
        oi.save(update_fields=["item_status"])

    _recalculate_order_amount(order)
    active_count = order.order_items.filter(item_status="ACTIVE").count()
    order.payment_status = "REFUNDED" if active_count == 0 else "PARTIALLY_REFUNDED"
    order.save(update_fields=["payment_status"])

    messages.success(
        request,
        f"Refund of ₹{refund_amount} finalised and credited to wallet.",
    )
    return redirect("shopcore:admin_return_detail", return_id=return_id)

# ─────────────────────────────────────────────── ADMIN: REJECT RETURN ───────────────────────────────────────────────
@never_cache
@admin_login_required
@transaction.atomic
def admin_reject_return(request, return_id):
    if request.method != "POST":
        return redirect("shopcore:admin_return_detail", return_id=return_id)

    ret = get_object_or_404(Return, id=return_id, status="REQUESTED")
    oi = ret.order_item

    admin_note = request.POST.get("admin_note", "").strip()
    if not admin_note:
        messages.error(request, "Please provide a reason for rejection.")
        return redirect("shopcore:admin_return_detail", return_id=return_id)

    ret.status = "REJECTED"
    ret.admin_note = admin_note
    ret.updated_at = timezone.now()
    ret.save(update_fields=["status", "admin_note", "updated_at"])

    oi.item_status = "ACTIVE"
    oi.save(update_fields=["item_status"])

    messages.success(request, f"Return rejected. Reason: {admin_note}")
    return redirect("shopcore:admin_return_detail", return_id=return_id)
