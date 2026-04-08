# shopcore/context_processors.py
# Register in settings.py → TEMPLATES[0]['OPTIONS']['context_processors']:
#   "shopcore.context_processors.shopcore_context"


def shopcore_context(request):
    """
    Injects into every template:
      cart_item_count    – number of items in the user's cart
      wishlist_count     – number of items in the user's wishlist
    """
    cart_item_count = 0
    wishlist_count = 0

    if request.user.is_authenticated:
        try:
            cart_item_count = request.user.cart.items.count()
        except Exception:
            cart_item_count = 0

        try:
            wishlist_count = request.user.wishlist.items.count()
        except Exception:
            wishlist_count = 0

    return {
        "cart_item_count": cart_item_count,
        "wishlist_count": wishlist_count,
    }


# ── Legacy alias kept for backward compatibility ─────────────
# If you already registered "shopcore.context_processors.cart_count" in settings,
# either rename the entry to shopcore_context or keep this alias:


def cart_count(request):
    return shopcore_context(request)
