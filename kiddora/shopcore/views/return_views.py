from __future__ import annotations
from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator
from accounts.decorators import admin_login_required, user_login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from decimal import Decimal

from shopcore.models import Order, OrderItem, Return


# # ───────────────────────────────── HELPERS ─────────────────────────────────

def _get_return_model():
    return Return

def _restore_inventory(order_item: OrderItem):
    try:
        inv = order_item.variant.inventory
        inv.quantity_available += order_item.quantity
        inv.quantity_sold       = max(0, inv.quantity_sold - order_item.quantity)
        inv.save(update_fields=["quantity_available", "quantity_sold"])
    except Exception:
        pass

def _credit_wallet(user, amount: Decimal, description: str):
    try:
        from accounts.models import Wallet, WalletTransaction
        wallet, _ = Wallet.objects.get_or_create(user=user)
        wallet.balance += amount
        wallet.save(update_fields=["balance", "updated_at"])
        WalletTransaction.objects.create(
            wallet = wallet,
            amount = amount,
            tx_type     = "CREDIT",
            description = description,
        )
    except Exception:
        pass

# ───────────────────────────────── USER ─────────────────────────────────
# USER: REQUEST RETURN

@never_cache
@user_login_required
@transaction.atomic
def request_return(request, order_id, item_id):
    order      = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order)

    if order.order_status != "DELIVERED":
        messages.error(request, "Returns are only allowed for delivered orders.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if order_item.item_status != "ACTIVE":
        messages.error(request, "This item is not eligible for return.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if request.method == "GET":
        return render(request, "returns/request_return.html", {
            "order": order,
            "order_item": order_item,
        })

    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "Please provide a reason for the return.")
        return render(request, "returns/request_return.html", {
            "order": order,
            "order_item": order_item,
            "error": "Reason is required.",
        })

    # Create return request
    try:
        Return = _get_return_model()
        if Return.objects.filter(order_item=order_item).exists():
            messages.warning(request, "A return request already exists for this item.")
            return redirect("shopcore:user_order_detail", order_id=order.order_id)

        Return.objects.create(
            order_item = order_item,
            reason = reason,
            status = "PENDING",
            refund_amount = order_item.total_price,
        )
    except ImportError:
        messages.error(request, "Return feature is currently unavailable. Please contact support.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    order_item.item_status = "RETURN_REQUESTED"
    order_item.save(update_fields=["item_status"])

    messages.success(
        request,
        f"Return request submitted for "
        f"'{order_item.variant.product.product_name}'. "
        "We will review it shortly.",
    )
    return redirect("shopcore:user_order_detail", order_id=order.order_id)

    # order = get_object_or_404(Order, order_id=order_id, user=request.user)
    # item = get_object_or_404(OrderItem, pk=item_id, order=order)
    
    # if order.order_status != "DELIVERED":
    #     messages.error(request, "Only delivered orders can be returned.")
    #     return redirect("shopcore:user_order_detail", order_id=order_id)
    
    # if item.item_status != "ACTIVE":
    #     messages.error(request, "This item cannot be returned.")
    #     return redirect("shopcore:user_order_detail", order_id=order_id)
    
    # if hasattr(item, "return_request"):
    #     messages.error(request, "Return request already submitted.")
    #     return redirect("shopcore:user_order_detail", order_id=order_id)
    
    # if request.method == "POST":
    #     reason = request.POST.get("reason", "").strip()
    #     if not reason:
    #         messages.error(request, "Please provide a reason for return.")
    #         return redirect("shopcore:request_item_return", order_id=order_id, item_id=item_id)
        
    #     Return.objects.create(
    #         order_item=item,
    #         reason=reason,
    #         status="REQUESTED"
    #     )
    #     item.item_status = "RETURN_REQUESTED"
    #     item.save(update_fields=["item_status"])
        
    #     messages.success(request, "Return request submitted successfully.")
    #     return redirect("shopcore:user_order_detail", order_id=order_id)
    
    # return render(request, "orders/user/return_request.html", {
    #     "order": order,
    #     "item": item
    # })

# ───────────────────────────────── ADMIN ─────────────────────────────────
# ADMIN: RETURN REQUEST LIST
@never_cache
@admin_login_required
def admin_return_list(request):
    try:
        Return = _get_return_model()
    except ImportError:
        messages.error(request, "Return model not found.")
        return redirect("shopcore:admin_order_list")

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

    status_choices = [("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")]
    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))

    return render(request, "returns/admin_return_list.html", {
        "page_obj": page_obj,
        "search": search,
        "status_f": status_f,
        "status_choices": status_choices,
    })

# ADMIN: RETURN REQUEST DETAIL
@never_cache
@admin_login_required
def admin_return_detail(request, return_id):
    try:
        Return = _get_return_model()
    except ImportError:
        return redirect("shopcore:admin_return_list")

    ret = get_object_or_404(Return.objects.select_related(
        "order_item__order__user",
        "order_item__order__address",
        "order_item__variant__product",
        "order_item__variant__color",
        "order_item__variant__age_group").prefetch_related("order_item__variant__product__images"), id=return_id )

    oi = ret.order_item
    img_url = None
    img_obj = oi.variant.product.images.filter(is_default=True).first() or \
                oi.variant.product.images.first()
    if img_obj:
        for field in ("image1", "image2", "image3", "image4", "image5"):
            val = getattr(img_obj, field)
            if val:
                img_url = val.url
                break

    context= {"ret": ret, "img_url": img_url}
    return render(request, "returns/admin_return_detail.html", context)

# ADMIN: APPROVE RETURN  →  refund to wallet + restock
@never_cache
@admin_login_required
@transaction.atomic
def admin_approve_return(request, return_id):
    
    if request.method != "POST":
        return redirect("shopcore:admin_return_detail", return_id=return_id)

    try:
        Return = _get_return_model()
    except ImportError:
        return redirect("shopcore:admin_return_list")

    ret = get_object_or_404(Return, id=return_id, status="PENDING")
    oi = ret.order_item

    # Approve request
    ret.status = "APPROVED"
    ret.admin_note = request.POST.get("admin_note", "Return approved.").strip()
    ret.save(update_fields=["status", "admin_note", "updated_at"])

    # Update item status
    oi.item_status = "REFUNDED"
    oi.save(update_fields=["item_status"])

    # Restore inventory
    _restore_inventory(oi)

    # Credit wallet
    _credit_wallet(
        user = oi.order.user,
        amount = ret.refund_amount,
        description = (f"Refund for return of '{oi.variant.product.product_name}' "f"in order {oi.order.order_id}"), )

    # Update order payment status
    order = oi.order
    active_items = order.order_items.filter(item_status="ACTIVE")
    if not active_items.exists():
        order.payment_status = "REFUNDED"
    else:
        order.payment_status = "PARTIALLY_REFUNDED"
    order.save(update_fields=["payment_status"])

    messages.success(
        request,
        f"Return approved. ₹{ret.refund_amount} credited to "
        f"{oi.order.user.email}'s wallet.",
    )
    return redirect("shopcore:admin_return_detail", return_id=return_id)

# ADMIN: REJECT RETURN
@never_cache
@admin_login_required
@transaction.atomic
def admin_reject_return(request, return_id):
    if request.method != "POST":
        return redirect("shopcore:admin_return_detail", return_id=return_id)

    try:
        Return = _get_return_model()
    except ImportError:
        return redirect("shopcore:admin_return_list")

    ret = get_object_or_404(Return, id=return_id, status="PENDING")
    oi  = ret.order_item

    admin_note = request.POST.get("admin_note", "").strip()
    if not admin_note:
        messages.error(request, "Please provide a reason for rejection.")
        return redirect("shopcore:admin_return_detail", return_id=return_id)

    ret.status = "REJECTED"
    ret.admin_note = admin_note
    ret.save(update_fields=["status", "admin_note", "updated_at"])

    # Restore item to ACTIVE (return was denied)
    oi.item_status = "RETURN_REJECTED"
    oi.save(update_fields=["item_status"])

    messages.success(
        request,
        f"Return request rejected. Reason: {admin_note}",
    )
    return redirect("shopcore:admin_return_detail", return_id=return_id)