from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from products.models import (Category, SubCategory, Product, ProductVariant, ProductImage, Inventory, Color, AgeGroup)
from shopcore.models import Review, Offer
from django.db.models import Q, Min, Max, Count, Sum, Prefetch, Avg
from django.core.paginator import Paginator
from django.db.models.functions import Coalesce
from django.db.models import Value
from shopcore.models import *

#  Build sidebar filter options from a filtered QS
def get_filter_options(products_qs):
    colors = (Color.objects.filter(variants__product__in=products_qs, variants__is_active=True).distinct().order_by("color"))
    age_groups = (AgeGroup.objects.filter(variants__product__in=products_qs, variants__is_active=True).distinct().order_by("age"))
    gender_codes = (products_qs.values_list("gender", flat=True).distinct().order_by("gender"))
    gender_map = dict(Product.GENDER_CHOICES)
    genders = [
        {"code": code, "label": gender_map.get(code, code)}
        for code in gender_codes if code]
    fabric_values = (products_qs.values_list("fabric", flat=True).distinct().order_by("fabric"))
    fabric_map = dict(Product.FABRIC_CHOICES)
    fabric_types = [
        {"code": f, "label": fabric_map.get(f, f)}
        for f in fabric_values if f]
    brands = (products_qs.values_list("brand", flat=True).distinct().order_by("brand"))
    price_range = products_qs.aggregate(min_price=Min("final_price"), max_price=Max("final_price"))

    return {
        "colors": colors,
        "age_groups": age_groups,
        "genders": genders,
        "fabric_types": fabric_types,
        "brands": list(brands),
        "min_price": price_range["min_price"] or 0,
        "max_price": price_range["max_price"] or 0,
    }

#  Build category tree from a filtered QS
def build_category_tree(products_qs):
    active_sub_ids = products_qs.values_list("subcategory_id", flat=True).distinct()
    active_subs = SubCategory.objects.filter(id__in=active_sub_ids)
    categories = (Category.objects.filter(is_active=True, subcategories__id__in=active_sub_ids)
        .prefetch_related(Prefetch("subcategories", queryset=active_subs, to_attr="active_subcategories"))
        .distinct().order_by("category_name"))
    return categories

#  SORT OPTIONS (used by product_list and search_products)
SORT_OPTIONS = [
    {"key": "newest", "label": "Newest First"},
    {"key": "oldest", "label": "Oldest First"},
    {"key": "price_low", "label": "Price: Low to High"},
    {"key": "price_high", "label": "Price: High to Low"},
    {"key": "az", "label": "Name: A → Z"},
    {"key": "za", "label": "Name: Z → A"},
    {"key": "popularity", "label": "Most Popular"},
    {"key": "highest_discount", "label": "Highest Discount"},
    {"key": "lowest_discount", "label": "Lowest Discount"},
]

SORT_MAP = {
    "price_low": "final_price",
    "price_high": "-final_price",
    "az": "product_name",
    "za": "-product_name",
    "highest_discount": "-discount_percent",
    "lowest_discount": "discount_percent",
    "newest": "-id",
    "oldest": "id",
}

def _cart_wishlist_ctx(user):
    """
    Returns cart_variant_ids (set), wishlist_product_ids (set),
    and cart_item_count (int) for authenticated users.
    Safe for anonymous users — returns empty sets and 0.
    Called by product_list and product_detail_view.
    """
    if not user.is_authenticated:
        return {
            "cart_variant_ids":     set(),
            "wishlist_product_ids": set(),
            "cart_item_count":      0,
        }
    try:
        cart_variant_ids = set(user.cart.items.values_list("variant_id", flat=True))
        cart_item_count  = user.cart.items.count()
    except Cart.DoesNotExist:
        cart_variant_ids = set()
        cart_item_count  = 0
    try:
        wishlist_product_ids = set(
            user.wishlist.items.values_list("product_id", flat=True)
        )
    except Wishlist.DoesNotExist:
        wishlist_product_ids = set()
    return {
        "cart_variant_ids":     cart_variant_ids,
        "wishlist_product_ids": wishlist_product_ids,
        "cart_item_count":      cart_item_count,
    }


def _apply_sort(products, sort_by):
    if sort_by == "popularity":
        return products.annotate(
            popularity=Sum("variants__inventory__quantity_sold")
        ).order_by("-popularity")
    return products.order_by(SORT_MAP.get(sort_by, "-id"))

#  Category list
def category_list_view(request):
    categories = Category.objects.filter(is_active=True)
    return render(request, "products/catalog/category_list.html", {"categories": categories})

#  VIEW: Subcategory list

def subcategory_list_view(request, category_id):
    category = get_object_or_404(Category, id=category_id, is_active=True)
    subcategories = category.subcategories.filter(products__is_active=True).distinct()
    return render(request, "products/catalog/subcategory_list.html", {
        "category":      category,
        "subcategories": subcategories,
    })

def product_list(request, category_id=None, subcategory_id=None):
    products = Product.objects.filter(
            is_active=True,
            is_deleted=False,
            subcategory__is_active=True,
            subcategory__is_deleted=False,
            subcategory__category__is_active=True,
            subcategory__category__is_deleted=False, 
            ).select_related("subcategory", "subcategory__category")

    if category_id:
        products = products.filter(subcategory__category_id=category_id)
    if subcategory_id:
        products = products.filter(subcategory_id=subcategory_id)

    query = request.GET.get("q", "").strip()
    selected_categories = request.GET.getlist("category")
    selected_subs = request.GET.getlist("subcategory")
    selected_colors = request.GET.getlist("color")
    selected_ages = request.GET.getlist("age")
    selected_genders = request.GET.getlist("gender")
    selected_fabrics = request.GET.getlist("fabric")
    selected_brands = request.GET.getlist("brand")   
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    sort_by = request.GET.getlist("sort_by")
    sort_by = sort_by[0] if sort_by else ""

    # Apply filters 
    if query:
        products = products.filter(
            Q(product_name__icontains=query) |
            Q(brand__icontains=query) |
            Q(about_product__icontains=query) |
            Q(subcategory__subcategory_name__icontains=query) |
            Q(subcategory__category__category_name__icontains=query)
        )
    if selected_categories:
        products = products.filter(subcategory__category_id__in=selected_categories)
    if selected_subs:
        products = products.filter(subcategory_id__in=selected_subs)
    if selected_colors:
        products = products.filter(variants__color_id__in=selected_colors, variants__is_active=True)
    if selected_ages:
        products = products.filter(variants__age_group_id__in=selected_ages, variants__is_active=True)
    if selected_genders:
        products = products.filter(gender__in=selected_genders)
    if selected_fabrics:
        products = products.filter(fabric__in=selected_fabrics)
    if selected_brands:
        products = products.filter(brand__in=selected_brands)
    if min_price:
        try:
            products = products.filter(final_price__gte=float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            products = products.filter(final_price__lte=float(max_price))
        except ValueError:
            pass

    products = products.distinct()
    products = products.annotate(
        total_stock=Coalesce(
            Sum(
                "variants__inventory__quantity_available",
                filter=Q(variants__is_active=True),
            ),
            Value(0),
        )
    )

    # Sort 
    products = _apply_sort(products, sort_by)

    # Pagination 
    paginator = Paginator(products, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Sidebar options
    filter_options = get_filter_options(products)
    categories = build_category_tree(products)

    # Resolve current category/subcategory for breadcrumb display
    current_category = None
    current_subcategory = None
    if subcategory_id:
        current_subcategory = SubCategory.objects.filter(id=subcategory_id).select_related("category").first()
        current_category = current_subcategory.category if current_subcategory else None
    elif category_id:
        current_category = Category.objects.filter(id=category_id).first()

    context = {
        "products": page_obj.object_list,
        "page_obj": page_obj,
        "categories": categories,
        "colors": filter_options["colors"],
        "age_groups": filter_options["age_groups"],
        "genders": filter_options["genders"],
        "fabric_types": filter_options["fabric_types"],
        "brands": filter_options["brands"],
        "min_price": filter_options["min_price"],
        "max_price": filter_options["max_price"],
        "sort_options": SORT_OPTIONS,
        "selected_categories": selected_categories,
        "selected_subcategories": selected_subs,
        "selected_colors": selected_colors,
        "selected_age_groups": selected_ages,
        "selected_genders": selected_genders,
        "selected_fabrics": selected_fabrics,
        "selected_brands": selected_brands,
        "sort_by": sort_by,
        "query": query,

        # breadcrumb
        "current_category": current_category,
        "current_subcategory": current_subcategory,
    }
    uw = _cart_wishlist_ctx(request.user)
    context.update({
        "cart_variant_ids": uw["cart_variant_ids"],
        "wishlist_product_ids":uw["wishlist_product_ids"],
        "cart_item_count": uw["cart_item_count"],
        "MAX_QTY": CartItem.MAX_QTY_PER_PRODUCT,
    })

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(
            request, "products/catalog/product_grid.html", context
        )
    return render(request, "products/catalog/product_list.html", context)

def search_products(request):

    query = request.GET.get("q", "").strip()
    query = query.replace("-", " ")

    if not query or len(query) < 2:
        return JsonResponse({"results": [], "query": query})

    products = (
        Product.objects
        .filter(
            is_active=True,
            is_deleted=False,
            subcategory__is_active=True,
            subcategory__is_deleted=False,
            subcategory__category__is_active=True,
            subcategory__category__is_deleted=False,
        )
        .filter(
            Q(product_name__icontains=query) |
            Q(brand__icontains=query) |
            Q(subcategory__subcategory_name__icontains=query) |
            Q(subcategory__category__category_name__icontains=query) |
            Q(about_product__icontains=query)
        )
        .select_related("subcategory", "subcategory__category")
        .prefetch_related("images")
        .distinct()
        [:8]   # Limit to top 8 results for autocomplete dropdown
    )

    results = []
    for p in products:
        img_url = None
        img_obj = p.images.filter(is_default=True).first() or p.images.first()
        if img_obj:
            for field in ("image1", "image2", "image3", "image4", "image5"):
                val = getattr(img_obj, field)
                if val:
                    img_url = val.url
                    break
        results.append({
            "id":       p.id,
            "name":     p.product_name,
            "brand":    p.brand,
            "price":    str(p.final_price),
            "base":     str(p.base_price),
            "discount": p.discount_percent,
            "img":      img_url,
            "url":      f"/products/user/products/{p.id}/",
        })

    return JsonResponse({"results": results, "query": query})

def product_detail_view(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True, is_deleted=False)
    try:
        product = Product.objects.select_related(
            "subcategory", "subcategory__category"
        ).get(id=product_id)
    except Product.DoesNotExist:
        messages.error(request, "Product not found.")
        return redirect("/products/user/products/")

    if (
        not product.is_active
        or product.is_deleted
        or not product.subcategory.is_active
        or product.subcategory.is_deleted
        or not product.subcategory.category.is_active
        or product.subcategory.category.is_deleted
    ):
        messages.warning(
            request,
            "This product is currently unavailable. Browse our other products below.",
        )
        return redirect("/products/user/products/")

    # ── Variants ─────────────────────────────────────────────
    variants_qs = (
        ProductVariant.objects.filter(product=product, is_active=True)
        .select_related("color", "age_group", "inventory")
        .order_by("color__color", "age_group__age")
    )
    variant_data     = []
    total_stock      = 0
    any_in_stock     = False
    all_out_of_stock = True

    for v in variants_qs:
        try:
            qty = v.inventory.quantity_available
        except Exception:
            qty = 0
        total_stock += qty
        if qty > 0:
            any_in_stock     = True
            all_out_of_stock = False
        variant_data.append({
            "id":           v.id,
            "color_id":     v.color.id,
            "color_name":   v.color.color,
            "age":          v.age_group.age,
            "sku":          v.sku,
            "qty":          qty,
            "is_oos":       qty == 0,
            "max_cart_qty": min(CartItem.MAX_QTY_PER_PRODUCT, qty) if qty > 0 else 0,
            "in_cart":      False,
        })

    # ── Images ───────────────────────────────────────────────
    image_urls = []
    for img_obj in product.images.all():
        for field in ("image1", "image2", "image3", "image4", "image5"):
            val = getattr(img_obj, field)
            if val:
                image_urls.append(val.url)

    # ── Related products ─────────────────────────────────────
    related_products = (
        Product.objects.filter(
            subcategory=product.subcategory,
            is_active=True,
            is_deleted=False,
            subcategory__category__is_active=True,
        )
        .exclude(id=product.id)
        .prefetch_related("images")[:6]
    )

    # ── Cart & Wishlist context ───────────────────────────────
    uw = _cart_wishlist_ctx(request.user)
    for vd in variant_data:
        vd["in_cart"] = vd["id"] in uw["cart_variant_ids"]

    # ── Reviews ──────────────────────────────────────────────
    reviews_qs = (
        Review.objects.filter(product=product, is_approved=True)
        .select_related("user")
        .order_by("-created_at")
    )
    review_list    = list(reviews_qs[:20])
    review_count   = reviews_qs.count()
    avg_data       = reviews_qs.aggregate(avg=Avg("rating"))
    average_rating = round(avg_data["avg"], 1) if avg_data["avg"] else None

    # ── Review eligibility — SINGLE source of truth ──────────
    # Do NOT duplicate this logic; compute it once here cleanly.
    user_review       = None
    user_has_reviewed = False
    user_can_review   = False

    if request.user.is_authenticated:
        # Check against ALL reviews (approved or pending) so a user who
        # submitted but is awaiting approval is not shown the button again.
        user_review = Review.objects.filter(
            user=request.user, product=product
        ).first()
        user_has_reviewed = user_review is not None

        if not user_has_reviewed:
            # Eligible only if they have a DELIVERED order containing
            # this product — any variant counts.
            user_can_review = Order.objects.filter(
                user=request.user,
                order_status="DELIVERED",
                order_items__variant__product=product,
            ).exists()

    # ── Active Offers ─────────────────────────────────────────
    from django.utils import timezone
    now = timezone.now()
    product_offers = [
        o for o in Offer.objects.filter(
            offer_type="PRODUCT",
            product=product,
            is_active=True,
            is_deleted=False,
            start_date__lte=now,
        )
        if o.is_valid()
    ]
    category_offers = [
        o for o in Offer.objects.filter(
            offer_type="CATEGORY",
            category=product.subcategory.category,
            is_active=True,
            is_deleted=False,
            start_date__lte=now,
        )
        if o.is_valid()
    ]
    all_offers = product_offers + category_offers
    best_offer = max(all_offers, key=lambda o: o.discount_percent) if all_offers else None

    context = {
        # ── product core ─────────────────────────────────────
        "product":          product,
        "variant_data":     variant_data,
        "image_urls":       image_urls,
        "total_stock":      total_stock,
        "any_in_stock":     any_in_stock,
        "all_out_of_stock": all_out_of_stock,
        "related_products": related_products,
        # ── cart / wishlist ───────────────────────────────────
        "cart_variant_ids":     uw["cart_variant_ids"],
        "wishlist_product_ids": uw["wishlist_product_ids"],
        "cart_item_count":      uw["cart_item_count"],
        "product_in_wishlist":  product.id in uw["wishlist_product_ids"],
        "MAX_QTY":              CartItem.MAX_QTY_PER_PRODUCT,
        "add_to_cart_url_base": "/shop/cart/add/",
        # ── reviews ───────────────────────────────────────────
        "reviews":           review_list,
        "review_count":      review_count,
        "average_rating":    average_rating,
        "user_review":       user_review,
        "user_has_reviewed": user_has_reviewed,  # ← single clean source
        "user_can_review":   user_can_review,    # ← single clean source
        # ── offers ────────────────────────────────────────────
        "product_offers":  product_offers,
        "category_offers": category_offers,
        "all_offers":      all_offers,
        "best_offer":      best_offer,
    }
    return render(request, "products/catalog/product_detail.html", context)
#  AJAX – Variant stock / price info

def ajax_variant_info(request):
    variant_id = request.GET.get("variant_id")
    if not variant_id:
        return JsonResponse({"error": "variant_id is required"}, status=400)

    try:
        variant = ProductVariant.objects.select_related(
            "inventory", "product", "color", "age_group"
        ).get(id=variant_id, is_active=True)
    except ProductVariant.DoesNotExist:
        return JsonResponse({"error": "Variant not found or inactive"}, status=404)

    inventory = getattr(variant, "inventory", None)
    qty       = inventory.quantity_available if inventory else 0

    if qty == 0:
        stock_status, stock_label = "out_of_stock", "Out of Stock"
    elif qty <= 5:
        stock_status, stock_label = "low_stock", f"Only {qty} left!"
    else:
        stock_status, stock_label = "in_stock", f"In Stock ({qty} available)"

    # ADD-ON: is this variant already in the user's cart?
    in_cart = False
    if request.user.is_authenticated:
        try:
            in_cart = CartItem.objects.filter(
                cart=request.user.cart, variant=variant
            ).exists()
        except Cart.DoesNotExist:
            pass

    data = {
        # ── original keys (unchanged) ─────────────────────────
        "variant_id":         variant.id,
        "sku":                variant.sku,
        "color":              str(variant.color),
        "age_group":          str(variant.age_group),
        "quantity_available": qty,
        "stock_status":       stock_status,
        "stock_label":        stock_label,
        "base_price":         str(variant.product.base_price),
        "final_price":        str(variant.product.final_price),
        "discount_percent":   variant.product.discount_percent,
        # ── ADD-ON keys ───────────────────────────────────────
        # Used by the product-detail page JS to update button state
        "in_cart":         in_cart,
        "max_cart_qty":    min(CartItem.MAX_QTY_PER_PRODUCT, qty),
        "add_to_cart_url": f"/shop/cart/add/{variant.id}/",
    }
    return JsonResponse(data)
#  VIEW: AJAX – partial product grid 

def ajax_product_grid(request, category_id=None, subcategory_id=None):
    # Re-use product_list with the AJAX header set
    request.META["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"
    return product_list(request, category_id=category_id, subcategory_id=subcategory_id)