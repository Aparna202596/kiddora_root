from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from accounts.decorators import user_login_required
from appkiddora.models import Wishlist, WishlistItem
from products.models import Product

@user_login_required
def wishlist_view(request):
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
    return render(request, "wishlist/wishlist.html", {"wishlist": wishlist})

@user_login_required
def add_to_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)

    item, created = WishlistItem.objects.get_or_create(wishlist=wishlist, product=product)
    if request.is_ajax():
        return JsonResponse({"success": True, "message": "Added to wishlist.", "item_id": item.id})
    return redirect(request.META.get("HTTP_REFERER", "/"))

@user_login_required
def remove_from_wishlist(request, item_id):
    deleted = WishlistItem.objects.filter(id=item_id, wishlist__user=request.user).delete()
    if request.is_ajax():
        return JsonResponse({"success": bool(deleted[0]), "message": "Removed from wishlist."})
    return redirect("wishlist:wishlist_view")
