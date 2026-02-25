from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.views.decorators.cache import never_cache
from products.models import *
from accounts.decorators import admin_login_required
from products.utils.pagination import paginate_queryset
from products.utils.queryset_utils import apply_product_filters, apply_sorting
from products.utils.search_utils import apply_search
from django.db.models import Avg, Count, Sum, F, Value
from django.db.models.functions import Coalesce
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile


# -----------------------------
# IMAGE PROCESSING
# -----------------------------
def process_image(file, size=(800, 800)):
    img = Image.open(file)
    img = img.convert("RGB")
    img.thumbnail(size)

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return ContentFile(buffer.getvalue(), name=file.name)


# -----------------------------
# PRODUCT LIST
# -----------------------------
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

    # SEARCH
    queryset = apply_search(queryset, search, ["product_name", "brand"])

    queryset = Product.objects.select_related(
        "subcategory", "subcategory__category"
    ).filter(subcategory__category__is_active=True)

    # ---- RATINGS ANNOTATION ----
    queryset = queryset.annotate(
        avg_rating=Coalesce(Avg("reviews__rating"), Value(0.0)),
        rating_count=Coalesce(Count("reviews"), Value(0)),
    )

    # ---- POPULARITY (BASED ON SOLD QTY) ----
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
        "rating": "-avg_rating",
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


# -----------------------------
# ADD PRODUCT
# -----------------------------
@admin_login_required
@transaction.atomic
def admin_add_product(request):

    if request.method == "POST":

        name = request.POST.get("product_name").strip()
        subcategory = get_object_or_404(
            SubCategory, id=request.POST.get("subcategory")
        )

        product = Product.objects.create(
            product_name=name,
            brand=request.POST.get("brand"),
            gender=request.POST.get("gender"),
            fabric=request.POST.get("fabric"),
            base_price=request.POST.get("base_price"),
            discount_percent=request.POST.get("discount_percent") or 0,
            about_product=request.POST.get("about_product"),
            subcategory=subcategory,
        )

        # IMAGE HANDLING
        images = request.FILES.getlist("images")
        if len(images) < 3:
            messages.error(request, "Minimum 3 images required")
            product.delete()
            return redirect("products:admin_add_product")

        processed = [process_image(img) for img in images[:5]]

        ProductImage.objects.create(
            product=product,
            image1=processed[0],
            image2=processed[1],
            image3=processed[2],
            image4=processed[3] if len(processed) > 3 else None,
            image5=processed[4] if len(processed) > 4 else None,
            is_default=True,
        )

        messages.success(request, "Product added successfully")
        return redirect("products:admin_product_list")

    return render(
        request,
        "products/admin/admin_product_form.html",
        {
            "subcategories": SubCategory.objects.filter(
                category__is_active=True
            )
        },
    )


# -----------------------------
# EDIT PRODUCT
# -----------------------------
@admin_login_required
def admin_edit_product(request, product_id):

    product = get_object_or_404(Product, id=product_id)

    if request.method == "POST":

        product.product_name = request.POST.get("product_name")
        product.brand = request.POST.get("brand")
        product.gender = request.POST.get("gender")
        product.fabric = request.POST.get("fabric")
        product.base_price = request.POST.get("base_price")
        product.discount_percent = request.POST.get("discount_percent")
        product.about_product = request.POST.get("about_product")
        product.subcategory_id = request.POST.get("subcategory")
        product.is_active = bool(request.POST.get("is_active"))

        product.save()
        messages.success(request, "Product updated")
        return redirect("products:admin_product_list")

    return render(
        request,
        "products/admin/admin_product_form.html",
        {"product": product, "subcategories": SubCategory.objects.all()},
    )


# -----------------------------
# SOFT DELETE PRODUCT
# -----------------------------
@admin_login_required
def admin_delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.is_active = False
    product.save()
    messages.success(request, "Product deleted safely")
    return redirect("products:admin_product_list")


# -----------------------------
# VARIANT MANAGEMENT
# -----------------------------
@admin_login_required
def admin_add_variant(request, product_id):

    product = get_object_or_404(Product, id=product_id)

    if request.method == "POST":

        variant = ProductVariant.objects.create(
            product=product,
            color_id=request.POST.get("color"),
            age_group_id=request.POST.get("age_group"),
            barcode=request.POST.get("barcode"),
        )

        Inventory.objects.create(
            variant=variant,
            quantity_available=request.POST.get("stock"),
        )

        messages.success(request, "Variant added")
        return redirect("products:admin_edit_product", product_id=product.id)

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
def admin_edit_variant(request, variant_id):

    variant = get_object_or_404(ProductVariant, id=variant_id)

    if request.method == "POST":
        variant.color_id = request.POST.get("color")
        variant.age_group_id = request.POST.get("age_group")
        variant.barcode = request.POST.get("barcode")
        variant.is_active = bool(request.POST.get("is_active"))
        variant.save()

        messages.success(request, "Variant updated")
        return redirect(
            "products:admin_edit_product", product_id=variant.product.id
        )

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
def admin_delete_variant(request, variant_id):
    variant = get_object_or_404(ProductVariant, id=variant_id)
    variant.delete()
    messages.success(request, "Variant removed")
    return redirect(
        "products:admin_edit_product", product_id=variant.product.id
    )