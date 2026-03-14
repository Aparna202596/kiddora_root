from __future__ import annotations

import io
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from accounts.decorators import admin_login_required
from accounts.models import UserAddress
from products.models import ProductVariant
from products.utils.pagination import paginate_queryset
from shopcore.models import Cart, CartItem, Order, OrderItem, Wishlist, WishlistItem

# ─────────────────────────────────────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_cart(user):
    try:
        return user.cart
    except Cart.DoesNotExist:
        return None


def _stock_for(variant: ProductVariant) -> int:
    try:
        return variant.inventory.quantity_available
    except Exception:
        return 0


def _variant_is_available(variant: ProductVariant) -> bool:
    p   = variant.product
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


# ─────────────────────────────────────────────────────────────────────────────
# USER: CHECKOUT
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
def checkout(request):
    """
    GET  – render checkout page (addresses, cart summary, price breakdown).
    POST – place COD order.
    """
    cart = _get_cart(request.user)
    if not cart or not cart.items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect("shopcore:cart")

    # ── validate every cart item before showing the checkout page ──────────
    items = cart.items.select_related(
        "variant",
        "variant__product",
        "variant__product__images",
        "variant__product__subcategory",
        "variant__product__subcategory__category",
        "variant__color",
        "variant__age_group",
        "variant__inventory",
    ).order_by("-added_at")

    checkout_items = []
    subtotal       = Decimal("0")
    blocked        = False

    for item in items:
        variant   = item.variant
        available = _variant_is_available(variant)
        stock     = _stock_for(variant)
        product   = variant.product

        if not available or stock == 0 or item.quantity > stock:
            blocked = True

        img_url = None
        img_obj = product.images.filter(is_default=True).first() or product.images.first()
        if img_obj:
            for field in ("image1", "image2", "image3", "image4", "image5"):
                val = getattr(img_obj, field)
                if val:
                    img_url = val.url
                    break

        item_total = product.final_price * item.quantity
        subtotal  += item_total

        checkout_items.append({
            "item":       item,
            "variant":    variant,
            "product":    product,
            "item_total": item_total,
            "available":  available,
            "stock":      stock,
            "img_url":    img_url,
        })

    if blocked:
        messages.error(
            request,
            "Some items in your cart are unavailable or out of stock. "
            "Please update your cart before checking out.",
        )
        return redirect("shopcore:cart")

    # ── addresses ────────────────────────────────────────────────────────────
    addresses       = UserAddress.objects.filter(user=request.user, is_deleted=False)
    default_address = addresses.filter(is_default=True).first() or addresses.first()

    shipping_charge = Decimal("0")   # extend with real logic later
    coupon_discount = Decimal("0")
    grand_total     = subtotal - coupon_discount + shipping_charge

    context = {
        "checkout_items":  checkout_items,
        "addresses":       addresses,
        "default_address": default_address,
        "subtotal":        subtotal,
        "shipping_charge": shipping_charge,
        "coupon_discount": coupon_discount,
        "grand_total":     grand_total,
    }
    return render(request, "cart/checkout.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# USER: PLACE ORDER  (COD)
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
@transaction.atomic
def place_order(request):
    """POST-only.  Creates Order + OrderItems, decrements inventory, clears cart."""
    if request.method != "POST":
        return redirect("shopcore:checkout")

    cart = _get_cart(request.user)
    if not cart or not cart.items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect("shopcore:cart")

    # ── resolve address ───────────────────────────────────────────────────────
    address_id = request.POST.get("address_id")
    if address_id:
        address = get_object_or_404(
            UserAddress, id=address_id, user=request.user, is_deleted=False
        )
    else:
        address = (
            UserAddress.objects.filter(user=request.user, is_deleted=False, is_default=True).first()
            or UserAddress.objects.filter(user=request.user, is_deleted=False).first()
        )

    if not address:
        messages.error(request, "Please add a delivery address before placing an order.")
        return redirect("shopcore:checkout")

    # ── re-validate cart ──────────────────────────────────────────────────────
    items = cart.items.select_related(
        "variant",
        "variant__product",
        "variant__product__subcategory",
        "variant__product__subcategory__category",
        "variant__inventory",
    ).all()

    for item in items:
        if not _variant_is_available(item.variant):
            messages.error(
                request,
                f"'{item.variant.product.product_name}' is no longer available. "
                "Please remove it from your cart.",
            )
            return redirect("shopcore:cart")
        stock = _stock_for(item.variant)
        if stock < item.quantity:
            messages.error(
                request,
                f"Only {stock} unit(s) of '{item.variant.product.product_name}' in stock.",
            )
            return redirect("shopcore:cart")

    # ── compute totals ────────────────────────────────────────────────────────
    subtotal        = sum(
        item.variant.product.final_price * item.quantity for item in items
    )
    shipping_charge = Decimal("0")
    coupon_discount = Decimal("0")
    final_amount    = subtotal - coupon_discount + shipping_charge

    # ── create Order ──────────────────────────────────────────────────────────
    order = Order.objects.create(
        user            = request.user,
        address         = address,
        payment_method  = "COD",
        payment_status  = "PENDING",
        order_status    = "PENDING",
        total_amount    = subtotal,
        discount_amount = Decimal("0"),
        coupon_discount = coupon_discount,
        shipping_charge = shipping_charge,
        final_amount    = final_amount,
    )

    # ── create OrderItems + decrement inventory ───────────────────────────────
    for item in items:
        variant    = item.variant
        product    = variant.product
        unit_price = product.final_price

        OrderItem.objects.create(
            order            = order,
            variant          = variant,
            quantity         = item.quantity,
            unit_price       = unit_price,
            discount_amount  = Decimal("0"),
            # total_price calculated in OrderItem.save()
        )

        # Decrement available stock
        inv = variant.inventory
        inv.quantity_available -= item.quantity
        inv.quantity_sold      += item.quantity
        inv.save()

    # ── clear cart ────────────────────────────────────────────────────────────
    cart.items.all().delete()

    return redirect("shopcore:order_success", order_id=order.order_id)


# ─────────────────────────────────────────────────────────────────────────────
# USER: ORDER SUCCESS PAGE
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    return render(request, "orders/user/order_success.html", {"order": order})


# ─────────────────────────────────────────────────────────────────────────────
# USER: ORDER LIST
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
def user_order_list(request):
    query   = request.GET.get("q", "").strip()
    orders  = Order.objects.filter(user=request.user).order_by("-order_date")

    if query:
        orders = orders.filter(
            Q(order_id__icontains=query)
            | Q(order_status__icontains=query)
            | Q(order_items__variant__product__product_name__icontains=query)
        ).distinct()

    paginator = Paginator(orders, 10)
    page_obj  = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "orders/user/user_order_list.html",
        {
            "page_obj": page_obj,
            "query":    query,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# USER: ORDER DETAIL
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
def user_order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("address", "coupon").prefetch_related(
            "order_items",
            "order_items__variant",
            "order_items__variant__product",
            "order_items__variant__product__images",
            "order_items__variant__color",
            "order_items__variant__age_group",
        ),
        order_id=order_id,
        user=request.user,
    )

    # Attach image URL to each item
    items_with_img = []
    for oi in order.order_items.all():
        product = oi.variant.product
        img_url = None
        img_obj = product.images.filter(is_default=True).first() or product.images.first()
        if img_obj:
            for field in ("image1", "image2", "image3", "image4", "image5"):
                val = getattr(img_obj, field)
                if val:
                    img_url = val.url
                    break
        items_with_img.append({"order_item": oi, "img_url": img_url})

    return render(
        request,
        "orders/user/user_order_detail.html",
        {
            "order":           order,
            "items_with_img":  items_with_img,
            # allow cancel only when PENDING or CONFIRMED
            "can_cancel_order": order.order_status in ("PENDING", "CONFIRMED"),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# USER: CANCEL ENTIRE ORDER
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
@transaction.atomic
def cancel_order(request, order_id):
    """
    POST.  Cancels the whole order if still PENDING / CONFIRMED.
    Restores inventory for each active OrderItem.
    """
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.order_status not in ("PENDING", "CONFIRMED"):
        messages.error(request, "This order cannot be cancelled at its current stage.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if request.method != "POST":
        return render(
            request,
            "orders/user/confirm_cancel_order.html",
            {"order": order},
        )

    reason = request.POST.get("cancel_reason", "").strip()

    # Restore stock for every active item
    for oi in order.order_items.filter(item_status="ACTIVE"):
        try:
            inv = oi.variant.inventory
            inv.quantity_available += oi.quantity
            inv.quantity_sold       = max(0, inv.quantity_sold - oi.quantity)
            inv.save()
        except Exception:
            pass
        oi.item_status  = "CANCELLED"
        oi.cancel_reason = reason or "Order cancelled by user"
        oi.cancelled_at  = timezone.now()
        oi.save()

    order.order_status  = "CANCELLED"
    order.cancel_reason = reason or "Cancelled by user"
    order.cancelled_at  = timezone.now()
    order.save()

    messages.success(request, f"Order {order.order_id} has been cancelled.")
    return redirect("shopcore:user_order_detail", order_id=order.order_id)


# ─────────────────────────────────────────────────────────────────────────────
# USER: CANCEL SINGLE ITEM
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
@transaction.atomic
def cancel_order_item(request, order_id, item_id):
    """Cancel one OrderItem within an order (partial cancellation)."""
    order     = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order, item_status="ACTIVE")

    if order.order_status not in ("PENDING", "CONFIRMED"):
        messages.error(request, "Items in this order can no longer be cancelled.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)

    if request.method != "POST":
        return render(
            request,
            "orders/user/confirm_cancel_item.html",
            {"order": order, "order_item": order_item},
        )

    reason = request.POST.get("cancel_reason", "").strip()

    # Restore stock
    try:
        inv = order_item.variant.inventory
        inv.quantity_available += order_item.quantity
        inv.quantity_sold       = max(0, inv.quantity_sold - order_item.quantity)
        inv.save()
    except Exception:
        pass

    order_item.item_status   = "CANCELLED"
    order_item.cancel_reason = reason or "Item cancelled by user"
    order_item.cancelled_at  = timezone.now()
    order_item.save()

    # If ALL items are now cancelled, cancel the order too
    if not order.order_items.filter(item_status="ACTIVE").exists():
        order.order_status  = "CANCELLED"
        order.cancel_reason = "All items cancelled"
        order.cancelled_at  = timezone.now()
        order.save()

    messages.success(
        request,
        f"Item '{order_item.variant.product.product_name}' has been cancelled.",
    )
    return redirect("shopcore:user_order_detail", order_id=order.order_id)


# ─────────────────────────────────────────────────────────────────────────────
# USER: DOWNLOAD INVOICE  (PDF)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def download_invoice(request, order_id):
    """
    Generate a plain-text invoice as PDF using ReportLab.
    Falls back to a text-based receipt if ReportLab is not installed.
    """
    order = get_object_or_404(
        Order.objects.select_related("address", "user").prefetch_related(
            "order_items__variant__product",
            "order_items__variant__color",
            "order_items__variant__age_group",
        ),
        order_id=order_id,
        user=request.user,
    )

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.pdfgen import canvas as rl_canvas

        buffer = io.BytesIO()
        c      = rl_canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 2 * cm

        def _write(text, font="Helvetica", size=11, indent=2):
            nonlocal y
            c.setFont(font, size)
            c.drawString(indent * cm, y, text)
            y -= size * 0.5 * cm

        _write("KIDDORA – Invoice", font="Helvetica-Bold", size=16)
        _write(f"Order ID   : {order.order_id}")
        _write(f"Order Date : {order.order_date.strftime('%d %b %Y, %I:%M %p')}")
        _write(f"Status     : {order.get_order_status_display()}")
        _write(f"Payment    : {order.get_payment_method_display()}")
        y -= cm

        addr = order.address
        _write("Deliver To:", font="Helvetica-Bold", size=11)
        _write(f"  {addr.full_name}  {addr.phone}")
        _write(f"  {addr.address_line1}")
        if addr.address_line2:
            _write(f"  {addr.address_line2}")
        _write(f"  {addr.city}, {addr.state} – {addr.pincode}")
        y -= cm

        _write("Items:", font="Helvetica-Bold", size=11)
        for oi in order.order_items.all():
            _write(
                f"  {oi.variant.product.product_name} "
                f"({oi.variant.color} / {oi.variant.age_group})  "
                f"x{oi.quantity}   ₹{oi.total_price}"
            )
        y -= 0.5 * cm
        _write(f"Subtotal        : ₹{order.total_amount}")
        _write(f"Discount        : -₹{order.discount_amount}")
        _write(f"Coupon Discount : -₹{order.coupon_discount}")
        _write(f"Shipping        : ₹{order.shipping_charge}")
        _write(f"Grand Total     : ₹{order.final_amount}", font="Helvetica-Bold", size=12)

        c.showPage()
        c.save()
        buffer.seek(0)

        response = HttpResponse(buffer, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="invoice_{order.order_id}.pdf"'
        )
        return response

    except ImportError:
        # Fallback plain-text receipt
        lines = [
            f"KIDDORA – Invoice",
            f"Order ID   : {order.order_id}",
            f"Order Date : {order.order_date.strftime('%d %b %Y')}",
            f"Status     : {order.get_order_status_display()}",
            "",
            "Items:",
        ]
        for oi in order.order_items.all():
            lines.append(
                f"  {oi.variant.product.product_name} x{oi.quantity} = ₹{oi.total_price}"
            )
        lines += [
            f"Grand Total: ₹{order.final_amount}",
        ]
        response = HttpResponse("\n".join(lines), content_type="text/plain")
        response["Content-Disposition"] = (
            f'attachment; filename="invoice_{order.order_id}.txt"'
        )
        return response


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN: ORDER LIST
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_order_list(request):
    """
    List all orders.
    Supports: search (order_id, user email/name), status filter, sort, clear.
    Ordered by newest first by default (Order.Meta already does this, 
    but we honour the sort param for overrides).
    """
    search     = request.GET.get("search", "").strip()
    status_f   = request.GET.get("status", "").strip()
    sort       = request.GET.get("sort", "order_date")
    direction  = request.GET.get("dir", "desc")

    orders = Order.objects.select_related("user", "address").prefetch_related(
        "order_items"
    )

    if search:
        orders = orders.filter(
            Q(order_id__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__phone__icontains=search)
        )

    if status_f:
        orders = orders.filter(order_status=status_f)

    allowed_sorts = {
        "order_date":    "order_date",
        "final_amount":  "final_amount",
        "order_status":  "order_status",
        "user":          "user__email",
    }
    sort_field = allowed_sorts.get(sort, "order_date")
    orders = orders.order_by(
        f"-{sort_field}" if direction == "desc" else sort_field
    )

    page_obj = paginate_queryset(request, orders, 20)

    context = {
        "page_obj":       page_obj,
        "search":         search,
        "status_f":       status_f,
        "sort":           sort,
        "dir":            direction,
        "status_choices": Order.ORDER_STATUS_CHOICES,
    }
    return render(request, "orders/admin/admin_order_list.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN: ORDER DETAIL
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("user", "address", "coupon").prefetch_related(
            "order_items",
            "order_items__variant__product__images",
            "order_items__variant__color",
            "order_items__variant__age_group",
        ),
        order_id=order_id,
    )

    items_with_img = []
    for oi in order.order_items.all():
        product = oi.variant.product
        img_url = None
        img_obj = product.images.filter(is_default=True).first() or product.images.first()
        if img_obj:
            for field in ("image1", "image2", "image3", "image4", "image5"):
                val = getattr(img_obj, field)
                if val:
                    img_url = val.url
                    break
        items_with_img.append({"order_item": oi, "img_url": img_url})

    context = {
        "order":           order,
        "items_with_img":  items_with_img,
        "status_choices":  Order.ORDER_STATUS_CHOICES,
    }
    return render(request, "orders/admin/admin_order_detail.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN: CHANGE ORDER STATUS
# ─────────────────────────────────────────────────────────────────────────────

# Valid forward-only transitions (admin cannot un-deliver, etc.)
_VALID_TRANSITIONS: dict[str, list[str]] = {
    "PENDING":          ["CONFIRMED", "CANCELLED"],
    "CONFIRMED":        ["SHIPPED",   "CANCELLED"],
    "SHIPPED":          ["OUT_FOR_DELIVERY"],
    "OUT_FOR_DELIVERY": ["DELIVERED"],
    "DELIVERED":        [],   # terminal — use return flow for refunds
    "CANCELLED":        [],   # terminal
}


@never_cache
@admin_login_required
@transaction.atomic
def admin_update_order_status(request, order_id):
    """POST.  Updates the order status with basic transition validation."""
    if request.method != "POST":
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    order      = get_object_or_404(Order, order_id=order_id)
    new_status = request.POST.get("order_status", "").strip()

    allowed = _VALID_TRANSITIONS.get(order.order_status, [])
    if new_status not in allowed:
        messages.error(
            request,
            f"Cannot transition from '{order.get_order_status_display()}' "
            f"to '{new_status}'.",
        )
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    old_status         = order.order_status
    order.order_status = new_status

    if new_status == "DELIVERED":
        order.delivered_at    = timezone.now()
        order.payment_status  = "PAID"
    elif new_status == "CANCELLED":
        order.cancelled_at    = timezone.now()
        order.cancel_reason   = request.POST.get("cancel_reason", "Cancelled by admin").strip()
        # Restore inventory for every still-active item
        for oi in order.order_items.filter(item_status="ACTIVE"):
            try:
                inv = oi.variant.inventory
                inv.quantity_available += oi.quantity
                inv.quantity_sold       = max(0, inv.quantity_sold - oi.quantity)
                inv.save()
            except Exception:
                pass
            oi.item_status   = "CANCELLED"
            oi.cancel_reason = order.cancel_reason
            oi.cancelled_at  = timezone.now()
            oi.save()

    order.save()
    messages.success(
        request,
        f"Order {order.order_id} status updated from "
        f"'{old_status}' → '{new_status}'.",
    )
    return redirect("shopcore:admin_order_detail", order_id=order_id)