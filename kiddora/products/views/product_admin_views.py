from django.views.decorators.cache import never_cache
from products.utils.queryset_utils import apply_product_filters, apply_sorting
from products.utils.search_utils import apply_search
from products.utils.pagination import paginate_queryset
from django.db.models.functions import Coalesce
from utils.image_utils import process_image
from accounts.decorators import admin_login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Avg, Count, Sum, F, Value
from shopcore.models import *
from products.models import *
from django.contrib import messages
from django.db import transaction
from decimal import Decimal

def calculate_final_price(base_price, discount_percent):
    try:
        base = Decimal(base_price or 0)
        discount = Decimal(discount_percent or 0)
        return base - (base * discount / 100)
    except Exception:
        return 0
# -----------------------------
# PRODUCT DETAILS
# -----------------------------
@never_cache
@admin_login_required
def admin_product_details(request, product_id):

    product = get_object_or_404(
        Product.objects.select_related("subcategory","subcategory__category"),
        id=product_id
    )

    images = ProductImage.objects.filter(product=product)

    variants = (
        ProductVariant.objects
        .filter(product=product)
        .select_related("color", "age_group")
        .annotate(
            stock=Coalesce(F("inventory__quantity_available"), Value(0)),
            sold=Coalesce(F("inventory__quantity_sold"), Value(0)),
            reserved=Coalesce(F("inventory__quantity_reserved"), Value(0)),
        )
    )
    stock_summary = variants.aggregate(
        total_stock=Coalesce(Sum("stock"), Value(0)),
        total_sold=Coalesce(Sum("sold"), Value(0)),
        total_reserved=Coalesce(Sum("reserved"), Value(0)),
    )
    # coupons = Coupon.objects.filter(is_active=True,products=product)

    final_price = product.base_price - (product.base_price * product.discount_percent / 100)

    context = {
        "product": product,
        "category": product.subcategory.category,
        "subcategory": product.subcategory,
        "images": images,
        "variants": variants,
        "stock_summary": stock_summary,
        # "coupons": coupons,
        "final_price": final_price,
        "last_updated": product.updated_at if hasattr(product, "updated_at") else product.id,
    }
    return render(request, "products/admin/admin_product_details.html",context  )

@never_cache
@admin_login_required
def admin_product_list(request):

    search = request.GET.get("search", "")
    sort = request.GET.get("sort", "new")
    category_id = request.GET.get("category")
    subcategory_id = request.GET.get("subcategory")
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    brand = request.GET.get("brand")

    queryset = Product.objects.select_related(
        "subcategory", "subcategory__category"
    ).filter(subcategory__category__is_active=True)
    queryset = queryset.filter(is_active=True)
# SEARCH
    queryset = apply_search(queryset, search, ["product_name", "brand"])

    # POPULARITY (BASED ON SOLD QTY)
    queryset = queryset.annotate(
        popularity_score=Coalesce(
            Sum("variants__inventory__quantity_sold"), Value(0)
        )
    )
    # FILTERS
    queryset = apply_product_filters(queryset, category_id, subcategory_id)

    if brand:
        queryset = queryset.filter(brand__iexact=brand)

    if min_price:
        queryset = queryset.filter(final_price__gte=Decimal(min_price))

    if max_price:
        queryset = queryset.filter(final_price__lte=Decimal(max_price))

    # SORTING
    sort_map = {
        "price_low": "final_price",
        "price_high": "-final_price",
        "az": "product_name",
        "za": "-product_name",
        "new": "-id",
        "popular": "-popularity_score",
    }

    queryset = apply_sorting(queryset, sort, sort_map, "-id")

    page_obj = paginate_queryset(request, queryset, 15)

    context = {
        "page_obj": page_obj,
        "search": search,
        "sort": sort,
        "categories": Category.objects.filter(is_active=True),
        "subcategories": SubCategory.objects.filter(category__is_active=True),
    }

    return render(request, "products/admin/admin_product_list.html", context)

# ADD PRODUCT

@never_cache
@admin_login_required
def admin_add_product(request):

    preview_final_price = None
    
    if request.method == "POST":
        base_price = request.POST.get("base_price")
        discount_percent = request.POST.get("discount_percent")
        preview_final_price = calculate_final_price(base_price, discount_percent)

        # Collect images by individual field names matching the HTML
        image1 = request.FILES.get("productImage1")
        image2 = request.FILES.get("productImage2")
        image3 = request.FILES.get("productImage3")
        image4 = request.FILES.get("productImage4")
        image5 = request.FILES.get("productImage5")
        # Validate minimum 3 images BEFORE touching the database
        if not (image1 and image2 and image3):
            messages.error(request, "Minimum 3 images required")
            return render(
                request,
                "products/admin/admin_product_form.html",
                {
                    "subcategories": SubCategory.objects.filter(category__is_active=True),
                    "preview_final_price": preview_final_price,
                    "fabric_choices": Product.FABRIC_CHOICES,
                    "gender_choices": Product.GENDER_CHOICES,
                },
            )
        print("Images received:",image1, image2, image3)
        print("Base Price:", base_price, "Discount Percent:", discount_percent, "Calculated Final Price:", preview_final_price)
        
        name = request.POST.get("product_name").strip()
        subcategory = get_object_or_404(
            SubCategory, id=request.POST.get("subcategory")
        )
        print("Creating product with name:", name, "and subcategory:", subcategory)

        # Process images before DB writes — fail fast if process_image errors
        processed1 = process_image(image1)
        processed2 = process_image(image2)
        processed3 = process_image(image3)
        processed4 = process_image(image4) if image4 else None
        processed5 = process_image(image5) if image5 else None

        # Now write to DB inside a single clean transaction
        with transaction.atomic():
            product = Product.objects.create(
                product_name=name,
                brand=request.POST.get("brand"),
                gender=request.POST.get("gender"),
                fabric=request.POST.get("fabric"),
                base_price=base_price,
                discount_percent=discount_percent or 0,
                about_product=request.POST.get("about_product"),
                subcategory=subcategory,
                is_active=True,
            )
            img_instance = ProductImage(
                product=product,
                image1=processed1,
                image2=processed2,
                image3=processed3,
                image4=processed4,
                image5=processed5,
                is_default=True,
            )
        
            ProductImage.objects.filter(
                product=product, is_default=True
            ).update(is_default=False)
            
            super(ProductImage, img_instance).save(force_insert=True)

        print("Product images saved for product ID:", product.id)
        print("image1",image1)
        print("image2",image2)
        print("image3",image3)
        print("image4",image4)
        print("image5",image5)
        
        messages.success(request, "Product added successfully")
        return redirect("products:admin_product_list")
    
    return render(
        request,
        "products/admin/admin_product_form.html",
        {
            "subcategories": SubCategory.objects.filter(category__is_active=True),
            "preview_final_price": preview_final_price,
            "fabric_choices": Product.FABRIC_CHOICES,
            "gender_choices": Product.GENDER_CHOICES,
        },
    )


# -----------------------------
# EDIT PRODUCT
# -----------------------------
@never_cache
@admin_login_required
def admin_edit_product(request, product_id):

    product = get_object_or_404(Product, id=product_id)
    preview_final_price = product.final_price

    if request.method == "POST":
        base_price = request.POST.get("base_price")
        discount_percent = request.POST.get("discount_percent")
        preview_final_price = calculate_final_price(base_price, discount_percent)

        product.product_name = request.POST.get("product_name")
        product.brand = request.POST.get("brand")
        product.gender = request.POST.get("gender")
        product.fabric = request.POST.get("fabric")
        product.base_price = base_price
        product.discount_percent = discount_percent
        product.about_product = request.POST.get("about_product")
        product.subcategory_id = request.POST.get("subcategory")
        product.is_active = bool(request.POST.get("is_active"))
        product.save()

        messages.success(request, "Product updated")
        return redirect("products:admin_product_list")

    return render(
        request,"products/admin/admin_product_form.html",
        {
            "product": product, 
            "subcategories": SubCategory.objects.all(),
            "preview_final_price": preview_final_price,
            "fabric_choices": Product.FABRIC_CHOICES,
            "gender_choices": Product.GENDER_CHOICES,
        },
    )

# SOFT DELETE PRODUCT

@never_cache
@admin_login_required
def admin_delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.is_active = False
    product.save()
    messages.success(request, "Product deleted safely")
    return redirect("products:admin_product_list")

# VARIANT MANAGEMENT

@never_cache
@admin_login_required
def admin_add_variant(request, product_id):

    product = get_object_or_404(Product, id=product_id)

    if request.method == "POST":

        variant = ProductVariant.objects.create(
            product=product,
            color_id=request.POST.get("color"),
            age_group_id=request.POST.get("age_group"),
        )

        Inventory.objects.create(
            variant=variant,
            quantity_available=request.POST.get("stock"),
        )

        messages.success(request, "Variant added")
        return redirect("products:admin_product_details", product_id=product.id)

    return render(
        request,
        "products/admin/admin_variant_form.html",
        {
            "product": product,
            "colors": Color.objects.all(),
            "ages": AgeGroup.objects.all(),
        },
    )

@admin_login_required
@never_cache
def admin_edit_variant(request, variant_id, product_id):

    variant = get_object_or_404(ProductVariant, id=variant_id,product_id=product_id)

    if request.method == "POST":
        variant.color_id = request.POST.get("color")
        variant.age_group_id = request.POST.get("age_group")
        variant.is_active = bool(request.POST.get("is_active"))
        variant.save()

        messages.success(request, "Variant updated")
        return redirect(
            "products:admin_product_details", product_id=product_id)

    return render(
        request,
        "products/admin/admin_variant_form.html",
        {
            "variant": variant,
            "colors": Color.objects.all(),
            "ages": AgeGroup.objects.all(),
        },
    )


@admin_login_required
@never_cache
def admin_delete_variant(request, product_id, variant_id):
    variant = get_object_or_404(ProductVariant, id=variant_id, product_id=product_id)
    variant.delete()
    messages.success(request, "Variant removed")
    return redirect(
        "products:admin_product_details", product_id=product_id
    )