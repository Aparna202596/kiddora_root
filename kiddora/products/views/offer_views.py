from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q

from products.models import Product, Category, Offer, Coupon
from accounts.models import CustomUser
from accounts.decorators import admin_login_required

#Apply to Specific Product
@admin_login_required
def admin_product_offer(request):
    products = Product.objects.filter(is_active=True)
    offers = Offer.objects.filter(offer_type="PRODUCT", is_deleted=False)

    if request.method == "POST":
        product_id = request.POST.get("product")
        discount = int(request.POST.get("discount_percent"))
        priority = int(request.POST.get("priority", 1))

        product = get_object_or_404(Product, id=product_id)

        Offer.objects.create(
            offer_type="PRODUCT",
            product=product,
            discount_percent=discount,
            priority=priority
        )

        messages.success(request, "Product offer applied successfully")
        return redirect("products:admin_product_offer")

    return render(request, "products/admin/admin_offer_product.html", {
        "products": products,
        "offers": offers
    })

#Apply to Entire Category
@admin_login_required
def admin_category_offer(request):
    categories = Category.objects.filter(is_active=True, is_deleted=False)
    offers = Offer.objects.filter(offer_type="CATEGORY", is_deleted=False)

    if request.method == "POST":
        category_id = request.POST.get("category")
        discount = int(request.POST.get("discount_percent"))
        priority = int(request.POST.get("priority", 1))

        category = get_object_or_404(Category, id=category_id)

        Offer.objects.create(
            offer_type="CATEGORY",
            category=category,
            discount_percent=discount,
            priority=priority
        )

        messages.success(request, "Category offer applied successfully")
        return redirect("products:admin_category_offer")

    return render(request, "products/admin/admin_offer_category.html", {
        "categories": categories,
        "offers": offers
    })
#Offer Conflict Handling (Largest Discount Only)
def get_best_offer_for_product(product):
    offers = Offer.objects.filter(
        is_active=True,
        is_deleted=False
    ).order_by("-discount_percent", "priority")

    applicable = [o for o in offers if o.applies_to(product)]
    return applicable[0] if applicable else None

#Referral Offer (Token URL + Coupon Generation)
@admin_login_required
def admin_referral_offer(request):
    if request.method == "POST":
        referrer_id = request.POST.get("user_id")
        discount = int(request.POST.get("discount_percent", 10))
        usage_limit = int(request.POST.get("usage_limit", 1))

        referrer = get_object_or_404(CustomUser, id=referrer_id)

        coupon_code = f"REF{referrer.id}{timezone.now().strftime('%H%M%S')}"

        Coupon.objects.create(
            code=coupon_code,
            discount_type="PERCENT",
            discount_value=discount,
            min_order_amount=0,
            usage_limit=usage_limit,
            expiry_date=timezone.now() + timezone.timedelta(days=30)
        )

        messages.success(request, f"Referral coupon created: {coupon_code}")
        return redirect("products:admin_referral_offer")

    users = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER)
    return render(request, "products/admin/admin_referral_offer.html", {
        "users": users
    })
