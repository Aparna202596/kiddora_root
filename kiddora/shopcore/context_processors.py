def shopcore_context(request):

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


def cart_count(request):
    return shopcore_context(request)
