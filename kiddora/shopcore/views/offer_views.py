from __future__ import annotations

from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator
from accounts.decorators import admin_login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.utils import timezone
from types import SimpleNamespace

from products.models import Category, Product
from shopcore.models import Coupon, Offer

# ────────────────────────────────────────────────── HELPER FUNCTION ──────────────────────────────────────────────────
def get_max_offer_discount_percent(product) -> int:
    if not product:
        return 0

    now = timezone.now()
    active_offers = Offer.objects.filter(
        is_active = True, is_deleted=False, start_date__lte = now
    )

    product_offer = active_offers.filter(
        offer_type="PRODUCT", product = product
    ).first()

    category_offer = None
    try:
        if product.subcategory and product.subcategory.category:
            category_offer = active_offers.filter(
                offer_type = "CATEGORY",
                category = product.subcategory.category,
            ).first()
    except Exception:
        pass

    max_pct = 0
    if product_offer and product_offer.is_valid():
        max_pct = max(max_pct, product_offer.discount_percent)
    if category_offer and category_offer.is_valid():
        max_pct = max(max_pct, category_offer.discount_percent)

    return max_pct

# ────────────────────────────────────────────────── ADMIN: LIST + FILTER + PAGINATION ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_offer_list(request):
    search = request.GET.get("search", "").strip()
    type_f = request.GET.get("type", "")
    status_f = request.GET.get("status", "")

    qs = Offer.objects.filter(is_deleted=False).select_related(
        "product", "category", "referral_coupon"
    )

    if search:
        qs = qs.filter(
            Q(product__product_name__icontains=search)
            | Q(category__category_name__icontains=search)
        )
    if type_f:
        qs = qs.filter(offer_type=type_f)
    if status_f == "active":
        qs = qs.filter(is_active=True)
    elif status_f == "inactive":
        qs = qs.filter(is_active=False)

    page_obj = Paginator(qs, 15).get_page(request.GET.get("page"))

    return render(request, "coupon_offer/admin_offer_list.html", {
        "page_obj": page_obj,
        "search": search,
        "type_f": type_f,
        "status_f": status_f,
        "offer_types": Offer.OFFER_TYPE_CHOICES,
        "now": timezone.now(),
    })

#────────────────────────────────────────────────── ADMIN: ADD ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_add_offer(request):
    if request.method == "POST":
        return _save_offer(request, instance=None)

    return render(request, "coupon_offer/admin_offer_form.html", {
        "action": "Add",
        "offer": None,
        "offer_types": Offer.OFFER_TYPE_CHOICES,
        "products": Product.objects.filter(is_active=True, is_deleted=False).order_by("product_name"),
        "categories": Category.objects.filter(is_active=True, is_deleted=False).order_by("category_name"),
        "coupons": Coupon.objects.filter(is_active=True, is_deleted=False).order_by("code"),
        "form_data": SimpleNamespace(
            offer_type="", product_id="", category_id="",
            referral_coupon_id="", discount_percent="",
            start_date="", end_date="", is_active=False,
        ),
    })

#────────────────────────────────────────────────── ADMIN: EDIT ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_edit_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id, is_deleted=False)

    if request.method == "POST":
        return _save_offer(request, instance=offer)

    return render(request, "coupon_offer/admin_offer_form.html", {
        "action": "Edit",
        "offer": offer,
        "offer_types": Offer.OFFER_TYPE_CHOICES,
        "products": Product.objects.filter(is_active=True, is_deleted=False).order_by("product_name"),
        "categories": Category.objects.filter(is_active=True, is_deleted=False).order_by("category_name"),
        "coupons": Coupon.objects.filter(is_active=True, is_deleted=False).order_by("code"),
        "form_data": offer,
    })

#───────────────────────────────────────────────── ADMIN: SAVE (for both add and edit) ──────────────────────────────────────────────────
def _save_offer(request, instance):
    offer_type = request.POST.get("offer_type", "")
    product_id = request.POST.get("product_id", "") or None
    category_id = request.POST.get("category_id", "") or None
    referral_coupon_id = request.POST.get("referral_coupon_id", "") or None
    discount_percent = request.POST.get("discount_percent", "")
    start_date = request.POST.get("start_date", "")
    end_date = request.POST.get("end_date", "") or None
    is_active = bool(request.POST.get("is_active"))

    errors = []

    if not offer_type:
        errors.append("Offer type is required.")
    if offer_type == "PRODUCT" and not product_id:
        errors.append("A product must be selected for product offers.")
    if offer_type == "CATEGORY" and not category_id:
        errors.append("A category must be selected for category offers.")

    try:
        dp = int(discount_percent)
        if dp < 1 or dp > 100:
            raise ValueError
    except (ValueError, TypeError):
        errors.append("Discount percent must be between 1 and 100.")

    if not start_date:
        errors.append("Start date is required.")

    ctx = {
        "action": "Edit" if instance else "Add",
        "offer": instance,
        "offer_types": Offer.OFFER_TYPE_CHOICES,
        "products": Product.objects.filter(is_active=True, is_deleted=False).order_by("product_name"),
        "categories": Category.objects.filter(is_active=True, is_deleted=False).order_by("category_name"),
        "coupons": Coupon.objects.filter(is_active=True, is_deleted=False).order_by("code"),
        "form_data": request.POST,
    }

    if errors:
        for e in errors:
            messages.error(request, e)
        return render(request, "coupon_offer/admin_offer_form.html", ctx)

    obj = instance or Offer()
    obj.offer_type = offer_type
    obj.product = Product.objects.filter(id=product_id).first() if product_id else None
    obj.category = Category.objects.filter(id=category_id).first() if category_id else None
    obj.referral_coupon = Coupon.objects.filter(id=referral_coupon_id).first() if referral_coupon_id else None
    obj.discount_percent = int(discount_percent)
    obj.start_date = start_date
    obj.end_date = end_date
    obj.is_active = is_active
    obj.save()

    messages.success(
        request,
        f'Offer {"updated" if instance else "created"} successfully.',
    )
    return redirect("shopcore:admin_offer_list")

# ────────────────────────────────────────────────── ADMIN: DELETE (soft delete) ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_delete_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    if request.method == "POST":
        offer.is_deleted = True
        offer.is_active  = False
        offer.save(update_fields=["is_deleted", "is_active"])
        messages.success(request, "Offer deleted.")
    return redirect("shopcore:admin_offer_list")

# ────────────────────────────────────────────────── ADMIN: BLOCK OFFER (deactivate) ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_block_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id, is_deleted=False)
    if request.method == "POST":
        offer.is_active = False
        offer.save(update_fields=["is_active"])
        messages.success(request, f'Offer "{offer}" blocked.')
        return redirect("shopcore:admin_offer_list")
    return render(request, "admin_confirm_block.html", {"offer": offer})

# ────────────────────────────────────────────────── ADMIN: UNBLOCK OFFER (activate) ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_unblock_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id, is_deleted=False)
    if request.method == "POST":
        offer.is_active = True
        offer.save(update_fields=["is_active"])
        messages.success(request, f'Offer "{offer}" unblocked.')
        return redirect("shopcore:admin_offer_list")
    return render(request, "admin_confirm_unblock.html", {"offer": offer})