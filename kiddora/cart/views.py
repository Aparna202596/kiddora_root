from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.db import transaction
from accounts.decorators import user_login_required
from .models import Cart, CartItem
from products.models import ProductVariant,Coupon
from wishlist.models import WishlistItem

@user_login_required
def cart_detail(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    invalid_items = []
    for item in cart.items.select_related("variant", "variant__product"):
        product = item.variant.product
        inventory = getattr(item.variant, "inventory", None)
        if not product.is_active or not item.variant.is_active or not inventory or inventory.quantity_available < item.quantity:
            invalid_items.append(item.id)
    return render(request, "cart/cart.html", {
        "cart": cart,
        "invalid_items": invalid_items,
    })


@user_login_required
def add_to_cart(request, variant_id):
    variant = get_object_or_404(ProductVariant, id=variant_id, is_active=True)
    product = variant.product

    if not product.is_active:
        return JsonResponse({"success": False, "message": "Product is unavailable."}) if request.is_ajax() else redirect("cart:cart_detail")

    inventory = getattr(variant, "inventory", None)
    if not inventory or inventory.quantity_available <= 0:
        return JsonResponse({"success": False, "message": "Out of stock."}) if request.is_ajax() else redirect("cart:cart_detail")

    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_item, created = CartItem.objects.get_or_create(cart=cart, variant=variant, defaults={"quantity": 1})

    if not created:
        if cart_item.quantity + 1 > inventory.quantity_available:
            return JsonResponse({"success": False, "message": "Stock limit reached."}) if request.is_ajax() else redirect("cart:cart_detail")
        cart_item.quantity += 1
        cart_item.save()

    # Remove from wishlist automatically
    WishlistItem.objects.filter(wishlist__user=request.user, product=product).delete()

    return JsonResponse({
        "success": True,
        "message": "Added to cart.",
        "cart_item_id": cart_item.id,
        "quantity": cart_item.quantity
    }) if request.is_ajax() else redirect("cart:cart_detail")


@user_login_required
def update_cart_item(request, item_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request."})

    quantity = int(request.POST.get("quantity", 1))
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    inventory = getattr(cart_item.variant, "inventory", None)

    if not inventory:
        return JsonResponse({"success": False, "message": "Invalid item."})

    if quantity < 1:
        cart_item.delete()
        return JsonResponse({"success": True, "message": "Item removed from cart.", "quantity": 0})

    if quantity > inventory.quantity_available:
        return JsonResponse({"success": False, "message": "Stock exceeded."})

    cart_item.quantity = quantity
    cart_item.save()
    return JsonResponse({"success": True, "message": "Cart updated.", "quantity": cart_item.quantity})


@user_login_required
def increase_quantity(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    inventory = getattr(item.variant, "inventory", None)

    if not inventory:
        return JsonResponse({"success": False, "message": "Invalid item."})

    if item.quantity < inventory.quantity_available:
        item.quantity += 1
        item.save()
        return JsonResponse({"success": True, "quantity": item.quantity})
    return JsonResponse({"success": False, "message": "Max stock reached."})


@user_login_required
def decrease_quantity(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    if item.quantity > 1:
        item.quantity -= 1
        item.save()
        return JsonResponse({"success": True, "quantity": item.quantity})
    item.delete()
    return JsonResponse({"success": True, "quantity": 0, "message": "Item removed from cart."})


@user_login_required
def remove_from_cart(request, item_id):
    item = CartItem.objects.filter(id=item_id, cart__user=request.user)
    if item.exists():
        item.delete()
        return JsonResponse({"success": True, "message": "Item removed from cart."})
    return JsonResponse({"success": False, "message": "Item not found."})


@user_login_required
def checkout(request):
    cart = get_object_or_404(Cart, user=request.user)

    cart_items = cart.items.select_related(
        "variant",
        "variant__product",
        "variant__inventory"
    )

    invalid_items = []
    subtotal = 0

    for item in cart_items:
        inventory = getattr(item.variant, "inventory", None)
        product = item.variant.product

        if (
            not product.is_active or
            not item.variant.is_active or
            not inventory or
            inventory.quantity_available < item.quantity
        ):
            invalid_items.append(item.id)
        else:
            subtotal += product.final_price * item.quantity

    if invalid_items:
        messages.error(request, "Invalid cart items detected.")
        return redirect("cart:cart_detail")

    # Coupon preview
    discount = 0
    coupon = None
    coupon_id = request.session.get("coupon_id")

    if coupon_id:
        coupon = Coupon.objects.filter(id=coupon_id, is_active=True).first()
        if coupon and coupon.can_use(request.user) and subtotal >= coupon.min_order_amount:
            if coupon.discount_type == "PERCENT":
                discount = (subtotal * coupon.discount_value) / 100
                if coupon.max_discount:
                    discount = min(discount, coupon.max_discount)
            else:
                discount = coupon.discount_value

    delivery_charge = 0 if subtotal >= 500 else 50
    final_total = subtotal - discount + delivery_charge

    addresses = request.user.addresses.all()

    return render(request, "cart/checkout.html", {
        "cart": cart,
        "cart_items": cart_items,
        "addresses": addresses,
        "subtotal": subtotal,
        "discount": discount,
        "delivery_charge": delivery_charge,
        "final_total": final_total,
        "coupon": coupon,
        "cod_allowed": final_total <= 1000
    })


