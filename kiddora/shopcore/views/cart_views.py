from decimal import Decimal

from accounts.decorators import user_login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from products.models import Product, ProductVariant
from shopcore.models import Cart, CartItem, Order, Wishlist, WishlistItem

MAX_QTY = CartItem.MAX_QTY_PER_PRODUCT


# ────────────────────────────────────────────────── HELPER FUNCTIONS ──────────────────────────────────────────────────
def _get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


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


def _is_ajax(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _cart_subtotal(cart) -> float:
    total = 0
    for item in cart.items.select_related(
        "variant__product",
        "variant__product__subcategory",
        "variant__product__subcategory__category",
        "variant__inventory",
    ).all():
        if _variant_is_available(item.variant):
            total += float(item.variant.product.final_price) * item.quantity
    return total


# ────────────────────────────────────────────────── CART VIEWS ──────────────────────────────────────────────────
@never_cache
@user_login_required
def cart_view(request):
    cart = _get_or_create_cart(request.user)
    items = (
        cart.items.select_related(
            "variant",
            "variant__product",
            "variant__product__subcategory",
            "variant__product__subcategory__category",
            "variant__color",
            "variant__age_group",
            "variant__inventory",
        )
        .prefetch_related("variant__product__images")
        .order_by("-added_at")
    )

    cart_data = []
    subtotal = 0
    any_unavailable = False
    any_out_of_stock = False

    for item in items:
        variant = item.variant
        available = _variant_is_available(variant)
        stock = _stock_for(variant)
        product = variant.product
        item_total = product.final_price * item.quantity if available else 0

        img_url = None
        img_obj = (
            product.images.filter(is_default=True).first() or product.images.first()
        )
        if img_obj:
            for field in ("image1", "image2", "image3", "image4", "image5"):
                val = getattr(img_obj, field)
                if val:
                    img_url = val.url
                    break

        if not available:
            any_unavailable = True
        if available and stock == 0:
            any_out_of_stock = True

        cart_data.append(
            {
                "item": item,
                "variant": variant,
                "product": product,
                "stock": stock,
                "available": available,
                "item_total": item_total,
                "img_url": img_url,
                "max_qty": min(MAX_QTY, stock) if stock > 0 else 0,
                "exceeds_stock": (item.quantity > stock) if available else False,
            }
        )
        if available:
            subtotal += item_total

    temp_order = Order(
        total_amount=subtotal,
        discount_amount=Decimal("0"),
        coupon_discount=Decimal("0"),
    )
    shipping_charge = temp_order.calculate_shipping()
    grand_total = subtotal + shipping_charge
    checkout_blocked = (
        any_unavailable
        or any_out_of_stock
        or any(d["exceeds_stock"] for d in cart_data)
    )
    return render(
        request,
        "cart/cart.html",
        {
            "cart": cart,
            "cart_data": cart_data,
            "subtotal": subtotal,
            "shipping_charge": shipping_charge,
            "grand_total": grand_total,
            "checkout_blocked": checkout_blocked,
            "any_unavailable": any_unavailable,
            "any_out_of_stock": any_out_of_stock,
            "MAX_QTY": MAX_QTY,
        },
    )


#   ────────────────────────────────────────────────── ADD TO CART  (AJAX-aware) ──────────────────────────────────────────────────
@never_cache
@user_login_required
@transaction.atomic
def add_to_cart(request, variant_id):
    if request.method != "POST":
        if _is_ajax(request):
            return JsonResponse({"error": "POST required"}, status=405)
        return redirect("shopcore:cart")

    ajax = _is_ajax(request)

    variant = get_object_or_404(
        ProductVariant.objects.select_related(
            "product",
            "product__subcategory",
            "product__subcategory__category",
            "inventory",
        ),
        id=variant_id,
    )

    if not _variant_is_available(variant):
        msg = "This product is currently unavailable."
        if ajax:
            return JsonResponse({"error": msg}, status=400)
        messages.error(request, msg)
        return redirect("products:product_detail", product_id=variant.product.id)

    stock = _stock_for(variant)
    if stock == 0:
        msg = "This product is out of stock."
        if ajax:
            return JsonResponse({"error": msg}, status=400)
        messages.error(request, msg)
        return redirect("products:product_detail", product_id=variant.product.id)

    cart = _get_or_create_cart(request.user)
    new_item = False

    try:
        cart_item = cart.items.get(variant=variant)
        if cart_item.quantity >= MAX_QTY:
            msg = f"You can add at most {MAX_QTY} of the same item."
            if ajax:
                return JsonResponse(
                    {"error": msg, "quantity": cart_item.quantity}, status=400
                )
            messages.warning(request, msg)
        elif cart_item.quantity >= stock:
            msg = f"Only {stock} unit(s) available. Cannot add more."
            if ajax:
                return JsonResponse(
                    {"error": msg, "quantity": cart_item.quantity}, status=400
                )
            messages.warning(request, msg)
        else:
            cart_item.quantity += 1
            cart_item.save()
    except CartItem.DoesNotExist:
        cart_item = CartItem.objects.create(cart=cart, variant=variant, quantity=1)
        new_item = True

    try:
        WishlistItem.objects.filter(
            wishlist=request.user.wishlist,
            product=variant.product,
        ).delete()
    except (Wishlist.DoesNotExist, AttributeError):
        pass

    if ajax:
        return JsonResponse(
            {
                "success": True,
                "new_item": new_item,
                "quantity": cart_item.quantity,
                "cart_count": cart.items.count(),
                "product_id": variant.product.id,
                "product_name": variant.product.product_name,
            }
        )

    messages.success(
        request,
        (
            f"{variant.product.product_name} added to cart."
            if new_item
            else "Cart updated — quantity increased."
        ),
    )
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    return redirect(next_url) if next_url.startswith("/") else redirect("shopcore:cart")


#   ────────────────────────────────────────────────── REMOVE FROM CART  (AJAX-aware) ──────────────────────────────────────────────────
@never_cache
@user_login_required
@require_POST
def remove_from_cart(request, item_id):
    ajax = _is_ajax(request)
    cart = _get_or_create_cart(request.user)
    cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
    product = cart_item.variant.product

    saved_to_wishlist = False
    if request.POST.get("save_to_wishlist") == "1" and not product.is_deleted:
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        WishlistItem.objects.get_or_create(wishlist=wishlist, product=product)
        saved_to_wishlist = True

    product_name = product.product_name
    cart_item.delete()

    if ajax:
        return JsonResponse(
            {
                "success": True,
                "item_id": item_id,
                "product_name": product_name,
                "saved_to_wishlist": saved_to_wishlist,
                "subtotal": str(_cart_subtotal(cart)),
                "grand_total": str(_cart_subtotal(cart)),
                "cart_count": cart.items.count(),
            }
        )

    msg = f"{product_name} removed from cart."
    if saved_to_wishlist:
        msg += " Saved to your wishlist."
    messages.success(request, msg)
    return redirect("shopcore:cart")


#   ────────────────────────────────────────────────── UPDATE CART QUANTITY  (AJAX-aware) ──────────────────────────────────────────────────
@never_cache
@user_login_required
@transaction.atomic
def update_cart_quantity(request, item_id):
    ajax = _is_ajax(request)

    if request.method != "POST":
        return (
            JsonResponse({"error": "POST required"}, status=405)
            if ajax
            else redirect("shopcore:cart")
        )

    cart = _get_or_create_cart(request.user)
    cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
    variant = cart_item.variant

    if not _variant_is_available(variant):
        msg = "This product is no longer available."
        return (
            JsonResponse({"error": msg}, status=400)
            if ajax
            else redirect("shopcore:cart")
        )

    stock = _stock_for(variant)
    action = request.POST.get("action", "set")
    qty = cart_item.quantity

    if action == "increment":
        qty += 1
    elif action == "decrement":
        qty -= 1
    else:
        try:
            qty = int(request.POST.get("quantity", qty))
        except (ValueError, TypeError):
            qty = cart_item.quantity

    warning = None
    if qty < 1:
        qty = 1
    if qty > MAX_QTY:
        warning = f"Maximum {MAX_QTY} per item."
        qty = MAX_QTY
    if qty > stock:
        warning = f"Only {stock} unit(s) available."
        qty = stock

    cart_item.quantity = qty
    cart_item.save()

    item_total = float(variant.product.final_price) * qty
    subtotal = _cart_subtotal(cart)

    if ajax:
        return JsonResponse(
            {
                "success": True,
                "quantity": qty,
                "max_qty": min(MAX_QTY, stock),
                "item_total": str(item_total),
                "subtotal": str(subtotal),
                "grand_total": str(subtotal),
                "warning": warning,
            }
        )

    if warning:
        messages.warning(request, warning)
    return redirect("shopcore:cart")


#   ────────────────────────────────────────────────── CLEAR CART  (AJAX-aware) ──────────────────────────────────────────────────
@never_cache
@user_login_required
def clear_cart(request):
    if request.method == "POST":
        _get_or_create_cart(request.user).items.all().delete()
        messages.success(request, "Cart cleared.")
    return redirect("shopcore:cart")


#   ────────────────────────────────────────────────── TOGGLE WISHLIST  (AJAX-aware) ──────────────────────────────────────────────────
@never_cache
@user_login_required
def toggle_wishlist(request, product_id):
    if request.method != "POST":
        if _is_ajax(request):
            return JsonResponse({"error": "POST required"}, status=405)
        return redirect("products:product_list")

    ajax = _is_ajax(request)
    product = get_object_or_404(Product, id=product_id)

    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
    existing = WishlistItem.objects.filter(wishlist=wishlist, product=product).first()

    if existing:
        existing.delete()
        wishlisted = False
        msg = f"{product.product_name} removed from your wishlist."
    else:
        WishlistItem.objects.create(wishlist=wishlist, product=product)
        wishlisted = True
        msg = f"{product.product_name} added to your wishlist."

    if ajax:
        return JsonResponse(
            {
                "success": True,
                "wishlisted": wishlisted,
                "message": msg,
                "product_id": product_id,
            }
        )

    messages.success(request, msg)
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    return (
        redirect(next_url)
        if next_url.startswith("/")
        else redirect("products:product_list")
    )
