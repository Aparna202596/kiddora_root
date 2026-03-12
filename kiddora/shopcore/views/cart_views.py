# shopcore/views/cart_views.py
# Cart management: add, remove, update, list — with all validations.

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.http import JsonResponse
from django.db import transaction

from products.models import ProductVariant, Product
from shopcore.models import Cart, CartItem, Wishlist, WishlistItem


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

MAX_QTY = CartItem.MAX_QTY_PER_PRODUCT   # 5 — defined on the model


def _get_or_create_cart(user):
    """Return the user's Cart, creating one if it doesn't exist."""
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def _variant_is_available(variant: ProductVariant) -> bool:
    """
    Return True only if the variant AND its full hierarchy are active/not-deleted.
    This mirrors the product_list filter in catalog_views.py.
    """
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


def _stock_for(variant: ProductVariant) -> int:
    """Return quantity_available for a variant, 0 if no inventory row exists."""
    try:
        return variant.inventory.quantity_available
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# CART LIST
# ---------------------------------------------------------------------------

@never_cache
@login_required
def cart_view(request):
    cart  = _get_or_create_cart(request.user)
    items = (
        cart.items
        .select_related(
            "variant",
            "variant__product",
            "variant__product__subcategory",
            "variant__product__subcategory__category",
            "variant__color",
            "variant__age_group",
            "variant__inventory",
        )
        .order_by("-added_at")
    )

    cart_data        = []
    subtotal         = 0
    any_unavailable  = False
    any_out_of_stock = False

    for item in items:
        variant    = item.variant
        available  = _variant_is_available(variant)
        stock      = _stock_for(variant)
        product    = variant.product
        item_total = product.final_price * item.quantity

        # Gather one image URL for display
        img_url = None
        img_obj = product.images.filter(is_default=True).first() or product.images.first()
        if img_obj:
            for field in ("image1", "image2", "image3", "image4", "image5"):
                val = getattr(img_obj, field)
                if val:
                    img_url = val.url
                    break

        if not available:
            any_unavailable = True
        if stock == 0:
            any_out_of_stock = True

        cart_data.append({
            "item":          item,
            "variant":       variant,
            "product":       product,
            "stock":         stock,
            "available":     available,
            "item_total":    item_total,
            "img_url":       img_url,
            "max_qty":       min(MAX_QTY, stock),
            "exceeds_stock": item.quantity > stock,
        })
        if available:
            subtotal += item_total

    shipping_charge = 0  # extend later
    grand_total     = subtotal + shipping_charge

    # Block checkout if any item is unavailable / OOS / quantity exceeds stock
    checkout_blocked = any_unavailable or any_out_of_stock or any(
        d["exceeds_stock"] for d in cart_data
    )

    context = {
        "cart":             cart,
        "cart_data":        cart_data,
        "subtotal":         subtotal,
        "shipping_charge":  shipping_charge,
        "grand_total":      grand_total,
        "checkout_blocked": checkout_blocked,
        "any_unavailable":  any_unavailable,
        "any_out_of_stock": any_out_of_stock,
        "MAX_QTY":          MAX_QTY,
    }
    return render(request, "cart/cart.html", context)


# ---------------------------------------------------------------------------
# ADD TO CART
# ---------------------------------------------------------------------------

@never_cache
@login_required
@transaction.atomic
def add_to_cart(request, variant_id):
    """
    POST-only.  Adds one unit of the variant to the cart.
    - Rejects blocked / deleted products (full hierarchy check).
    - Increments quantity if the item already exists (up to MAX_QTY / stock).
    - Removes the product from the wishlist when successfully added.
    """
    if request.method != "POST":
        return redirect("shopcore:cart")

    variant = get_object_or_404(
        ProductVariant.objects.select_related(
            "product",
            "product__subcategory",
            "product__subcategory__category",
            "inventory",
        ),
        id=variant_id,
    )

    # ── Availability check (mirrors catalog_views filters) ──────────────────
    if not _variant_is_available(variant):
        messages.error(request, "This product is currently unavailable.")
        return redirect("products:product_detail", product_id=variant.product.id)

    stock = _stock_for(variant)
    if stock == 0:
        messages.error(request, "This product is out of stock.")
        return redirect("products:product_detail", product_id=variant.product.id)

    cart = _get_or_create_cart(request.user)

    try:
        cart_item = cart.items.get(variant=variant)
        # Already in cart — increment if possible
        if cart_item.quantity >= MAX_QTY:
            messages.warning(
                request,
                f"You can add at most {MAX_QTY} of the same item.",
            )
        elif cart_item.quantity >= stock:
            messages.warning(
                request,
                f"Only {stock} unit(s) available. Cannot add more.",
            )
        else:
            cart_item.quantity += 1
            cart_item.save()
            messages.success(request, "Cart updated — quantity increased.")
    except CartItem.DoesNotExist:
        CartItem.objects.create(cart=cart, variant=variant, quantity=1)
        messages.success(request, f"{variant.product.product_name} added to cart.")

    # ── Remove from wishlist if present ─────────────────────────────────────
    try:
        wishlist = request.user.wishlist
        WishlistItem.objects.filter(
            wishlist=wishlist, product=variant.product
        ).delete()
    except Wishlist.DoesNotExist:
        pass

    # Honour redirect-back header or fall back to cart
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "shopcore:cart"
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("shopcore:cart")


# ---------------------------------------------------------------------------
# REMOVE FROM CART
# ---------------------------------------------------------------------------

@never_cache
@login_required
def remove_from_cart(request, item_id):
    """Remove a CartItem entirely."""
    cart      = _get_or_create_cart(request.user)
    cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
    product_name = cart_item.variant.product.product_name
    cart_item.delete()
    messages.success(request, f"{product_name} removed from cart.")
    return redirect("shopcore:cart")


# ---------------------------------------------------------------------------
# UPDATE QUANTITY  (AJAX-friendly: returns JSON when called via fetch/XHR)
# ---------------------------------------------------------------------------

@never_cache
@login_required
@transaction.atomic
def update_cart_quantity(request, item_id):
    """
    POST.  Body param: action = 'increment' | 'decrement' | 'set'
                        quantity = <int>  (only for 'set')
    Returns JSON when the request has X-Requested-With: XMLHttpRequest,
    otherwise redirects to cart.
    """
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    if request.method != "POST":
        return (
            JsonResponse({"error": "POST required"}, status=405)
            if is_ajax
            else redirect("shopcore:cart")
        )

    cart      = _get_or_create_cart(request.user)
    cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
    variant   = cart_item.variant

    # Re-check availability
    if not _variant_is_available(variant):
        msg = "This product is no longer available."
        if is_ajax:
            return JsonResponse({"error": msg}, status=400)
        messages.error(request, msg)
        return redirect("shopcore:cart")

    stock  = _stock_for(variant)
    action = request.POST.get("action", "set")
    qty    = cart_item.quantity

    if action == "increment":
        qty += 1
    elif action == "decrement":
        qty -= 1
    else:  # "set"
        try:
            qty = int(request.POST.get("quantity", qty))
        except (ValueError, TypeError):
            qty = cart_item.quantity

    # ── Clamp ────────────────────────────────────────────────────────────────
    if qty < 1:
        qty = 1
    if qty > MAX_QTY:
        msg = f"Maximum {MAX_QTY} per item."
        if is_ajax:
            return JsonResponse({"error": msg, "quantity": cart_item.quantity}, status=400)
        messages.warning(request, msg)
        qty = MAX_QTY
    if qty > stock:
        msg = f"Only {stock} unit(s) available."
        if is_ajax:
            return JsonResponse({"error": msg, "quantity": min(cart_item.quantity, stock)}, status=400)
        messages.warning(request, msg)
        qty = stock

    cart_item.quantity = qty
    cart_item.save()

    if is_ajax:
        # Recalculate totals for the AJAX response
        product    = variant.product
        item_total = product.final_price * qty
        # Recalculate full cart subtotal
        subtotal = sum(
            i.variant.product.final_price * i.quantity
            for i in cart.items.select_related("variant__product", "variant__inventory").all()
            if _variant_is_available(i.variant)
        )
        return JsonResponse({
            "quantity":   qty,
            "item_total": str(item_total),
            "subtotal":   str(subtotal),
            "grand_total": str(subtotal),  # extend with shipping if needed
        })

    return redirect("shopcore:cart")


# ---------------------------------------------------------------------------
# CLEAR ENTIRE CART
# ---------------------------------------------------------------------------

@never_cache
@login_required
def clear_cart(request):
    if request.method == "POST":
        cart = _get_or_create_cart(request.user)
        cart.items.all().delete()
        messages.success(request, "Cart cleared.")
    return redirect("shopcore:cart")

@never_cache
@login_required
def toggle_wishlist(request, product_id):
    """
    POST-only.
    Adds the product to the wishlist if not present, removes it if it is.
    Redirects back to the referring page (passed as POST 'next' or HTTP_REFERER).
    """
    if request.method != "POST":
        return redirect("products:product_list")

    product  = get_object_or_404(Product, id=product_id)
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)

    existing = WishlistItem.objects.filter(wishlist=wishlist, product=product).first()
    if existing:
        existing.delete()
        messages.success(request, f"{product.product_name} removed from your wishlist.")
    else:
        WishlistItem.objects.create(wishlist=wishlist, product=product)
        messages.success(request, f"{product.product_name} added to your wishlist.")

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("products:product_list")
