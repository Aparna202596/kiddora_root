from __future__ import annotations
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
#from shopcore.views.coupon_views import compute_coupon_discount
from accounts.models import UserAddress
from shopcore.models import Cart, CartItem, Order, OrderItem


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def _get_cart(user):
    try:
        return user.cart
    except Cart.DoesNotExist:
        return None


def _variant_is_available(variant) -> bool:
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


def _stock_for(variant) -> int:
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


# ──────────────────────────────────────────────────────────────
# CHECKOUT  (GET)
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
    subtotal       = Decimal("0")
    blocked        = False

    for item in items:
        variant   = item.variant
        available = _variant_is_available(variant)
        stock     = _stock_for(variant)
        product   = variant.product

        if not available or stock == 0 or item.quantity > stock:
            blocked = True

        item_total = product.final_price * item.quantity
        subtotal  += item_total

        checkout_items.append({
            "item":       item,
            "variant":    variant,
            "product":    product,
            "item_total": item_total,
            "available":  available,
            "stock":      stock,
            "img_url":    _img_url_for(product),
        })

    if blocked:
        messages.error(
            request,
            "Some items in your cart are unavailable or out of stock. "
            "Please update your cart before proceeding.",
        )
        return redirect("shopcore:cart")

    # # Coupon
    # coupon_discount = Decimal("0")
    # applied_coupon  = getattr(cart, "coupon", None)
    # if applied_coupon:
    #     try:
    #         if applied_coupon.is_valid():
    #             coupon_discount = compute_coupon_discount(applied_coupon, subtotal)
    #     except Exception:
    #         coupon_discount = Decimal("0")

    addresses = UserAddress.objects.filter(user=request.user, is_deleted=False)
    #addresses = UserAddress.objects.filter(user=request.user)
    default_address = addresses.filter(is_default=True).first() or addresses.first()
    DEFAULT_SHIPPING = Decimal("100") 

    shipping_charge = Decimal("0")
    if subtotal < 499:
        shipping_charge = DEFAULT_SHIPPING

    grand_total = subtotal - Decimal("0") + shipping_charge
    
    #grand_total = subtotal - coupon_discount + shipping_charge

    return render(request, "cart/checkout.html", {
        "checkout_items": checkout_items,
        "addresses":       addresses,
        "default_address": default_address,
        "subtotal":        subtotal,
        "shipping_charge": shipping_charge,
        # "coupon_discount": coupon_discount,
        # "applied_coupon":  applied_coupon,
        "grand_total":     grand_total,
    })


# ──────────────────────────────────────────────────────────────
# PLACE ORDER  (POST)
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

    # Resolve address
    address_id = request.POST.get("address_id")
    if address_id:
        #address = get_object_or_404(UserAddress, id=address_id, user=request.user)
        address = get_object_or_404( UserAddress, id=address_id, user=request.user, is_deleted=False)
    else:
        address = (
            UserAddress.objects.filter(user=request.user, is_deleted=False, is_default=True).first()
            or UserAddress.objects.filter(user=request.user, is_deleted=False).first()
        )
        # address = (
        #     UserAddress.objects.filter(user=request.user, is_default=True).first()
        #     or UserAddress.objects.filter(user=request.user).first()
        # )
    if not address:
        messages.error(request, "Please add a delivery address before placing an order.")
        return redirect("shopcore:checkout")

    # Re-validate cart
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

    # Totals
    subtotal        = sum(i.variant.product.final_price * i.quantity for i in items)
    shipping_charge = Decimal("0")
    coupon_discount = Decimal("0")
    applied_coupon  = getattr(cart, "coupon", None)

    if applied_coupon:
        try:
            if applied_coupon.is_valid():
                #coupon_discount = compute_coupon_discount(applied_coupon, subtotal)
                applied_coupon.used_count += 1
                applied_coupon.used_by.add(request.user)
                applied_coupon.save(update_fields=["used_count"])
        except Exception:
            coupon_discount = Decimal("0")
            applied_coupon  = None

    final_amount = subtotal - coupon_discount + shipping_charge

    # Create Order
    order = Order.objects.create(
        user            = request.user,
        address         = address,
        payment_method  = request.POST.get("payment_method", "COD"),
        payment_status  = "PENDING",
        order_status    = "PENDING",
        coupon          = applied_coupon,
        coupon_discount = coupon_discount,
        total_amount    = subtotal,
        discount_amount = Decimal("0"),
        shipping_charge = shipping_charge,
        final_amount    = final_amount,
    )

    # Copy address snapshot (if model has these fields)
    _snapshot = {
        "snapshot_name":    getattr(address, "full_name", ""),
        "snapshot_phone":   getattr(address, "phone", ""),
        "snapshot_line1":   getattr(address, "address_line1", ""),
        "snapshot_line2":   getattr(address, "address_line2", ""),
        "snapshot_city":    getattr(address, "city", ""),
        "snapshot_state":   getattr(address, "state", ""),
        "snapshot_pincode": getattr(address, "pincode", ""),
    }
    _dirty = [f for f, v in _snapshot.items() if hasattr(order, f)]
    if _dirty:
        for f in _dirty:
            setattr(order, f, _snapshot[f])
        order.save(update_fields=_dirty)

    # Create OrderItems + decrement stock
    for item in items:
        variant    = item.variant
        unit_price = variant.product.final_price
        OrderItem.objects.create(
            order           = order,
            variant         = variant,
            quantity        = item.quantity,
            unit_price      = unit_price,
            discount_amount = Decimal("0"),
        )
        inv = variant.inventory
        inv.quantity_available = max(0, inv.quantity_available - item.quantity)
        inv.quantity_sold      += item.quantity
        inv.save(update_fields=["quantity_available", "quantity_sold"])

    # Clear cart
    cart.items.all().delete()
    if hasattr(cart, "coupon") and cart.coupon:
        cart.coupon = None
        cart.save(update_fields=["coupon"])

    return redirect("shopcore:order_success", order_id=order.order_id)


# ──────────────────────────────────────────────────────────────
# ORDER SUCCESS
# ──────────────────────────────────────────────────────────────

@never_cache
@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    return render(request, "orders/user/order_success.html", {"order": order})