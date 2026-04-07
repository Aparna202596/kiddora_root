from __future__ import annotations

from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from accounts.decorators import user_login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction
from decimal import Decimal

from shopcore.views.coupon_views import compute_coupon_discount
from shopcore.views.offer_views import get_max_offer_discount_percent, get_offer_discount_detail

from accounts.models import UserAddress
from payments.models import Wallet, Payment
from shopcore.models import Cart, Coupon, CouponUsage, Order, OrderItem, ReferralUse


# ────────────────────────────────────────────────── HELPER FUNCTIONS ──────────────────────────────────────────────────

def _get_cart(user):
    try:
        return user.cart
    except Cart.DoesNotExist:
        return None


def _variant_is_available(variant) -> bool:
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
        "id": addr.id,
        "address_line1": addr.address_line1,
        "address_line2": addr.address_line2 or "",
        "city": addr.city,
        "state": addr.state,
        "country": addr.country,
        "pincode": addr.pincode,
        "address_type": addr.address_type,
        "is_default": addr.is_default,
        "display_name": addr.user.full_name or addr.user.email,
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


# ────────────────────────────────────────────────────────────────────────────
# TASK 4 — Re-validate coupon eligibility and free-shipping after a
#           cancellation or return reduces the active order total.
# ────────────────────────────────────────────────────────────────────────────

def revalidate_order_after_item_change(order: Order) -> dict:
    """
    Called whenever an item is cancelled or a return is processed on an order.

    Recalculates the remaining order total from non-cancelled/returned items,
    then checks:
      1. Whether the applied coupon is still valid at the new subtotal.
         If not, the coupon discount is zeroed out and the coupon is detached.
      2. Whether free-shipping still applies at the new subtotal.
         If not, the correct shipping charge is applied.

    Returns a dict:
        coupon_invalidated  – bool
        shipping_changed    – bool
        new_coupon_discount – Decimal
        new_shipping_charge – Decimal
        new_final_amount    – Decimal
    """
    result = {
        "coupon_invalidated": False,
        "shipping_changed": False,
        "new_coupon_discount": order.coupon_discount,
        "new_shipping_charge": order.shipping_charge,
        "new_final_amount": order.final_amount,
    }

    # Sum up only active (non-cancelled, non-returned) items
    active_items = order.order_items.filter(
        item_status__in=("PENDING", "CONFIRMED", "SHIPPED", "DELIVERED")
    ).select_related("variant__product")

    remaining_subtotal = Decimal("0")
    remaining_offer_discount = Decimal("0")

    for oi in active_items:
        base = oi.unit_price * oi.quantity
        # TASK 3: always use the larger of product / category offer
        offer_pct = get_max_offer_discount_percent(oi.variant.product)
        item_disc = base * Decimal(str(offer_pct)) / 100
        remaining_subtotal += base
        remaining_offer_discount += item_disc

    price_after_offers = remaining_subtotal - remaining_offer_discount

    # ── 1. Coupon re-validation ───────────────────────────────────────────
    new_coupon_discount = Decimal("0")
    if order.coupon:
        coupon = order.coupon
        if coupon.is_valid() and price_after_offers >= coupon.min_order_amount:
            new_coupon_discount = compute_coupon_discount(coupon, price_after_offers)
        else:
            # Coupon condition no longer met → detach it
            result["coupon_invalidated"] = True
            order.coupon = None
            new_coupon_discount = Decimal("0")

    result["new_coupon_discount"] = new_coupon_discount

    # ── 2. Shipping re-validation ─────────────────────────────────────────
    # Use a temporary Order instance just to call calculate_shipping()
    temp_order = Order(
        total_amount=price_after_offers,
        discount_amount=remaining_offer_discount,
        coupon_discount=new_coupon_discount,
    )
    new_shipping = temp_order.calculate_shipping()

    if new_shipping != order.shipping_charge:
        result["shipping_changed"] = True
    result["new_shipping_charge"] = new_shipping

    # ── 3. Persist changes ────────────────────────────────────────────────
    new_final = price_after_offers - new_coupon_discount + new_shipping
    result["new_final_amount"] = new_final

    order.total_amount = remaining_subtotal
    order.discount_amount = remaining_offer_discount
    order.coupon_discount = new_coupon_discount
    order.shipping_charge = new_shipping
    order.final_amount = new_final
    order.save(update_fields=[
        "total_amount", "discount_amount", "coupon_discount",
        "shipping_charge", "final_amount", "coupon",
    ])

    return result


# ────────────────────────────────────────────────── SAVE NEW ADDRESS ──────────────────────────────────────────────────

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
        user=request.user,
        address_line1=request.POST.get("address_line1", "").strip(),
        address_line2=request.POST.get("address_line2", "").strip(),
        city=request.POST.get("city", "").strip(),
        state=request.POST.get("state", "").strip(),
        country=request.POST.get("country", "").strip(),
        pincode=request.POST.get("pincode", "").strip(),
        address_type=request.POST.get("address_type", "home").strip(),
        is_default=set_default,
    )
    return JsonResponse({"success": True, "address": _address_to_dict(address)})


# ────────────────────────────────────────────────── EDIT ADDRESS ──────────────────────────────────────────────────

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
    address.city = request.POST.get("city", "").strip()
    address.state = request.POST.get("state", "").strip()
    address.country = request.POST.get("country", "").strip()
    address.pincode = request.POST.get("pincode", "").strip()
    address.address_type = request.POST.get("address_type", "home").strip()
    address.is_default = set_default
    address.save()
    return JsonResponse({"success": True, "address": _address_to_dict(address)})


# ────────────────────────────────────────────────── CHECKOUT PAGE (GET) ──────────────────────────────────────────────────

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

    checkout_items = []
    subtotal = Decimal("0")
    offer_discount_total = Decimal("0")
    blocked = False

    for item in items:
        variant = item.variant
        product = variant.product
        available = _variant_is_available(variant)
        stock = _stock_for(variant)

        if not available or stock == 0 or item.quantity > stock:
            blocked = True

        base_price = product.final_price

        # TASK 3: get_offer_discount_detail picks the larger of product vs category offer
        offer_detail = get_offer_discount_detail(product)
        offer_pct = offer_detail["discount_percent"]
        offer_pct_dec = Decimal(str(offer_pct))
        discounted_price = base_price * (Decimal("1") - offer_pct_dec / 100)

        item_base_total = base_price * item.quantity
        item_offer_discount = (base_price - discounted_price) * item.quantity
        item_final_total = discounted_price * item.quantity

        subtotal += item_base_total
        offer_discount_total += item_offer_discount

        checkout_items.append({
            "item": item,
            "variant": variant,
            "product": product,
            "unit_price": base_price,
            "discounted_price": discounted_price,
            "item_total": item_final_total,
            "base_item_total": item_base_total,
            "offer_discount": item_offer_discount,
            "offer_pct": offer_pct,
            # TASK 3: breakdown context — which offer type won and why
            "offer_type": offer_detail["offer_type"],           # "PRODUCT", "CATEGORY", or None
            "product_offer_pct": offer_detail["product_percent"],
            "category_offer_pct": offer_detail["category_percent"],
            "available": available,
            "stock": stock,
            "img_url": _img_url_for(product),
        })

    if blocked:
        messages.error(
            request,
            "Some items in your cart are unavailable or out of stock. "
            "Please update your cart before proceeding.",
        )
        return redirect("shopcore:cart")

    price_after_offers = subtotal - offer_discount_total

    # Coupon from session
    applied_coupon, coupon_discount = _session_coupon(request, price_after_offers)

    # Shipping
    temp_order = Order(
        total_amount=price_after_offers,
        discount_amount=offer_discount_total,
        coupon_discount=coupon_discount,
    )
    shipping_charge = temp_order.calculate_shipping()

    grand_total = price_after_offers - coupon_discount + shipping_charge
    cod_blocked = grand_total > Decimal("1000")

    wallet_balance = _wallet_balance(request.user)
    wallet_sufficient = wallet_balance >= grand_total

    # ── TASK 1 & TASK 2: Available coupons (PUBLIC + user's own REFERRAL rewards) ─
    now = timezone.now()

    # Coupon given to THIS user as the new user who signed up via referral
    new_user_referral_coupon_ids = ReferralUse.objects.filter(
        referred_user=request.user
    ).values_list("new_user_coupon_id", flat=True)

    # Coupon given to THIS user as the referrer who brought someone in
    referrer_coupon_ids = ReferralUse.objects.filter(
        referral_code__user=request.user
    ).values_list("coupon_awarded_id", flat=True)

    exhausted_ids = _exhausted_coupon_ids(request.user)

    available_coupons = (
        Coupon.objects.filter(
            is_active=True,
            is_deleted=False,
            start_date__lte=now,
            expiry_date__gte=now,
        )
        .filter(
            Q(coupon_type="PUBLIC")
            | Q(coupon_type="REFERRAL", id__in=new_user_referral_coupon_ids)
            | Q(coupon_type="REFERRAL", id__in=referrer_coupon_ids)
        )
        .exclude(id__in=exhausted_ids)
        .distinct()
    )

    # Tag each coupon so the template can show "referral reward" labels
    tagged_coupons = []
    new_user_ids_list = list(new_user_referral_coupon_ids)
    referrer_ids_list = list(referrer_coupon_ids)
    for c in available_coupons:
        role = None
        if c.coupon_type == "REFERRAL":
            if c.id in new_user_ids_list:
                role = "new_user"    # welcome reward for THIS user
            elif c.id in referrer_ids_list:
                role = "referrer"   # reward for referring someone
        tagged_coupons.append({"coupon": c, "referral_role": role})

    addresses = UserAddress.objects.filter(user=request.user, is_deleted=False)
    default_address = addresses.filter(is_default=True).first() or addresses.first()

    # TASK 2: structured price breakdown dict for the checkout summary panel
    price_breakdown = {
        "subtotal": subtotal,                          # MRP total (before any discounts)
        "offer_discount": offer_discount_total,        # savings from product/category offers
        "price_after_offers": price_after_offers,      # subtotal after offers applied
        "coupon_discount": coupon_discount,            # savings from coupon
        "shipping_charge": shipping_charge,            # 0 if free shipping
        "grand_total": grand_total,                    # final amount payable
        "free_shipping": shipping_charge == Decimal("0"),
        "free_shipping_threshold": Order.FREE_SHIPPING_THRESHOLD,
        "amount_to_free_shipping": max(
            Decimal("0"), Order.FREE_SHIPPING_THRESHOLD - price_after_offers
        ),
    }

    return render(request, "cart/checkout.html", {
        "checkout_items": checkout_items,
        "addresses": addresses,
        "default_address": default_address,
        # Individual fields kept for backward-compat with existing template references
        "subtotal": subtotal,
        "offer_discount_total": offer_discount_total,
        "price_after_offers": price_after_offers,
        "shipping_charge": shipping_charge,
        "coupon_discount": coupon_discount,
        "applied_coupon": applied_coupon,
        "grand_total": grand_total,
        "cod_blocked": cod_blocked,
        "wallet_balance": wallet_balance,
        "wallet_sufficient": wallet_sufficient,
        "available_coupons": available_coupons,
        "tagged_coupons": tagged_coupons,           # TASK 1 & 2: tagged with referral_role
        "address_type_choices": UserAddress.ADDRESS_TYPE_CHOICES,
        # TASK 2: structured breakdown for the checkout summary panel
        "price_breakdown": price_breakdown,
    })


# ────────────────────────────────────────────────── PLACE ORDER (POST) ──────────────────────────────────────────────────

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

    # ── Address ───────────────────────────────────────────────────────────
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
            user=request.user,
            address_line1=request.POST.get("address_line1", "").strip(),
            address_line2=request.POST.get("address_line2", "").strip(),
            city=request.POST.get("city", "").strip(),
            state=request.POST.get("state", "").strip(),
            country=request.POST.get("country", "").strip(),
            pincode=request.POST.get("pincode", "").strip(),
            address_type=request.POST.get("address_type", "home").strip(),
            is_default=set_default,
        )
    else:
        address = (
            UserAddress.objects.filter(
                user=request.user, is_deleted=False, is_default=True
            ).first()
            or UserAddress.objects.filter(user=request.user, is_deleted=False).first()
        )
        if not address:
            messages.error(request, "Please add a delivery address before placing an order.")
            return redirect("shopcore:checkout")

    # ── Stock validation ──────────────────────────────────────────────────
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
                f"'{item.variant.product.product_name}' is no longer available.",
            )
            return redirect("shopcore:cart")
        stock = _stock_for(item.variant)
        if stock < item.quantity:
            messages.error(
                request,
                f"Only {stock} unit(s) of '{item.variant.product.product_name}' left.",
            )
            return redirect("shopcore:cart")

    # ── TASK 3: Totals — best of product vs category offer per item ───────
    subtotal = Decimal("0")
    offer_discount_total = Decimal("0")
    item_offer_data: dict[int, Decimal] = {}

    for item in items:
        base = item.variant.product.final_price * item.quantity
        offer_pct = get_max_offer_discount_percent(item.variant.product)
        item_disc = base * Decimal(str(offer_pct)) / 100
        subtotal += base
        offer_discount_total += item_disc
        item_offer_data[item.variant_id] = item_disc

    price_after_offers = subtotal - offer_discount_total

    applied_coupon, coupon_discount = _session_coupon(request, price_after_offers)

    temp_order = Order(
        total_amount=price_after_offers,
        discount_amount=offer_discount_total,
        coupon_discount=coupon_discount,
    )
    shipping_charge = temp_order.calculate_shipping()

    final_amount = price_after_offers - coupon_discount + shipping_charge

    if payment_method == "COD" and final_amount > Decimal("1000"):
        messages.error(
            request, "Cash on Delivery is not available for orders above ₹1,000."
        )
        return redirect("shopcore:checkout")

    if payment_method == "WALLET":
        balance = _wallet_balance(request.user)
        if balance < final_amount:
            messages.error(request, f"Insufficient wallet balance (₹{balance:.2f}).")
            return redirect("shopcore:checkout")

    # ── Create order ──────────────────────────────────────────────────────
    order_kwargs = dict(
        user=request.user,
        address=address,
        payment_method=payment_method,
        coupon=applied_coupon,
        coupon_discount=coupon_discount,
        total_amount=subtotal,
        discount_amount=offer_discount_total,
        shipping_charge=shipping_charge,
        final_amount=final_amount,
    )

    if payment_method == "COD":
        order = Order.objects.create(
            **order_kwargs,
            payment_status="PENDING",
            order_status="PENDING",
        )
    else:
        order = Order.objects.create(
            **order_kwargs,
            payment_status="INITIATED",
            order_status="ORDER NOT PLACED",
        )

    for item in items:
        variant = item.variant
        base_price = variant.product.final_price
        item_disc = item_offer_data.get(item.variant_id, Decimal("0"))
        OrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=item.quantity,
            unit_price=base_price,
            discount_amount=item_disc,
            item_status="PENDING",
        )
        inv = variant.inventory
        inv.quantity_available = max(0, inv.quantity_available - item.quantity)
        inv.quantity_sold += item.quantity
        inv.save(update_fields=["quantity_available", "quantity_sold"])

    if payment_method == "COD":
        Payment.objects.create(
            order=order,
            payment_method="COD",
            payment_status="PENDING",
            amount=final_amount,
            initiated_at=timezone.now(),
        )

        if applied_coupon:
            usage, _ = CouponUsage.objects.get_or_create(
                coupon=applied_coupon, user=request.user
            )
            usage.times_used += 1
            usage.save(update_fields=["times_used"])
            applied_coupon.used_count += 1
            applied_coupon.save(update_fields=["used_count"])

        cart.items.all().delete()
        request.session.pop("applied_coupon_code", None)
        request.session.pop("applied_coupon_discount", None)
        return redirect("shopcore:order_success", order_id=order.order_id)

    # Non-COD (WALLET / PAYPAL)
    request.session["pending_kiddora_order_id"] = order.order_id
    if applied_coupon:
        request.session["pending_coupon_id"] = applied_coupon.id

    if payment_method == "WALLET":
        return render(request, "payments/wallet_pay_confirm.html", {"order": order})
    else:
        return redirect("payments:initiate_paypal_payment", order_id=order.order_id)


# ────────────────────────────────────────────────── ORDER SUCCESS ──────────────────────────────────────────────────

@never_cache
@user_login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    return render(request, "orders/user/order_success.html", {"order": order})

# ────────────────────────────────────────────────── CANCEL ITEM ──────────────────────────────────────────────────
@never_cache
@user_login_required
@require_POST
@transaction.atomic
def cancel_order_item(request, item_id):
    order_item = get_object_or_404(
        OrderItem,
        id=item_id,
        order__user=request.user,
    )
    order = order_item.order

    if order_item.item_status not in ("PENDING", "CONFIRMED"):
        messages.error(request, "This item cannot be cancelled at its current status.")
        return redirect("shopcore:order_detail", order_id=order.order_id)

    order_item.item_status = "CANCELLED"
    order_item.save(update_fields=["item_status"])

    # Restore inventory
    try:
        inv = order_item.variant.inventory
        inv.quantity_available += order_item.quantity
        inv.quantity_sold = max(0, inv.quantity_sold - order_item.quantity)
        inv.save(update_fields=["quantity_available", "quantity_sold"])
    except Exception:
        pass

    # TASK 4: re-validate coupon and shipping
    validation = revalidate_order_after_item_change(order)

    # Optional: If the entire order now has no active items, decrement coupon usage
    active_items_count = order.order_items.filter(
        item_status__in=("PENDING", "CONFIRMED", "SHIPPED", "DELIVERED")
    ).count()

    if active_items_count == 0 and order.coupon:
        try:
            usage = CouponUsage.objects.get(coupon=order.coupon, user=order.user)
            usage.times_used = max(0, usage.times_used - 1)
            usage.save(update_fields=["times_used"])

            order.coupon.used_count = max(0, order.coupon.used_count - 1)
            order.coupon.save(update_fields=["used_count"])
        except CouponUsage.DoesNotExist:
            pass
        except Exception:
            pass  # safety

    feedback = []
    if validation["coupon_invalidated"]:
        feedback.append(
            "The applied coupon has been removed because the remaining order "
            "total no longer meets its minimum requirement."
        )
    if validation["shipping_changed"]:
        if validation["new_shipping_charge"] == Decimal("0"):
            feedback.append("Your order now qualifies for free shipping.")
        else:
            feedback.append(
                f"Shipping charge updated to ₹{validation['new_shipping_charge']:.2f}."
            )

    messages.success(request, "Item cancelled successfully.")
    for msg in feedback:
        messages.info(request, msg)

    return redirect("shopcore:order_detail", order_id=order.order_id)


# ────────────────────────────────────────────────── RETURN ITEM ──────────────────────────────────────────────────
@never_cache
@user_login_required
@require_POST
@transaction.atomic
def return_order_item(request, item_id):
    order_item = get_object_or_404(
        OrderItem,
        id=item_id,
        order__user=request.user,
    )
    order = order_item.order

    if order_item.item_status != "DELIVERED":
        messages.error(request, "Only delivered items can be returned.")
        return redirect("shopcore:order_detail", order_id=order.order_id)

    order_item.item_status = "RETURN_REQUESTED"
    order_item.save(update_fields=["item_status"])

    # TASK 4: re-validate coupon and shipping
    validation = revalidate_order_after_item_change(order)

    # Optional: If no active items remain, decrement coupon usage
    active_items_count = order.order_items.filter(
        item_status__in=("PENDING", "CONFIRMED", "SHIPPED", "DELIVERED")
    ).count()

    if active_items_count == 0 and order.coupon:
        try:
            usage = CouponUsage.objects.get(coupon=order.coupon, user=order.user)
            usage.times_used = max(0, usage.times_used - 1)
            usage.save(update_fields=["times_used"])

            order.coupon.used_count = max(0, order.coupon.used_count - 1)
            order.coupon.save(update_fields=["used_count"])
        except CouponUsage.DoesNotExist:
            pass
        except Exception:
            pass

    feedback = []
    if validation["coupon_invalidated"]:
        feedback.append(
            "The applied coupon has been removed because the remaining order "
            "total no longer meets its minimum requirement."
        )
    if validation["shipping_changed"]:
        if validation["new_shipping_charge"] == Decimal("0"):
            feedback.append("Your order now qualifies for free shipping.")
        else:
            feedback.append(
                f"Shipping charge updated to ₹{validation['new_shipping_charge']:.2f}."
            )

    messages.success(request, "Return request submitted successfully.")
    for msg in feedback:
        messages.info(request, msg)

    return redirect("shopcore:order_detail", order_id=order.order_id)



