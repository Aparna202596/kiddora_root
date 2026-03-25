from django.contrib import messages
from accounts.decorators import user_login_required 
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.db import transaction
from products.models import Product, ProductVariant
from shopcore.models import Cart, CartItem, Wishlist, WishlistItem

MAX_QTY = CartItem.MAX_QTY_PER_PRODUCT


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _stock_for(variant):
    try:
        return variant.inventory.quantity_available
    except Exception:
        return 0


def _variant_is_available(variant):
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


def _is_ajax(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


# ─────────────────────────────────────────────────────────────
# WISHLIST PAGE
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
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

        total_stock = sum(
            _stock_for(v) for v in product.variants.filter(is_active=True)
        )

        available = (
            product.is_active and not product.is_deleted
            and product.subcategory.is_active and not product.subcategory.is_deleted
            and product.subcategory.category.is_active
            and not product.subcategory.category.is_deleted
        )

        item_data.append({
            "wishlist_item": wi,
            "product":       product,
            "img_url":       img_url,
            "total_stock":   total_stock,
            "available":     available,
        })

    return render(request, "wishlist/wishlist.html", {
        "wishlist":  wishlist,
        "item_data": item_data,
    })


# ─────────────────────────────────────────────────────────────
# REMOVE FROM WISHLIST  (AJAX-aware)
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@require_POST
def remove_from_wishlist(request, product_id):
    ajax     = _is_ajax(request)
    product  = get_object_or_404(Product, id=product_id)
    wishlist = getattr(request.user, "wishlist", None)
    if wishlist:
        WishlistItem.objects.filter(wishlist=wishlist, product=product).delete()

    if ajax:
        return JsonResponse({
            "success":    True,
            "product_id": product_id,
            "message":    f'"{product.product_name}" removed from wishlist.',
        })
    messages.success(request, f'"{product.product_name}" removed from wishlist.')
    return redirect("shopcore:wishlist")


# ─────────────────────────────────────────────────────────────
# VARIANT POPUP  (GET — renders partial HTML for modal)
#
# Shows ALL active variants (including OOS) for selection.
# OOS variants are shown but cannot be added to cart.
# First in-stock variant is auto-selected as default.
# Cart add uses the existing add_to_cart view (POST to /shop/cart/add/<variant_id>/).
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
def wishlist_variant_popup(request, product_id):
    product = get_object_or_404(
        Product.objects.prefetch_related(
            "images",
            "variants__inventory",
            "variants__color",
            "variants__age_group",
        ),
        id=product_id,
        is_active=True,
        is_deleted=False,
    )

    # Resolve product image URL in Python (can't call .filter() in Django templates)
    img_url = None
    img_obj = product.images.filter(is_default=True).first() or product.images.first()
    if img_obj:
        for field in ("image1", "image2", "image3", "image4", "image5"):
            val = getattr(img_obj, field)
            if val:
                img_url = val.url
                break

    # Build variant_data — ALL active variants regardless of stock
    variant_data = []
    first_in_stock = None  # default selection: first variant that has stock

    for v in product.variants.filter(is_active=True).select_related(
        "inventory", "color", "age_group"
    ):
        if not _variant_is_available(v):
            continue
        stock      = _stock_for(v)
        color_id   = v.color_id if v.color else None
        color_name = v.color.color if v.color else "N/A"
        age_label = v.age_group.age if v.age_group else "N/A"

        variant_data.append({
            "id":         v.id,
            "color_id":   color_id,
            "color_name": color_name,
            "age":        age_label,
            "qty":        stock,
            "is_oos":     stock == 0,
        })

        if first_in_stock is None and stock > 0:
            first_in_stock = {
                "id":       v.id,
                "color_id": color_id,
                "age":      age_label,
                "qty":      stock,
            }

    return render(request, "wishlist/wishlist_product_variant.html", {
        "product":       product,
        "variant_data":  variant_data,
        "first_in_stock": first_in_stock,
    })

# NEW: MOVE FROM WISHLIST TO CART (variant + remove from wishlist)
# ─────────────────────────────────────────────────────────────
@never_cache
@user_login_required                     # ← Changed to standard login_required
@require_POST
def move_to_cart(request, variant_id):
    """Add selected variant to cart and remove the product from wishlist."""
    try:
        with transaction.atomic():
            variant = get_object_or_404(
                ProductVariant.objects.select_related("product"),
                id=variant_id,
                is_active=True
            )
            product = variant.product

            cart, _ = Cart.objects.get_or_create(user=request.user)

            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                variant=variant,
                defaults={"quantity": 1}
            )
            if not created and cart_item.quantity < MAX_QTY:
                cart_item.quantity += 1
                cart_item.save()

            # Remove from wishlist
            wishlist = getattr(request.user, "wishlist", None)
            if wishlist:
                WishlistItem.objects.filter(wishlist=wishlist, product=product).delete()

            cart_count = cart.items.count()

        return JsonResponse({
            "success": True,
            "product_id": product.id,
            "product_name": product.product_name,
            "cart_count": cart_count,
            "message": f'"{product.product_name}" moved to cart.'
        })

    except Exception as e:
        print(f"[move_to_cart] ERROR for variant {variant_id}: {type(e).__name__} - {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            "success": False,
            "message": "Something went wrong. Please try again."
        }, status=400)