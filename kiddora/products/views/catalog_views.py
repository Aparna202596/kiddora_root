from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from products.models import (
    Category, SubCategory, Product,
    ProductVariant, ProductImage, Inventory, Color, AgeGroup
)
from django.db.models import Q, Min, Max, Count, Sum, Prefetch
from django.core.paginator import Paginator


def category_list_view(request):
    categories = Category.objects.filter(is_active=True)
    return render(request, 'products/catalog/category_list.html', {
        'categories': categories,
    })


def subcategory_list_view(request, category_id):
    category = get_object_or_404(Category, id=category_id, is_active=True)
    subcategories = category.subcategories.filter(
        products__is_active=True
    ).distinct()
    return render(request, "products/catalog/subcategory_list.html", {
        "category": category,
        "subcategories": subcategories,
    })


def get_filter_options(products_qs):
    """
    Build sidebar filter options strictly from products in the current queryset.
    All values come from actual DB records — nothing hardcoded.
    """

    # Colors: from variants of matching products
    colors = (
        Color.objects
        .filter(variants__product__in=products_qs, variants__is_active=True)
        .distinct()
        .order_by("color")
    )

    # Age groups: from variants of matching products
    age_groups = (
        AgeGroup.objects
        .filter(variants__product__in=products_qs, variants__is_active=True)
        .distinct()
        .order_by("age")
    )

    # Genders: only genders actually used by products in this queryset
    gender_codes = (
        products_qs
        .values_list("gender", flat=True)
        .distinct()
        .order_by("gender")
    )
    gender_map = dict(Product.GENDER_CHOICES)
    genders = [
        {"code": code, "label": gender_map.get(code, code)}
        for code in gender_codes
        if code
    ]

    # Fabrics: only fabrics actually used by products in this queryset
    fabric_values = (
        products_qs
        .values_list("fabric", flat=True)
        .distinct()
        .order_by("fabric")
    )
    fabric_map = dict(Product.FABRIC_CHOICES)
    fabric_types = [
        {"code": f, "label": fabric_map.get(f, f)}
        for f in fabric_values
        if f
    ]

    # Price range
    price_range = products_qs.aggregate(
        min_price=Min("final_price"),
        max_price=Max("final_price"),
    )

    return {
        "colors": colors,
        "age_groups": age_groups,
        "genders": genders,
        "fabric_types": fabric_types,          # key matches template
        "min_price": price_range["min_price"] or 0,
        "max_price": price_range["max_price"] or 0,
    }


def build_category_tree(products_qs):
    """
    Return only categories and subcategories that have
    at least one active product in the current queryset.
    """
    # subcategory ids that have products in this queryset
    active_sub_ids = products_qs.values_list(
        "subcategory_id", flat=True
    ).distinct()

    # prefetch only subcategories with active products
    active_subs = SubCategory.objects.filter(
        id__in=active_sub_ids
    )

    categories = (
        Category.objects
        .filter(
            is_active=True,
            subcategories__id__in=active_sub_ids,
        )
        .prefetch_related(
            Prefetch(
                "subcategories",
                queryset=active_subs,
                to_attr="active_subcategories",   # custom attr, not .all()
            )
        )
        .distinct()
        .order_by("category_name")
    )
    return categories


SORT_OPTIONS = [
    {"key": "newest",           "label": "Newest First"},
    {"key": "oldest",           "label": "Oldest First"},
    {"key": "price_low",        "label": "Price: Low to High"},
    {"key": "price_high",       "label": "Price: High to Low"},
    {"key": "az",               "label": "Name: A → Z"},
    {"key": "za",               "label": "Name: Z → A"},
    {"key": "popularity",       "label": "Most Popular"},
    {"key": "highest_discount", "label": "Highest Discount"},
    {"key": "lowest_discount",  "label": "Lowest Discount"},
]


def product_list(request, category_id=None, subcategory_id=None):

    products = Product.objects.filter(
        is_active=True,
        subcategory__category__is_active=True,
    ).select_related("subcategory", "subcategory__category")

    if category_id:
        products = products.filter(subcategory__category_id=category_id)
    if subcategory_id:
        products = products.filter(subcategory_id=subcategory_id)

    # ── GET params ──
    query               = request.GET.get("q", "")
    selected_categories = request.GET.getlist("category")
    selected_subs       = request.GET.getlist("subcategory")
    selected_colors     = request.GET.getlist("color")
    selected_ages       = request.GET.getlist("age")
    selected_genders    = request.GET.getlist("gender")
    selected_fabrics    = request.GET.getlist("fabric")
    min_price           = request.GET.get("min_price")
    max_price           = request.GET.get("max_price")
    sort_by_list        = request.GET.getlist("sort_by")
    sort_by             = sort_by_list[0] if sort_by_list else None

    # ── Filters ──
    if query:
        products = products.filter(
            Q(product_name__icontains=query) |
            Q(brand__icontains=query) |
            Q(about_product__icontains=query)
        )
    if selected_categories:
        products = products.filter(
            subcategory__category_id__in=selected_categories
        )
    if selected_subs:
        products = products.filter(subcategory_id__in=selected_subs)
    if selected_colors:
        # color filter: match by Color object id
        products = products.filter(
            variants__color_id__in=selected_colors,
            variants__is_active=True,
        )
    if selected_ages:
        products = products.filter(
            variants__age_group_id__in=selected_ages,
            variants__is_active=True,
        )
    if selected_genders:
        products = products.filter(gender__in=selected_genders)
    if selected_fabrics:
        products = products.filter(fabric__in=selected_fabrics)
    if min_price:
        products = products.filter(final_price__gte=min_price)
    if max_price:
        products = products.filter(final_price__lte=max_price)

    products = products.distinct()

    # ── Sorting ──
    sort_map = {
        "price_low":        "final_price",
        "price_high":       "-final_price",
        "az":               "product_name",
        "za":               "-product_name",
        "highest_discount": "-discount_percent",
        "lowest_discount":  "discount_percent",
        "newest":           "-id",
        "oldest":           "id",
    }
    if sort_by == "popularity":
        products = products.annotate(
            popularity=Sum("variants__inventory__quantity_sold")
        ).order_by("-popularity")
    else:
        products = products.order_by(sort_map.get(sort_by, "-id"))

    # ── Pagination ──
    paginator  = Paginator(products, 15)
    page_obj   = paginator.get_page(request.GET.get("page"))

    # ── Sidebar filter options (based on filtered queryset) ──
    filter_options = get_filter_options(products)
    categories     = build_category_tree(products)

    context = {
        "products":             page_obj.object_list,
        "page_obj":             page_obj,
        "categories":           categories,
        "colors":               filter_options["colors"],
        "age_groups":           filter_options["age_groups"],
        "genders":              filter_options["genders"],
        "fabric_types":         filter_options["fabric_types"],  # matches template
        "min_price":            filter_options["min_price"],
        "max_price":            filter_options["max_price"],
        "sort_options":         SORT_OPTIONS,                    # was missing
        "selected_categories":  selected_categories,
        "selected_subcategories": selected_subs,
        "selected_colors":      selected_colors,
        "selected_age_groups":  selected_ages,
        "selected_genders":     selected_genders,
        "selected_fabrics":     selected_fabrics,
        "sort_by":              sort_by,
        "query":                query,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(
            request, "products/catalog/ajax_product_list.html", context
        )
    return render(request, "products/catalog/product_list.html", context)


def product_detail_view(request, product_id):
    product = get_object_or_404(
        Product, id=product_id, is_active=True,
        subcategory__category__is_active=True,
    )
    variants = ProductVariant.objects.filter(
        product=product, is_active=True
    ).select_related("color", "age_group", "inventory")
    related_products = Product.objects.filter(
        subcategory=product.subcategory, is_active=True
    ).exclude(id=product.id)[:4]
    return render(request, "products/catalog/product_detail.html", {
        "product":          product,
        "variants":         variants,
        "related_products": related_products,
    })


def ajax_variant_info(request):
    variant_id = request.GET.get("variant_id")
    try:
        variant  = ProductVariant.objects.select_related(
            "inventory", "product", "color", "age_group"
        ).get(id=variant_id, is_active=True)
        inventory = getattr(variant, "inventory", None)
        data = {
            "price":              str(variant.product.final_price),
            "color":              str(variant.color),
            "age_group":          str(variant.age_group),
            "quantity_available": inventory.quantity_available if inventory else 0,
        }
    except ProductVariant.DoesNotExist:
        data = {"error": "Variant not found"}
    return JsonResponse(data)