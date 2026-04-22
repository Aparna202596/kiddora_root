from __future__ import annotations

import io
import os
import platform
from decimal import Decimal

from accounts.decorators import admin_login_required, user_login_required
from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from payments.models import Payment
from payments.views.wallet_helpers import credit_refund_to_wallet
from products.models import ProductVariant
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)
from shopcore.models import Cart, Offer, Order, OrderItem, Return
from shopcore.views.coupon_views import compute_coupon_discount


# ────────────────────────────────────────────────── HELPER FUNCTIONS ─────────────────────────────────────────────────────────────
def _get_cart(user):
    try:
        return user.cart
    except Cart.DoesNotExist:
        return None


def _variant_is_available(variant: ProductVariant) -> bool:
    try:
        p = variant.product
        sub = p.subcategory
        cat = sub.category
        return (
            variant.is_active
            and p.is_active
            and not p.is_deleted
            and sub.is_active
            and not sub.is_deleted
            and cat.is_active
            and not cat.is_deleted
        )
    except Exception:
        return False


def _stock_for(variant: ProductVariant) -> int:
    try:
        return variant.inventory.quantity_available
    except Exception:
        return 0


def _img_url_for(product) -> str | None:
    img_obj = product.images.filter(is_default=True).first() or product.images.first()
    if img_obj:
        for field in ("image1", "image2", "image3", "image4", "image5"):
            val = getattr(img_obj, field)
            if val:
                return val.url
    return None


def _restore_inventory(order_item):
    """Restore stock when an item is returned or cancelled."""
    try:
        inv = order_item.variant.inventory
        inv.quantity_available += order_item.quantity
        inv.quantity_sold = max(0, inv.quantity_sold - order_item.quantity)
        inv.save(update_fields=["quantity_available", "quantity_sold"])
    except Exception as e:
        print(f"Warning: Could not restore inventory for item {order_item.id}: {e}")


def _recalculate_order_amount(order: Order) -> None:
    """
    Recalculate order totals using active_quantity on every item.
    Works correctly for both full-item and partial-quantity cancellations.
    """
    active_items = order.order_items.filter(item_status="ACTIVE")

    subtotal = Decimal("0")
    for item in active_items:
        per_unit_net = (
            item.total_price / item.quantity if item.quantity else Decimal("0")
        )
        subtotal += per_unit_net * item.active_quantity

    order.total_amount = subtotal

    if order.coupon:
        if subtotal < order.coupon.min_order_amount:
            order.coupon = None
            order.coupon_discount = Decimal("0")
        else:
            order.coupon_discount = compute_coupon_discount(order.coupon, subtotal)
    else:
        order.coupon_discount = Decimal("0")

    order.shipping_charge = order.calculate_shipping()
    total_deductions = order.discount_amount + order.coupon_discount
    order.final_amount = max(
        Decimal("0"), subtotal - total_deductions + order.shipping_charge
    )
    order.save(
        update_fields=[
            "total_amount",
            "coupon",
            "coupon_discount",
            "shipping_charge",
            "final_amount",
        ]
    )


def get_max_offer_discount_percent(product) -> int:
    if not product:
        return 0

    now = timezone.now()
    active_offers = Offer.objects.filter(
        is_active=True, is_deleted=False, start_date__lte=now
    )
    product_offer = active_offers.filter(offer_type="PRODUCT", product=product).first()
    category_offer = None
    try:
        if product.subcategory and product.subcategory.category:
            category_offer = active_offers.filter(
                offer_type="CATEGORY",
                category=product.subcategory.category,
            ).first()
    except Exception:
        pass

    max_pct = 0
    if product_offer and product_offer.is_valid():
        max_pct = max(max_pct, product_offer.discount_percent)
    if category_offer and category_offer.is_valid():
        max_pct = max(max_pct, category_offer.discount_percent)

    return max_pct


# ────────────────────────────────────────────────── USER: ORDER LIST ─────────────────────────────────────────────────────────────
@never_cache
@user_login_required
def user_order_list(request):
    query = request.GET.get("q", "").strip()
    orders = Order.objects.filter(user=request.user).order_by("-order_date")

    if query:
        orders = orders.filter(
            Q(order_id__icontains=query)
            | Q(order_status__icontains=query)
            | Q(order_items__variant__product__product_name__icontains=query)
        ).distinct()

    page_obj = Paginator(orders, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "orders/user/user_order_list.html",
        {
            "page_obj": page_obj,
            "query": query,
        },
    )


# ────────────────────────────────────────────────── USER: ORDER DETAIL ─────────────────────────────────────────────────────────────
@never_cache
@user_login_required
def user_order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("address", "coupon").prefetch_related(
            "order_items__variant__product__images",
            "order_items__variant__color",
            "order_items__variant__age_group",
        ),
        order_id=order_id,
        user=request.user,
    )
    items_with_img = [
        {"order_item": oi, "img_url": _img_url_for(oi.variant.product)}
        for oi in order.order_items.all()
    ]
    return render(
        request,
        "orders/user/user_order_detail.html",
        {
            "order": order,
            "items_with_img": items_with_img,
            "can_cancel_order": order.order_status in ("PENDING", "CONFIRMED"),
        },
    )


#   ────────────────────────────────────────────────── USER: CANCEL ORDER ─────────────────────────────────────────────────────────────
@never_cache
@user_login_required
@transaction.atomic
def cancel_order(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.order_status == "OUT_FOR_DELIVERY":
        messages.error(
            request, "Your order is out for delivery. You cannot cancel the order now."
        )
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if order.order_status not in ("PENDING", "CONFIRMED", "SHIPPED"):
        messages.error(request, "This order cannot be cancelled at its current stage.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if request.method != "POST":
        return render(
            request, "orders/user/confirm_cancel_order.html", {"order": order}
        )

    reason = request.POST.get("cancel_reason", "").strip()

    for oi in order.order_items.filter(item_status="ACTIVE"):
        try:
            inv = oi.variant.inventory
            inv.quantity_available += oi.quantity
            inv.quantity_sold = max(0, inv.quantity_sold - oi.quantity)
            inv.save()
        except Exception:
            pass
        oi.item_status = "CANCELLED"
        oi.cancel_reason = reason or "Order cancelled by user"
        oi.cancelled_at = timezone.now()
        oi.save()

    order.order_status = "CANCELLED"
    order.cancel_reason = reason or "Cancelled by user"
    order.cancelled_at = timezone.now()

    if order.payment_status == "PAID":
        if order.payment_method in ("PAYPAL", "WALLET"):
            credit_refund_to_wallet(
                user=order.user,
                amount=order.final_amount,
                description=f"Refund for cancelled order {order.order_id}",
                reference_type="CANCEL",
                reference_id=str(order.order_id),  
                order=order,
            )
            order.payment_status = "REFUNDED"
        elif order.payment_method == "COD":
            order.payment_status = "CANCELLED"

    order.save()

    messages.success(request, f"Order {order.order_id} has been cancelled.")
    return redirect("shopcore:user_order_detail", order_id=order.order_id)


# ───────────────────────────────────────────────────────────── CANCEL ORDER ITEM (partial cancellation) ─────────────────────────────────────────────────────────────
@never_cache
@user_login_required
@transaction.atomic
def cancel_order_item(request, order_id, item_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_item = get_object_or_404(
        OrderItem, id=item_id, order=order, item_status="ACTIVE"
    )

    if order.order_status == "OUT_FOR_DELIVERY":
        messages.error(
            request, "Your order is out for delivery. You cannot cancel now."
        )
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if order.order_status not in ("PENDING", "CONFIRMED", "SHIPPED"):
        messages.error(request, "Items in this order can no longer be cancelled.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if request.method != "POST":
        return render(
            request,
            "orders/user/confirm_cancel_item.html",
            {
                "order": order,
                "order_item": order_item,
                "max_qty": order_item.active_quantity,
            },
        )

    reason = request.POST.get("cancel_reason", "").strip()

    try:
        cancel_qty = int(
            request.POST.get("cancel_quantity", order_item.active_quantity)
        )
    except (ValueError, TypeError):
        cancel_qty = order_item.active_quantity

    cancel_qty = max(1, min(cancel_qty, order_item.active_quantity))
    cancel_all = cancel_qty >= order_item.active_quantity

    try:
        inv = order_item.variant.inventory
        inv.quantity_available += cancel_qty
        inv.quantity_sold = max(0, inv.quantity_sold - cancel_qty)
        inv.save(update_fields=["quantity_available", "quantity_sold"])
    except Exception:
        pass

    per_unit_net = (
        order_item.total_price / order_item.quantity
        if order_item.quantity
        else Decimal("0")
    )
    item_refund_amount = (per_unit_net * cancel_qty).quantize(Decimal("0.01"))

    if order.payment_status == "PAID" and order.payment_method in ("PAYPAL", "WALLET"):

        new_total_cancelled = order_item.cancelled_quantity + cancel_qty
        refund_ref = f"{order.order_id}-item-{order_item.id}-cq-{new_total_cancelled}"
        credit_refund_to_wallet(
            user=order.user,
            amount=item_refund_amount,
            description=(
                f"Refund for {cancel_qty} unit(s) of "
                f"'{order_item.variant.product.product_name}' cancelled in order {order.order_id}"
            ),
            reference_type="CANCEL",
            reference_id=refund_ref,
            order=order,
        )

    order_item.cancelled_quantity += cancel_qty
    if cancel_all:
        order_item.item_status = "CANCELLED"
        order_item.cancel_reason = reason or "Item cancelled by user"
        order_item.cancelled_at = timezone.now()
    order_item.save()

    _recalculate_order_amount(order)

    remaining_active = order.order_items.filter(item_status="ACTIVE")
    if not remaining_active.exists():
        order.order_status = "CANCELLED"
        order.cancel_reason = "All items cancelled"
        order.cancelled_at = timezone.now()
        if (
            order.payment_method in ("PAYPAL", "WALLET")
            and order.payment_status == "PAID"
        ):
            order.payment_status = "REFUNDED"
        elif order.payment_method == "COD":
            order.payment_status = "CANCELLED"
        order.save(
            update_fields=[
                "order_status",
                "cancel_reason",
                "cancelled_at",
                "payment_status",
            ]
        )
    else:
        if (
            order.payment_method in ("PAYPAL", "WALLET")
            and order.payment_status == "PAID"
        ):
            order.payment_status = "PARTIALLY_REFUNDED"
            order.save(update_fields=["payment_status"])

    if cancel_all:
        msg = f"Item '{order_item.variant.product.product_name}' fully cancelled."
    else:
        msg = f"{cancel_qty} unit(s) of '{order_item.variant.product.product_name}' cancelled."

    if order.payment_method in ("PAYPAL", "WALLET") and order.payment_status == "PAID":
        msg += f" ₹{item_refund_amount:.2f} refunded to your wallet."

    messages.success(request, msg)
    return redirect("shopcore:user_order_detail", order_id=order.order_id)


# ────────────────────────────────────────────────── REQUEST RETURN ─────────────────────────────────────────────────────────────
@never_cache
@user_login_required
@transaction.atomic
def request_return(request, order_id, item_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order)

    if order.order_status != "DELIVERED":
        messages.error(
            request, "Returns are only allowed after the order is delivered."
        )
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if order_item.item_status != "ACTIVE":
        messages.error(request, "This item is not eligible for return.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if hasattr(order_item, "return_request"):
        messages.error(request, "A return request already exists for this item.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if request.method != "POST":
        return render(
            request,
            "orders/user/request_return.html",
            {"order": order, "order_item": order_item},
        )

    reason = request.POST.get("return_reason", "").strip()
    if not reason:
        messages.error(request, "Please provide a reason for the return.")
        return render(
            request,
            "orders/user/request_return.html",
            {"order": order, "order_item": order_item},
        )

    Return.objects.create(order_item=order_item, reason=reason)
    order_item.item_status = "RETURN_REQUESTED"
    order_item.save(update_fields=["item_status"])

    messages.success(request, "Return request submitted successfully.")
    return redirect("shopcore:user_order_detail", order_id=order.order_id)


# ───────────────────────────────────────────────────────────── ADMIN: ORDER LIST ─────────────────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_order_list(request):
    search = request.GET.get("search", "").strip()
    status_f = request.GET.get("status", "").strip()
    sort = request.GET.get("sort", "order_date")
    direction = request.GET.get("dir", "desc")

    orders = (
        Order.objects.select_related("user", "address")
        .prefetch_related("order_items")
        .order_by("-order_date")
    )

    if search:
        orders = orders.filter(
            Q(order_id__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__full_name__icontains=search)
        )
    if status_f:
        orders = orders.filter(order_status=status_f)

    if sort in ("order_date", "final_amount", "order_status"):
        order_field = f"-{sort}" if direction == "desc" else sort
        orders = orders.order_by(order_field)

    page_obj = Paginator(orders, 15).get_page(request.GET.get("page"))

    return render(
        request,
        "orders/admin/admin_order_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "status_f": status_f,
            "sort": sort,
            "dir": direction,
            "status_choices": Order.ORDER_STATUS_CHOICES,
        },
    )


# ───────────────────────────────────────────────────────────── ADMIN: ORDER DETAIL ─────────────────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("user", "address", "coupon").prefetch_related(
            "order_items__variant__product__images",
            "order_items__variant__color",
            "order_items__variant__age_group",
        ),
        order_id=order_id,
    )
    items_with_img = [
        {"order_item": oi, "img_url": _img_url_for(oi.variant.product)}
        for oi in order.order_items.all()
    ]
    return render(
        request,
        "orders/admin/admin_order_detail.html",
        {
            "order": order,
            "items_with_img": items_with_img,
            "status_choices": Order.ORDER_STATUS_CHOICES,
            "item_status_choices": OrderItem.ITEM_STATUS_CHOICES,
        },
    )


# ───────────────────────────────────────────────────────────── ADMIN: UPDATE ORDER STATUS ─────────────────────────────────────────────────────────────
@never_cache
@admin_login_required
@transaction.atomic
def admin_update_order_status(request, order_id):
    if request.method != "POST":
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    order = get_object_or_404(Order, order_id=order_id)
    new_status = request.POST.get("order_status", "").strip()

    valid_transitions = {
        "PENDING": [
            "CONFIRMED",
            "SHIPPED",
            "OUT_FOR_DELIVERY",
            "DELIVERED",
            "CANCELLED",
        ],
        "CONFIRMED": ["SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
        "SHIPPED": ["OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
        "OUT_FOR_DELIVERY": ["DELIVERED"],
        "DELIVERED": [],
        "CANCELLED": [],
        "RETURNED": [],
    }

    allowed = valid_transitions.get(order.order_status, [])
    if new_status not in allowed:
        messages.error(
            request,
            f"Cannot change status from "
            f"'{order.get_order_status_display()}' to '{new_status}'.",
        )
        return redirect("shopcore:admin_order_detail", order_id=order.order_id)

    old_status = order.order_status
    order.order_status = new_status

    if new_status == "DELIVERED":
        order.delivered_at = timezone.now()
        order.order_items.filter(item_status="ACTIVE").update(
            delivered_at=timezone.now(),
        )
        if order.payment_method == "COD":
            order.payment_status = "PAID"

            Payment.objects.filter(
                order=order, payment_method="COD", payment_status="PENDING"
            ).update(
                payment_status="PAID",
                completed_at=timezone.now(),
            )

    elif new_status == "CANCELLED":
        order.cancelled_at = timezone.now()
        order.cancel_reason = request.POST.get(
            "cancel_reason", "Cancelled by admin"
        ).strip()
        for oi in order.order_items.filter(item_status="ACTIVE"):
            try:
                inv = oi.variant.inventory
                inv.quantity_available += oi.quantity
                inv.quantity_sold = max(0, inv.quantity_sold - oi.quantity)
                inv.save()
            except Exception:
                pass
            oi.item_status = "CANCELLED"
            oi.cancel_reason = order.cancel_reason
            oi.cancelled_at = timezone.now()
            oi.save()

        if order.payment_status == "PAID":
            if order.payment_method in ("PAYPAL", "WALLET"):

                credit_refund_to_wallet(
                    user=order.user,
                    amount=order.final_amount,
                    description=f"Admin refund for cancelled order {order.order_id}",
                    reference_type="CANCEL",
                    reference_id=str(order.order_id),
                    order=order,
                )
                order.payment_status = "REFUNDED"
            elif order.payment_method == "COD":
                order.payment_status = "CANCELLED"
    order.save()
    messages.success(
        request,
        f"Order {order.order_id} status updated: {old_status} → {new_status}",
    )
    return redirect("shopcore:admin_order_detail", order_id=order.order_id)


# ───────────────────────────────────────────────────────────── ADMIN: UPDATE ORDER ITEM STATUS ─────────────────────────────────────────────────────────────
@never_cache
@admin_login_required
@transaction.atomic
def admin_update_item_status(request, order_id, item_id):
    if request.method != "POST":
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    order = get_object_or_404(Order, order_id=order_id)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order)
    new_status = request.POST.get("item_status", "")

    if new_status not in dict(OrderItem.ITEM_STATUS_CHOICES):
        messages.error(request, "Invalid item status.")
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    order_item.item_status = new_status
    order_item.save()

    if new_status == "CANCELLED":
        _recalculate_order_amount(order)

    messages.success(
        request,
        f"Item '{order_item.variant.product.product_name}' updated to {new_status}.",
    )
    return redirect("shopcore:admin_order_detail", order_id=order_id)


# ───────────────────────────────────────────────────────────── ADMIN: HANDLE RETURN REQUEST ─────────────────────────────────────────────────────────────
@never_cache
@admin_login_required
@transaction.atomic
def admin_handle_return(request, return_id):
    from shopcore.models import Return

    ret = get_object_or_404(Return, id=return_id)
    order_item = ret.order_item
    order = order_item.order

    if request.method != "POST":
        return render(
            request,
            "orders/admin/admin_handle_return.html",
            {
                "ret": ret,
                "order": order,
                "order_item": order_item,
            },
        )

    action = request.POST.get("action", "").strip()
    admin_note = request.POST.get("admin_note", "").strip()

    if action == "APPROVE":
        ret.status = "APPROVED"
        ret.admin_note = admin_note or "Return approved by admin."
        ret.updated_at = timezone.now()
        ret.save(update_fields=["status", "admin_note", "updated_at"])

        order_item.item_status = "REFUNDED"
        order_item.save(update_fields=["item_status"])

        _restore_inventory(order_item)

        refund_amount = order_item.active_total
        credit_refund_to_wallet(
            user=order.user,
            amount=refund_amount,
            description=(
                f"Refund for approved return of "
                f"'{order_item.variant.product.product_name}' in order {order.order_id}"
            ),
            reference_type="RETURN",
            reference_id=f"{order.order_id}-item-{order_item.id}",
            order=order,
        )

        _recalculate_order_amount(order)

        if not order.order_items.filter(item_status="ACTIVE").exists():
            order.payment_status = "REFUNDED"
        else:
            order.payment_status = "PARTIALLY_REFUNDED"
        order.save(update_fields=["payment_status"])
        messages.success(request, f"Return approved and ₹{refund_amount:.2f} refunded.")

    elif action == "REJECT":
        ret.status = "REJECTED"
        ret.admin_note = admin_note or "Return rejected by admin."
        ret.updated_at = timezone.now()
        ret.save(update_fields=["status", "admin_note", "updated_at"])
        order_item.item_status = "RETURN_REJECTED"
        order_item.save(update_fields=["item_status"])
        messages.success(request, "Return request rejected.")

    return redirect("shopcore:admin_order_detail", order_id=order.order_id)


# ───────────────────────────────────────────────────────────── DOWNLOAD INVOICE ─────────────────────────────────────────────────────────────
@never_cache
@user_login_required
def download_invoice(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("coupon", "address").prefetch_related(
            "order_items__variant__product"
        ),
        order_id=order_id,
        user=request.user,
    )
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    if platform.system() == "Windows":
        font_path = "C:/Windows/Fonts/arial.ttf"
    else:
        # Path for Ubuntu/Linux
        font_path = "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"
    pdfmetrics.registerFont(TTFont("Arial", font_path))
    pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))

    styles = getSampleStyleSheet()

    def ps(
        name,
        size=9,
        bold=False,
        color=colors.black,
        align="LEFT",
        space_after=4,
        leading=13,
    ):
        return ParagraphStyle(
            name,
            fontName="Arial-Bold" if bold else "Arial",
            fontSize=size,
            textColor=color,
            alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}[align],
            spaceAfter=space_after,
            leading=leading,
        )

    PINK = colors.HexColor("#f06292")
    PINK_DARK = colors.HexColor("#c2185b")
    AMBER_BG = colors.HexColor("#fff3e0")
    AMBER_TXT = colors.HexColor("#e65100")
    ROSE_BG = colors.HexColor("#fce4ec")
    ROSE_TXT = colors.HexColor("#880e4f")
    GREEN_TXT = colors.HexColor("#15803d")
    MUTED = colors.HexColor("#888888")
    LIGHT_GRY = colors.HexColor("#f8f8f8")
    BORDER = colors.HexColor("#e0e0e0")

    elements = []

    logo_path = os.path.join(settings.BASE_DIR, "static/images/kiddora_logo.PNG")
    logo_cell = (
        Image(logo_path, width=110, height=45)
        if os.path.exists(logo_path)
        else Paragraph("KIDDORA", ps("lh", 20, bold=True, color=colors.white))
    )

    hdr_data = [
        [
            logo_cell,
            Paragraph(
                "Kids Fashion &amp; Apparel<br/>www.kiddora.com",
                ps("hs", 8, color=colors.HexColor("#fce4ec"), leading=12),
            ),
            Paragraph(
                f"<b>INVOICE</b><br/><font size='8' color='#fce4ec'>{order.order_id}</font>",
                ps("hi", 15, bold=True, color=colors.white, align="RIGHT", leading=20),
            ),
        ]
    ]
    hdr = Table(hdr_data, colWidths=[110, 230, 135])
    hdr.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PINK),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    elements.append(hdr)
    elements.append(Spacer(1, 12))

    address = order.address
    cust_name = (
        getattr(address, "full_name", None)
        or getattr(order.user, "full_name", "")
        or order.user.email
    )
    cust_phone = (
        getattr(address, "phone", None) or getattr(order.user, "phone", "") or "—"
    )
    addr_str = ", ".join(
        filter(
            None,
            [
                getattr(address, "address_line1", ""),
                getattr(address, "address_line2", ""),
                getattr(address, "city", ""),
                getattr(address, "state", ""),
                getattr(address, "pincode", ""),
                getattr(address, "country", ""),
            ],
        )
    )

    def meta_block(rows):
        t = Table(rows, colWidths=[70, 170])
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Arial"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
                    ("TEXTCOLOR", (1, 0), (1, -1), colors.black),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return t

    left_rows = [
        [
            Paragraph("Order Date", ps("ml", 8, color=MUTED)),
            Paragraph(order.order_date.strftime("%d %b %Y, %I:%M %p"), ps("mv", 8)),
        ],
        [
            Paragraph("Order Status", ps("ml2", 8, color=MUTED)),
            Paragraph(
                f"<b>{order.get_order_status_display()}</b>",
                ps("mv2", 8, bold=True, color=PINK_DARK),
            ),
        ],
        [
            Paragraph("Payment", ps("ml3", 8, color=MUTED)),
            Paragraph(
                f"{order.payment_method} — {order.payment_status.replace('_', ' ').title()}",
                ps("mv3", 8),
            ),
        ],
    ]
    right_rows = [
        [
            Paragraph("Customer", ps("rl", 8, color=MUTED)),
            Paragraph(cust_name, ps("rv", 8)),
        ],
        [
            Paragraph("Phone", ps("rl2", 8, color=MUTED)),
            Paragraph(cust_phone, ps("rv2", 8)),
        ],
        [
            Paragraph("Email", ps("rl3", 8, color=MUTED)),
            Paragraph(order.user.email, ps("rv3", 8)),
        ],
        [
            Paragraph("Ship To", ps("rl4", 8, color=MUTED)),
            Paragraph(addr_str, ps("rv4", 8, leading=11)),
        ],
    ]

    meta_tbl = Table(
        [[meta_block(left_rows), meta_block(right_rows)]], colWidths=[245, 240]
    )
    meta_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#fff8f9")),
                ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#f9f9fb")),
                ("BOX", (0, 0), (0, -1), 0.5, colors.HexColor("#f8bbd0")),
                ("BOX", (1, 0), (1, -1), 0.5, colors.HexColor("#e8eaf6")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(meta_tbl)
    elements.append(Spacer(1, 14))

    INACTIVE = {
        "CANCELLED",
        "RETURN_REQUESTED",
        "RETURN_APPROVED",
        "REFUNDED",
        "RETURN_REJECTED",
    }
    STATUS_LABEL = {
        "CANCELLED": "[CANCELLED]",
        "RETURN_REQUESTED": "[RETURN REQUESTED]",
        "RETURN_APPROVED": "[RETURN APPROVED]",
        "REFUNDED": "[REFUNDED]",
        "RETURN_REJECTED": "[RETURN REJECTED]",
    }

    def th(text, align="LEFT"):
        return Paragraph(
            f"<b>{text}</b>",
            ps(f"th_{text}", 8, bold=True, color=colors.white, align=align),
        )

    item_data = [
        [
            th("Item"),
            th("Variant"),
            th("Qty", "CENTER"),
            th("Unit Price", "RIGHT"),
            th("Offer", "RIGHT"),
            th("Amount", "RIGHT"),
        ]
    ]

    item_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), PINK),
        ("FONTNAME", (0, 0), (-1, -1), "Arial"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, LIGHT_GRY]),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]

    has_inactive = False
    row_idx = 1

    for oi in order.order_items.all():
        is_fully_inactive = oi.item_status in INACTIVE
        is_cancelled = oi.item_status == "CANCELLED"
        is_return = oi.item_status in INACTIVE and not is_cancelled
        label = STATUS_LABEL.get(oi.item_status, "")
        has_partial_cancel = oi.cancelled_quantity > 0 and not is_fully_inactive

        offer_pct = get_max_offer_discount_percent(oi.variant.product)
        offer_str = f"{offer_pct}%" if offer_pct else "—"

        muted_clr = (
            AMBER_TXT if is_cancelled else (ROSE_TXT if is_return else colors.black)
        )
        name_base = oi.variant.product.product_name
        variant_str = f"{oi.variant.color}\n{oi.variant.age_group}"

        def item_ps(inactive=False, clr=colors.black):
            return ps(
                f"ip_{row_idx}", 8, color=clr if not inactive else MUTED, leading=11
            )

        def num_ps(inactive=False, align="RIGHT"):
            return ps(
                f"np_{row_idx}",
                8,
                color=MUTED if inactive else colors.HexColor("#333"),
                align=align,
                leading=11,
            )

        if is_fully_inactive:
            has_inactive = True
            name_html = f"{name_base}  <font color='{muted_clr.hexval()}' size='7'><b>{label}</b></font>"
            if is_cancelled and getattr(oi, "cancel_reason", None):
                name_html += f"<br/><font size='7' color='#888'>Reason: {oi.cancel_reason}</font>"
            if is_return:
                try:
                    name_html += f"<br/><font size='7' color='#888'>Return: {oi.return_request.reason}</font>"
                except Exception:
                    pass
            item_data.append(
                [
                    Paragraph(
                        name_html, ps(f"fn_{row_idx}", 8, color=MUTED, leading=12)
                    ),
                    Paragraph(
                        variant_str, ps(f"vn_{row_idx}", 7, color=MUTED, leading=11)
                    ),
                    Paragraph(
                        f"<strike>{oi.quantity}</strike>", num_ps(True, "CENTER")
                    ),
                    Paragraph(f"<strike>Rs.{oi.unit_price:.2f}</strike>", num_ps(True)),
                    Paragraph(offer_str, num_ps(True)),
                    Paragraph(
                        f"<strike>Rs.{oi.total_price:.2f}</strike> *", num_ps(True)
                    ),
                ]
            )
            bg = AMBER_BG if is_cancelled else ROSE_BG
            item_cmds += [
                ("BACKGROUND", (0, row_idx), (-1, row_idx), bg),
                ("TEXTCOLOR", (0, row_idx), (-1, row_idx), muted_clr),
            ]
            row_idx += 1

        elif has_partial_cancel:
            has_inactive = True
            per_unit_net = oi.total_price / oi.quantity
            active_price = (per_unit_net * oi.active_quantity).quantize(Decimal("0.01"))
            cancel_price = (per_unit_net * oi.cancelled_quantity).quantize(
                Decimal("0.01")
            )

            item_data.append(
                [
                    Paragraph(name_base, ps(f"an_{row_idx}", 8, leading=11)),
                    Paragraph(
                        variant_str, ps(f"av_{row_idx}", 7, color=MUTED, leading=11)
                    ),
                    Paragraph(str(oi.active_quantity), num_ps(align="CENTER")),
                    Paragraph(f"Rs.{oi.unit_price:.2f}", num_ps()),
                    Paragraph(offer_str, num_ps()),
                    Paragraph(f"Rs.{active_price:.2f}", num_ps()),
                ]
            )
            row_idx += 1

            item_data.append(
                [
                    Paragraph(
                        f"{name_base}  <font color='{AMBER_TXT.hexval()}' size='7'><b>[PARTIALLY CANCELLED]</b></font>",
                        ps(f"cn_{row_idx}", 8, color=MUTED, leading=11),
                    ),
                    Paragraph(
                        variant_str, ps(f"cv_{row_idx}", 7, color=MUTED, leading=11)
                    ),
                    Paragraph(
                        f"<strike>{oi.cancelled_quantity}</strike>",
                        num_ps(True, "CENTER"),
                    ),
                    Paragraph(f"<strike>Rs.{oi.unit_price:.2f}</strike>", num_ps(True)),
                    Paragraph(offer_str, num_ps(True)),
                    Paragraph(
                        f"<strike>Rs.{cancel_price:.2f}</strike> *", num_ps(True)
                    ),
                ]
            )
            item_cmds += [
                ("BACKGROUND", (0, row_idx), (-1, row_idx), AMBER_BG),
                ("TEXTCOLOR", (0, row_idx), (-1, row_idx), AMBER_TXT),
            ]
            row_idx += 1

        else:
            item_data.append(
                [
                    Paragraph(name_base, ps(f"nn_{row_idx}", 8, leading=11)),
                    Paragraph(
                        variant_str, ps(f"nv_{row_idx}", 7, color=MUTED, leading=11)
                    ),
                    Paragraph(str(oi.quantity), num_ps(align="CENTER")),
                    Paragraph(f"Rs.{oi.unit_price:.2f}", num_ps()),
                    Paragraph(offer_str, num_ps()),
                    Paragraph(f"Rs.{oi.total_price:.2f}", num_ps()),
                ]
            )
            row_idx += 1

    items_tbl = Table(item_data, colWidths=[170, 80, 35, 65, 40, 75])
    items_tbl.setStyle(TableStyle(item_cmds))
    elements.append(items_tbl)
    elements.append(Spacer(1, 10))

    if has_inactive:
        elements.append(
            Paragraph(
                "* Cancelled / returned items are excluded from the Grand Total.",
                ps("fn_note", 7, color=MUTED, leading=10),
            )
        )
        elements.append(Spacer(1, 8))

    def tot_row(
        label,
        value,
        label_clr=colors.HexColor("#333"),
        val_clr=colors.HexColor("#333"),
        bold=False,
    ):
        lp = ps(f"tl_{label}", 8, bold=bold, color=label_clr, align="RIGHT", leading=11)
        vp = ps(f"tv_{label}", 8, bold=bold, color=val_clr, align="RIGHT", leading=11)
        return ["", Paragraph(label, lp), Paragraph(value, vp)]

    totals = []

    raw_subtotal = sum(
        oi.unit_price * oi.active_quantity
        for oi in order.order_items.filter(item_status="ACTIVE")
    )
    totals.append(tot_row("Items Subtotal", f"Rs.{raw_subtotal:.2f}"))

    if order.discount_amount and order.discount_amount > 0:
        totals.append(
            tot_row(
                "Offer Discount",
                f"- Rs.{order.discount_amount:.2f}",
                val_clr=GREEN_TXT,
            )
        )
        offer_names = []
        for oi in order.order_items.filter(item_status="ACTIVE"):
            pct = get_max_offer_discount_percent(oi.variant.product)
            if pct:
                offer_names.append(f"{oi.variant.product.product_name} ({pct}% off)")
        if offer_names:
            for oname in offer_names[:4]:  
                totals.append(
                    tot_row(
                        f"  • {oname}",
                        "",
                        label_clr=MUTED,
                    )
                )

    if order.coupon_discount and order.coupon_discount > 0:
        coupon = order.coupon
        if coupon:
            dtype = coupon.discount_type
            dval = coupon.discount_value
            min_a = coupon.min_order_amount
            if dtype == "PERCENT":
                cond_str = f"{int(dval)}% off — min order Rs.{min_a:.0f}"
            else:
                cond_str = f"Rs.{dval:.0f} flat off — min order Rs.{min_a:.0f}"
            if coupon.max_discount:
                cond_str += f", max cap Rs.{coupon.max_discount:.0f}"
            totals.append(
                tot_row(
                    f"Coupon: {coupon.code}",
                    f"- Rs.{order.coupon_discount:.2f}",
                    val_clr=GREEN_TXT,
                )
            )
            totals.append(
                tot_row(
                    f"  Condition: {cond_str}",
                    "",
                    label_clr=MUTED,
                )
            )
        else:
            totals.append(
                tot_row(
                    "Coupon Discount",
                    f"- Rs.{order.coupon_discount:.2f}",
                    val_clr=GREEN_TXT,
                )
            )

    if order.shipping_charge and order.shipping_charge > 0:
        totals.append(tot_row("Shipping Charge", f"+ Rs.{order.shipping_charge:.2f}"))
    else:
        totals.append(tot_row("Shipping Charge", "FREE", val_clr=GREEN_TXT))

    n = len(totals)
    totals.append(
        [
            "",
            Paragraph(
                "<b>GRAND TOTAL</b>",
                ps("gtl", 10, bold=True, color=colors.white, align="RIGHT"),
            ),
            Paragraph(
                f"<b>Rs.{order.final_amount:.2f}</b>",
                ps("gtv", 10, bold=True, color=colors.white, align="RIGHT"),
            ),
        ]
    )

    tot_tbl = Table(totals, colWidths=[185, 215, 75])
    tot_cmds = [
        ("FONTNAME", (0, 0), (-1, -1), "Arial"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (1, n), (-1, n), PINK),
        ("TOPPADDING", (1, n), (-1, n), 9),
        ("BOTTOMPADDING", (1, n), (-1, n), 9),
        ("LINEABOVE", (1, n), (-1, n), 1, PINK),
    ]
    tot_tbl.setStyle(TableStyle(tot_cmds))
    elements.append(tot_tbl)
    elements.append(Spacer(1, 16))

    elements.append(
        Table(
            [
                [
                    Paragraph(
                        "Thank you for shopping with Kiddora!  |  www.kiddora.com  |  support@kiddora.com",
                        ps("ft", 7, color=MUTED, align="CENTER"),
                    )
                ]
            ],
            colWidths=[475],
        )
    )

    doc.build(elements)
    buffer.seek(0)
    return HttpResponse(
        buffer,
        content_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="invoice_{order.order_id}.pdf"'
        },
    )
