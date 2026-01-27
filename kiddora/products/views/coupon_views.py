from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from cart.models import Cart, CartItem
from products.models import Product, Category, Offer, Coupon
from accounts.models import CustomUser
from accounts.decorators import admin_login_required,user_login_required

@admin_login_required
def admin_create_coupon(request):
    if request.method == "POST":
        code = request.POST.get("code").upper()

        if Coupon.objects.filter(code=code).exists():
            messages.error(request, "Coupon code already exists")
            return redirect("products:admin_create_coupon")

        Coupon.objects.create(
            code=code,
            discount_type=request.POST.get("discount_type"),
            discount_value=int(request.POST.get("discount_value")),
            min_order_amount=request.POST.get("min_order_amount"),
            max_discount=request.POST.get("max_discount") or None,
            usage_limit=int(request.POST.get("usage_limit")),
            expiry_date=request.POST.get("expiry_date"),
        )

        messages.success(request, "Coupon created successfully")
        return redirect("products:admin_create_coupon")

    return render(request, "products/admin/admin_coupon_form.html")

@admin_login_required
def admin_delete_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id)
    coupon.is_deleted = True
    coupon.is_active = False
    coupon.save()

    messages.success(request, "Coupon deleted successfully")
    return redirect("products:admin_create_coupon")

def apply_coupon(coupon, user):
    if not coupon.can_use(user):
        return False

    coupon.used_by.add(user)
    coupon.used_count += 1
    coupon.save()
    return True

@user_login_required
def apply_coupon(request):
    code = request.POST.get("code")
    cart = get_object_or_404(Cart, user=request.user)

    coupon = Coupon.objects.filter(code=code, is_active=True).first()
    if not coupon or not coupon.can_use(request.user):
        messages.error(request, "Invalid coupon.")
        return redirect("cart:checkout")

    request.session["coupon_id"] = coupon.id
    messages.success(request, "Coupon applied.")
    return redirect("cart:checkout")

@user_login_required
def remove_coupon(request):
    request.session.pop("coupon_id", None)
    messages.success(request, "Coupon removed.")
    return redirect("cart:checkout")
