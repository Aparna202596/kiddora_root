from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from products.models import Product
from shopcore.models import (
    Cart, CartItem, Wishlist, WishlistItem,
)

MAX_QTY = CartItem.MAX_QTY_PER_PRODUCT


def _stock_for(variant):
    try:
        return variant.inventory.quantity_available
    except Exception:
        return 0


def _variant_is_available(variant):
    p   = variant.product
    sub = p.subcategory
    cat = sub.category
    return (
        variant.is_active
        and p.is_active and not p.is_deleted
        and sub.is_active and not sub.is_deleted
        and cat.is_active and not cat.is_deleted
    )


# ─────────────────────────────────────────────────────────────
# USER: WISHLIST PAGE
# ─────────────────────────────────────────────────────────────

@never_cache
@login_required
def wishlist_view(request):
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
    items = wishlist.items.select_related(
        "product",
        "product__subcategory",
        "product__subcategory__category",
    ).prefetch_related(
        "product__images",
        "product__variants",
        "product__variants__inventory",
    ).order_by("-added_at")

    item_data = []
    for wi in items:
        product = wi.product
        img_url = None
        img_obj = product.images.filter(is_default=True).first() or product.images.first()
        if img_obj:
            for field in ("image1", "image2", "image3", "image4", "image5"):
                val = getattr(img_obj, field)
                if val:
                    img_url = val.url
                    break

        # Total stock across all active variants
        total_stock = sum(
            _stock_for(v) for v in product.variants.filter(is_active=True)
        )
        available   = (
            product.is_active and not product.is_deleted
            and product.subcategory.is_active and not product.subcategory.is_deleted
            and product.subcategory.category.is_active and not product.subcategory.category.is_deleted
        )

        item_data.append({
            "wishlist_item": wi,
            "product":       product,
            "img_url":       img_url,
            "total_stock":   total_stock,
            "available":     available,
        })

    return render(request, "wishlist/wishlist.html", {
        "wishlist":   wishlist,
        "item_data":  item_data,
    })


# ─────────────────────────────────────────────────────────────
# USER: REMOVE FROM WISHLIST
# ─────────────────────────────────────────────────────────────

@never_cache
@login_required
def remove_from_wishlist(request, product_id):
    """POST — remove a product from wishlist."""
    if request.method != "POST":
        return redirect("shopcore:wishlist")
    product  = get_object_or_404(Product, id=product_id)
    wishlist = getattr(request.user, "wishlist", None)
    if wishlist:
        WishlistItem.objects.filter(wishlist=wishlist, product=product).delete()
        messages.success(request, f'"{product.product_name}" removed from wishlist.')
    return redirect("shopcore:wishlist")


# ─────────────────────────────────────────────────────────────
# USER: MOVE TO CART
# Picks the first available variant with stock for the product.
# ─────────────────────────────────────────────────────────────

@never_cache
@login_required
def move_to_cart(request, product_id):
    """POST — move a wishlist item directly to cart (first available variant)."""
    if request.method != "POST":
        return redirect("shopcore:wishlist")

    product  = get_object_or_404(Product, id=product_id, is_active=True, is_deleted=False)

    # Find first active variant with stock
    variant = None
    for v in product.variants.filter(is_active=True):
        if _variant_is_available(v) and _stock_for(v) > 0:
            variant = v
            break

    if not variant:
        messages.error(request, f'"{product.product_name}" is out of stock — cannot add to cart.')
        return redirect("shopcore:wishlist")

    cart, _ = Cart.objects.get_or_create(user=request.user)
    try:
        cart_item = cart.items.get(variant=variant)
        new_qty   = min(cart_item.quantity + 1, MAX_QTY, _stock_for(variant))
        cart_item.quantity = new_qty
        cart_item.save()
    except CartItem.DoesNotExist:
        CartItem.objects.create(cart=cart, variant=variant, quantity=1)

    # Remove from wishlist
    wishlist = getattr(request.user, "wishlist", None)
    if wishlist:
        WishlistItem.objects.filter(wishlist=wishlist, product=product).delete()

    messages.success(request, f'"{product.product_name}" moved to cart.')
    return redirect("shopcore:cart")