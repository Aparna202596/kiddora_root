# views/product_views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from products.models import Category, SubCategory, Product, ProductVariant, Inventory
from django.db.models import Q, Min, Max, F

# ------------------------------
# Product List View with Filters
# ------------------------------
def product_list_view(request, subcategory_id=None):
    products = Product.objects.filter(is_active=True)
    subcategory = None

    # Filter by subcategory if provided
    if subcategory_id:
        subcategory = get_object_or_404(SubCategory, id=subcategory_id)
        products = products.filter(subcategory=subcategory)

    # Extract filter values from GET params
    selected_colors = request.GET.getlist("color")
    selected_sizes = request.GET.getlist("size")
    selected_age_groups = request.GET.getlist("age_group")
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    sort_by = request.GET.get("sort_by")  # e.g., popularity, price_asc, price_desc

    # Filter by variant attributes
    if selected_colors:
        products = products.filter(variants__color__in=selected_colors).distinct()
    if selected_sizes:
        products = products.filter(variants__size__in=selected_sizes).distinct()
    if selected_age_groups:
        products = products.filter(subcategory__subcategory_name__in=selected_age_groups).distinct()  # assuming age_group stored in subcategory
    if min_price and max_price:
        products = products.filter(final_price__gte=min_price, final_price__lte=max_price)

    # Sort
    if sort_by == "price_asc":
        products = products.order_by("final_price")
    elif sort_by == "price_desc":
        products = products.order_by("-final_price")
    elif sort_by == "popularity":
        products = products.order_by("-variants__inventory__quantity_reserved")  # simple popularity logic
    else:
        products = products.order_by("-id")  # latest products first

    # Fetch unique filter options for frontend
    all_colors = ProductVariant.objects.filter(product__in=products).values_list("color", flat=True).distinct()
    all_sizes = ProductVariant.objects.filter(product__in=products).values_list("size", flat=True).distinct()
    all_age_groups = SubCategory.objects.filter(products__in=products).values_list("subcategory_name", flat=True).distinct()
    price_range = products.aggregate(min_price=Min("final_price"), max_price=Max("final_price"))

    context = {
        "products": products,
        "subcategory": subcategory,
        "filters": {
            "colors": all_colors,
            "sizes": all_sizes,
            "age_groups": all_age_groups,
            "price_range": price_range,
            "selected_colors": selected_colors,
            "selected_sizes": selected_sizes,
            "selected_age_groups": selected_age_groups,
            "min_price": min_price,
            "max_price": max_price,
            "sort_by": sort_by,
        },
    }
    return render(request, "products/catalog/product_list.html", context)


# ------------------------------
# Product Detail View
# ------------------------------
def product_detail_view(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    variants = product.variants.filter(is_active=True).select_related("inventory")

    context = {
        "product": product,
        "variants": variants,
    }
    return render(request, "products/products/product_detail.html", context)


# ------------------------------
# AJAX Endpoint: Variant Info
# ------------------------------
def ajax_variant_info(request):
    variant_id = request.GET.get("variant_id")
    try:
        variant = ProductVariant.objects.get(id=variant_id, is_active=True)
        inventory = getattr(variant, "inventory", None)
        quantity_available = inventory.quantity_available if inventory else 0
        data = {
            "price": str(variant.product.final_price),
            "color": variant.color,
            "size": variant.size,
            "quantity_available": quantity_available,
        }
    except ProductVariant.DoesNotExist:
        data = {"error": "Variant not found"}

    return JsonResponse(data)
