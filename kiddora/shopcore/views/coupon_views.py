from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from accounts.decorators import admin_login_required, user_login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from shopcore.models import Cart, Coupon, CouponUsage, ReferralUse

# ────────────────────────────────────────────────── HELPERS ──────────────────────────────────────────────────


def _get_cart(user):
    try:
        return user.cart
    except Cart.DoesNotExist:
        return None


def compute_coupon_discount(coupon: Coupon, subtotal: Decimal) -> Decimal:
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
    try:
        return coupon.usages.get(user=user).times_used
    except CouponUsage.DoesNotExist:
        return 0


def _referral_coupon_ids_for_user(user):
    """
    TASK 1 — Returns the set of coupon IDs that `user` is entitled to via the
    referral system.  Two separate coupon types are now supported:

    new_user_coupon  – awarded to THIS user when they signed up via someone
                       else's referral link (ReferralUse.new_user_coupon).
    coupon_awarded   – awarded to THIS user when THEY referred someone else
                       (ReferralUse.coupon_awarded, the legacy referrer field).

    Both coupon IDs are returned so checkout can display and accept them.
    """
    # Coupons THIS user received as the NEW user (signed up via referral)
    new_user_ids = ReferralUse.objects.filter(referred_user=user).values_list(
        "new_user_coupon_id", flat=True
    )

    # Coupons THIS user received as the REFERRER (they referred someone)
    referrer_ids = ReferralUse.objects.filter(referral_code__user=user).values_list(
        "coupon_awarded_id", flat=True
    )

    # Combine and deduplicate, dropping None values
    combined = set(filter(None, list(new_user_ids) + list(referrer_ids)))
    return list(combined)


# ────────────────────────────────────────────────── APPLY COUPON ──────────────────────────────────────────────────


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

    # Validate per-user usage limit
    times_used = _user_usage(coupon, request.user)
    if times_used >= coupon.usage_limit:
        msg = "You have reached the maximum usage limit for this coupon."
        if ajax:
            return _coupon_json_error(msg)
        messages.error(request, msg)
        return redirect("shopcore:checkout")

    # TASK 1: For REFERRAL coupons, verify this user is actually entitled to it
    if coupon.coupon_type == "REFERRAL":
        entitled_ids = _referral_coupon_ids_for_user(request.user)
        if coupon.id not in entitled_ids:
            msg = "This referral coupon is not valid for your account."
            if ajax:
                return _coupon_json_error(msg)
            messages.error(request, msg)
            return redirect("shopcore:checkout")

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
        msg = (
            f"Minimum order of ₹{coupon.min_order_amount:.0f} required for this coupon."
        )
        if ajax:
            return _coupon_json_error(msg)
        messages.error(request, msg)
        return redirect("shopcore:checkout")

    discount = compute_coupon_discount(coupon, subtotal)

    request.session["applied_coupon_code"] = coupon.code
    request.session["applied_coupon_discount"] = str(discount)
    request.session.modified = True

    if ajax:
        return JsonResponse(
            {
                "success": True,
                "coupon_code": coupon.code,
                "coupon_type": coupon.coupon_type,  # "PUBLIC" or "REFERRAL"
                "discount_type": coupon.discount_type,
                "discount_value": str(coupon.discount_value),
                "max_discount": (
                    str(coupon.max_discount) if coupon.max_discount else None
                ),
                "discount": str(discount),
                "message": f'Coupon "{coupon.code}" applied! You save ₹{discount:.2f}.',
            }
        )

    messages.success(request, f'Coupon "{code}" applied! You save ₹{discount:.0f}.')
    return redirect("shopcore:checkout")


# ────────────────────────────────────────────────── REMOVE COUPON ──────────────────────────────────────────────────


@never_cache
@user_login_required
@require_POST
def remove_coupon(request):
    ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    request.session.pop("applied_coupon_code", None)
    request.session.pop("applied_coupon_discount", None)
    request.session.modified = True

    cart = _get_cart(request.user)
    if cart and getattr(cart, "coupon", None):
        cart.coupon = None
        cart.save(update_fields=["coupon"])

    if ajax:
        return JsonResponse({"success": True, "message": "Coupon removed."})

    messages.success(request, "Coupon removed.")
    return redirect("shopcore:checkout")


# ────────────────────────────────────────────────── USER: COUPON LIST ──────────────────────────────────────────────────


@never_cache
@user_login_required
def user_coupon_list(request):
    now = timezone.now()
    referral_coupon_ids = _referral_coupon_ids_for_user(request.user)

    coupons = (
        Coupon.objects.filter(
            is_active=True,
            is_deleted=False,
            start_date__lte=now,
            expiry_date__gte=now,
        )
        .filter(
            Q(coupon_type="PUBLIC")
            | Q(coupon_type="REFERRAL", id__in=referral_coupon_ids)
        )
        .distinct()
    )

    coupon_data = []
    for coupon in coupons:
        times_used = _user_usage(coupon, request.user)
        usage_exhausted = times_used >= coupon.usage_limit
        remaining_uses = max(coupon.usage_limit - times_used, 0)

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

        # TASK 1: Tag so the template can explain where the coupon came from
        is_referral = coupon.coupon_type == "REFERRAL"
        referral_role = None
        if is_referral:
            # Was this coupon awarded to THIS user when they signed up via referral?
            new_user_ids = list(
                ReferralUse.objects.filter(referred_user=request.user).values_list(
                    "new_user_coupon_id", flat=True
                )
            )
            if coupon.id in new_user_ids:
                referral_role = "new_user"  # earned by signing up via referral
            else:
                referral_role = "referrer"  # earned by referring someone else

        coupon_data.append(
            {
                "code": coupon.code,
                "discount_type": coupon.discount_type,
                "discount_label": discount_label,
                "discount_value": coupon.discount_value,
                "max_discount": coupon.max_discount,
                "min_order_amount": coupon.min_order_amount,
                "condition": condition,
                "start_date": coupon.start_date,
                "expiry_date": coupon.expiry_date,
                "usage_limit": coupon.usage_limit,
                "used_count": coupon.used_count,
                "remaining_uses": remaining_uses,
                "already_used": times_used > 0,
                "usage_exhausted": usage_exhausted,
                "is_available": not usage_exhausted,
                "is_referral": is_referral,
                # TASK 1: "new_user" | "referrer" | None
                "referral_role": referral_role,
            }
        )

    return render(
        request,
        "coupons/user_coupon_list.html",
        {
            "coupon_data": coupon_data,
            "now": now,
        },
    )


# ────────────────────────────────────────────────── ADMIN: COUPON LIST ──────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_coupon_list(request):
    search = request.GET.get("search", "").strip()
    type_f = request.GET.get("type", "")
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

    return render(
        request,
        "coupon_offer/admin_coupon_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "type_f": type_f,
            "status_f": status_f,
            "now": timezone.now(),
            "discount_choices": Coupon.DISCOUNT_TYPE_CHOICES,
        },
    )


# ────────────────────────────────────────────────── ADMIN: COUPON DETAIL ──────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_coupon_detail(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id)
    now = timezone.now()

    is_expired = coupon.expiry_date < now
    is_upcoming = coupon.start_date > now
    if is_expired:
        status_label, status_class = "Expired", "badge-expired"
    elif not coupon.is_active:
        status_label, status_class = "Inactive", "badge-inactive"
    elif is_upcoming:
        status_label, status_class = "Scheduled", "badge-scheduled"
    else:
        status_label, status_class = "Active", "badge-active"

    if coupon.discount_type == "PERCENT":
        discount_label = f"{coupon.discount_value:.0f}% off"
        if coupon.max_discount:
            discount_label += f" (max ₹{coupon.max_discount:.0f})"
    else:
        discount_label = f"₹{coupon.discount_value:.0f} flat off"

    usages = (
        CouponUsage.objects.filter(coupon=coupon)
        .select_related("user")
        .order_by("-times_used", "user__email")
    )

    usage_rows = []
    for u in usages:
        usage_rows.append(
            {
                "user": u.user,
                "times_used": u.times_used,
                "remaining": max(coupon.usage_limit - u.times_used, 0),
                "exhausted": u.times_used >= coupon.usage_limit,
            }
        )

    unique_users_count = usages.count()
    exhausted_users_count = sum(1 for r in usage_rows if r["exhausted"])

    from shopcore.models import Order

    linked_orders = (
        Order.objects.filter(coupon=coupon)
        .select_related("user", "address")
        .order_by("-order_date")
    )
    total_discount_given = linked_orders.aggregate(total=Sum("coupon_discount"))[
        "total"
    ] or Decimal("0")
    total_revenue = linked_orders.aggregate(total=Sum("final_amount"))[
        "total"
    ] or Decimal("0")

    orders_page = Paginator(linked_orders, 10).get_page(request.GET.get("opage"))

    referral_offers = coupon.referral_offers.filter(is_deleted=False)

    return render(
        request,
        "coupon_offer/admin_coupon_detail.html",
        {
            "coupon": coupon,
            "now": now,
            "status_label": status_label,
            "status_class": status_class,
            "is_expired": is_expired,
            "is_upcoming": is_upcoming,
            "discount_label": discount_label,
            "usage_rows": usage_rows,
            "unique_users_count": unique_users_count,
            "exhausted_users_count": exhausted_users_count,
            "linked_orders": linked_orders,
            "orders_page": orders_page,
            "total_discount_given": total_discount_given,
            "total_revenue": total_revenue,
            "referral_offers": referral_offers,
        },
    )


# ────────────────────────────────────────────────── ADMIN: ADD / EDIT COUPON ──────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_add_coupon(request):
    if request.method == "POST":
        return _save_coupon(request, instance=None)

    return render(
        request,
        "coupon_offer/admin_coupon_form.html",
        {
            "action": "Add",
            "discount_choices": Coupon.DISCOUNT_TYPE_CHOICES,
            "coupon_type_choices": Coupon.COUPON_TYPE_CHOICES,
            "coupon": None,
            "form_data": SimpleNamespace(
                code="",
                coupon_type="PUBLIC",
                discount_type="",
                discount_value="",
                max_discount="",
                min_order_amount="",
                start_date="",
                expiry_date="",
                usage_limit="",
                is_active=False,
            ),
        },
    )


@never_cache
@admin_login_required
def admin_edit_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id, is_deleted=False)
    if request.method == "POST":
        return _save_coupon(request, instance=coupon)

    return render(
        request,
        "coupon_offer/admin_coupon_form.html",
        {
            "action": "Edit",
            "coupon": coupon,
            "discount_choices": Coupon.DISCOUNT_TYPE_CHOICES,
            "coupon_type_choices": Coupon.COUPON_TYPE_CHOICES,
            "form_data": coupon,
        },
    )


def _save_coupon(request, instance):
    code = request.POST.get("code", "").strip().upper()
    coupon_type = request.POST.get("coupon_type", "PUBLIC")
    discount_type = request.POST.get("discount_type", "PERCENT")
    discount_val = request.POST.get("discount_value", "")
    max_discount = request.POST.get("max_discount", "") or None
    min_order = request.POST.get("min_order_amount", "0") or "0"
    start_date = request.POST.get("start_date", "")
    expiry_date = request.POST.get("expiry_date", "")
    usage_limit = request.POST.get("usage_limit", "1") or "1"
    is_active = bool(request.POST.get("is_active"))

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
        "action": "Edit" if instance else "Add",
        "coupon": instance,
        "discount_choices": Coupon.DISCOUNT_TYPE_CHOICES,
        "coupon_type_choices": Coupon.COUPON_TYPE_CHOICES,
        "form_data": request.POST,
    }

    if errors:
        for e in errors:
            messages.error(request, e)
        return render(request, "coupon_offer/admin_coupon_form.html", ctx)

    obj = instance or Coupon()
    obj.code = code
    obj.coupon_type = coupon_type
    obj.discount_type = discount_type
    obj.discount_value = Decimal(discount_val)
    obj.max_discount = Decimal(max_discount) if max_discount else None
    obj.min_order_amount = Decimal(min_order)
    obj.start_date = start_date
    obj.expiry_date = expiry_date
    obj.usage_limit = int(usage_limit)
    obj.is_active = is_active
    obj.save()

    messages.success(
        request,
        f'Coupon "{obj.code}" {"updated" if instance else "created"}.',
    )
    return redirect("shopcore:admin_coupon_list")


# ────────────────────────────────────────────────── ADMIN: DELETE / BLOCK / UNBLOCK ──────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_delete_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id)
    if request.method == "POST":
        coupon.is_deleted = True
        coupon.is_active = False
        coupon.save(update_fields=["is_deleted", "is_active"])
        messages.success(request, f'Coupon "{coupon.code}" deleted.')
    return redirect("shopcore:admin_coupon_list")


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
