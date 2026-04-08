from types import SimpleNamespace

from accounts.decorators import admin_login_required, user_login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from products.models import Category, Product
from shopcore.models import Banner, Cart, Review, Wishlist

User = get_user_model()


# ────────────────────────────────────────────────── HELPER FUNCTIONS ─────────────────────────────────────────────────────────────
def _cart_wishlist_ctx(user):
    if not user.is_authenticated:
        return {
            "cart_variant_ids": set(),
            "wishlist_product_ids": set(),
            "cart_item_count": 0,
        }
    try:
        cart_variant_ids = set(user.cart.items.values_list("variant_id", flat=True))
        cart_item_count = user.cart.items.count()
    except Cart.DoesNotExist:
        cart_variant_ids = set()
        cart_item_count = 0
    try:
        wishlist_product_ids = set(
            user.wishlist.items.values_list("product_id", flat=True)
        )
    except Wishlist.DoesNotExist:
        wishlist_product_ids = set()
    return {
        "cart_variant_ids": cart_variant_ids,
        "wishlist_product_ids": wishlist_product_ids,
        "cart_item_count": cart_item_count,
    }


def _active_products():
    return (
        Product.objects.filter(
            is_active=True,
            is_deleted=False,
            subcategory__is_active=True,
            subcategory__is_deleted=False,
            subcategory__category__is_active=True,
            subcategory__category__is_deleted=False,
        )
        .select_related("subcategory", "subcategory__category")
        .prefetch_related("images")
    )


def _attach_reviews(product_list):
    pids = [p.id for p in product_list]
    review_map = {
        r["product_id"]: r
        for r in Review.objects.filter(product_id__in=pids, is_approved=True)
        .values("product_id")
        .annotate(avg=Avg("rating"), cnt=Count("id"))
    }
    for p in product_list:
        rd = review_map.get(p.id, {})
        p.avg_rating = round(rd.get("avg") or 0, 1)
        p.review_count = rd.get("cnt", 0)
    return product_list


def anonymous_home(request):
    live_banners = Banner.objects.filter(is_active=True).order_by(
        "display_order", "-created_at"
    )

    # Filter using is_live() method
    hero_banners = [b for b in live_banners if b.slot == "HERO" and b.is_live()]
    secondary_banners = [
        b for b in live_banners if b.slot == "SECONDARY" and b.is_live()
    ][:6]

    # Fallback if no hero banners
    if not hero_banners:
        # You can show a default banner or just the no-banner message
        pass

    categories = Category.objects.filter(is_active=True).order_by("category_name")

    top_products = list(
        _active_products()
        .annotate(
            total_sold=Coalesce(Sum("variants__inventory__quantity_sold"), Value(0))
        )
        .order_by("-total_sold")[:6]
    )
    _attach_reviews(top_products)

    new_arrivals = list(_active_products().order_by("-id")[:6])
    _attach_reviews(new_arrivals)

    uw = _cart_wishlist_ctx(request.user)

    return render(
        request,
        "store/all_home.html",
        {
            "hero_banners": hero_banners,
            "secondary_banners": secondary_banners,
            "categories": categories,
            "top_products": top_products,
            "new_arrivals": new_arrivals,
            "cart_variant_ids": uw["cart_variant_ids"],
            "wishlist_product_ids": uw["wishlist_product_ids"],
            "cart_item_count": uw["cart_item_count"],
        },
    )


@user_login_required
def home(request):
    # Same logic as anonymous_home (we use the same template)
    live_banners = Banner.objects.filter(is_active=True).order_by(
        "display_order", "-created_at"
    )

    hero_banners = [b for b in live_banners if b.slot == "HERO" and b.is_live()]
    secondary_banners = [
        b for b in live_banners if b.slot == "SECONDARY" and b.is_live()
    ][:6]

    categories = Category.objects.filter(is_active=True).order_by("category_name")

    top_products = list(
        _active_products()
        .annotate(
            total_sold=Coalesce(Sum("variants__inventory__quantity_sold"), Value(0))
        )
        .order_by("-total_sold")[:6]
    )
    _attach_reviews(top_products)

    new_arrivals = list(_active_products().order_by("-id")[:6])
    _attach_reviews(new_arrivals)

    uw = _cart_wishlist_ctx(request.user)

    return render(
        request,
        "store/all_home.html",
        {
            "hero_banners": hero_banners,
            "secondary_banners": secondary_banners,
            "categories": categories,
            "top_products": top_products,
            "new_arrivals": new_arrivals,
            "cart_variant_ids": uw["cart_variant_ids"],
            "wishlist_product_ids": uw["wishlist_product_ids"],
            "cart_item_count": uw["cart_item_count"],
        },
    )


# ────────────────────────────────────────────────── ADMIN — BANNER LIST ─────────────────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_banner_list(request):
    search = request.GET.get("search", "").strip()
    slot_f = request.GET.get("slot", "")
    banners = Banner.objects.all()
    if search:
        banners = banners.filter(title__icontains=search)
    if slot_f:
        banners = banners.filter(slot=slot_f)
    return render(
        request,
        "banner/admin_banner_list.html",
        {
            "banners": banners,
            "search": search,
            "slot_f": slot_f,
            "slot_choices": Banner.SLOT_CHOICES,
        },
    )


# ────────────────────────────────────────────────── ADMIN — ADD BANNER ─────────────────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_add_banner(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        subtitle = request.POST.get("subtitle", "").strip()
        cta_text = request.POST.get("cta_text", "Shop Now").strip()
        cta_url = request.POST.get("cta_url", "/products/user/products/").strip()
        badge_text = request.POST.get("badge_text", "").strip()
        slot = request.POST.get("slot", "HERO")
        display_order = request.POST.get("display_order", 0)
        start_date = request.POST.get("start_date") or None
        end_date = request.POST.get("end_date") or None
        image = request.FILES.get("image")
        if not title:
            messages.error(request, "Title is required.")
            return render(
                request,
                "banner/admin_banner_form.html",
                {
                    "slot_choices": Banner.SLOT_CHOICES,
                    "banner": None,
                    "form_data": request.POST,
                },
            )
        if not image:
            messages.error(request, "Banner image is required.")
            return render(
                request,
                "banner/admin_banner_form.html",
                {
                    "slot_choices": Banner.SLOT_CHOICES,
                    "banner": None,
                    "form_data": request.POST,
                },
            )
        Banner.objects.create(
            title=title,
            subtitle=subtitle,
            image=image,
            cta_text=cta_text,
            cta_url=cta_url,
            badge_text=badge_text,
            slot=slot,
            display_order=int(display_order),
            start_date=start_date,
            end_date=end_date,
            is_active=True,
        )
        messages.success(request, f'Banner "{title}" created.')
        return redirect("shopcore:admin_banner_list")
    return render(
        request,
        "banner/admin_banner_form.html",
        {
            "slot_choices": Banner.SLOT_CHOICES,
            "banner": None,
            "form_data": SimpleNamespace(
                title="",
                subtitle="",
                cta_text="Shop Now",
                cta_url="/products/user/products/",
                badge_text="",
                slot="HERO",
                display_order=0,
                start_date="",
                end_date="",
            ),
        },
    )


# ────────────────────────────────────────────────── ADMIN — EDIT BANNER ─────────────────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_edit_banner(request, banner_id):
    banner = get_object_or_404(Banner, id=banner_id)
    if request.method == "POST":
        banner.title = request.POST.get("title", banner.title).strip()
        banner.subtitle = request.POST.get("subtitle", "").strip()
        banner.cta_text = request.POST.get("cta_text", "Shop Now").strip()
        banner.cta_url = request.POST.get("cta_url", "/products/user/products/").strip()
        banner.badge_text = request.POST.get("badge_text", "").strip()
        banner.slot = request.POST.get("slot", banner.slot)
        banner.display_order = int(
            request.POST.get("display_order", banner.display_order)
        )
        banner.start_date = request.POST.get("start_date") or None
        banner.end_date = request.POST.get("end_date") or None
        new_image = request.FILES.get("image")
        if new_image:
            if banner.image:
                try:
                    import os

                    if os.path.isfile(banner.image.path):
                        os.remove(banner.image.path)
                except Exception:
                    pass
            banner.image = new_image
        if not banner.title:
            messages.error(request, "Title is required.")
            return render(
                request,
                "banner/admin_banner_form.html",
                {
                    "banner": banner,
                    "slot_choices": Banner.SLOT_CHOICES,
                    "form_data": request.POST,
                },
            )
        banner.save()
        messages.success(request, f'Banner "{banner.title}" updated.')
        return redirect("shopcore:admin_banner_list")
    return render(
        request,
        "banner/admin_banner_form.html",
        {
            "banner": banner,
            "slot_choices": Banner.SLOT_CHOICES,
            "form_data": SimpleNamespace(
                title="",
                subtitle="",
                cta_text="Shop Now",
                cta_url="/products/user/products/",
                badge_text="",
                slot="HERO",
                display_order=0,
                start_date="",
                end_date="",
            ),
        },
    )


# ────────────────────────────────────────────────── ADMIN — BLOCK BANNER ─────────────────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_block_banner(request, banner_id):
    banner = get_object_or_404(Banner, id=banner_id)

    if request.method == "POST":
        banner.is_active = False
        banner.save()
        messages.success(request, f'Banner "{banner.title}" blocked.')
        return redirect("shopcore:admin_banner_list")

    return render(request, "admin_confirm_block.html", {"banner": banner})


@never_cache
@admin_login_required
def admin_unblock_banner(request, banner_id):
    banner = get_object_or_404(Banner, id=banner_id)

    if request.method == "POST":
        banner.is_active = True
        banner.save()
        messages.success(request, f'Banner "{banner.title}" unblocked.')
        return redirect("shopcore:admin_banner_list")

    return render(request, "admin_confirm_unblock.html", {"banner": banner})


@never_cache
@admin_login_required
def admin_delete_banner(request, banner_id):
    banner = get_object_or_404(Banner, id=banner_id)
    if request.method == "POST":
        title = banner.title
        if banner.image:
            try:
                import os

                if os.path.isfile(banner.image.path):
                    os.remove(banner.image.path)
            except Exception:
                pass
        banner.delete()
        messages.success(request, f'Banner "{title}" deleted.')
        return redirect("shopcore:admin_banner_list")
    return render(
        request,
        "banner/admin_banner_list.html",
        {
            "banners": Banner.objects.all(),
            "slot_choices": Banner.SLOT_CHOICES,
            "delete_target": banner,
        },
    )


def size_chart(request):
    return render(request, "products/catalog/kids_size_chart.html")


def aboutus_view(request):
    return render(request, "store/about_us.html")


def contactus_view(request):
    return render(request, "store/contact_us.html")


def privacy_policy_view(request):
    return render(request, "store/privacy_policy.html")


def terms_conditions_view(request):
    return render(request, "store/terms_conditions.html")


def return_policy_view(request):
    return render(request, "store/return_policy.html")


def cookie_policy_view(request):
    return render(request, "store/cookie_policy.html")


def blog_view(request):
    return render(request, "store/blog.html")
