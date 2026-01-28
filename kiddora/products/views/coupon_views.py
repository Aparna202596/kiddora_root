from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db import transaction

from cart.models import Cart
from products.models import Coupon
from accounts.decorators import admin_login_required, user_login_required

@admin_login_required
def admin_create_coupon(request):
    if request.method == "POST":
        code = request.POST.get("code", "").upper().strip()
        discount_type = request.POST.get("discount_type")
        discount_value = request.POST.get("discount_value")
        min_order_amount = request.POST.get("min_order_amount")
        max_discount = request.POST.get("max_discount")
        usage_limit = request.POST.get("usage_limit")
        expiry_date = request.POST.get("expiry_date")

        # ---------------- VALIDATIONS ----------------
        if not code:
            messages.error(request, "Coupon code is required")
            return redirect("products:admin_create_coupon")

        if Coupon.objects.filter(code=code, is_deleted=False).exists():
            messages.error(request, "Coupon code already exists")
            return redirect("products:admin_create_coupon")

        try:
            discount_value = int(discount_value)
            usage_limit = int(usage_limit)
            min_order_amount = float(min_order_amount)
            max_discount = float(max_discount) if max_discount else None
        except ValueError:
            messages.error(request, "Invalid numeric values")
            return redirect("products:admin_create_coupon")

        if discount_value <= 0 or usage_limit <= 0:
            messages.error(request, "Values must be greater than zero")
            return redirect("products:admin_create_coupon")

        if not expiry_date:
            messages.error(request, "Expiry date is required")
            return redirect("products:admin_create_coupon")

        # ---------------- CREATE COUPON ----------------
        Coupon.objects.create(
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            min_order_amount=min_order_amount,
            max_discount=max_discount,
            usage_limit=usage_limit,
            expiry_date=expiry_date,
            is_active=True,
        )

        messages.success(request, "Coupon created successfully")
        return redirect("products:admin_create_coupon")

    return render(request, "products/coupon_offer/admin_coupon_form.html")

@admin_login_required
def admin_delete_coupon(request, coupon_id):
    Coupon.objects.filter(
        expiry_date__lt=timezone.now(),
        is_active=True
    ).update(is_active=False)

    coupon = get_object_or_404(Coupon, id=coupon_id)

    coupon.is_active = False
    coupon.is_deleted = True
    coupon.save(update_fields=["is_active", "is_deleted"])

    messages.success(request, "Coupon deleted successfully")
    return redirect("products:admin_create_coupon")

@admin_login_required
def admin_coupon_list(request):
    coupons = Coupon.objects.all().order_by("-expiry_date")

    return render(request, "products/coupon_offer/admin_coupon_list.html", {
        "coupons": coupons,
        "now": timezone.now()
    })

@user_login_required
def available_coupons(request):
    coupons = Coupon.objects.filter(
        is_active=True,
        is_deleted=False,
        expiry_date__gte=timezone.now()
    )

    return render(request, "products/coupon_offer/available_coupons.html", {
        "coupons": coupons
    })

@user_login_required
@transaction.atomic
def apply_coupon(request):
    code = request.POST.get("code", "").upper().strip()

    cart = get_object_or_404(Cart, user=request.user)

    coupon = Coupon.objects.filter(
        code=code,
        is_active=True,
        is_deleted=False,
        expiry_date__gte=timezone.now()
    ).first()

    if not coupon:
        messages.error(request, "Invalid or expired coupon")
        return redirect("cart:checkout")

    # ---------- Prevent duplicate usage ----------
    if coupon.used_by.filter(id=request.user.id).exists():
        messages.error(request, "You have already used this coupon")
        return redirect("cart:checkout")

    # ---------- Usage limit ----------
    if coupon.used_count >= coupon.usage_limit:
        messages.error(request, "Coupon usage limit exceeded")
        return redirect("cart:checkout")

    # ---------- Minimum order amount ----------
    if cart.total_price < coupon.min_order_amount:
        messages.error(
            request,
            f"Minimum order amount is {coupon.min_order_amount}"
        )
        return redirect("cart:checkout")

    # ---------- Apply coupon ----------
    request.session["coupon_id"] = coupon.id

    coupon.used_by.add(request.user)
    coupon.used_count += 1
    coupon.save(update_fields=["used_count"])

    messages.success(request, "Coupon applied successfully")
    return redirect("cart:checkout")

@user_login_required
def remove_coupon(request):
    request.session.pop("coupon_id", None)
    messages.success(request, "Coupon removed")
    return redirect("cart:checkout")
