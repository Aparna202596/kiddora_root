from __future__ import annotations

import io
import os
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from accounts.decorators import admin_login_required, user_login_required
from accounts.models import UserAddress
from shopcore.models import Cart, Order, OrderItem, Offer
from products.models import ProductVariant


# ─────────────────────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────────────────────

def _get_cart(user):
    try:
        return user.cart
    except Cart.DoesNotExist:
        return None


def _variant_is_available(variant: ProductVariant) -> bool:
    try:
        p   = variant.product
        sub = p.subcategory
        cat = sub.category
        return (
            variant.is_active
            and p.is_active   and not p.is_deleted
            and sub.is_active and not sub.is_deleted
            and cat.is_active and not cat.is_deleted
        )
    except Exception:
        return False


def _stock_for(variant: ProductVariant) -> int:
    try:
        return variant.inventory.quantity_available
    except Exception:
        return 0


def _img_url_for(product) -> str | None:
    img_obj = (
        product.images.filter(is_default=True).first()
        or product.images.first()
    )
    if img_obj:
        for field in ("image1", "image2", "image3", "image4", "image5"):
            val = getattr(img_obj, field)
            if val:
                return val.url
    return None


def _recalculate_order_amount(order: Order) -> None:
    """Recalculate totals after an item is cancelled."""
    active_items = order.order_items.filter(item_status="ACTIVE")
    subtotal = sum(item.unit_price * item.quantity for item in active_items)

    shipping_charge = Decimal("100") if Decimal("0") < subtotal < Decimal("1000") else Decimal("0")

    order.total_amount    = subtotal
    order.shipping_charge = shipping_charge

    total_deductions  = order.discount_amount + order.coupon_discount
    order.final_amount = max(Decimal("0"), subtotal - total_deductions + shipping_charge)

    order.save(update_fields=["total_amount", "shipping_charge", "final_amount"])


def get_max_offer_discount_percent(product) -> int:
    """
    Returns the highest applicable offer percentage for this product.
    Compares product-specific and category-specific offers; picks the larger.
    """
    if not product:
        return 0

    now = timezone.now()
    active_offers = Offer.objects.filter(
        is_active=True, is_deleted=False, start_date__lte=now
    )

    product_offer  = active_offers.filter(offer_type="PRODUCT", product=product).first()
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


# ─────────────────────────────────────────────────────────────
# USER: ORDER LIST
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
def user_order_list(request):
    query  = request.GET.get("q", "").strip()
    orders = Order.objects.filter(user=request.user).order_by("-order_date")

    if query:
        orders = orders.filter(
            Q(order_id__icontains=query)
            | Q(order_status__icontains=query)
            | Q(order_items__variant__product__product_name__icontains=query)
        ).distinct()

    page_obj = Paginator(orders, 10).get_page(request.GET.get("page"))
    return render(request, "orders/user/user_order_list.html", {
        "page_obj": page_obj,
        "query":    query,
    })


# ─────────────────────────────────────────────────────────────
# USER: ORDER DETAIL
# ─────────────────────────────────────────────────────────────

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

    return render(request, "orders/user/user_order_detail.html", {
        "order":            order,
        "items_with_img":   items_with_img,
        "can_cancel_order": order.order_status in ("PENDING", "CONFIRMED"),
    })


# ─────────────────────────────────────────────────────────────
# USER: CANCEL ENTIRE ORDER
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@transaction.atomic
def cancel_order(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.order_status == "OUT_FOR_DELIVERY":
        messages.error(
            request,
            "Your order is out for delivery. You cannot cancel the order now."
        )
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if order.order_status not in ("PENDING", "CONFIRMED", "SHIPPED"):
        messages.error(request, "This order cannot be cancelled at its current stage.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if request.method != "POST":
        return render(request, "orders/user/confirm_cancel_order.html", {"order": order})

    reason = request.POST.get("cancel_reason", "").strip()

    for oi in order.order_items.filter(item_status="ACTIVE"):
        try:
            inv = oi.variant.inventory
            inv.quantity_available += oi.quantity
            inv.quantity_sold = max(0, inv.quantity_sold - oi.quantity)
            inv.save()
        except Exception:
            pass
        oi.item_status   = "CANCELLED"
        oi.cancel_reason = reason or "Order cancelled by user"
        oi.cancelled_at  = timezone.now()
        oi.save()

    order.order_status  = "CANCELLED"
    order.cancel_reason = reason or "Cancelled by user"
    order.cancelled_at  = timezone.now()

    if order.payment_status == "PAID":
        if order.payment_method in ("PAYPAL", "WALLET"):
            from payments.views.wallet_helpers import credit_refund_to_wallet
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

# ─────────────────────────────────────────────────────────────
# USER: CANCEL SINGLE ITEM
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@transaction.atomic
def cancel_order_item(request, order_id, item_id):
    order      = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order, item_status="ACTIVE")

    if order.order_status == "OUT_FOR_DELIVERY":
        messages.error(
            request,
            "Your order is out for delivery. You cannot cancel the order now."
        )
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if order.order_status not in ("PENDING", "CONFIRMED", "SHIPPED"):
        messages.error(request, "Items in this order can no longer be cancelled.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if request.method != "POST":
        return render(request, "orders/user/confirm_cancel_item.html", {
            "order": order, "order_item": order_item,
        })

    reason = request.POST.get("cancel_reason", "").strip()

    try:
        inv = order_item.variant.inventory
        inv.quantity_available += order_item.quantity
        inv.quantity_sold = max(0, inv.quantity_sold - order_item.quantity)
        inv.save()
    except Exception:
        pass

    item_refund_amount = order_item.total_price
    if order.payment_status == "PAID" and order.payment_method in ("PAYPAL", "WALLET"):
        from payments.views.wallet_helpers import credit_refund_to_wallet
        credit_refund_to_wallet(
            user=order.user,
            amount=item_refund_amount,
            description=(
                f"Partial refund for cancelled item "
                f"'{order_item.variant.product.product_name}' "
                f"in order {order.order_id}"
            ),
            reference_type="CANCEL",
            reference_id=str(order.order_id),
            order=order,
        )

    order_item.item_status   = "CANCELLED"
    order_item.cancel_reason = reason or "Item cancelled by user"
    order_item.cancelled_at  = timezone.now()
    order_item.save()

    _recalculate_order_amount(order)

    # Check if all items are now cancelled
    remaining_active = order.order_items.filter(item_status="ACTIVE")
    if not remaining_active.exists():
        order.order_status   = "CANCELLED"
        order.cancel_reason  = "All items cancelled"
        order.cancelled_at   = timezone.now()

        if order.payment_method in ("PAYPAL", "WALLET") and order.payment_status == "PAID":
            order.payment_status = "REFUNDED"
        elif order.payment_method == "COD":
            order.payment_status = "CANCELLED"
        order.save(update_fields=["order_status", "cancel_reason", "cancelled_at", "payment_status"])
    else:

        if order.payment_method in ("PAYPAL", "WALLET") and order.payment_status == "PAID":
            order.payment_status = "PARTIALLY_REFUNDED"
            order.save(update_fields=["payment_status"])

    messages.success(
        request,
        f"Item '{order_item.variant.product.product_name}' cancelled."
        + (f" ₹{item_refund_amount:.2f} refunded to your wallet." 
           if order.payment_method in ("PAYPAL", "WALLET") else ""),
    )
    return redirect("shopcore:user_order_detail", order_id=order.order_id)

# ─────────────────────────────────────────────────────────────
# USER: REQUEST RETURN (only after DELIVERED)
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@transaction.atomic
def request_return(request, order_id, item_id):
    from shopcore.models import Return  # local import to avoid circular

    order      = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order)

    if order.order_status != "DELIVERED":
        messages.error(request, "Returns are only allowed after the order is delivered.")
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


# ─────────────────────────────────────────────────────────────
# USER: DOWNLOAD INVOICE (PDF)
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
def download_invoice(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=A4)

    font_path = "C:/Windows/Fonts/arial.ttf"
    pdfmetrics.registerFont(TTFont("Arial", font_path))

    styles        = getSampleStyleSheet()
    normal_style  = ParagraphStyle(
        "CustomNormal", parent=styles["Normal"],
        fontName="Arial", spaceAfter=8, leading=14,
    )
    heading_style = ParagraphStyle(
        "Heading", parent=styles["Heading2"],
        fontName="Arial", spaceAfter=12,
    )

    elements = []

    # Logo
    logo_path = os.path.join(settings.BASE_DIR, "static/images/kiddora_logo.PNG")
    if os.path.exists(logo_path):
        elements.append(Image(logo_path, width=120, height=50))
    elements.append(Spacer(1, 15))

    # Title
    elements.append(Paragraph("<b>KIDDORA INVOICE</b>", styles["Title"]))
    elements.append(Spacer(1, 20))

    # Order info
    elements.append(Paragraph(f"<b>Order ID:</b> {order.order_id}", normal_style))
    elements.append(Paragraph(
        f"<b>Date:</b> {order.order_date.strftime('%d %b %Y')}", normal_style
    ))
    elements.append(Paragraph(
        f"<b>Status:</b> {order.get_order_status_display()}", normal_style
    ))
    elements.append(Spacer(1, 20))

    # Customer details
    address = order.address
    name    = getattr(address, "full_name", None) or getattr(order.user, "full_name", "")
    phone   = getattr(address, "phone", None) or getattr(order.user, "phone", "")
    full_address = (
        f"{getattr(address, 'address_line1', '')}, "
        f"{getattr(address, 'address_line2', '')}, "
        f"{getattr(address, 'city', '')}, "
        f"{getattr(address, 'state', '')} - {getattr(address, 'pincode', '')} "
        f"{getattr(address, 'country', '')}"
    )

    elements.append(Paragraph("<b>Customer Details</b>", heading_style))
    elements.append(Paragraph(f"<b>Name:</b> {name}", normal_style))
    elements.append(Paragraph(f"<b>Phone:</b> {phone}", normal_style))
    elements.append(Paragraph(f"<b>Address:</b> {full_address}", normal_style))
    elements.append(Spacer(1, 25))

    # Items table
    data = [["Order ID", "Item", "Qty", "Price (₹)"]]
    for oi in order.order_items.all():
        data.append([
            str(order.order_id),
            oi.variant.product.product_name,
            str(oi.quantity),
            f"₹{oi.unit_price * oi.quantity:.2f}",
        ])
    data.append(["", "", "Grand Total", f"₹{order.final_amount:.2f}"])

    table = Table(data, colWidths=[100, 200, 60, 100])
    table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0),  (-1, 0),  colors.HexColor("#f06292")),
        ("TEXTCOLOR",     (0, 0),  (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0),  (-1, -1), "Arial"),
        ("ALIGN",         (0, 0),  (-1, 0),  "CENTER"),
        ("GRID",          (0, 0),  (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS",(0, 1),  (-1, -2), [colors.whitesmoke, colors.lightgrey]),
        ("ALIGN",         (2, 1),  (2, -1),  "CENTER"),
        ("ALIGN",         (3, 1),  (3, -1),  "RIGHT"),
        ("BOTTOMPADDING", (0, 0),  (-1, -1), 10),
        ("TOPPADDING",    (0, 0),  (-1, -1), 10),
        ("BACKGROUND",    (0, -1), (-1, -1), colors.HexColor("#f06292")),
    ]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)

    return HttpResponse(
        buffer,
        content_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="invoice_{order.order_id}.pdf"'
        },
    )


# ─────────────────────────────────────────────────────────────
# ADMIN: ORDER LIST
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_order_list(request):
    search   = request.GET.get("search", "").strip()
    status_f = request.GET.get("status", "").strip()
    sort     = request.GET.get("sort", "order_date")
    direction= request.GET.get("dir", "desc")

    orders = (
        Order.objects
        .select_related("user", "address")
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

    page_obj = Paginator(orders, 20).get_page(request.GET.get("page"))

    return render(request, "orders/admin/admin_order_list.html", {
        "page_obj":       page_obj,
        "search":         search,
        "status_f":       status_f,
        "sort":           sort,
        "dir":            direction,
        "status_choices": Order.ORDER_STATUS_CHOICES,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: ORDER DETAIL
# ─────────────────────────────────────────────────────────────

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

    return render(request, "orders/admin/admin_order_detail.html", {
        "order":              order,
        "items_with_img":     items_with_img,
        "status_choices":     Order.ORDER_STATUS_CHOICES,
        "item_status_choices": OrderItem.ITEM_STATUS_CHOICES,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: UPDATE ORDER STATUS
# Allowed transitions: PENDING → CONFIRMED → SHIPPED →
#                      OUT_FOR_DELIVERY → DELIVERED → (terminal)
#                      Any non-terminal → CANCELLED
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
@transaction.atomic
def admin_update_order_status(request, order_id):
    if request.method != "POST":
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    order      = get_object_or_404(Order, order_id=order_id)
    new_status = request.POST.get("order_status", "").strip()

    valid_transitions = {
        "PENDING":          ["CONFIRMED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
        "CONFIRMED":        ["SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
        "SHIPPED":          ["OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
        "OUT_FOR_DELIVERY": ["DELIVERED"],
        "DELIVERED":        [],
        "CANCELLED":        [],
        "RETURNED":         [],
    }

    allowed = valid_transitions.get(order.order_status, [])
    if new_status not in allowed:
        messages.error(
            request,
            f"Cannot change status from "
            f"'{order.get_order_status_display()}' to '{new_status}'.",
        )
        return redirect("shopcore:admin_order_detail", order_id=order.order_id)

    old_status        = order.order_status
    order.order_status = new_status

    if new_status == "DELIVERED":
        order.delivered_at = timezone.now()
        order.order_items.filter(item_status="ACTIVE").update(
            delivered_at=timezone.now(),
        )
        # ✅ Only COD gets marked PAID on delivery
        if order.payment_method == "COD":
            order.payment_status = "PAID"
            # Update the COD Payment record too
            from payments.models import Payment
            Payment.objects.filter(
                order=order,
                payment_method="COD",
                payment_status="PENDING"
            ).update(
                payment_status="PAID",
                completed_at=timezone.now(),
            )

    elif new_status == "CANCELLED":
        order.cancelled_at  = timezone.now()
        order.cancel_reason = request.POST.get("cancel_reason", "Cancelled by admin").strip()
        for oi in order.order_items.filter(item_status="ACTIVE"):
            try:
                inv = oi.variant.inventory
                inv.quantity_available += oi.quantity
                inv.quantity_sold = max(0, inv.quantity_sold - oi.quantity)
                inv.save()
            except Exception:
                pass
            oi.item_status   = "CANCELLED"
            oi.cancel_reason = order.cancel_reason
            oi.cancelled_at  = timezone.now()
            oi.save()

        # ✅ Refund if already paid
        if order.payment_status == "PAID":
            if order.payment_method in ("PAYPAL", "WALLET"):
                from payments.views.wallet_helpers import credit_refund_to_wallet
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


# ─────────────────────────────────────────────────────────────
# ADMIN: UPDATE INDIVIDUAL ITEM STATUS
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
@transaction.atomic
def admin_update_item_status(request, order_id, item_id):
    if request.method != "POST":
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    order      = get_object_or_404(Order, order_id=order_id)
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


# ─────────────────────────────────────────────────────────────
# ADMIN: HANDLE RETURN REQUEST
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
@transaction.atomic
def admin_handle_return(request, return_id):
    from shopcore.models import Return  # local import

    ret        = get_object_or_404(Return, id=return_id)
    order_item = ret.order_item
    order      = order_item.order

    if request.method != "POST":
        return render(
            request,
            "orders/admin/admin_handle_return.html",
            {"ret": ret, "order": order, "order_item": order_item},
        )

    action     = request.POST.get("action", "")
    admin_note = request.POST.get("admin_note", "").strip()

    if action == "APPROVE":
        ret.status     = "APPROVED"
        ret.admin_note = admin_note
        ret.updated_at = timezone.now()
        ret.save()

        order_item.item_status = "RETURN_APPROVED"
        order_item.save(update_fields=["item_status"])

        # Refund to wallet
        refund_amount = order_item.total_price
        try:
            wallet = order.user.wallet
            wallet.balance += refund_amount
            wallet.save(update_fields=["balance"])
        except Exception:
            pass

        ret.refund_amount = refund_amount
        ret.status        = "REFUNDED"
        ret.refunded_at   = timezone.now()
        ret.save()

        order_item.item_status = "REFUNDED"
        order_item.save(update_fields=["item_status"])

        messages.success(
            request,
            f"Return approved and ₹{refund_amount:.2f} refunded to wallet.",
        )

    elif action == "REJECT":
        ret.status     = "REJECTED"
        ret.admin_note = admin_note
        ret.updated_at = timezone.now()
        ret.save()

        order_item.item_status = "RETURN_REJECTED"
        order_item.save(update_fields=["item_status"])

        messages.success(request, "Return request rejected.")

    else:
        messages.error(request, "Invalid action.")

    return redirect("shopcore:admin_order_detail", order_id=order.order_id)