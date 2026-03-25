from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.decorators import user_login_required
from accounts.models import UserAddress
from payments.models import Wallet
from shopcore.models import Cart, Coupon, CouponUsage, Order, OrderItem
from shopcore.views.coupon_views import compute_coupon_discount
from shopcore.views.offer_views import get_max_offer_discount_percent


# ─────────────────────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────────────────────

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


def _address_to_dict(addr) -> dict:
    return {
        "id":            addr.id,
        "address_line1": addr.address_line1,
        "address_line2": addr.address_line2 or "",
        "city":          addr.city,
        "state":         addr.state,
        "country":       addr.country,
        "pincode":       addr.pincode,
        "address_type":  addr.address_type,
        "is_default":    addr.is_default,
        "display_name":  addr.user.full_name or addr.user.email,
        "display_phone": addr.user.phone or "",
    }


def _validate_address_post(post) -> list[str]:
    errors = []
    if not post.get("address_line1", "").strip():
        errors.append("Address Line 1 is required.")
    if not post.get("city", "").strip():
        errors.append("City is required.")
    if not post.get("state", "").strip():
        errors.append("State is required.")
    if not post.get("country", "").strip():
        errors.append("Country is required.")
    pincode = post.get("pincode", "").strip()
    if not pincode or not pincode.isdigit() or len(pincode) not in (5, 6):
        errors.append("Enter a valid pincode (5 or 6 digits).")
    if post.get("address_type", "").strip() not in ("home", "work", "other"):
        errors.append("Address type must be Home, Work, or Other.")
    return errors


def _wallet_balance(user) -> Decimal:
    """Return wallet balance. Creates the wallet row if it doesn't exist yet."""
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet.balance


def _user_has_exhausted_coupon(coupon: Coupon, user) -> bool:
    try:
        usage = coupon.usages.get(user=user)
        return usage.times_used >= coupon.usage_limit
    except CouponUsage.DoesNotExist:
        return False


def _session_coupon(request, subtotal: Decimal):
    code = request.session.get("applied_coupon_code")
    if not code:
        return None, Decimal("0")

    try:
        coupon = Coupon.objects.get(code=code, is_active=True, is_deleted=False)
    except Coupon.DoesNotExist:
        request.session.pop("applied_coupon_code", None)
        request.session.pop("applied_coupon_discount", None)
        return None, Decimal("0")

    if (
        coupon.is_valid()
        and not _user_has_exhausted_coupon(coupon, request.user)
        and subtotal >= coupon.min_order_amount
    ):
        return coupon, compute_coupon_discount(coupon, subtotal)

    request.session.pop("applied_coupon_code", None)
    request.session.pop("applied_coupon_discount", None)
    return None, Decimal("0")


def _exhausted_coupon_ids(user) -> list[int]:
    return [
        cu.coupon_id
        for cu in CouponUsage.objects.filter(user=user).select_related("coupon")
        if cu.times_used >= cu.coupon.usage_limit
    ]


# ─────────────────────────────────────────────────────────────
# AJAX: SAVE NEW ADDRESS
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@require_POST
def save_new_address(request):
    errors = _validate_address_post(request.POST)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    set_default = request.POST.get("set_default") == "1"
    if set_default:
        UserAddress.objects.filter(
            user=request.user, is_deleted=False
        ).update(is_default=False)

    address = UserAddress.objects.create(
        user          = request.user,
        address_line1 = request.POST.get("address_line1", "").strip(),
        address_line2 = request.POST.get("address_line2", "").strip(),
        city          = request.POST.get("city", "").strip(),
        state         = request.POST.get("state", "").strip(),
        country       = request.POST.get("country", "").strip(),
        pincode       = request.POST.get("pincode", "").strip(),
        address_type  = request.POST.get("address_type", "home").strip(),
        is_default    = set_default,
    )
    return JsonResponse({"success": True, "address": _address_to_dict(address)})


# ─────────────────────────────────────────────────────────────
# AJAX: EDIT EXISTING ADDRESS
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@require_POST
def edit_address(request, address_id):
    address = get_object_or_404(
        UserAddress, id=address_id, user=request.user, is_deleted=False
    )
    errors = _validate_address_post(request.POST)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    set_default = request.POST.get("set_default") == "1"
    if set_default:
        UserAddress.objects.filter(
            user=request.user, is_deleted=False
        ).update(is_default=False)

    address.address_line1 = request.POST.get("address_line1", "").strip()
    address.address_line2 = request.POST.get("address_line2", "").strip()
    address.city          = request.POST.get("city", "").strip()
    address.state         = request.POST.get("state", "").strip()
    address.country       = request.POST.get("country", "").strip()
    address.pincode       = request.POST.get("pincode", "").strip()
    address.address_type  = request.POST.get("address_type", "home").strip()
    address.is_default    = set_default
    address.save()
    return JsonResponse({"success": True, "address": _address_to_dict(address)})


# ─────────────────────────────────────────────────────────────
# CHECKOUT  (GET)
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
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

    checkout_items       = []
    subtotal             = Decimal("0")
    offer_discount_total = Decimal("0")
    blocked              = False

    for item in items:
        variant   = item.variant
        product   = variant.product
        available = _variant_is_available(variant)
        stock     = _stock_for(variant)

        if not available or stock == 0 or item.quantity > stock:
            blocked = True

        base_price       = product.final_price
        offer_pct        = get_max_offer_discount_percent(product)
        offer_pct_dec    = Decimal(str(offer_pct))
        discounted_price = base_price * (Decimal("1") - offer_pct_dec / 100)

        item_base_total     = base_price * item.quantity
        item_offer_discount = (base_price - discounted_price) * item.quantity
        item_final_total    = discounted_price * item.quantity

        subtotal             += item_base_total
        offer_discount_total += item_offer_discount

        checkout_items.append({
            "item":             item,
            "variant":          variant,
            "product":          product,
            "unit_price":       base_price,
            "discounted_price": discounted_price,
            "item_total":       item_final_total,
            "base_item_total":  item_base_total,
            "offer_discount":   item_offer_discount,
            "offer_pct":        offer_pct,
            "available":        available,
            "stock":            stock,
            "img_url":          _img_url_for(product),
        })

    if blocked:
        messages.error(
            request,
            "Some items in your cart are unavailable or out of stock. "
            "Please update your cart before proceeding.",
        )
        return redirect("shopcore:cart")

    price_after_offers = subtotal - offer_discount_total
    shipping_charge = (
        Decimal("0") if price_after_offers >= Decimal("1000") else Decimal("100")
    )

    applied_coupon, coupon_discount = _session_coupon(request, price_after_offers)
    grand_total = price_after_offers - coupon_discount + shipping_charge

    cod_blocked = grand_total > Decimal("1000")

    # Safe wallet lookup — creates wallet row if user has none yet
    wallet_balance    = _wallet_balance(request.user)
    wallet_sufficient = wallet_balance >= grand_total

    now = timezone.now()
    available_coupons = Coupon.objects.filter(
        is_active=True,
        is_deleted=False,
        start_date__lte=now,
        expiry_date__gte=now,
    ).exclude(id__in=_exhausted_coupon_ids(request.user))

    addresses       = UserAddress.objects.filter(user=request.user, is_deleted=False)
    default_address = addresses.filter(is_default=True).first() or addresses.first()

    return render(request, "cart/checkout.html", {
        "checkout_items":       checkout_items,
        "addresses":            addresses,
        "default_address":      default_address,
        "subtotal":             subtotal,
        "offer_discount_total": offer_discount_total,
        "price_after_offers":   price_after_offers,
        "shipping_charge":      shipping_charge,
        "coupon_discount":      coupon_discount,
        "applied_coupon":       applied_coupon,
        "grand_total":          grand_total,
        "cod_blocked":          cod_blocked,
        "wallet_balance":       wallet_balance,
        "wallet_sufficient":    wallet_sufficient,
        "available_coupons":    available_coupons,
        "address_type_choices": UserAddress.ADDRESS_TYPE_CHOICES,
    })


# ─────────────────────────────────────────────────────────────
# PLACE ORDER  (POST)
# COD    → shopcore:order_success
# WALLET → payments:pay_with_wallet
# PAYPAL → payments:initiate_paypal_payment
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# PLACE ORDER  (POST)
# ─────────────────────────────────────────────────────────────
@never_cache
@user_login_required
@transaction.atomic
def place_order(request):
    if request.method != "POST":
        return redirect("shopcore:checkout")

    cart = _get_cart(request.user)
    if not cart or not cart.items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect("shopcore:cart")

    payment_method = request.POST.get("payment_method", "COD").upper()
    if payment_method not in ("COD", "WALLET", "PAYPAL"):
        messages.error(request, "Invalid payment method selected.")
        return redirect("shopcore:checkout")

    # ── Address ───────────────────────────────────────────────
    address_id = request.POST.get("address_id")
    if address_id:
        address = get_object_or_404(
            UserAddress, id=address_id, user=request.user, is_deleted=False
        )
    elif request.POST.get("address_line1"):
        errs = _validate_address_post(request.POST)
        if errs:
            messages.error(request, " ".join(errs))
            return redirect("shopcore:checkout")
        set_default = bool(request.POST.get("set_default"))
        if set_default:
            UserAddress.objects.filter(
                user=request.user, is_deleted=False
            ).update(is_default=False)
        address = UserAddress.objects.create(
            user          = request.user,
            address_line1 = request.POST.get("address_line1", "").strip(),
            address_line2 = request.POST.get("address_line2", "").strip(),
            city          = request.POST.get("city", "").strip(),
            state         = request.POST.get("state", "").strip(),
            country       = request.POST.get("country", "").strip(),
            pincode       = request.POST.get("pincode", "").strip(),
            address_type  = request.POST.get("address_type", "home").strip(),
            is_default    = set_default,
        )
    else:
        address = (
            UserAddress.objects.filter(user=request.user, is_deleted=False, is_default=True).first()
            or UserAddress.objects.filter(user=request.user, is_deleted=False).first()
        )
        if not address:
            messages.error(request, "Please add a delivery address before placing an order.")
            return redirect("shopcore:checkout")

    # ── Re-validate cart items ────────────────────────────────
    items = cart.items.select_related(
        "variant__product",
        "variant__product__subcategory",
        "variant__product__subcategory__category",
        "variant__inventory",
    ).all()

    for item in items:
        if not _variant_is_available(item.variant):
            messages.error(request, f"'{item.variant.product.product_name}' is no longer available.")
            return redirect("shopcore:cart")
        stock = _stock_for(item.variant)
        if stock < item.quantity:
            messages.error(request, f"Only {stock} unit(s) of '{item.variant.product.product_name}' left in stock.")
            return redirect("shopcore:cart")

    # ── Calculate Totals ──────────────────────────────────────
    subtotal             = Decimal("0")
    offer_discount_total = Decimal("0")
    item_offer_data: dict[int, Decimal] = {}

    for item in items:
        base      = item.variant.product.final_price * item.quantity
        offer_pct = get_max_offer_discount_percent(item.variant.product)
        item_disc = base * Decimal(str(offer_pct)) / 100
        subtotal             += base
        offer_discount_total += item_disc
        item_offer_data[item.variant_id] = item_disc

    price_after_offers = subtotal - offer_discount_total
    shipping_charge    = Decimal("100") if price_after_offers < Decimal("1000") else Decimal("0")

    applied_coupon, coupon_discount = _session_coupon(request, price_after_offers)
    final_amount = price_after_offers - coupon_discount + shipping_charge

    # ── Guards ────────────────────────────────────────────────
    if payment_method == "COD" and final_amount > Decimal("1000"):
        messages.error(request, "Cash on Delivery is not available for orders above ₹1,000.")
        return redirect("shopcore:checkout")

    if payment_method == "WALLET":
        balance = _wallet_balance(request.user)
        if balance < final_amount:
            messages.error(request, f"Insufficient wallet balance (₹{balance:.2f}).")
            return redirect("shopcore:checkout")

    # ── CREATE ORDER ONLY FOR COD ─────────────────────────────
    order = None
    if payment_method == "COD":
        order = Order.objects.create(
            user            = request.user,
            address         = address,
            payment_method  = "COD",
            payment_status  = "PAID",           # COD is treated as paid
            order_status    = "PENDING",
            coupon          = applied_coupon,
            coupon_discount = coupon_discount,
            total_amount    = subtotal,
            discount_amount = offer_discount_total,
            shipping_charge = shipping_charge,
            final_amount    = final_amount,
        )

        # Create OrderItems + deduct stock for COD
        for item in items:
            variant    = item.variant
            base_price = variant.product.final_price
            item_disc  = item_offer_data.get(item.variant_id, Decimal("0"))

            OrderItem.objects.create(
                order           = order,
                variant         = variant,
                quantity        = item.quantity,
                unit_price      = base_price,
                discount_amount = item_disc,
            )

            inv = variant.inventory
            inv.quantity_available = max(0, inv.quantity_available - item.quantity)
            inv.quantity_sold     += item.quantity
            inv.save(update_fields=["quantity_available", "quantity_sold"])

        # Coupon usage
        if applied_coupon:
            usage, _ = CouponUsage.objects.get_or_create(coupon=applied_coupon, user=request.user)
            usage.times_used += 1
            usage.save(update_fields=["times_used"])
            applied_coupon.used_count += 1
            applied_coupon.save(update_fields=["used_count"])

        # Clear cart
        cart.items.all().delete()
        request.session.pop("applied_coupon_code", None)
        request.session.pop("applied_coupon_discount", None)

        return redirect("shopcore:order_success", order_id=order.order_id)

    # ── For Online Payments (PayPal / Wallet) ─────────────────
    # Do NOT create order yet
    request.session['pending_order_data'] = {
        'payment_method': payment_method,
        'address_id': address.id,
        'final_amount': str(final_amount),
        'subtotal': str(subtotal),
        'offer_discount_total': str(offer_discount_total),
        'shipping_charge': str(shipping_charge),
        'coupon_id': applied_coupon.id if applied_coupon else None,
        'coupon_discount': str(coupon_discount),
    }

    # Clear cart
    cart.items.all().delete()
    request.session.pop("applied_coupon_code", None)
    request.session.pop("applied_coupon_discount", None)

    if payment_method == "WALLET":
        return redirect("payments:pay_with_wallet")           # No order_id needed
    else:
        # For PayPal: redirect to a version that does NOT require order_id
        return redirect("payments:initiate_paypal_payment_no_order")
# ─────────────────────────────────────────────────────────────
# ORDER SUCCESS
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    return render(request, "orders/user/order_success.html", {"order": order})