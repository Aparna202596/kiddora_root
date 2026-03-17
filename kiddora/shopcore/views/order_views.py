# shopcore/views/order_views.py
from __future__ import annotations
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
#from shopcore.views.coupon_views import compute_coupon_discount
from accounts.decorators import admin_login_required
from accounts.models import UserAddress
from shopcore.models import Cart, CartItem, Order, OrderItem
from products.models import ProductVariant
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import io

# ──────────────────────────────────────────────────────────────
# HELPERS (shared between user & admin)
# ──────────────────────────────────────────────────────────────
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
            and p.is_active and not p.is_deleted
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

def _img_url_for(product):
    img_obj = product.images.filter(is_default=True).first() or product.images.first()
    if img_obj:
        for field in ("image1", "image2", "image3", "image4", "image5"):
            val = getattr(img_obj, field)
            if val:
                return val.url
    return None

def _recalculate_order_amount(order):
    """
    Recalculate order totals based on ACTIVE items only.
    Also update shipping charge based on subtotal.
    """

    active_items = order.order_items.filter(item_status="ACTIVE")

    subtotal = sum(item.unit_price * item.quantity for item in active_items)

    # Shipping rule
    shipping_charge = Decimal("0")
    if 0 < subtotal < Decimal("499"):
        shipping_charge = Decimal("100")

    order.total_amount = subtotal
    order.shipping_charge = shipping_charge

    # Calculate final amount ensuring it doesn't go negative
    total_deductions = order.discount_amount + order.coupon_discount
    order.final_amount = max(Decimal("0"), subtotal - total_deductions + shipping_charge)

    order.save(update_fields=[
        "total_amount",
        "shipping_charge",
        "final_amount",
    ])
# ──────────────────────────────────────────────────────────────
# USER: CHECKOUT (GET)
# ──────────────────────────────────────────────────────────────
@never_cache
@login_required
def checkout(request):
    cart = _get_cart(request.user)
    if not cart or not cart.items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect("shopcore:cart")

    items = cart.items.select_related(
        "variant__product",
        "variant__product__subcategory",
        "variant__product__subcategory__category",
        "variant__color",
        "variant__age_group",
        "variant__inventory",
    ).prefetch_related("variant__product__images").order_by("-added_at")

    checkout_items = []
    subtotal = Decimal("0")
    blocked = False

    for item in items:
        variant = item.variant
        available = _variant_is_available(variant)
        stock = _stock_for(variant)
        product = variant.product
        if not available or stock == 0 or item.quantity > stock:
            blocked = True
        item_total = product.final_price * item.quantity
        subtotal += item_total
        checkout_items.append({
            "item": item,
            "variant": variant,
            "product": product,
            "item_total": item_total,
            "available": available,
            "stock": stock,
            "img_url": _img_url_for(product),
        })

    if blocked:
        messages.error(
            request,
            "Some items in your cart are unavailable or out of stock. "
            "Please update your cart before proceeding."
        )
        return redirect("shopcore:cart")

    # # Coupon
    # coupon_discount = Decimal("0")
    # applied_coupon = getattr(cart, "coupon", None)
    # if applied_coupon:
    #     try:
    #         if applied_coupon.is_valid():
    #             coupon_discount = sum(
    #                 compute_coupon_discount(applied_coupon, item.variant.product.final_price * item.quantity)
    #                 for item in items
    #             )
    #     except Exception:
    #         coupon_discount = Decimal("0")

    addresses = UserAddress.objects.filter(user=request.user, is_deleted=False)
    default_address = addresses.filter(is_default=True).first() or addresses.first()
    shipping_charge = Decimal("0")
    grand_total = subtotal + shipping_charge
    # grand_total = subtotal - coupon_discount + shipping_charge

    context = {
        "checkout_items": checkout_items,
        "addresses": addresses,
        "default_address": default_address,
        "subtotal": subtotal,
        "shipping_charge": shipping_charge,
        # "coupon_discount": coupon_discount,
        # "applied_coupon": applied_coupon,
        "grand_total": grand_total,
    }
    return render(request, "cart/checkout.html", context)

# ──────────────────────────────────────────────────────────────
# USER: PLACE ORDER (POST – COD only for now)
# ──────────────────────────────────────────────────────────────
@never_cache
@login_required
@transaction.atomic
def place_order(request):
    if request.method != "POST":
        return redirect("shopcore:checkout")

    cart = _get_cart(request.user)
    if not cart or not cart.items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect("shopcore:cart")

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

    items = cart.items.select_related(
        "variant__product",
        "variant__product__subcategory",
        "variant__product__subcategory__category",
        "variant__inventory",
    ).all()

    for item in items:
        if not _variant_is_available(item.variant):
            messages.error(
                request,
                f"'{item.variant.product.product_name}' is no longer available."
            )
            return redirect("shopcore:cart")
        stock = _stock_for(item.variant)
        if stock < item.quantity:
            messages.error(
                request,
                f"Only {stock} unit(s) of '{item.variant.product.product_name}' in stock."
            )
            return redirect("shopcore:cart")

    subtotal = sum(i.variant.product.final_price * i.quantity for i in items)
    shipping_charge = Decimal("0")
    coupon_discount = Decimal("0")
    applied_coupon = getattr(cart, "coupon", None)
    if applied_coupon:
        try:
            if applied_coupon.is_valid():
                # coupon_discount = compute_coupon_discount(applied_coupon, subtotal)
                applied_coupon.used_count += 1
                applied_coupon.used_by.add(request.user)
                applied_coupon.save(update_fields=["used_count"])
        except Exception:
            coupon_discount = Decimal("0")

    final_amount = subtotal - coupon_discount + shipping_charge

    # COD limit check (from your requirements)
    if final_amount > Decimal("1000") and request.POST.get("payment_method", "COD") == "COD":
        messages.error(request, "Orders above ₹1000 cannot use Cash on Delivery.")
        return redirect("shopcore:checkout")

    order = Order.objects.create(
        user=request.user,
        address=address,
        payment_method=request.POST.get("payment_method", "COD"),
        payment_status="PENDING",
        order_status="PENDING",
        coupon=applied_coupon,
        coupon_discount=coupon_discount,
        total_amount=subtotal,
        discount_amount=Decimal("0"),
        shipping_charge=shipping_charge,
        final_amount=final_amount,
    )

    for item in items:
        variant = item.variant
        OrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=item.quantity,
            unit_price=variant.product.final_price,
            discount_amount=Decimal("0"),
        )
        inv = variant.inventory
        inv.quantity_available = max(0, inv.quantity_available - item.quantity)
        inv.quantity_sold += item.quantity
        inv.save(update_fields=["quantity_available", "quantity_sold"])

    cart.items.all().delete()
    if hasattr(cart, "coupon") and cart.coupon:
        cart.coupon = None
        cart.save(update_fields=["coupon"])

    return redirect("shopcore:order_success", order_id=order.order_id)

# ──────────────────────────────────────────────────────────────
# USER: ORDER SUCCESS
# ──────────────────────────────────────────────────────────────
@never_cache
@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    return render(request, "orders/user/order_success.html", {"order": order})

# ──────────────────────────────────────────────────────────────
# USER: ORDER LIST
# ──────────────────────────────────────────────────────────────
@never_cache
@login_required
def user_order_list(request):
    query = request.GET.get("q", "").strip()
    orders = Order.objects.filter(user=request.user).order_by("-order_date")
    if query:
        orders = orders.filter(
            Q(order_id__icontains=query) |
            Q(order_status__icontains=query) |
            Q(order_items__variant__product__product_name__icontains=query)
        ).distinct()
    paginator = Paginator(orders, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "orders/user/user_order_list.html", {
        "page_obj": page_obj,
        "query": query,
    })

# ──────────────────────────────────────────────────────────────
# USER: ORDER DETAIL
# ──────────────────────────────────────────────────────────────
@never_cache
@login_required
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
    items_with_img = []
    for oi in order.order_items.all():
        product = oi.variant.product
        img_url = _img_url_for(product)
        items_with_img.append({"order_item": oi, "img_url": img_url})
    context = {
        "order": order,
        "items_with_img": items_with_img,
        "can_cancel_order": order.order_status in ("PENDING", "CONFIRMED"),
    }
    return render(request, "orders/user/user_order_detail.html", context)

# ──────────────────────────────────────────────────────────────
# USER: CANCEL WHOLE ORDER
# ──────────────────────────────────────────────────────────────
@never_cache
@login_required
@transaction.atomic
def cancel_order(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    if order.order_status not in ("PENDING", "CONFIRMED"):
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
        oi.item_status = "CANCELLED"
        oi.cancel_reason = reason or "Order cancelled by user"
        oi.cancelled_at = timezone.now()
        oi.save()
    order.order_status = "CANCELLED"
    order.cancel_reason = reason or "Cancelled by user"
    order.cancelled_at = timezone.now()
    order.save()
    messages.success(request, f"Order {order.order_id} has been cancelled.")
    return redirect("shopcore:user_order_detail", order_id=order.order_id)

# ──────────────────────────────────────────────────────────────
# USER: CANCEL SINGLE ITEM
# ──────────────────────────────────────────────────────────────
@never_cache
@login_required
@transaction.atomic
def cancel_order_item(request, order_id, item_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order, item_status="ACTIVE")
    if order.order_status not in ("PENDING", "CONFIRMED"):
        messages.error(request, "Items in this order can no longer be cancelled.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)
    if request.method != "POST":
        return render(request, "orders/user/confirm_cancel_item.html", {
            "order": order,
            "order_item": order_item,
        })
    reason = request.POST.get("cancel_reason", "").strip()
    try:
        inv = order_item.variant.inventory
        inv.quantity_available += order_item.quantity
        inv.quantity_sold = max(0, inv.quantity_sold - order_item.quantity)
        inv.save()
    except Exception:
        pass
    order_item.item_status = "CANCELLED"
    order_item.cancel_reason = reason or "Item cancelled by user"
    order_item.cancelled_at = timezone.now()
    order_item.save()

    # Recalculate order totals
    _recalculate_order_amount(order)

    # If all items cancelled -> cancel order
    if not order.order_items.filter(item_status="ACTIVE").exists():
        order.order_status = "CANCELLED"
        order.cancel_reason = "All items cancelled"
        order.cancelled_at = timezone.now()
        order.save(update_fields=["order_status", "cancel_reason", "cancelled_at"])
    messages.success(request, f"Item '{order_item.variant.product.product_name}' cancelled.")
    return redirect("shopcore:user_order_detail", order_id=order.order_id)

# ──────────────────────────────────────────────────────────────
# USER: DOWNLOAD INVOICE
# ──────────────────────────────────────────────────────────────
@login_required
def download_invoice(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    try:
        
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 50
        c.drawString(100, y, f"KIDDORA Invoice - {order.order_id}")
        y -= 30
        c.drawString(100, y, f"Date: {order.order_date.strftime('%d %b %Y')}")
        y -= 30
        c.drawString(100, y, f"Status: {order.get_order_status_display()}")
        y -= 50
        for oi in order.order_items.all():
            c.drawString(100, y, f"{oi.variant.product.product_name} x{oi.quantity} = ₹{oi.total_price}")
            y -= 20
        y -= 30
        c.drawString(100, y, f"Grand Total: ₹{order.final_amount}")
        c.showPage()
        c.save()
        buffer.seek(0)
        response = HttpResponse(buffer, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="invoice_{order.order_id}.pdf"'
        return response
    except ImportError:
        content = f"KIDDORA Invoice\nOrder ID: {order.order_id}\nTotal: ₹{order.final_amount}"
        response = HttpResponse(content, content_type="text/plain")
        response["Content-Disposition"] = f'attachment; filename="invoice_{order.order_id}.txt"'
        return response

# ──────────────────────────────────────────────────────────────
# ADMIN: ORDER LIST
# ──────────────────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_order_list(request):
    search = request.GET.get("search", "").strip()
    status_f = request.GET.get("status", "").strip()
    sort = request.GET.get("sort", "order_date")
    dir = request.GET.get("dir", "desc")
    orders = Order.objects.select_related("user", "address").prefetch_related("order_items").order_by("-order_date")
    if search:
        orders = orders.filter(
            Q(order_id__icontains=search) |
            Q(user__email__icontains=search) |
            Q(user__full_name__icontains=search)
        )
    if status_f:
        orders = orders.filter(order_status=status_f)
    if sort in ["order_date", "final_amount", "order_status"]:
        order_field = f"-{sort}" if dir == "desc" else sort
        orders = orders.order_by(order_field)
    page_obj = Paginator(orders, 20).get_page(request.GET.get("page"))
    context = {
        "page_obj": page_obj,
        "search": search,
        "status_f": status_f,
        "sort": sort,
        "dir": dir,
        "status_choices": Order.ORDER_STATUS_CHOICES,
    }
    return render(request, "orders/admin/admin_order_list.html", context)

# ──────────────────────────────────────────────────────────────
# ADMIN: ORDER DETAIL
# ──────────────────────────────────────────────────────────────
# shopcore/views/order_views.py

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
    
    items_with_img = []
    for oi in order.order_items.all():
        product = oi.variant.product
        img_url = _img_url_for(product)
        items_with_img.append({"order_item": oi, "img_url": img_url})

    context = {
        "order": order,
        "items_with_img": items_with_img,
        "status_choices": Order.ORDER_STATUS_CHOICES,                
        "item_status_choices": OrderItem.ITEM_STATUS_CHOICES,        
    }
    return render(request, "orders/admin/admin_order_detail.html", context)
# ──────────────────────────────────────────────────────────────
# ADMIN: UPDATE ORDER STATUS
# ──────────────────────────────────────────────────────────────
@never_cache
@admin_login_required
@transaction.atomic
def admin_update_order_status(request, order_id):
    if request.method != "POST":
        return redirect("shopcore:admin_order_detail", order_id=order_id)
    order = get_object_or_404(Order, order_id=order_id)
    new_status = request.POST.get("order_status", "").strip()
    valid_transitions = {
        "PENDING": ["CONFIRMED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
        "CONFIRMED": ["SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
        "SHIPPED": ["OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
        "OUT_FOR_DELIVERY": ["DELIVERED", "CANCELLED"],
        "DELIVERED": [],
        "CANCELLED": [],
    }
    allowed = valid_transitions.get(order.order_status, [])
    if new_status not in allowed:
        messages.error(
            request,
            f"Cannot change status from '{order.get_order_status_display()}' to '{new_status}'."
        )
        print(order.order_status)
        print(new_status)
        return redirect("shopcore:admin_order_detail", order_id=order.order_id)
    old_status = order.order_status
    order.order_status = new_status
    print(order.order_status)
    print(new_status)
    if new_status == "DELIVERED":
        order.delivered_at = timezone.now()
        order.payment_status = "PAID"
    elif new_status == "CANCELLED":
        order.cancelled_at = timezone.now()
        order.cancel_reason = request.POST.get("cancel_reason", "Cancelled by admin").strip()
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
    order.save()
    messages.success(
        request,
        f"Order {order.order_id} status updated: {old_status} → {new_status}"
    )
    return redirect("shopcore:admin_order_detail", order_id=order.order_id)

@never_cache
@admin_login_required
@transaction.atomic
def admin_update_item_status(request, order_id, item_id):

    if request.method != "POST":
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    order = get_object_or_404(Order, order_id=order_id)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order)

    new_status = request.POST.get("item_status")

    if new_status not in dict(OrderItem.ITEM_STATUS_CHOICES):
        messages.error(request, "Invalid item status.")
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    order_item.item_status = new_status
    order_item.save()

    if new_status == "CANCELLED":
        _recalculate_order_amount(order)

    messages.success(
        request,
        f"Item '{order_item.variant.product.product_name}' updated to {new_status}"
    )

    return redirect("shopcore:admin_order_detail", order_id=order_id)