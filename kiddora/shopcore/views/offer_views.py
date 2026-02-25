from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db import transaction

from products.models import *
from accounts.models import *
from shopcore.models import *

from accounts.decorators import admin_login_required,user_login_required
@admin_login_required
def admin_offer_list(request):
    offers = Offer.objects.filter(is_deleted=False).select_related(
        "product", "category"
    ).order_by("-created_at")

    return render(request, "products/coupon_offer/admin_offer_list.html", {
        "offers": offers
    })

@admin_login_required
@transaction.atomic
def admin_product_offer(request):
    products = Product.objects.filter(is_active=True, is_deleted=False)

    if request.method == "POST":
        product = get_object_or_404(Product, id=request.POST.get("product"))
        discount = int(request.POST.get("discount_percent"))
        priority = int(request.POST.get("priority", 1))

        # Disable existing product offers
        Offer.objects.filter(
            offer_type=Offer.PRODUCT,
            product=product,
            is_active=True
        ).update(is_active=False)

        Offer.objects.create(
            offer_type=Offer.PRODUCT,
            product=product,
            discount_percent=discount,
            priority=priority,
            is_active=True
        )

        messages.success(request, "Product offer created")
        return redirect("products:admin_offer_list")

    return render(request, "products/coupon_offer/admin_product_offer.html", {
        "products": products
    })


@admin_login_required
@transaction.atomic
def admin_category_offer(request):
    categories = Category.objects.filter(is_active=True, is_deleted=False)

    if request.method == "POST":
        category = get_object_or_404(Category, id=request.POST.get("category"))
        discount = int(request.POST.get("discount_percent"))
        priority = int(request.POST.get("priority", 1))

        # Disable existing category offers
        Offer.objects.filter(
            offer_type=Offer.CATEGORY,
            category=category,
            is_active=True
        ).update(is_active=False)

        Offer.objects.create(
            offer_type=Offer.CATEGORY,
            category=category,
            discount_percent=discount,
            priority=priority,
            is_active=True
        )

        messages.success(request, "Category offer created")
        return redirect("products:admin_offer_list")

    return render(request, "products/coupon_offer/admin_category_offer.html", {
        "categories": categories
    })


@admin_login_required
@transaction.atomic
def admin_referral_offer(request):
    users = CustomUser.objects.filter(is_active=True)

    if request.method == "POST":
        user = get_object_or_404(CustomUser, id=request.POST.get("user_id"))
        discount = int(request.POST.get("discount_percent", 10))
        usage_limit = int(request.POST.get("usage_limit", 1))

        token = f"REF-{user.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        coupon_code = f"REF{user.id}{timezone.now().strftime('%H%M%S')}"

        Coupon.objects.create(
            code=coupon_code,
            discount_type=Coupon.PERCENT,
            discount_value=discount,
            min_order_amount=0,
            usage_limit=usage_limit,
            expiry_date=timezone.now() + timezone.timedelta(days=30),
            created_by=user
        )

        Offer.objects.create(
            offer_type=Offer.REFERRAL,
            referral_token=token,
            created_by=user,
            is_active=True
        )

        messages.success(
            request,
            f"Referral created | Token: {token} | Coupon: {coupon_code}"
        )
        return redirect("products:admin_offer_list")

    return render(request, "products/coupon_offer/admin_referral_offer.html", {
        "users": users
    })

@admin_login_required
def admin_remove_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    offer.is_active = False
    offer.is_deleted = True
    offer.save()

    messages.success(request, "Offer removed successfully")
    return redirect("products:admin_offer_list")


def get_best_offer_for_product(product):
    """
    Returns the single best applicable offer
    (highest discount, then lowest priority)
    """

    offers = Offer.objects.filter(
        is_active=True,
        is_deleted=False
    ).order_by("-discount_percent", "priority")

    for offer in offers:
        if offer.applies_to(product):
            return offer

    return None

def calculate_offer_price(product):
    """
    Returns:
    - original_price
    - discounted_price
    - applied_offer (or None)
    """

    original_price = product.price
    offer = get_best_offer_for_product(product)

    if not offer:
        return {
            "original_price": original_price,
            "discounted_price": original_price,
            "offer": None
        }

    discount_amount = (offer.discount_percent / 100) * original_price
    discounted_price = max(original_price - discount_amount, 0)

    return {
        "original_price": original_price,
        "discounted_price": round(discounted_price, 2),
        "offer": offer
    }

def calculate_cart_total(cart):
    total = 0
    offer_savings = 0

    for item in cart.items.select_related("product"):
        price_data = calculate_offer_price(item.product)

        item_price = price_data["discounted_price"]
        total += item_price * item.quantity

        offer_savings += (
            price_data["original_price"] - item_price
        ) * item.quantity

    return {
        "cart_total": round(total, 2),
        "offer_savings": round(offer_savings, 2)
    }

def apply_coupon_to_total(total, coupon):
    if coupon.discount_type == Coupon.PERCENT:
        discount = (coupon.discount_value / 100) * total
        if coupon.max_discount:
            discount = min(discount, coupon.max_discount)

    elif coupon.discount_type == Coupon.FLAT:
        discount = coupon.discount_value

    else:
        discount = 0

    return max(total - discount, 0)

def calculate_checkout_total(cart, coupon=None):
    cart_data = calculate_cart_total(cart)
    total = cart_data["cart_total"]

    coupon_discount = 0
    if coupon:
        coupon_discount = total - apply_coupon_to_total(total, coupon)
        total = apply_coupon_to_total(total, coupon)

    return {
        "final_total": round(total, 2),
        "offer_savings": cart_data["offer_savings"],
        "coupon_savings": round(coupon_discount, 2)
    }
