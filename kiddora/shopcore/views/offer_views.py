from __future__ import annotations

from types import SimpleNamespace

from accounts.decorators import admin_login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from products.models import Category, Product
from shopcore.models import Coupon, Offer

# ────────────────────────────────────────────────── HELPER FUNCTIONS ──────────────────────────────────────────────────


def get_max_offer_discount_percent(product) -> int:

    if not product:
        return 0

    now = timezone.now()
    active_offers = Offer.objects.filter(
        is_active=True,
        is_deleted=False,
        start_date__lte=now,
    )

    product_pct = 0
    category_pct = 0

    product_offer = active_offers.filter(offer_type="PRODUCT", product=product).first()
    if product_offer and product_offer.is_valid():
        product_pct = product_offer.discount_percent

    try:
        if product.subcategory and product.subcategory.category:
            category_offer = active_offers.filter(
                offer_type="CATEGORY",
                category=product.subcategory.category,
            ).first()
            if category_offer and category_offer.is_valid():
                category_pct = category_offer.discount_percent
    except Exception:
        pass

    return max(product_pct, category_pct)


def get_offer_discount_detail(product) -> dict:
    
    if not product:
        return {
            "discount_percent": 0,
            "offer_type": None,
            "product_percent": 0,
            "category_percent": 0,
        }

    now = timezone.now()
    active_offers = Offer.objects.filter(
        is_active=True,
        is_deleted=False,
        start_date__lte=now,
    )

    product_pct = 0
    category_pct = 0

    product_offer = active_offers.filter(offer_type="PRODUCT", product=product).first()
    if product_offer and product_offer.is_valid():
        product_pct = product_offer.discount_percent

    try:
        if product.subcategory and product.subcategory.category:
            category_offer = active_offers.filter(
                offer_type="CATEGORY",
                category=product.subcategory.category,
            ).first()
            if category_offer and category_offer.is_valid():
                category_pct = category_offer.discount_percent
    except Exception:
        pass

    if product_pct == 0 and category_pct == 0:
        return {
            "discount_percent": 0,
            "offer_type": None,
            "product_percent": 0,
            "category_percent": 0,
        }

    if category_pct >= product_pct:
        winning_type = "CATEGORY"
        winning_pct = category_pct
    else:
        winning_type = "PRODUCT"
        winning_pct = product_pct

    return {
        "discount_percent": winning_pct,
        "offer_type": winning_type,
        "product_percent": product_pct,
        "category_percent": category_pct,
    }


# ────────────────────────────────────────────────── ADMIN: LIST ──────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_offer_list(request):
    search = request.GET.get("search", "").strip()
    type_f = request.GET.get("type", "")
    status_f = request.GET.get("status", "")

    qs = Offer.objects.filter(is_deleted=False).select_related(
        "product", "category", "referral_coupon", "referrer_coupon", "new_user_coupon"
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

    return render(
        request,
        "coupon_offer/admin_offer_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "type_f": type_f,
            "status_f": status_f,
            "offer_types": Offer.OFFER_TYPE_CHOICES,
            "now": timezone.now(),
        },
    )


# ────────────────────────────────────────────────── ADMIN: ADD ──────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_add_offer(request):
    if request.method == "POST":
        return _save_offer(request, instance=None)

    return render(
        request,
        "coupon_offer/admin_offer_form.html",
        {
            "action": "Add",
            "offer": None,
            "offer_types": Offer.OFFER_TYPE_CHOICES,
            "products": Product.objects.filter(
                is_active=True, is_deleted=False
            ).order_by("product_name"),
            "categories": Category.objects.filter(
                is_active=True, is_deleted=False
            ).order_by("category_name"),
            "coupons": Coupon.objects.filter(is_active=True, is_deleted=False).order_by(
                "code"
            ),
            "form_data": SimpleNamespace(
                offer_type="",
                product_id="",
                category_id="",
                referral_coupon_id="",  
                referrer_coupon_id="",  
                new_user_coupon_id="",  
                discount_percent="",
                start_date="",
                end_date="",
                is_active=False,
            ),
        },
    )


# ────────────────────────────────────────────────── ADMIN: EDIT ──────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_edit_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id, is_deleted=False)

    if request.method == "POST":
        return _save_offer(request, instance=offer)

    return render(
        request,
        "coupon_offer/admin_offer_form.html",
        {
            "action": "Edit",
            "offer": offer,
            "offer_types": Offer.OFFER_TYPE_CHOICES,
            "products": Product.objects.filter(
                is_active=True, is_deleted=False
            ).order_by("product_name"),
            "categories": Category.objects.filter(
                is_active=True, is_deleted=False
            ).order_by("category_name"),
            "coupons": Coupon.objects.filter(is_active=True, is_deleted=False).order_by(
                "code"
            ),
            "form_data": offer,
        },
    )


# ────────────────────────────────────────────────── ADMIN: SAVE (internal) ───────────────────────────────────────────


def _save_offer(request, instance):

    offer_type = request.POST.get("offer_type", "").strip()
    product_id = request.POST.get("product_id", "") or None
    category_id = request.POST.get("category_id", "") or None
    referrer_coupon_id = request.POST.get("referrer_coupon_id", "") or None
    new_user_coupon_id = request.POST.get("new_user_coupon_id", "") or None
    discount_percent_str = request.POST.get("discount_percent", "").strip()
    start_date = request.POST.get("start_date", "").strip()
    end_date = request.POST.get("end_date", "") or None
    is_active = bool(request.POST.get("is_active"))

    errors = []

    if not offer_type:
        errors.append("Offer type is required.")

    if offer_type == "PRODUCT" and not product_id:
        errors.append("A product must be selected for product offers.")
    if offer_type == "CATEGORY" and not category_id:
        errors.append("A category must be selected for category offers.")

    if offer_type in ("PRODUCT", "CATEGORY"):
        if not discount_percent_str:
            errors.append(
                "Discount percent is required for Product and Category offers."
            )
        else:
            try:
                dp = int(discount_percent_str)
                if dp < 1 or dp > 100:
                    raise ValueError
                discount_percent = dp
            except (ValueError, TypeError):
                errors.append("Discount percent must be a number between 1 and 100.")
    else:
        discount_percent = 0

    if not start_date:
        errors.append("Start date is required.")

    if errors:
        ctx = {
            "action": "Edit" if instance else "Add",
            "offer": instance,
            "offer_types": Offer.OFFER_TYPE_CHOICES,
            "products": Product.objects.filter(
                is_active=True, is_deleted=False
            ).order_by("product_name"),
            "categories": Category.objects.filter(
                is_active=True, is_deleted=False
            ).order_by("category_name"),
            "coupons": Coupon.objects.filter(is_active=True, is_deleted=False).order_by(
                "code"
            ),
            "form_data": request.POST,
        }
        for e in errors:
            messages.error(request, e)
        return render(request, "coupon_offer/admin_offer_form.html", ctx)

    obj = instance or Offer()
    obj.offer_type = offer_type
    obj.product = Product.objects.filter(id=product_id).first() if product_id else None
    obj.category = (
        Category.objects.filter(id=category_id).first() if category_id else None
    )

    obj.referrer_coupon = (
        Coupon.objects.filter(id=referrer_coupon_id).first()
        if referrer_coupon_id
        else None
    )
    obj.new_user_coupon = (
        Coupon.objects.filter(id=new_user_coupon_id).first()
        if new_user_coupon_id
        else None
    )

    obj.discount_percent = discount_percent
    obj.start_date = start_date
    obj.end_date = end_date
    obj.is_active = is_active
    obj.save()

    messages.success(
        request, f'Offer {"updated" if instance else "created"} successfully.'
    )
    return redirect("shopcore:admin_offer_list")


# ────────────────────────────────────────────────── ADMIN: DELETE ──────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_delete_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    if request.method == "POST":
        offer.is_deleted = True
        offer.is_active = False
        offer.save(update_fields=["is_deleted", "is_active"])
        messages.success(request, "Offer deleted.")
    return redirect("shopcore:admin_offer_list")


# ────────────────────────────────────────────────── ADMIN: BLOCK ──────────────────────────────────────────────────


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


# ────────────────────────────────────────────────── ADMIN: UNBLOCK ──────────────────────────────────────────────────


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
