from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from products.models import Category, SubCategory, Product, ProductVariant
from django.db.models import Q, Min, Max, Count, Sum
from django.core.paginator import Paginator

# Category listing page
def category_list_view(request):
    categories = Category.objects.all()
    min_price = request.GET.get('min_price', 0)  
    max_price = request.GET.get('max_price', 10000)
    context = {
        'categories': categories,
        'min_price': min_price,
        'max_price': max_price,
    }
    return render(request, 'products/catalog/category_list.html', context)

# SubCategory listing page
def subcategory_list_view(request, category_id):
    category = get_object_or_404(Category, id=category_id, is_active=True)
    subcategories = category.subcategories.all() 
    return render(request,
        "products/catalog/subcategory_list.html",
        {"category": category, "subcategories": subcategories})

def get_filter_options(products_queryset):
    """Fetch dynamic filter options for sidebar with faceted counts."""
    colors = ProductVariant.objects.filter(product__in=products_queryset)\
        .values('color')\
        .annotate(count=Count('id'))\
        .order_by('color')

    sizes = ProductVariant.objects.filter(product__in=products_queryset)\
        .values('size')\
        .annotate(count=Count('id'))\
        .order_by('size')
    
    age_groups = Product.objects.filter(id__in=products_queryset)\
        .values('age_group')\
        .annotate(count=Count('id'))\
        .order_by('age_group')
    
    genders = Product.objects.filter(id__in=products_queryset)\
        .values('gender')\
        .annotate(count=Count('id'))\
        .order_by('gender')
    
    fabrics = Product.objects.filter(id__in=products_queryset)\
        .values('fabric')\
        .annotate(count=Count('id'))\
        .order_by('fabric')
    # Price range
    price_range = products_queryset.aggregate(min_price=Min('final_price'),
                                                max_price=Max('final_price'))
    
    return {
        "colors": colors,
        "sizes": sizes,
        "age_groups": age_groups,
        "genders": genders,
        "fabrics": fabrics,  
        "min_price": price_range["min_price"] or 0,
        "max_price": price_range["max_price"] or 0
    }

# ---------------------------
# Product List View with Filters & Facets
# ---------------------------
def product_list(request, category_id=None, subcategory_id=None):
    """Filtered product listing with AJAX support and faceted counts."""
    
    products = Product.objects.filter(is_active=True, subcategory__category__is_active=True)
    
    # Optional category/subcategory filters
    if category_id:
        products = products.filter(subcategory__category_id=category_id)
    if subcategory_id:
        products = products.filter(subcategory_id=subcategory_id)
    
    # GET filter parameters
    query = request.GET.get("q", "")
    selected_categories = request.GET.getlist("category")
    selected_subcategories = request.GET.getlist("subcategory")
    selected_products = request.GET.getlist("product")
    selected_variants = request.GET.getlist("variant")
    selected_colors = request.GET.getlist("color")
    selected_sizes = request.GET.getlist("size")
    selected_age_groups = request.GET.getlist("age")
    selected_genders = request.GET.getlist("gender")
    selected_fabrics = request.GET.getlist("fabric")
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    sort_by_list = request.GET.getlist("sort_by")
    sort_by = sort_by_list[0] if sort_by_list else None
    
    # ---------------------------
    # Filtering logic
    # ---------------------------
    if query:
        products = products.filter(Q(product_name__icontains=query) | 
                                    Q(brand__icontains=query) |
                                    Q(about_product__icontains=query))
    
    if selected_categories:
        products = products.filter(subcategory__category_id__in=selected_categories)
    if selected_subcategories:
        products = products.filter(subcategory_id__in=selected_subcategories)
    if selected_products:
        products = products.filter(id__in=selected_products)
    if selected_variants:
        products = products.filter(variants__id__in=selected_variants)
    if selected_colors:
        products = products.filter(variants__color__in=selected_colors)
    if selected_sizes:
        products = products.filter(variants__size__in=selected_sizes)
    if selected_age_groups:
        products = products.filter(age_group__in=selected_age_groups)
    if selected_genders:
        products = products.filter(gender__in=selected_genders)
    if selected_fabrics:                
        products = products.filter(fabric__in=selected_fabrics)
    if min_price and max_price:
        products = products.filter(final_price__gte=min_price, final_price__lte=max_price)
    
    # ---------------------------
    # Sorting
    # ---------------------------
    products=products.distinct()

    if sort_by == "price_low":
        products = products.order_by("final_price")
    elif sort_by == "price_high":
        products = products.order_by("-final_price")
    elif sort_by == "az":
        products = products.order_by("product_name")
    elif sort_by == "za":
        products = products.order_by("-product_name")
    elif sort_by == "popularity":
        products = products.annotate(popularity=Sum("variants__inventory__quantity_sold")).order_by("-popularity")
    elif sort_by == "higest_discount":
        products = products.order_by("-discount_percent")
    elif sort_by == "lowest_discount":
        products = products.order_by("discount_percent")
    elif sort_by == "newest":
        products = products.order_by("-created_at")
    elif sort_by == "oldest":
        products = products.order_by("created_at")
    else:
        products = products.order_by("-id")
    
    # ---------------------------
    # Pagination
    # ---------------------------
    paginator = Paginator(products.distinct(), 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    # ---------------------------
    # Sidebar dynamic options (faceted counts)
    # ---------------------------
    filter_options = get_filter_options(products)
    
    # Prefetch categories/subcategories/products/variants for sidebar hierarchy
    categories = Category.objects.filter(is_active=True)\
        .prefetch_related("subcategories__products__variants")
    
    context = {
        "products": page_obj.object_list,
        "page_obj": page_obj,
        "categories": categories,
        "colors": filter_options["colors"],
        "sizes": filter_options["sizes"],
        "age_groups": filter_options["age_groups"],
        "genders": [
            {"code": k, "label": v} for k, v in Product.GENDER_CHOICES],
        "fabrics": filter_options["fabrics"],  
        "min_price": filter_options["min_price"],
        "max_price": filter_options["max_price"],

        "selected_categories": selected_categories,
        "selected_subcategories": selected_subcategories,
        "selected_products": selected_products,
        "selected_variants": selected_variants,
        "selected_colors": selected_colors,
        "selected_sizes": selected_sizes,
        "selected_age_groups": selected_age_groups,
        "selected_genders": selected_genders,
        "selected_fabrics": selected_fabrics, 
        "sort_by": sort_by,
    }
    
    # ---------------------------
    # AJAX Filtering
    # ---------------------------
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "products/catalog/ajax_product_list.html", context)
    
    return render(request, "products/catalog/product_list.html", context)

# ---------------------------
# Product Detail View
# ---------------------------
def product_detail_view(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True, subcategory__category__is_active=True)
    variants = ProductVariant.objects.filter(product=product, is_active=True).select_related("inventory")
    related_products = Product.objects.filter(subcategory=product.subcategory, is_active=True).exclude(id=product.id)[:4]
    return render(request, "products/catalog/product_detail.html", {
        "product": product,
        "variants": variants,
        "related_products": related_products,
        "fabric": product.fabric,     
        "about_product": product.about_product,
    })

# ---------------------------
# AJAX Endpoint: Variant Info
# ---------------------------
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
