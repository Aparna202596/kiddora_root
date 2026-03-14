# shopcore/views/coupon_views.py
# User : apply / remove coupon on cart
# Admin: list, add, edit, soft-delete, toggle

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from types import SimpleNamespace
from accounts.decorators import admin_login_required
from shopcore.models import Cart, Coupon


# ─────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────

def compute_coupon_discount(coupon: Coupon, subtotal: Decimal) -> Decimal:
    """Return discount amount. Exported so checkout / order views can reuse it."""
    if coupon.discount_type == "PERCENT":
        discount = subtotal * coupon.discount_value / 100
        if coupon.max_discount:
            discount = min(discount, coupon.max_discount)
    else:
        discount = coupon.discount_value
    return min(discount, subtotal)


# ─────────────────────────────────────────────────────────────
# USER: APPLY COUPON
# ─────────────────────────────────────────────────────────────

@never_cache
@login_required
def apply_coupon(request):
    if request.method != "POST":
        return redirect("shopcore:cart")

    code = request.POST.get("coupon_code", "").strip().upper()
    if not code:
        messages.error(request, "Please enter a coupon code.")
        return redirect("shopcore:cart")

    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        messages.error(request, f'Coupon "{code}" not found.')
        return redirect("shopcore:cart")

    if not coupon.is_valid():
        messages.error(request, f'Coupon "{code}" is expired or inactive.')
        return redirect("shopcore:cart")

    if coupon.used_by.filter(id=request.user.id).exists():
        messages.error(request, "You have already used this coupon.")
        return redirect("shopcore:cart")

    if coupon.used_count >= coupon.usage_limit:
        messages.error(request, "This coupon has reached its usage limit.")
        return redirect("shopcore:cart")

    cart, _ = Cart.objects.get_or_create(user=request.user)
    subtotal = sum(
        item.variant.product.final_price * item.quantity
        for item in cart.items.select_related("variant__product").all()
    )
    if subtotal < coupon.min_order_amount:
        messages.error(
            request,
            f"Minimum order of ₹{coupon.min_order_amount:.0f} required "
            f"(your cart: ₹{subtotal:.0f})."
        )
        return redirect("shopcore:cart")

    cart.coupon = coupon
    cart.save(update_fields=["coupon"])
    discount = compute_coupon_discount(coupon, subtotal)
    messages.success(request, f'Coupon "{code}" applied — you save ₹{discount:.0f}!')
    return redirect("shopcore:cart")


# ─────────────────────────────────────────────────────────────
# USER: REMOVE COUPON
# ─────────────────────────────────────────────────────────────

@never_cache
@login_required
def remove_coupon(request):
    if request.method != "POST":
        return redirect("shopcore:cart")
    try:
        cart = request.user.cart
        cart.coupon = None
        cart.save(update_fields=["coupon"])
        messages.success(request, "Coupon removed.")
    except Cart.DoesNotExist:
        pass
    return redirect("shopcore:cart")


# ─────────────────────────────────────────────────────────────
# ADMIN: LIST
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
        "page_obj": page_obj,
        "search":   search,
        "type_f":   type_f,
        "status_f": status_f,
        "now":      timezone.now(),
        "discount_choices": Coupon.DISCOUNT_TYPE_CHOICES,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: ADD
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_add_coupon(request):
    if request.method == "POST":
        return _save_coupon(request, instance=None)
    return render(request, "coupon_offer/admin_coupon_form.html", {
        "action": "Add",
        "discount_choices": Coupon.DISCOUNT_TYPE_CHOICES,      
        "coupon": None,
        "form_data": SimpleNamespace(
            code="", discount_type="", discount_value="",
            max_discount="", min_order_amount="", start_date="",
            expiry_date="", usage_limit="", is_active=False,
        ),
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: EDIT
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
        "form_data": SimpleNamespace(
            code="", discount_type="", discount_value="",
            max_discount="", min_order_amount="", start_date="",
            expiry_date="", usage_limit="", is_active=False,
        ),
    })


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
        errors.append("Discount value must be a positive number.")
    if not start_date or not expiry_date:
        errors.append("Start date and expiry date are required.")

    ctx = {
        "action": "Edit" if instance else "Add",
        "coupon": instance,
        "discount_choices": Coupon.DISCOUNT_TYPE_CHOICES,
        "form_data": request.POST,
    }
    if errors:
        for e in errors:
            messages.error(request, e)
        return render(request, "coupon_offer/admin_coupon_form.html", ctx)

    obj = instance or Coupon()
    obj.code             = code
    obj.discount_type    = discount_type
    obj.discount_value   = Decimal(discount_val)
    obj.max_discount     = Decimal(max_discount) if max_discount else None
    obj.min_order_amount = Decimal(min_order)
    obj.start_date       = start_date
    obj.expiry_date      = expiry_date
    obj.usage_limit      = int(usage_limit)
    obj.is_active        = is_active
    obj.save()

    messages.success(request, f'Coupon "{obj.code}" {"updated" if instance else "created"}.')
    return redirect("shopcore:admin_coupon_list")


# ─────────────────────────────────────────────────────────────
# ADMIN: SOFT DELETE
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
    # GET - handled via confirm_modal.html in the list template
    return redirect("shopcore:admin_coupon_list")


# ─────────────────────────────────────────────────────────────
# ADMIN: TOGGLE ACTIVE
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_toggle_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id)
    if request.method == "POST":
        coupon.is_active = not coupon.is_active
        coupon.save(update_fields=["is_active"])
        messages.success(request, f'Coupon "{coupon.code}" {"activated" if coupon.is_active else "deactivated"}.')
    return redirect("shopcore:admin_coupon_list")