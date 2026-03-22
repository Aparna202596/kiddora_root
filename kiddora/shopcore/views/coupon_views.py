from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.decorators import admin_login_required, user_login_required
from shopcore.models import Cart, Coupon, CouponUsage


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _get_cart(user):
    try:
        return user.cart
    except Cart.DoesNotExist:
        return None


def compute_coupon_discount(coupon: Coupon, subtotal: Decimal) -> Decimal:
    """
    Compute the actual money saved for a given coupon + subtotal.
    • PERCENT: discount = subtotal × pct/100, capped by max_discount if set.
    • FLAT:    discount = flat value.
    Discount is always capped to subtotal (can't exceed order value).
    """
    if subtotal < coupon.min_order_amount:
        return Decimal("0")

    if coupon.discount_type == "PERCENT":
        discount = subtotal * coupon.discount_value / Decimal("100")
        if coupon.max_discount:
            discount = min(discount, coupon.max_discount)
    else:  # FLAT
        discount = coupon.discount_value

    return min(discount, subtotal)


def _coupon_json_error(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"success": False, "error": msg}, status=status)


def _user_usage(coupon: Coupon, user) -> int:
    """How many times has this user already used this coupon."""
    try:
        return coupon.usages.get(user=user).times_used
    except CouponUsage.DoesNotExist:
        return 0


# ─────────────────────────────────────────────────────────────
# USER: APPLY COUPON  (AJAX + form-POST)
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@require_POST
def apply_coupon(request):
    ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    code = request.POST.get("coupon_code", "").strip().upper()

    if not code:
        if ajax:
            return _coupon_json_error("Please enter a coupon code.")
        messages.error(request, "Please enter a coupon code.")
        return redirect("shopcore:checkout")

    try:
        coupon = Coupon.objects.get(code=code, is_active=True, is_deleted=False)
    except Coupon.DoesNotExist:
        if ajax:
            return _coupon_json_error(f'Coupon "{code}" not found or inactive.')
        messages.error(request, f'Coupon "{code}" not found.')
        return redirect("shopcore:checkout")

    if not coupon.is_valid():
        if ajax:
            return _coupon_json_error(f'Coupon "{code}" is expired or inactive.')
        messages.error(request, f'Coupon "{code}" is expired or inactive.')
        return redirect("shopcore:checkout")

    # Per-user usage check (uses CouponUsage — no used_by M2M)
    times_used = _user_usage(coupon, request.user)
    if times_used >= coupon.usage_limit:
        msg = "You have reached the maximum usage limit for this coupon."
        if ajax:
            return _coupon_json_error(msg)
        messages.error(request, msg)
        return redirect("shopcore:checkout")

    # Determine subtotal
    if ajax:
        try:
            subtotal = Decimal(request.POST.get("subtotal", "0"))
        except Exception:
            subtotal = Decimal("0")
    else:
        cart = _get_cart(request.user)
        if not cart:
            messages.error(request, "No active cart found.")
            return redirect("shopcore:checkout")
        subtotal = sum(
            item.variant.product.final_price * item.quantity
            for item in cart.items.select_related("variant__product")
        )

    if subtotal < coupon.min_order_amount:
        msg = f"Minimum order of ₹{coupon.min_order_amount:.0f} required for this coupon."
        if ajax:
            return _coupon_json_error(msg)
        messages.error(request, msg)
        return redirect("shopcore:checkout")

    discount = compute_coupon_discount(coupon, subtotal)

    # Store in session (works for both AJAX and form POST)
    request.session["applied_coupon_code"]     = coupon.code
    request.session["applied_coupon_discount"] = str(discount)
    request.session.modified = True

    if ajax:
        return JsonResponse({
            "success":        True,
            "coupon_code":    coupon.code,
            "discount_type":  coupon.discount_type,
            "discount_value": str(coupon.discount_value),
            "max_discount":   str(coupon.max_discount) if coupon.max_discount else None,
            "discount":       str(discount),
            "message":        f'Coupon "{coupon.code}" applied! You save ₹{discount:.2f}.',
        })

    messages.success(request, f'Coupon "{code}" applied! You save ₹{discount:.0f}.')
    return redirect("shopcore:checkout")


# ─────────────────────────────────────────────────────────────
# USER: REMOVE COUPON
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
@require_POST
def remove_coupon(request):
    ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    request.session.pop("applied_coupon_code", None)
    request.session.pop("applied_coupon_discount", None)
    request.session.modified = True

    # Also clear from cart model FK if present (backward compat)
    cart = _get_cart(request.user)
    if cart and getattr(cart, "coupon", None):
        cart.coupon = None
        cart.save(update_fields=["coupon"])

    if ajax:
        return JsonResponse({"success": True, "message": "Coupon removed."})

    messages.success(request, "Coupon removed.")
    return redirect("shopcore:checkout")


# ─────────────────────────────────────────────────────────────
# USER: COUPON LIST (browse available coupons)
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
def user_coupon_list(request):
    now     = timezone.now()
    coupons = Coupon.objects.filter(
        is_active=True, is_deleted=False,
        start_date__lte=now, expiry_date__gte=now,
    )

    coupon_data = []
    for coupon in coupons:
        times_used       = _user_usage(coupon, request.user)
        usage_exhausted  = times_used >= coupon.usage_limit
        remaining_uses   = max(coupon.usage_limit - times_used, 0)

        condition = (
            f"Minimum order of ₹{coupon.min_order_amount:.0f} required"
            if coupon.min_order_amount and coupon.min_order_amount > 0
            else "No minimum order required"
        )

        if coupon.discount_type == "PERCENT":
            discount_label = f"{coupon.discount_value:.0f}% off"
            if coupon.max_discount:
                discount_label += f" (up to ₹{coupon.max_discount:.0f})"
        else:
            discount_label = f"₹{coupon.discount_value:.0f} flat off"

        coupon_data.append({
            "code":             coupon.code,
            "discount_type":    coupon.discount_type,
            "discount_label":   discount_label,
            "discount_value":   coupon.discount_value,
            "max_discount":     coupon.max_discount,
            "min_order_amount": coupon.min_order_amount,
            "condition":        condition,
            "start_date":       coupon.start_date,
            "expiry_date":      coupon.expiry_date,
            "usage_limit":      coupon.usage_limit,
            "used_count":       coupon.used_count,
            "remaining_uses":   remaining_uses,
            "already_used":     times_used > 0,
            "usage_exhausted":  usage_exhausted,
            "is_available":     not usage_exhausted,
        })

    return render(request, "coupons/user_coupon_list.html", {
        "coupon_data": coupon_data,
        "now":         now,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: COUPON LIST
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_coupon_list(request):
    search   = request.GET.get("search", "").strip()
    type_f   = request.GET.get("type", "")
    status_f = request.GET.get("status", "")

    qs = Coupon.objects.filter(is_deleted=False)

    if search:
        qs = qs.filter(code__icontains=search)
    if type_f:
        qs = qs.filter(discount_type=type_f)
    if status_f == "active":
        qs = qs.filter(is_active=True, expiry_date__gte=timezone.now())
    elif status_f == "inactive":
        qs = qs.filter(is_active=False)
    elif status_f == "expired":
        qs = qs.filter(expiry_date__lt=timezone.now())

    page_obj = Paginator(qs, 15).get_page(request.GET.get("page"))

    return render(request, "coupon_offer/admin_coupon_list.html", {
        "page_obj":         page_obj,
        "search":           search,
        "type_f":           type_f,
        "status_f":         status_f,
        "now":              timezone.now(),
        "discount_choices": Coupon.DISCOUNT_TYPE_CHOICES,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: ADD COUPON
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_add_coupon(request):
    if request.method == "POST":
        return _save_coupon(request, instance=None)

    return render(request, "coupon_offer/admin_coupon_form.html", {
        "action":           "Add",
        "discount_choices": Coupon.DISCOUNT_TYPE_CHOICES,
        "coupon":           None,
        "form_data": SimpleNamespace(
            code="", discount_type="", discount_value="",
            max_discount="", min_order_amount="", start_date="",
            expiry_date="", usage_limit="", is_active=False,
        ),
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: EDIT COUPON
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_edit_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id, is_deleted=False)

    if request.method == "POST":
        return _save_coupon(request, instance=coupon)

    return render(request, "coupon_offer/admin_coupon_form.html", {
        "action":           "Edit",
        "coupon":           coupon,
        "discount_choices": Coupon.DISCOUNT_TYPE_CHOICES,
        "form_data":        coupon,   # use model instance for pre-fill
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: SAVE COUPON (shared by add + edit)
# ─────────────────────────────────────────────────────────────

def _save_coupon(request, instance):
    code          = request.POST.get("code", "").strip().upper()
    discount_type = request.POST.get("discount_type", "PERCENT")
    discount_val  = request.POST.get("discount_value", "")
    max_discount  = request.POST.get("max_discount", "") or None
    min_order     = request.POST.get("min_order_amount", "0") or "0"
    start_date    = request.POST.get("start_date", "")
    expiry_date   = request.POST.get("expiry_date", "")
    usage_limit   = request.POST.get("usage_limit", "1") or "1"
    is_active     = bool(request.POST.get("is_active"))

    errors = []

    if not code:
        errors.append("Coupon code is required.")
    if instance is None and Coupon.objects.filter(code=code).exists():
        errors.append(f'Code "{code}" already exists.')

    try:
        dv = Decimal(discount_val)
        if dv <= 0:
            raise ValueError
        if discount_type == "PERCENT" and dv > 100:
            errors.append("Percentage discount cannot exceed 100.")
    except Exception:
        if not errors or "Percentage" not in str(errors):
            errors.append("Discount value must be a positive number.")

    if not start_date or not expiry_date:
        errors.append("Start date and expiry date are required.")

    ctx = {
        "action":           "Edit" if instance else "Add",
        "coupon":           instance,
        "discount_choices": Coupon.DISCOUNT_TYPE_CHOICES,
        "form_data":        request.POST,
    }

    if errors:
        for e in errors:
            messages.error(request, e)
        return render(request, "coupon_offer/admin_coupon_form.html", ctx)

    obj               = instance or Coupon()
    obj.code          = code
    obj.discount_type = discount_type
    obj.discount_value   = Decimal(discount_val)
    obj.max_discount     = Decimal(max_discount) if max_discount else None
    obj.min_order_amount = Decimal(min_order)
    obj.start_date       = start_date
    obj.expiry_date      = expiry_date
    obj.usage_limit      = int(usage_limit)
    obj.is_active        = is_active
    obj.save()

    messages.success(
        request,
        f'Coupon "{obj.code}" {"updated" if instance else "created"}.',
    )
    return redirect("shopcore:admin_coupon_list")


# ─────────────────────────────────────────────────────────────
# ADMIN: SOFT-DELETE COUPON
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_delete_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id)
    if request.method == "POST":
        coupon.is_deleted = True
        coupon.is_active  = False
        coupon.save(update_fields=["is_deleted", "is_active"])
        messages.success(request, f'Coupon "{coupon.code}" deleted.')
    return redirect("shopcore:admin_coupon_list")


# ─────────────────────────────────────────────────────────────
# ADMIN: BLOCK COUPON  (deactivate)
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_block_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id, is_deleted=False)
    if request.method == "POST":
        coupon.is_active = False
        coupon.save(update_fields=["is_active"])
        messages.success(request, f'Coupon "{coupon.code}" blocked.')
        return redirect("shopcore:admin_coupon_list")
    return render(request, "admin_confirm_block.html", {"coupon": coupon})


# ─────────────────────────────────────────────────────────────
# ADMIN: UNBLOCK COUPON  (reactivate)
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_unblock_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id, is_deleted=False)
    if request.method == "POST":
        coupon.is_active = True
        coupon.save(update_fields=["is_active"])
        messages.success(request, f'Coupon "{coupon.code}" unblocked.')
        return redirect("shopcore:admin_coupon_list")
    return render(request, "admin_confirm_unblock.html", {"coupon": coupon})